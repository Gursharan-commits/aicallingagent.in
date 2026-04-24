"""
Twilio Media Stream telephony bridge.

Architecture
────────────
Caller → Twilio (μ-law 8 kHz) ──WebSocket──► FastAPI /twilio-stream
                                                      ↕
                                              VoicePipeline
                                            (STT / LLM / TTS)
                                                      ↕
Twilio plays audio ◄── μ-law 8 kHz ◄── PCM s16le 16 kHz

Audio codec chain
──────────────────
Inbound  (Twilio → pipeline):
  base64 decode → μ-law 8 kHz → audioop.ulaw2lin → PCM s16le 8 kHz
  → audioop.ratecv(8000→16000) → PCM s16le 16 kHz → pipeline.process_audio()

Outbound (pipeline → Twilio):
  pipeline on_audio_output PCM s16le 16 kHz
  → audioop.ratecv(16000→8000) → PCM s16le 8 kHz
  → audioop.lin2ulaw → μ-law 8 kHz → base64 encode
  → {"event":"media","streamSid":"...","media":{"payload":"..."}}

Twilio WebSocket message events handled
────────────────────────────────────────
  connected  — WS handshake confirmed; protocol/version metadata
  start      — stream metadata: streamSid, callSid, mediaFormat
  media      — raw audio chunk (inbound track only in bidirectional mode)
  stop       — call ended; tear down pipeline

Endpoints
──────────
  GET  /health          — liveness probe
  GET  /twiml           — returns TwiML that opens a bidirectional Media Stream
  WS   /twilio-stream   — Twilio connects here for live audio exchange

Dependencies
────────────
  pip install fastapi uvicorn python-dotenv

Note on audioop: built-in up to Python 3.12 (deprecated but present).
For Python 3.13+ install:  pip install audioop-lts
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os

try:
    import audioop                    # stdlib ≤ 3.12
except ModuleNotFoundError:
    import audioop_lts as audioop     # pip install audioop-lts  (Python 3.13+)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

from config_manager import load_config
from interrupt_handler import InterruptHandler
from llm_router import LLMConfig
from observability import MetricsCollector, TurnMetrics
from pipeline import PipelineConfig, VoicePipeline
from tts_service import TTSConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App + config
# ---------------------------------------------------------------------------

app = FastAPI(title="Voice AI Telephony Bridge")
cfg = load_config()

# ---------------------------------------------------------------------------
# Module-level event hook (used by test harness in call mode)
# ---------------------------------------------------------------------------

_event_callback = None


def set_event_callback(cb) -> None:
    """Register an async callable(event: str, data: dict) for pipeline events."""
    global _event_callback
    _event_callback = cb


async def _emit(event: str, data: dict) -> None:
    """Fire the registered event callback, swallowing any exceptions."""
    if _event_callback is not None:
        try:
            await _event_callback(event, data)
        except Exception:
            pass

# ---------------------------------------------------------------------------
# Audio conversion helpers
# ---------------------------------------------------------------------------

_TWILIO_RATE = 8_000    # μ-law 8 kHz (Twilio wire format)
_PIPELINE_RATE = 16_000  # PCM s16le 16 kHz (pipeline requirement)
_SAMPLE_WIDTH = 2       # bytes per sample (s16le)


def _mulaw_to_pcm16(mulaw_bytes: bytes, state_in=None):
    """μ-law 8 kHz → PCM s16le 16 kHz.  Returns (pcm_16k, ratecv_state)."""
    pcm_8k = audioop.ulaw2lin(mulaw_bytes, _SAMPLE_WIDTH)
    pcm_16k, state_out = audioop.ratecv(
        pcm_8k, _SAMPLE_WIDTH, 1, _TWILIO_RATE, _PIPELINE_RATE, state_in
    )
    return pcm_16k, state_out


def _pcm16_to_mulaw(pcm_16k: bytes, state_in=None):
    """PCM s16le 16 kHz → μ-law 8 kHz.  Returns (mulaw_bytes, ratecv_state)."""
    pcm_8k, state_out = audioop.ratecv(
        pcm_16k, _SAMPLE_WIDTH, 1, _PIPELINE_RATE, _TWILIO_RATE, state_in
    )
    mulaw = audioop.lin2ulaw(pcm_8k, _SAMPLE_WIDTH)
    return mulaw, state_out


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/twiml", response_class=Response)
async def twiml():
    """
    Return TwiML that opens a bidirectional Media Stream to this server.

    Twilio fetches this URL when a call arrives.  Point your Twilio phone
    number's Voice webhook to:  https://<your-domain>/twiml
    """
    stream_url = cfg.twilio_stream_url
    if not stream_url:
        logger.warning(
            "TWILIO_STREAM_URL is not set — returning placeholder TwiML. "
            "Set it to your public server URL (e.g. from ngrok) in .env."
        )
        stream_url = "https://YOUR_PUBLIC_URL_HERE"

    # Convert https:// → wss:// for the WebSocket URL
    ws_url = stream_url.replace("https://", "wss://").replace("http://", "ws://")
    ws_url = ws_url.rstrip("/") + "/twilio-stream"

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="{ws_url}"/>
  </Connect>
</Response>"""
    return Response(content=xml, media_type="application/xml")


# ---------------------------------------------------------------------------
# WebSocket handler
# ---------------------------------------------------------------------------

@app.websocket("/twilio-stream")
async def twilio_stream(ws: WebSocket):
    """
    Handle one Twilio bidirectional Media Stream connection (= one phone call).

    Each call gets its own VoicePipeline instance so conversations are fully
    isolated.
    """
    await ws.accept()
    call_id: str = ""
    stream_sid: str = ""
    pipeline: VoicePipeline | None = None
    metrics_collector: MetricsCollector | None = None

    # Rate-conversion state is preserved across chunks for continuity.
    inbound_ratecv_state = None
    outbound_ratecv_state = None

    # Protect outbound state from concurrent writes (pipeline emits from a task).
    send_lock = asyncio.Lock()

    async def send_audio_to_twilio(pcm_16k: bytes) -> None:
        nonlocal outbound_ratecv_state
        if not stream_sid:
            return
        try:
            mulaw, outbound_ratecv_state = _pcm16_to_mulaw(pcm_16k, outbound_ratecv_state)
            payload = base64.b64encode(mulaw).decode("ascii")
            msg = json.dumps({
                "event": "media",
                "streamSid": stream_sid,
                "media": {"payload": payload},
            })
            async with send_lock:
                await ws.send_text(msg)
        except Exception as exc:
            logger.error("send_audio_to_twilio: %s", exc)

    async def send_clear_to_twilio() -> None:
        """Flush Twilio's audio buffer on barge-in."""
        if not stream_sid:
            return
        try:
            async with send_lock:
                await ws.send_text(json.dumps({"event": "clear", "streamSid": stream_sid}))
        except Exception as exc:
            logger.error("send_clear_to_twilio: %s", exc)

    try:
        async for raw_msg in ws.iter_text():
            try:
                msg: dict = json.loads(raw_msg)
            except json.JSONDecodeError:
                continue

            event = msg.get("event")

            # ── connected ─────────────────────────────────────────────────
            if event == "connected":
                logger.info(
                    "Twilio WS connected  protocol=%s version=%s",
                    msg.get("protocol"), msg.get("version"),
                )

            # ── start ─────────────────────────────────────────────────────
            elif event == "start":
                start = msg.get("start", {})
                stream_sid = msg.get("streamSid", "")
                call_id = start.get("callSid", "")
                fmt = start.get("mediaFormat", {})
                logger.info(
                    "Call started  callSid=%s streamSid=%s  format=%s/%s",
                    call_id, stream_sid, fmt.get("encoding"), fmt.get("sampleRate"),
                )

                # Build pipeline wired to this call's keys and config.yaml settings.
                pipeline_cfg = PipelineConfig(
                    tts=TTSConfig(sample_rate=_PIPELINE_RATE),
                    llm=LLMConfig(
                        provider=cfg.llm.provider,
                        system_prompt=cfg.llm.system_prompt,
                        max_tokens=cfg.llm.max_tokens,
                        temperature=cfg.llm.temperature,
                    ),
                    deepgram_kwargs={"api_key": cfg.deepgram_api_key},
                    sarvam_stt_kwargs={"api_key": cfg.sarvam_api_key},
                    cartesia_kwargs={"api_key": cfg.cartesia_api_key},
                    sarvam_tts_kwargs={"api_key": cfg.sarvam_api_key},
                    openai_tts_kwargs={"api_key": cfg.openai_api_key},
                    gemini_kwargs={"api_key": cfg.gemini_api_key},
                    openai_llm_kwargs={"api_key": cfg.openai_api_key},
                )

                interrupter = InterruptHandler(
                    energy_threshold=600.0,
                    on_interrupt=send_clear_to_twilio,
                )
                pipeline = VoicePipeline(pipeline_cfg, interrupt_handler=interrupter)
                pipeline.on_audio_output = send_audio_to_twilio

                async def _on_transcript(text: str, is_final: bool) -> None:
                    await _emit("transcript", {"text": text, "is_final": is_final, "call_sid": call_id})

                async def _on_llm_response(chunk: str) -> None:
                    await _emit("llm_chunk", {"chunk": chunk, "call_sid": call_id})

                pipeline.on_transcript = _on_transcript
                pipeline.on_llm_response = _on_llm_response

                # ── Observability ──────────────────────────────────────────
                metrics_collector = MetricsCollector(call_sid=call_id)

                async def _on_turn_metrics(m: dict) -> None:
                    if metrics_collector is not None:
                        metrics_collector.record_turn(TurnMetrics(**m))
                    await _emit("turn_metrics", {**m, "call_sid": call_id})

                pipeline.on_turn_metrics = _on_turn_metrics

                await pipeline.start()
                logger.info("VoicePipeline started for call %s", call_id)

            # ── media ─────────────────────────────────────────────────────
            elif event == "media" and pipeline is not None:
                media = msg.get("media", {})
                if media.get("track") != "inbound":
                    continue  # ignore outbound echo in bidirectional mode
                raw = base64.b64decode(media.get("payload", ""))
                if not raw:
                    continue
                try:
                    pcm_16k, inbound_ratecv_state = _mulaw_to_pcm16(raw, inbound_ratecv_state)
                    await pipeline.process_audio(pcm_16k)
                except Exception as exc:
                    logger.error("Audio conversion error: %s", exc)

            # ── stop ──────────────────────────────────────────────────────
            elif event == "stop":
                logger.info("Call ended  callSid=%s", call_id)
                break

    except WebSocketDisconnect:
        logger.info("Twilio WS disconnected  callSid=%s", call_id)
    except Exception as exc:
        logger.error("Twilio WS error  callSid=%s  err=%s", call_id, exc)
    finally:
        if pipeline is not None:
            try:
                await pipeline.stop()
            except Exception as exc:
                logger.error("Pipeline stop error: %s", exc)
        if metrics_collector is not None:
            metrics_collector.summary()
            await _emit("call_summary", {"call_sid": call_id})
        logger.info("Twilio WS handler exited  callSid=%s", call_id)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    uvicorn.run(
        "telephony_bridge:app",
        host=cfg.host,
        port=cfg.port,
        log_level="info",
    )
