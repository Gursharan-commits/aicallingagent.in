"""
Streaming TTS abstraction layer.

Providers:
  CartesiaTTS  — WebSocket streaming, primary (sonic-3 / sonic-turbo)
  SarvamTTS    — WebSocket streaming, Indian voices (bulbul:v2 / bulbul:v3)
  OpenAITTS    — HTTP chunk-transfer streaming, fallback (gpt-4o-mini-tts)
  TTSRouter    — Cartesia primary → Sarvam for Indian → OpenAI on failure
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncGenerator
from urllib.parse import urlencode

import websockets
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

_INDIC_LANGUAGES = frozenset({
    "hi", "hi-in", "bn", "bn-in", "gu", "gu-in", "kn", "kn-in",
    "ml", "ml-in", "mr", "mr-in", "pa", "pa-in", "ta", "ta-in",
    "te", "te-in", "or", "od-in", "hinglish",
})


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class TTSConfig:
    """Provider-agnostic TTS parameters.

    voice          : Cartesia voice UUID or OpenAI voice name.
    speaker        : Sarvam speaker name (e.g. "meera", "arvind").
    language       : BCP-47-ish tag used for routing decisions.
    speed          : Pace multiplier (0.5–2.0; Sarvam bulbul valid range).
    sample_rate    : Desired output sample rate in Hz.
    min_buffer_size: Sarvam — minimum chunks buffered before first audio send.
    output_audio_codec: Sarvam — always "pcm" for this pipeline.
    """

    voice: str = "f786b574-daa5-4673-aa0c-cbe3e8534c02"  # Cartesia default
    speaker: str = "meera"                                # Sarvam default
    language: str = "en"
    speed: float = 1.0
    sample_rate: int = 16000
    min_buffer_size: int = 5
    output_audio_codec: str = "pcm"


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class BaseTTS(ABC):
    """Common interface for all streaming TTS providers."""

    @abstractmethod
    async def synthesize_stream(
        self, text: str, config: TTSConfig
    ) -> AsyncGenerator[bytes, None]:
        """Async generator that yields raw PCM audio chunks."""
        yield b""  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Cartesia
# ---------------------------------------------------------------------------

class CartesiaTTS(BaseTTS):
    """
    Streaming TTS via the official Cartesia Python SDK (WebSocket).

    The SDK is synchronous; it runs in a thread pool via asyncio.to_thread so
    the event loop is never blocked. Audio chunks are forwarded through an
    asyncio.Queue back to the async generator.

    Output: raw PCM signed-16-bit LE at config.sample_rate.
    Install: pip install 'cartesia[websockets]'
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "sonic-3",
    ) -> None:
        self._api_key = api_key or os.environ["CARTESIA_API_KEY"]
        self._model = model
        # Persistent WebSocket state (FIX 3: avoid per-call WS reconnect overhead)
        self._ws = None          # type: ignore[assignment]
        self._client = None      # type: ignore[assignment]
        self._ws_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Persistent WebSocket management
    # ------------------------------------------------------------------

    def _ensure_ws(self):  # type: ignore[return]
        """Open (or return existing) Cartesia WebSocket.  Thread-safe.

        Called from worker threads via asyncio.to_thread — the lock prevents
        concurrent open attempts on the first call.
        """
        with self._ws_lock:
            if self._ws is None:
                from cartesia import Cartesia  # lazy import
                self._client = Cartesia(api_key=self._api_key)
                self._ws = self._client.tts.websocket_connect().enter()
                logger.info("CartesiaTTS: persistent WebSocket connected")
            return self._ws

    def _invalidate_ws(self) -> None:
        """Close and forget the WebSocket so the next call reconnects."""
        with self._ws_lock:
            if self._ws is not None:
                try:
                    self._ws.close()
                except Exception:
                    pass
            self._ws = None
            self._client = None

    async def warmup(self) -> None:
        """Pre-open the Cartesia WebSocket in a thread (FIX 4: pre-warm)."""
        await asyncio.to_thread(self._ensure_ws)
        logger.info("CartesiaTTS: warmup complete (persistent WS ready)")

    async def close(self) -> None:
        """Close the persistent WebSocket gracefully."""
        await asyncio.to_thread(self._invalidate_ws)
        logger.info("CartesiaTTS: WebSocket closed")

    async def synthesize_stream(
        self, text: str, config: TTSConfig
    ) -> AsyncGenerator[bytes, None]:
        from cartesia.types import GenerationConfig  # lazy import

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        model = self._model

        # sonic-3 accepts speed in [0.6, 1.5]; clamp silently if out of range.
        cartesia_speed = max(0.6, min(1.5, config.speed))

        def _run() -> None:
            try:
                ws = self._ensure_ws()
                ctx = ws.context(
                    model_id=model,
                    voice={"mode": "id", "id": config.voice},
                    output_format={
                        "container": "raw",
                        "encoding": "pcm_s16le",
                        "sample_rate": config.sample_rate,
                    },
                    generation_config=GenerationConfig(speed=cartesia_speed),
                )
                ctx.push(text)
                ctx.no_more_inputs()
                for response in ctx.receive():
                    if response.type == "chunk" and response.audio:
                        loop.call_soon_threadsafe(queue.put_nowait, response.audio)
                    elif response.type == "done":
                        break
            except Exception as exc:
                logger.error("CartesiaTTS synthesis error: %s — reconnecting WS", exc)
                # Invalidate the WebSocket so next call gets a fresh connection.
                self._invalidate_ws()
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel

        task = asyncio.create_task(asyncio.to_thread(_run))
        try:
            while True:
                chunk = await queue.get()
                if chunk is None:
                    break
                yield chunk
        finally:
            await task


# ---------------------------------------------------------------------------
# Sarvam
# ---------------------------------------------------------------------------

class SarvamTTS(BaseTTS):
    """
    Streaming TTS via Sarvam WebSocket (raw websockets — no official async SDK).

    Protocol sequence per utterance:
      1. Send config message  {"type":"config", speaker, min_buffer_size,
                               output_audio_codec, pace}
      2. Send text chunks     {"type":"text", "text":"..."}
      3. Send flush           {"type":"flush"}

    Server sends:
      {"type":"audio",  "data":"<base64 PCM>"}
      {"type":"event",  "data":"completion"}   — end-of-stream marker
      {"type":"error",  "message":"..."}

    bulbul:v2 — 22050 Hz, supports pitch / loudness / pace (0.3–3.0)
    bulbul:v3 — 24000 Hz, temperature + pace (0.5–2.0), no pitch/loudness
    """

    _ENDPOINT = "wss://api.sarvam.ai/text-to-speech/ws"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "bulbul:v2",
    ) -> None:
        self._api_key = api_key or os.environ["SARVAM_API_KEY"]
        self._model = model

    def _ws_url(self) -> str:
        params = {"model": self._model, "send_completion_event": "true"}
        return f"{self._ENDPOINT}?{urlencode(params)}"

    async def synthesize_stream(
        self, text: str, config: TTSConfig
    ) -> AsyncGenerator[bytes, None]:
        url = self._ws_url()
        try:
            async with websockets.connect(
                url,
                additional_headers={"Api-Subscription-Key": self._api_key},
                ping_interval=20,
                ping_timeout=10,
            ) as ws:
                # Step 1: send config (required first message)
                cfg: dict = {
                    "type": "config",
                    "speaker": config.speaker,
                    "min_buffer_size": config.min_buffer_size,
                    "output_audio_codec": config.output_audio_codec,
                    "pace": max(0.3, min(3.0, config.speed)),
                }
                await ws.send(json.dumps(cfg))

                # Step 2: send text
                await ws.send(json.dumps({"type": "text", "text": text}))

                # Step 3: flush — tells server no more text is coming
                await ws.send(json.dumps({"type": "flush"}))

                # Receive until completion event
                async for message in ws:
                    if isinstance(message, bytes):
                        # Unexpected raw binary — yield directly
                        yield message
                        continue
                    try:
                        data: dict = json.loads(message)
                    except json.JSONDecodeError as exc:
                        logger.warning("SarvamTTS: JSON decode error — %s", exc)
                        continue

                    msg_type = data.get("type")
                    if msg_type == "audio":
                        encoded = data.get("data", "")
                        if encoded:
                            yield base64.b64decode(encoded)
                    elif msg_type == "event" and data.get("data") == "completion":
                        break
                    elif msg_type == "error":
                        logger.error("SarvamTTS server error: %s", data.get("message"))
                        break

        except websockets.ConnectionClosed as exc:
            logger.warning("SarvamTTS: connection closed — %s", exc)
        except Exception as exc:
            logger.error("SarvamTTS: unexpected error — %s", exc)


# ---------------------------------------------------------------------------
# OpenAI (HTTP streaming fallback)
# ---------------------------------------------------------------------------

class OpenAITTS(BaseTTS):
    """
    Streaming TTS via OpenAI Audio API (HTTP chunked transfer encoding).

    Used as a fallback when Cartesia or Sarvam are unavailable.
    Output: raw PCM signed-16-bit LE, 24 kHz (OpenAI 'pcm' format, headerless).

    Install: pip install openai
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "gpt-4o-mini-tts",
    ) -> None:
        self._api_key = api_key or os.environ["OPENAI_API_KEY"]
        self._model = model
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(api_key=self._api_key)
        return self._client

    async def synthesize_stream(
        self, text: str, config: TTSConfig
    ) -> AsyncGenerator[bytes, None]:
        # OpenAI voice names are strings like "alloy", "nova", etc.
        # If config.voice looks like a UUID (Cartesia ID), fall back to "alloy".
        voice = config.voice if len(config.voice) < 20 else "alloy"
        client = self._get_client()
        try:
            async with client.audio.speech.with_streaming_response.create(
                model=self._model,
                voice=voice,  # type: ignore[arg-type]
                input=text,
                response_format="pcm",   # 24 kHz 16-bit LE, no header
                speed=max(0.25, min(4.0, config.speed)),
            ) as response:
                async for chunk in response.iter_bytes(chunk_size=4096):
                    if chunk:
                        yield chunk
        except Exception as exc:
            logger.error("OpenAITTS synthesis error: %s", exc)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

class TTSRouter(BaseTTS):
    """
    Routes TTS requests by language:
      • Indic language (hi, bn, ta, te …) → SarvamTTS
      • All other languages               → CartesiaTTS
      • Either provider fails             → OpenAITTS fallback

    Both CartesiaTTS and SarvamTTS failures are caught; OpenAI is only
    invoked when the primary yields no audio or raises an exception.
    """

    def __init__(
        self,
        *,
        cartesia_kwargs: dict | None = None,
        sarvam_kwargs: dict | None = None,
        openai_kwargs: dict | None = None,
    ) -> None:
        self._cartesia = CartesiaTTS(**(cartesia_kwargs or {}))
        self._sarvam = SarvamTTS(**(sarvam_kwargs or {}))
        self._openai = OpenAITTS(**(openai_kwargs or {}))
        self.last_provider: str = "cartesia"   # updated each synthesize_stream() call

    async def warmup(self) -> None:
        """Pre-warm the Cartesia (and optionally Sarvam) connection."""
        if hasattr(self._cartesia, "warmup"):
            await self._cartesia.warmup()

    async def close(self) -> None:
        """Close all provider connections that support it."""
        if hasattr(self._cartesia, "close"):
            await self._cartesia.close()

    def _select(self, config: TTSConfig) -> BaseTTS:
        lang = config.language.lower().rstrip("-in")
        if lang in _INDIC_LANGUAGES or lang.startswith("hi"):
            return self._sarvam
        return self._cartesia

    async def synthesize_stream(
        self, text: str, config: TTSConfig
    ) -> AsyncGenerator[bytes, None]:
        primary = self._select(config)
        self.last_provider = type(primary).__name__.replace("TTS", "").lower()  # cartesia | sarvam | openai
        got_audio = False

        try:
            async for chunk in primary.synthesize_stream(text, config):
                got_audio = True
                yield chunk
        except Exception as exc:
            logger.warning(
                "TTSRouter: %s failed ('%s') — falling back to OpenAITTS",
                type(primary).__name__, exc,
            )

        if not got_audio:
            logger.info(
                "TTSRouter: %s produced no audio — falling back to OpenAITTS",
                type(primary).__name__,
            )
            self.last_provider = "openai"
            try:
                async for chunk in self._openai.synthesize_stream(text, config):
                    yield chunk
            except Exception as exc:
                logger.error("TTSRouter: OpenAI fallback also failed — %s", exc)
