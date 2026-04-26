"""
CallConsumer — Django Channels WebSocket consumer.

Responsibilities:
- Relay transcript events from Redis channel layer to the connected frontend.
- Receive human-takeover control commands from the frontend and broadcast them.
- Persist every transcript event to the Transcript model with PII masking applied.
"""

import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from apps.calls.pii import mask_pii

logger = logging.getLogger(__name__)


class CallConsumer(AsyncWebsocketConsumer):
    """
    Bidirectional WebSocket handler for a single live call session.
    URL pattern: /ws/calls/<call_id>/
    """

    async def connect(self) -> None:
        self.call_id: str = self.scope["url_route"]["kwargs"]["call_id"]
        self.room_group_name: str = f"call_{self.call_id}"

        # Tenant isolation: verify the connecting user has access to this call.
        user = self.scope.get("user")
        if user and user.is_authenticated:
            allowed = await self._check_call_access(user, self.call_id)
            if not allowed:
                logger.warning(
                    "[WS] Rejected — user %s has no access to call %s",
                    user.id, self.call_id,
                )
                await self.close(code=4003)
                return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        logger.info("[WS] Connected — call_id=%s", self.call_id)
        await self.accept()
        await self.send(text_data=json.dumps({"type": "connection_ready", "call_id": self.call_id}))

    async def disconnect(self, close_code: int) -> None:
        logger.info("[WS] Disconnected — call_id=%s code=%s", self.call_id, close_code)
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    # ── Inbound (from frontend) ───────────────────────────────────────────────

    async def receive(self, text_data: str) -> None:
        try:
            data: dict = json.loads(text_data)
        except json.JSONDecodeError:
            logger.warning("[WS] Non-JSON message — call_id=%s", self.call_id)
            return

        action = data.get("action")

        if action == "human_takeover":
            logger.info("[WS] Human takeover — call_id=%s", self.call_id)
            await self.channel_layer.group_send(
                self.room_group_name,
                {"type": "control_event", "event": "HUMAN_TAKEOVER"},
            )
        elif action == "ping":
            await self.send(text_data=json.dumps({"type": "pong"}))
        else:
            logger.debug("[WS] Unknown action=%s — call_id=%s", action, self.call_id)

    # ── Outbound (from Redis channel layer) ───────────────────────────────────

    async def transcript_stream(self, event: dict) -> None:
        """
        Relay a transcript chunk to the browser and persist it.
        PII masking is applied before the DB write; the raw text is still
        sent to the frontend (operator UI) but the masked version is stored.
        """
        text: str = event.get("text", "")
        role: str = event.get("role", "bot")

        await self._persist_transcript(self.call_id, role, text)

        await self.send(text_data=json.dumps({
            "type": "transcript",
            "call_id": self.call_id,
            "role": role,
            "text": text,
        }))

    async def control_event(self, event: dict) -> None:
        await self.send(text_data=json.dumps({
            "type": "control",
            "call_id": self.call_id,
            "action": event.get("event"),
        }))

    # ── Helpers ───────────────────────────────────────────────────────────────

    @database_sync_to_async
    def _persist_transcript(self, call_id: str, role: str, text: str) -> None:
        """
        Persist a transcript line. PII masking is applied inside
        Transcript.save() via the model's override, so all stored
        transcripts have text_masked populated automatically.
        """
        try:
            from apps.calls.models import Call, Transcript

            call = Call.objects.filter(livekit_room_id=call_id).first()
            if call is None:
                logger.debug("[WS] Transcript skipped — no Call for call_id=%s", call_id)
                return

            db_role = role if role in ("user", "bot", "system") else "bot"
            Transcript.objects.create(call=call, role=db_role, text=text)
            logger.debug("[WS] Transcript persisted — call_id=%s role=%s", call_id, role)

        except Exception as exc:
            logger.error("[WS] Failed to persist transcript: %s", exc)

    @database_sync_to_async
    def _check_call_access(self, user, call_id: str) -> bool:
        """
        Return True if the authenticated user's tenant owns this call.
        SuperAdmins bypass the check.
        """
        try:
            if user.role == "super_admin":
                return True
            from apps.calls.models import Call
            return Call.objects.filter(
                livekit_room_id=call_id,
                tenant_id=user.tenant_id,
            ).exists()
        except Exception:
            return False
