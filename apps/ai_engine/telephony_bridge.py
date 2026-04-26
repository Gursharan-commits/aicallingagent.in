"""
TelephonyBridge — LiveKit ↔ GraphExecutor middleware.

Responsibilities:
1. Load AIConfig (graph + compliance settings) from DB at call-start.
2. Start the GraphExecutor with the live provider config.
3. Pipe raw PCM audio from the LiveKit room into the STT entry node.
4. Pull TTS audio from GraphContext and publish it back to the LiveKit room.
5. React to control events (HUMAN_TAKEOVER, OUT_OF_CREDITS) from Redis.

tenant_id is extracted from the LiveKit room metadata JWT so every call is
automatically isolated to the correct tenant and regional DB shard.
"""

import asyncio
import json
import logging

from asgiref.sync import sync_to_async
from livekit import agents, rtc

from apps.ai_engine.executor import GraphExecutor
from apps.tenants.middleware import set_tenant_context

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# DB helpers (run in Django ORM thread pool)
# ─────────────────────────────────────────────────────────────────────────────

@sync_to_async
def _load_ai_config(tenant_id: int, campaign_id: int | None = None):
    """
    Load the active AIConfig for this tenant.

    Precedence: campaign-specific config → most recently updated active config.
    Returns (AIConfig instance) or raises AIConfig.DoesNotExist.
    """
    from apps.ai_engine.models import AIConfig

    qs = AIConfig.objects.filter(tenant_id=tenant_id, is_active=True)
    if campaign_id:
        qs_campaign = qs.filter(campaigns__id=campaign_id)
        if qs_campaign.exists():
            return qs_campaign.select_related("tenant").latest("updated_at")
    return qs.select_related("tenant").latest("updated_at")


@sync_to_async
def _create_call_record(tenant_id: int, livekit_room_id: str, ai_config_id: int):
    """Create a Call DB row when the room opens."""
    from apps.calls.models import Call
    from apps.tenants.models import Tenant

    tenant = Tenant.objects.get(pk=tenant_id)
    call, _ = Call.objects.get_or_create(
        livekit_room_id=livekit_room_id,
        defaults=dict(
            tenant_id=tenant_id,
            ai_config_id=ai_config_id,
            status="IN_PROGRESS",
            data_region=tenant.cloud_region,
        ),
    )
    call.status = "IN_PROGRESS"
    call.save(update_fields=["status"])
    return call


@sync_to_async
def _mark_call_completed(livekit_room_id: str):
    from django.utils.timezone import now
    from apps.calls.models import Call

    Call.objects.filter(livekit_room_id=livekit_room_id).update(
        status="COMPLETED", ended_at=now()
    )


# ─────────────────────────────────────────────────────────────────────────────
# TelephonyBridge
# ─────────────────────────────────────────────────────────────────────────────

class TelephonyBridge:
    def __init__(self, ctx: agents.JobContext, tenant_id: int) -> None:
        self.ctx = ctx
        self.tenant_id = tenant_id
        self.executor: GraphExecutor | None = None
        self.engine_tasks: list[asyncio.Task] = []
        self.source = rtc.AudioSource(sample_rate=16000, num_channels=1)
        self._call = None

    async def start(self) -> None:
        room_name = self.ctx.room.name

        # ── Set thread-local so RegionRouter routes to the correct DB shard ──
        await self._set_tenant_context()

        # ── Load live config from DB ──────────────────────────────────────────
        try:
            ai_config = await _load_ai_config(self.tenant_id)
            logger.info(
                "Loaded AIConfig id=%s name=%r for tenant=%s",
                ai_config.id, ai_config.name, self.tenant_id,
            )
        except Exception as exc:
            logger.warning(
                "No AIConfig for tenant=%s (%s). Using fallback graph.", self.tenant_id, exc
            )
            ai_config = self._fallback_config()

        # ── Create Call record ────────────────────────────────────────────────
        self._call = await _create_call_record(
            tenant_id=self.tenant_id,
            livekit_room_id=room_name,
            ai_config_id=getattr(ai_config, "id", 0),
        )

        # ── Resolve compliance disclosure prefix ──────────────────────────────
        compliance_prefix = ""
        if getattr(ai_config, "ai_disclosure_enabled", False):
            compliance_prefix = getattr(
                ai_config,
                "ai_disclosure_text",
                "This call is handled by an AI assistant.",
            )
            logger.info("AI disclosure enabled for call %s", room_name)

        # ── Build and start GraphExecutor ─────────────────────────────────────
        graph_json = getattr(ai_config, "graph_json", self._fallback_graph())
        self.executor = GraphExecutor(
            graph_json=graph_json,
            call_id=room_name,
            compliance_prefix=compliance_prefix,
            ai_config_id=getattr(ai_config, "id", None),
        )
        self.engine_tasks = await self.executor.start()

        # ── Publish agent audio track ─────────────────────────────────────────
        track = rtc.LocalAudioTrack.create_audio_track("agent_voice", self.source)
        options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        await self.ctx.room.local_participant.publish_track(track, options)

        # ── Subscribe to participant audio ────────────────────────────────────
        self.ctx.room.on("track_subscribed", self._on_track_subscribed)

        # ── Start TTS publisher loop ──────────────────────────────────────────
        asyncio.create_task(self._publish_tts_audio())

        # ── Subscribe to control events from Redis ────────────────────────────
        asyncio.create_task(self._listen_control_events())

        logger.info("TelephonyBridge ready — room=%s tenant=%s", room_name, self.tenant_id)

    @sync_to_async
    def _set_tenant_context(self) -> None:
        """Stamp thread-local with tenant region so RegionRouter works."""
        from apps.tenants.models import Tenant
        try:
            tenant = Tenant.objects.get(pk=self.tenant_id)
            set_tenant_context(self.tenant_id, tenant.region)
        except Exception:
            set_tenant_context(self.tenant_id, None)

    # ── Audio I/O ─────────────────────────────────────────────────────────────

    def _on_track_subscribed(
        self,
        track: rtc.Track,
        publication: rtc.TrackPublication,
        participant: rtc.RemoteParticipant,
    ) -> None:
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            logger.info("Audio track subscribed from %s", participant.identity)
            asyncio.create_task(self._read_user_audio(track))

    async def _read_user_audio(self, track: rtc.Track) -> None:
        audio_stream = rtc.AudioStream(track)
        async for audio_frame in audio_stream:
            if self.executor:
                await self.executor.push_audio(bytes(audio_frame.data))

    async def _publish_tts_audio(self) -> None:
        """Drain context.tts_audio_queue and publish frames to the LiveKit room."""
        if not self.executor:
            return
        while True:
            try:
                audio_bytes = await asyncio.wait_for(
                    self.executor.context.tts_audio_queue.get(), timeout=0.5
                )
                # Build a LiveKit AudioFrame from raw PCM bytes
                frame = rtc.AudioFrame(
                    data=audio_bytes,
                    sample_rate=16000,
                    num_channels=1,
                    samples_per_channel=len(audio_bytes) // 2,
                )
                await self.source.capture_frame(frame)
            except asyncio.TimeoutError:
                if not self.executor.context.active:
                    break
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("TTS publish error: %s", exc)

    # ── Control events (Redis channel layer) ─────────────────────────────────

    async def _listen_control_events(self) -> None:
        """
        Listens for control messages sent via Django Channels group
        (e.g. HUMAN_TAKEOVER, OUT_OF_CREDITS from the billing task).
        """
        from channels.layers import get_channel_layer

        channel_layer = get_channel_layer()
        if not channel_layer:
            return

        room_name = self.ctx.room.name
        channel = await channel_layer.new_channel()
        await channel_layer.group_add(f"call_{room_name}", channel)

        try:
            while True:
                message = await channel_layer.receive(channel)
                if message.get("type") == "control_event":
                    event = message.get("event")
                    logger.info("Control event %r for call %s", event, room_name)
                    if event in ("HUMAN_TAKEOVER", "OUT_OF_CREDITS"):
                        await self.stop()
                        break
        except asyncio.CancelledError:
            pass
        finally:
            await channel_layer.group_discard(f"call_{room_name}", channel)

    # ── Teardown ──────────────────────────────────────────────────────────────

    async def stop(self) -> None:
        if self.executor:
            await self.executor.stop()
        if self.engine_tasks:
            await asyncio.gather(*self.engine_tasks, return_exceptions=True)
        if self._call:
            await _mark_call_completed(self.ctx.room.name)
            # Fire end-of-call ledger task
            from apps.billing.tasks import record_call_end_ledger
            record_call_end_ledger.delay(self._call.id)
        logger.info("TelephonyBridge stopped — room=%s", self.ctx.room.name)

    # ── Fallback helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _fallback_graph() -> dict:
        return {
            "nodes": [
                {"id": "stt_1", "type": "STT", "config": {"provider": "deepgram", "language": "en-IN"}},
                {"id": "llm_1", "type": "LLM", "config": {"provider": "gemini", "system_prompt": "You are a helpful voice AI."}},
                {"id": "tts_1", "type": "TTS", "config": {"provider": "cartesia"}},
            ],
            "edges": [
                {"from": "stt_1", "to": "llm_1"},
                {"from": "llm_1", "to": "tts_1"},
            ],
        }

    @staticmethod
    def _fallback_config():
        """Return a minimal duck-typed config object when no DB record exists."""
        class _FallbackConfig:
            id = None
            graph_json = TelephonyBridge._fallback_graph.__func__(None)
            ai_disclosure_enabled = False
            ai_disclosure_text = ""
        return _FallbackConfig()


# ─────────────────────────────────────────────────────────────────────────────
# LiveKit worker entrypoint
# ─────────────────────────────────────────────────────────────────────────────

async def worker_entrypoint(ctx: agents.JobContext) -> None:
    """
    Called by LiveKit Agents SDK when a new room is assigned to this worker.

    tenant_id is extracted from the room's metadata field (set by the backend
    when it creates the LiveKit room via the server SDK).

    Expected metadata JSON:  {"tenant_id": 42, "campaign_id": 7}
    """
    metadata_raw = ctx.room.metadata or "{}"
    try:
        metadata = json.loads(metadata_raw)
    except json.JSONDecodeError:
        metadata = {}

    tenant_id: int = int(metadata.get("tenant_id", 1))
    logger.info("Worker entrypoint — room=%s tenant_id=%s", ctx.room.name, tenant_id)

    bridge = TelephonyBridge(ctx, tenant_id=tenant_id)
    await bridge.start()

    # Keep the worker alive until the room closes or bridge stops.
    await ctx.wait_for_disconnect()
    await bridge.stop()
