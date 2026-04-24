"""
CallConsumer — Django Channels WebSocket consumer.

Responsibilities:
- Relay transcript events from Redis channel layer to the connected frontend.
- Receive human-takeover control commands from the frontend and broadcast them.
- Persist every transcript event to the Transcript model (telemetry write-through).
"""

import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

logger = logging.getLogger(__name__)


class CallConsumer(AsyncWebsocketConsumer):
    """
    Bidirectional WebSocket handler for a single live call session.
    URL pattern: /ws/calls/<call_id>/
    """

    async def connect(self) -> None:
        """Accept the connection and join the Redis broadcast group for this call."""
        self.call_id: str = self.scope["url_route"]["kwargs"]["call_id"]
        self.room_group_name: str = f"call_{self.call_id}"

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)

        logger.info("[WS] Connected — call_id=%s", self.call_id)
        await self.accept()

        # Notify client that the WS connection is ready.
        await self.send(
            text_data=json.dumps({"type": "connection_ready", "call_id": self.call_id})
        )

    async def disconnect(self, close_code: int) -> None:
        """Leave the Redis group on disconnect."""
        logger.info("[WS] Disconnected — call_id=%s code=%s", self.call_id, close_code)
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    # ──────────────────────────────────────────────────────────
    # Inbound messages from the frontend client
    # ──────────────────────────────────────────────────────────

    async def receive(self, text_data: str) -> None:
        """
        Handle messages sent by the frontend over WebSocket.
        Supported actions:
            - human_takeover: broadcast a control event to the GraphExecutor.
        """
        try:
            data: dict = json.loads(text_data)
        except json.JSONDecodeError:
            logger.warning("[WS] Received non-JSON message — call_id=%s", self.call_id)
            return

        action = data.get("action")

        if action == "human_takeover":
            logger.info("[WS] Human takeover — call_id=%s", self.call_id)
            await self.channel_layer.group_send(
                self.room_group_name,
                {"type": "control_event", "event": "HUMAN_TAKEOVER"},
            )
        else:
            logger.debug("[WS] Unknown action=%s — call_id=%s", action, self.call_id)

    # ──────────────────────────────────────────────────────────
    # Outbound messages from the Redis channel layer
    # ──────────────────────────────────────────────────────────

    async def transcript_stream(self, event: dict) -> None:
        """
        Relay a transcript event from Redis to the connected frontend browser.
        Also persists the transcript line to the database for analytics.
        """
        text: str = event.get("text", "")
        role: str = event.get("role", "bot")

        # Write to DB asynchronously without blocking the event loop.
        await self._persist_transcript(self.call_id, role, text)

        await self.send(
            text_data=json.dumps(
                {
                    "type": "transcript",
                    "call_id": self.call_id,
                    "role": role,
                    "text": text,
                }
            )
        )

    async def control_event(self, event: dict) -> None:
        """Echo control events (e.g. HUMAN_TAKEOVER confirmation) back to the client."""
        await self.send(
            text_data=json.dumps(
                {
                    "type": "control",
                    "call_id": self.call_id,
                    "action": event.get("event"),
                }
            )
        )

    # ──────────────────────────────────────────────────────────
    # Database helpers (run in Django ORM thread pool)
    # ──────────────────────────────────────────────────────────

    @database_sync_to_async
    def _persist_transcript(self, call_id: str, role: str, text: str) -> None:
        """
        Write a Transcript row to the database for the given call.
        Silently skips if the Call record does not exist yet
        (e.g. during local dev without a real telephony session).
        """
        try:
            from apps.calls.models import Call, Transcript  # Local import avoids circular refs

            call = Call.objects.filter(livekit_room_id=call_id).first()
            if call is None:
                logger.debug(
                    "[WS] Transcript skipped — no Call record for call_id=%s", call_id
                )
                return

            # Normalise the role to match Transcript.ROLE_CHOICES
            db_role = role if role in ("user", "bot", "system") else "bot"
            Transcript.objects.create(call=call, role=db_role, text=text)
            logger.debug("[WS] Transcript persisted — call_id=%s role=%s", call_id, role)

        except Exception as exc:  # noqa: BLE001
            logger.error("[WS] Failed to persist transcript: %s", exc)
