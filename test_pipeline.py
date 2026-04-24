"""
Terminal test harness for the Voice AI Pipeline.

Three modes
───────────
  --mode mic
        Capture audio from the default microphone in real time, run it
        through the full STT → LLM → TTS pipeline, and play the reply
        through the default speaker.  Press Ctrl+C to stop.

  --mode file --input path/to/audio.wav
        Feed a WAV file through the pipeline and write the synthesised
        reply to  output.wav  (or the path given by --output).

  --mode call --to +91XXXXXXXXXX
        Place an outbound Twilio call to the given number, start the
        FastAPI telephony bridge locally, stream a live transcript to
        the terminal in real time, and save every turn to call_log.txt.

Coloured output
───────────────
  [USER]   → blue
  [AI]     → green
  [SYSTEM] → yellow
  [ERROR]  → red

Usage examples
──────────────
  python test_pipeline.py --mode mic
  python test_pipeline.py --mode file --input hello.wav --output reply.wav
  python test_pipeline.py --mode call --to +919876543210
  python test_pipeline.py --mode call --to +919876543210 --log my_call.txt
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import io
import logging
import os
import struct
import sys
import wave
from pathlib import Path
from typing import Callable

# ── Third-party ───────────────────────────────────────────────────────────────
try:
    import colorama
    colorama.init(autoreset=True)
    _BLUE   = colorama.Fore.CYAN
    _GREEN  = colorama.Fore.GREEN
    _YELLOW = colorama.Fore.YELLOW
    _RED    = colorama.Fore.RED
    _RESET  = colorama.Style.RESET_ALL
except ImportError:
    _BLUE = _GREEN = _YELLOW = _RED = _RESET = ""
    print(
        "[WARN] colorama not installed — output will be uncoloured.\n"
        "       Fix: pip install colorama"
    )

try:
    import sounddevice as sd
    _SD_AVAILABLE = True
except ImportError:
    _SD_AVAILABLE = False

from dotenv import load_dotenv
load_dotenv()

from config_manager import ConfigError, load_config
from interrupt_handler import InterruptHandler
from llm_router import LLMConfig
from observability import MetricsCollector, TurnMetrics
from pipeline import PipelineConfig, VoicePipeline
from tts_service import TTSConfig

# ── Constants ─────────────────────────────────────────────────────────────────

_SAMPLE_RATE   = 16_000   # Hz — pipeline requirement
_CHANNELS      = 1
_BLOCKSIZE     = 1_600    # 100 ms at 16 kHz
_SAMPLE_WIDTH  = 2        # bytes (int16)
_LOG_ENCODING  = "utf-8"

logging.basicConfig(
    level=logging.WARNING,        # suppress library noise in terminal mode
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)


# ── Pretty-print helpers ───────────────────────────────────────────────────────

def _ts() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")


def _print(tag: str, colour: str, text: str) -> None:
    print(f"{colour}[{_ts()}] [{tag}]{_RESET} {text}", flush=True)


def info(text: str)    -> None: _print("SYSTEM", _YELLOW, text)
def ai(text: str)      -> None: _print("AI",     _GREEN,  text)
def user(text: str)    -> None: _print("USER",   _BLUE,   text)
def error(text: str)   -> None: _print("ERROR",  _RED,    text)


# ── Config guard ──────────────────────────────────────────────────────────────

def _load_cfg_or_exit():
    try:
        return load_config()
    except ConfigError as exc:
        error(str(exc))
        error("Fix: fill in all required values in your .env file.")
        sys.exit(1)


# ── Pipeline factory ──────────────────────────────────────────────────────────

def _make_pipeline(
    cfg,
    *,
    on_interrupt=None,
    metrics_collector: MetricsCollector | None = None,
) -> VoicePipeline:
    """Build a VoicePipeline wired to the loaded AppConfig."""
    pipeline_cfg = PipelineConfig(
        tts=TTSConfig(sample_rate=_SAMPLE_RATE),
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
        energy_threshold=cfg.vad.energy_threshold,
        on_interrupt=on_interrupt or _async_noop,
    )
    pipeline = VoicePipeline(pipeline_cfg, interrupt_handler=interrupter)

    if metrics_collector is not None:
        async def _on_turn_metrics(m: dict) -> None:
            metrics_collector.record_turn(TurnMetrics(**m))
        pipeline.on_turn_metrics = _on_turn_metrics

    return pipeline


async def _async_noop(*_a, **_kw) -> None:
    pass


# ─────────────────────────────────────────────────────────────────────────────
# MODE 1 — Microphone
# ─────────────────────────────────────────────────────────────────────────────

async def run_mic_mode(cfg) -> None:
    """
    Capture microphone audio → pipeline → play speaker reply.
    Press Ctrl+C to stop.
    """
    if not _SD_AVAILABLE:
        error("sounddevice is not installed.")
        error("Fix: pip install sounddevice")
        sys.exit(1)

    info("Mic mode — speak into your microphone.  Ctrl+C to stop.")

    mc = MetricsCollector()

    # Queue bridges the sounddevice callback (called from a C thread) into async.
    audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
    playback_queue: asyncio.Queue[bytes] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    # Accumulate AI reply text for a clean single-line print.
    _ai_buffer: list[str] = []
    _user_partial = {"text": ""}

    async def on_transcript(text: str, is_final: bool) -> None:
        _user_partial["text"] = text
        if is_final and text.strip():
            user(text)
            _user_partial["text"] = ""

    async def on_llm_response(chunk: str) -> None:
        _ai_buffer.append(chunk)

    audio_chunks: list[bytes] = []

    async def on_audio(audio: bytes) -> None:
        audio_chunks.append(audio)
        await playback_queue.put(audio)

    # Flush AI text to terminal when audio output finishes.
    async def _flush_ai_text() -> None:
        if _ai_buffer:
            ai("".join(_ai_buffer))
            _ai_buffer.clear()

    def _mic_callback(indata, frames, time_info, status):
        """Called from sounddevice's C thread on every audio block."""
        if status:
            pass  # ignore under-run warnings in terminal mode
        pcm = bytes(indata)
        loop.call_soon_threadsafe(audio_queue.put_nowait, pcm)

    # Interrupt: clear playback queue and flush accumulated AI text.
    async def on_interrupt() -> None:
        while not playback_queue.empty():
            try:
                playback_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        await _flush_ai_text()

    pipeline = _make_pipeline(cfg, on_interrupt=on_interrupt, metrics_collector=mc)
    pipeline.on_transcript   = on_transcript
    pipeline.on_llm_response = on_llm_response
    pipeline.on_audio_output = on_audio

    await pipeline.start()
    info("Pipeline ready — listening…")

    # ── Playback task ──────────────────────────────────────────────────────
    async def _playback_loop() -> None:
        """Drain playback_queue and play audio via sounddevice."""
        buf = b""
        while True:
            chunk = await playback_queue.get()
            buf += chunk
            # Drain all immediately available chunks into buf.
            while not playback_queue.empty():
                try:
                    buf += playback_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            # Play synchronously in a thread to avoid blocking the event loop.
            try:
                await asyncio.to_thread(
                    sd.play,
                    _pcm_to_numpy(buf),
                    samplerate=_SAMPLE_RATE,
                )
                await asyncio.to_thread(sd.wait)
            except Exception as exc:
                error(f"Playback error: {exc}")
            finally:
                buf = b""
                await _flush_ai_text()

    playback_task = asyncio.create_task(_playback_loop(), name="playback")

    try:
        with sd.InputStream(
            samplerate=_SAMPLE_RATE,
            channels=_CHANNELS,
            dtype="int16",
            blocksize=_BLOCKSIZE,
            callback=_mic_callback,
        ):
            # Feed microphone audio into the pipeline.
            while True:
                chunk = await audio_queue.get()
                await pipeline.process_audio(chunk)
    except KeyboardInterrupt:
        info("Stopping…")
    finally:
        playback_task.cancel()
        try:
            await playback_task
        except asyncio.CancelledError:
            pass
        await pipeline.stop()
        mc.summary()
        info("Done.")


def _pcm_to_numpy(pcm: bytes):
    """Convert raw PCM s16le bytes to a float32 numpy array for sounddevice."""
    import numpy as np
    arr = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    arr /= 32768.0
    return arr.reshape(-1, _CHANNELS)


# ─────────────────────────────────────────────────────────────────────────────
# MODE 2 — File
# ─────────────────────────────────────────────────────────────────────────────

async def run_file_mode(cfg, input_path: str, output_path: str) -> None:
    """
    Feed a WAV file through the pipeline → save synthesised reply to WAV.
    """
    inp = Path(input_path)
    if not inp.exists():
        error(f"Input file not found: {inp}")
        error("Fix: provide a valid path to a WAV file with --input.")
        sys.exit(1)

    info(f"File mode  input={inp}  output={output_path}")

    # ── Read input WAV ────────────────────────────────────────────────────────
    try:
        with wave.open(str(inp), "rb") as wf:
            channels  = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            raw_pcm   = wf.readframes(wf.getnframes())
    except Exception as exc:
        error(f"Cannot read {inp}: {exc}")
        error("Fix: ensure the file is a valid WAV (PCM, mono or stereo).")
        sys.exit(1)

    info(f"Input WAV: {framerate} Hz  {channels}ch  {sampwidth*8}-bit  "
         f"{len(raw_pcm)//(_SAMPLE_WIDTH*channels)/framerate:.1f}s")

    # Resample / convert to 16 kHz mono s16le using audioop.
    try:
        import audioop
    except ModuleNotFoundError:
        import audioop_lts as audioop  # type: ignore[no-redef]

    # Convert to s16le if needed.
    if sampwidth == 1:
        raw_pcm = audioop.bias(raw_pcm, 1, -128)         # unsigned→signed
        raw_pcm = b"".join(
            struct.pack("<h", b * 256) for b in raw_pcm
        )
        sampwidth = 2
    elif sampwidth == 4:
        raw_pcm = audioop.lin2lin(raw_pcm, 4, 2)
        sampwidth = 2

    # Mix down to mono.
    if channels > 1:
        raw_pcm = audioop.tomono(raw_pcm, sampwidth, 1.0 / channels) * channels
        channels = 1

    # Resample to 16 kHz.
    if framerate != _SAMPLE_RATE:
        raw_pcm, _ = audioop.ratecv(raw_pcm, sampwidth, 1, framerate, _SAMPLE_RATE, None)

    # ── Run through pipeline ──────────────────────────────────────────────────
    collected_audio: list[bytes] = []
    full_transcript = ""
    full_reply      = ""
    mc = MetricsCollector()

    async def on_transcript(text: str, is_final: bool) -> None:
        nonlocal full_transcript
        if is_final and text.strip():
            full_transcript = text
            user(text)

    async def on_llm_response(chunk: str) -> None:
        nonlocal full_reply
        full_reply += chunk

    async def on_audio(audio: bytes) -> None:
        collected_audio.append(audio)

    pipeline = _make_pipeline(cfg, metrics_collector=mc)
    pipeline.on_transcript   = on_transcript
    pipeline.on_llm_response = on_llm_response
    pipeline.on_audio_output = on_audio

    await pipeline.start()
    info("Feeding audio to pipeline…")

    # Feed audio in 100 ms chunks.
    chunk_size = _SAMPLE_RATE * _SAMPLE_WIDTH // 10   # 100 ms
    for i in range(0, len(raw_pcm), chunk_size):
        await pipeline.process_audio(raw_pcm[i : i + chunk_size])
        await asyncio.sleep(0)   # yield to event loop

    # Allow STT to finalise (silence timeout ~700 ms).
    info("Waiting for STT finalisation…")
    await asyncio.sleep(1.5)

    await pipeline.stop()
    mc.summary()

    if full_reply:
        ai(full_reply)

    if not collected_audio:
        error("No audio was synthesised — the pipeline produced no TTS output.")
        error("Possible fixes:")
        error("  • Check that CARTESIA_API_KEY (or fallback keys) are valid.")
        error("  • Verify the input WAV contains audible speech.")
        sys.exit(1)

    # ── Write output WAV ──────────────────────────────────────────────────────
    output_pcm = b"".join(collected_audio)
    with wave.open(output_path, "wb") as wf:
        wf.setnchannels(_CHANNELS)
        wf.setsampwidth(_SAMPLE_WIDTH)
        wf.setframerate(_SAMPLE_RATE)
        wf.writeframes(output_pcm)

    duration_s = len(output_pcm) / (_SAMPLE_RATE * _SAMPLE_WIDTH)
    info(f"Saved reply to {output_path}  ({duration_s:.1f}s, {len(output_pcm):,} bytes)")
    info("Done.")


# ─────────────────────────────────────────────────────────────────────────────
# MODE 3 — Outbound Call
# ─────────────────────────────────────────────────────────────────────────────

async def run_call_mode(cfg, to_number: str, log_path: str) -> None:
    """
    Place an outbound Twilio call → stream live transcript → save call_log.txt.
    """
    try:
        from twilio.rest import Client as TwilioClient
    except ImportError:
        error("twilio package is not installed.")
        error("Fix: pip install twilio")
        sys.exit(1)

    try:
        import uvicorn
    except ImportError:
        error("uvicorn is not installed.")
        error("Fix: pip install uvicorn")
        sys.exit(1)

    if not cfg.twilio_stream_url:
        error("TWILIO_STREAM_URL is not set in your .env file.")
        error("Fix: set it to your public HTTPS URL (e.g. from ngrok).")
        error("  Example: TWILIO_STREAM_URL=https://abc123.ngrok.io")
        sys.exit(1)

    # ── Set up event hook BEFORE the server starts ────────────────────────────
    import telephony_bridge as bridge

    log_lines: list[str] = []
    ai_buffer:  list[str] = []
    call_active = asyncio.Event()

    def _log(tag: str, text: str) -> None:
        line = f"[{_ts()}] [{tag}] {text}"
        log_lines.append(line)

    async def event_handler(event: str, data: dict) -> None:
        if event == "transcript":
            text     = data.get("text", "")
            is_final = data.get("is_final", False)
            if is_final and text.strip():
                user(text)
                _log("USER", text)
        elif event == "llm_chunk":
            ai_buffer.append(data.get("chunk", ""))
        elif event == "turn_metrics":
            # Sidebar is already printed by MetricsCollector inside telephony_bridge.
            # Log it to the call log file as well.
            e2e   = data.get("e2e_latency_ms")
            llm_p = data.get("llm_provider", "?")
            tts_p = data.get("tts_provider",  "?")
            e2e_s = f"{e2e:.0f}ms" if e2e is not None else "—"
            _log("METRICS", f"e2e={e2e_s} llm={llm_p} tts={tts_p}")
        elif event == "call_summary":
            # Summary already printed by MetricsCollector; just mark it in the log.
            _log("SUMMARY", "Call ended — see metrics_log.jsonl for details")

    bridge.set_event_callback(event_handler)

    # ── Start the FastAPI server in a background task ─────────────────────────
    server_config = uvicorn.Config(
        bridge.app,
        host=cfg.host,
        port=cfg.port,
        log_level="warning",   # suppress request logs in terminal mode
    )
    server = uvicorn.Server(server_config)
    server_task = asyncio.create_task(server.serve(), name="uvicorn")

    # Give the server a moment to bind the port.
    await asyncio.sleep(1.5)
    info(f"Telephony bridge listening on {cfg.host}:{cfg.port}")

    # ── Place the outbound call ───────────────────────────────────────────────
    twiml_url = cfg.twilio_stream_url.rstrip("/") + "/twiml"
    info(f"Placing call → {to_number}  (TwiML: {twiml_url})")

    try:
        twilio_client = TwilioClient(cfg.twilio_account_sid, cfg.twilio_auth_token)
        call = twilio_client.calls.create(
            to=to_number,
            from_=cfg.twilio_phone_number,
            url=twiml_url,
        )
    except Exception as exc:
        error(f"Failed to place call: {exc}")
        error("Possible fixes:")
        error("  • Verify TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN in .env")
        error("  • Check that TWILIO_PHONE_NUMBER is a valid Twilio number")
        error("  • Ensure TWILIO_STREAM_URL is publicly reachable")
        server.should_exit = True
        await server_task
        sys.exit(1)

    call_sid = call.sid
    info(f"Call placed  SID={call_sid}")
    info("Live transcript below.  Press Ctrl+C to end the call.")
    print()

    # ── Monitor until call ends ───────────────────────────────────────────────
    try:
        poll_interval = 5.0   # seconds between Twilio status polls
        while True:
            await asyncio.sleep(poll_interval)

            # Flush any accumulated AI text.
            if ai_buffer:
                reply = "".join(ai_buffer)
                ai(reply)
                _log("AI", reply)
                ai_buffer.clear()

            # Poll call status.
            try:
                status = twilio_client.calls(call_sid).fetch().status
            except Exception:
                status = "unknown"

            if status in ("completed", "failed", "busy", "no-answer", "canceled"):
                info(f"Call ended  status={status}")
                break

    except KeyboardInterrupt:
        info("Ctrl+C — ending call…")
        try:
            twilio_client.calls(call_sid).update(status="completed")
        except Exception:
            pass

    # ── Flush remaining AI text ───────────────────────────────────────────────
    if ai_buffer:
        reply = "".join(ai_buffer)
        ai(reply)
        _log("AI", reply)
        ai_buffer.clear()

    # ── Save log file ─────────────────────────────────────────────────────────
    if log_lines:
        log_file = Path(log_path)
        log_file.write_text("\n".join(log_lines), encoding=_LOG_ENCODING)
        info(f"Call log saved → {log_file}  ({len(log_lines)} lines)")
    else:
        info("No transcript lines captured (call may have been too short).")

    # ── Shut down server ──────────────────────────────────────────────────────
    server.should_exit = True
    try:
        await asyncio.wait_for(server_task, timeout=5.0)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        pass

    info("Done.")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Voice AI Pipeline test harness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--mode",
        choices=["mic", "file", "call"],
        required=True,
        help="Test mode: mic | file | call",
    )
    p.add_argument(
        "--input",
        default="test.wav",
        metavar="PATH",
        help="[file mode] Path to input WAV file (default: test.wav)",
    )
    p.add_argument(
        "--output",
        default="output.wav",
        metavar="PATH",
        help="[file mode] Path for synthesised output WAV (default: output.wav)",
    )
    p.add_argument(
        "--to",
        default="",
        metavar="E164",
        help="[call mode] Destination phone number in E.164 format, e.g. +919876543210",
    )
    p.add_argument(
        "--log",
        default="call_log.txt",
        metavar="PATH",
        help="[call mode] Path for the call transcript log (default: call_log.txt)",
    )
    return p


async def _main() -> None:
    parser = _build_parser()
    args   = parser.parse_args()

    cfg = _load_cfg_or_exit()

    if args.mode == "mic":
        await run_mic_mode(cfg)

    elif args.mode == "file":
        await run_file_mode(cfg, args.input, args.output)

    elif args.mode == "call":
        if not args.to:
            error("--to is required for call mode.")
            error("Example: python test_pipeline.py --mode call --to +919876543210")
            sys.exit(1)
        await run_call_mode(cfg, args.to, args.log)


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        info("Interrupted.")
