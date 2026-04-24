"""
Streaming STT abstraction layer.

Providers:
  DeepgramSTT  — wss://api.deepgram.com/v1/listen (primary, non-Hindi)
  SarvamSTT    — wss://api.sarvam.ai/speech-to-text/ws (Hindi / Hinglish)
  STTRouter    — selects provider by declared language or runtime script detection
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncGenerator
from urllib.parse import urlencode

import websockets

logger = logging.getLogger(__name__)

# Devanagari Unicode block  (U+0900 – U+097F)
_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")

# Common Hinglish function words that rarely appear in pure English
_HINGLISH_TOKENS = frozenset({
    "hai", "hain", "nahi", "nahin", "kya", "aur", "ka", "ki", "ke",
    "mein", "se", "ko", "yeh", "woh", "toh", "bhi", "kuch", "theek",
    "acha", "accha", "agar", "phir", "abhi", "karo", "karo",
})

_HINGLISH_MATCH_THRESHOLD = 2  # tokens needed to classify as Hinglish


@dataclass
class TranscriptResult:
    text: str
    is_final: bool
    language: str | None = None


def _looks_hindi_or_hinglish(text: str) -> bool:
    """Heuristic: Devanagari script OR ≥2 Hinglish function-word matches."""
    if _DEVANAGARI_RE.search(text):
        return True
    tokens = set(text.lower().split())
    return len(tokens & _HINGLISH_TOKENS) >= _HINGLISH_MATCH_THRESHOLD


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class BaseSTT(ABC):
    """Common interface for all streaming STT providers."""

    @abstractmethod
    async def connect(self) -> None:
        """Open the WebSocket connection."""

    @abstractmethod
    async def close(self) -> None:
        """Flush any pending audio, send close signal, tear down connection."""

    @abstractmethod
    async def transcribe_stream(self, audio_chunk: bytes) -> None:
        """Feed a raw audio chunk into the live stream. Non-blocking."""

    @abstractmethod
    async def results(self) -> AsyncGenerator[TranscriptResult, None]:
        """Async generator that yields TranscriptResults as they arrive."""
        # Subclasses must override as async generators (use yield).
        yield  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Deepgram implementation
# ---------------------------------------------------------------------------

class DeepgramSTT(BaseSTT):
    """
    Live streaming STT via Deepgram WebSocket API (raw websockets, SDK-agnostic).

    Uses the Deepgram v1 streaming endpoint directly so that the SDK version
    (v3 / v4 / v5) does not matter.  Auth is a plain Authorization header.

    Wire format (inbound JSON from Deepgram):
      {
        "type": "Results",
        "is_final": true,
        "channel": {"alternatives": [{"transcript": "hello", ...}]}
      }

    Outbound:
      Send raw PCM bytes to stream audio.
      Send {"type": "CloseStream"} to end the session gracefully.

    Connection lifecycle:
      await connect()  →  loop: await transcribe_stream(chunk)
      async for r in results(): ...
      await close()
    """

    _WS_URL = "wss://api.deepgram.com/v1/listen"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "nova-3",           # nova-3 is ~15% faster than nova-2
        language: str = "en-US",
        smart_format: bool = True,
        interim_results: bool = True,    # enable for speech_final eager trigger
        punctuate: bool = True,
        endpointing: int = 300,          # ms of silence before utterance end
        utterance_end_ms: int = 1000,    # emit UtteranceEnd after N ms silence
        vad_events: bool = True,         # receive SpeechStarted / UtteranceEnd
    ) -> None:
        self._api_key = api_key or os.environ["DEEPGRAM_API_KEY"]
        self._model = model
        self._language = language
        self._smart_format = smart_format
        self._interim_results = interim_results
        self._punctuate = punctuate
        self._endpointing = endpointing
        self._utterance_end_ms = utterance_end_ms
        self._vad_events = vad_events

        self._queue: asyncio.Queue[TranscriptResult] = asyncio.Queue()
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._recv_task: asyncio.Task[None] | None = None
        self._connected = False

    def _build_url(self) -> str:
        from urllib.parse import urlencode
        params: dict[str, str] = {
            "model": self._model,
            "language": self._language,
            "smart_format": str(self._smart_format).lower(),
            "interim_results": str(self._interim_results).lower(),
            "punctuate": str(self._punctuate).lower(),
            "endpointing": str(self._endpointing),
            "utterance_end_ms": str(self._utterance_end_ms),
            "vad_events": str(self._vad_events).lower(),
            "encoding": "linear16",
            "sample_rate": "16000",
            "channels": "1",
        }
        return f"{self._WS_URL}?{urlencode(params)}"

    async def connect(self) -> None:
        url = self._build_url()
        self._ws = await websockets.connect(
            url,
            additional_headers={"Authorization": f"Token {self._api_key}"},
            ping_interval=20,
            ping_timeout=10,
        )
        self._connected = True
        self._recv_task = asyncio.create_task(
            self._recv_loop(), name="deepgram_recv"
        )
        logger.info(
            "DeepgramSTT connected (model=%s lang=%s)", self._model, self._language
        )

    async def _recv_loop(self) -> None:
        assert self._ws is not None
        try:
            async for message in self._ws:
                if isinstance(message, bytes):
                    continue  # Deepgram sends JSON strings; skip unexpected binary
                try:
                    data: dict = json.loads(message)
                except json.JSONDecodeError as exc:
                    logger.warning("DeepgramSTT: JSON decode error — %s", exc)
                    continue

                msg_type = data.get("type")

                # ── Results (transcript) ─────────────────────────────────────
                if msg_type == "Results":
                    try:
                        alts = data["channel"]["alternatives"]
                        text = (alts[0].get("transcript") or "").strip() if alts else ""
                        if not text:
                            continue
                        is_final = bool(data.get("is_final", False))
                        # speech_final=True means Deepgram detected a phrase
                        # endpoint (VAD silence within the utterance) — treat as
                        # final for eager LLM triggering without waiting for the
                        # full endpointing silence window.
                        speech_final = bool(data.get("speech_final", False))
                        treat_as_final = is_final or speech_final
                        if treat_as_final or self._interim_results:
                            await self._queue.put(TranscriptResult(
                                text=text,
                                is_final=treat_as_final,
                                language=self._language,
                            ))
                    except (KeyError, IndexError) as exc:
                        logger.warning("DeepgramSTT: transcript parse error — %s", exc)

                # ── UtteranceEnd ─────────────────────────────────────────────
                # Deepgram fires UtteranceEnd when it hasn't received speech for
                # utterance_end_ms ms.  We use it to ensure the pipeline doesn't
                # stall if the user's last word produced no is_final/speech_final.
                elif msg_type == "UtteranceEnd":
                    logger.debug("DeepgramSTT: UtteranceEnd received")
                    # Nothing extra to do — a speech_final or is_final should
                    # already have arrived just before this event in practice.

                # ── SpeechStarted ────────────────────────────────────────────
                elif msg_type == "SpeechStarted":
                    logger.debug("DeepgramSTT: SpeechStarted")

                # Ignore Metadata and any other event types.
                else:
                    continue

        except websockets.ConnectionClosed:
            logger.info("DeepgramSTT: server closed connection")
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("DeepgramSTT: recv loop crashed — %s", exc)

    async def close(self) -> None:
        if self._ws and not self._ws.closed:
            try:
                await self._ws.send(json.dumps({"type": "CloseStream"}))
                await asyncio.sleep(0.1)
            except Exception:
                pass
            await self._ws.close()
        self._ws = None
        self._connected = False

        if self._recv_task and not self._recv_task.done():
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                pass
        self._recv_task = None
        logger.info("DeepgramSTT closed")

    async def transcribe_stream(self, audio_chunk: bytes) -> None:
        if not self._connected or not self._ws:
            raise RuntimeError("DeepgramSTT: call connect() before streaming audio")
        await self._ws.send(audio_chunk)

    async def results(self) -> AsyncGenerator[TranscriptResult, None]:
        while True:
            yield await self._queue.get()


# ---------------------------------------------------------------------------
# Sarvam implementation
# ---------------------------------------------------------------------------

class SarvamSTT(BaseSTT):
    """
    Live streaming STT via Sarvam WebSocket (raw websockets library).

    Audio format required by Sarvam:
      PCM signed-16-bit little-endian (pcm_s16le), 16 kHz, mono

    Connection lifecycle:
      await connect()  →  loop: await transcribe_stream(chunk)
      async for r in results(): ...
      await close()
    """

    _ENDPOINT = "wss://api.sarvam.ai/speech-to-text/ws"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        language_code: str = "hi-IN",
        model: str = "saaras:v3",
        # codemix preserves mixed Hindi/English script — ideal for Hinglish
        mode: str = "codemix",
        sample_rate: int = 16000,
    ) -> None:
        self._api_key = api_key or os.environ["SARVAM_API_KEY"]
        self._language_code = language_code
        self._model = model
        self._mode = mode
        self._sample_rate = sample_rate

        self._queue: asyncio.Queue[TranscriptResult] = asyncio.Queue()
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._recv_task: asyncio.Task[None] | None = None

    def _build_url(self) -> str:
        params = {
            "language-code": self._language_code,
            "model": self._model,
            "mode": self._mode,
            "sample_rate": str(self._sample_rate),
            "input_audio_codec": "pcm_s16le",
        }
        return f"{self._ENDPOINT}?{urlencode(params)}"

    async def connect(self) -> None:
        url = self._build_url()
        self._ws = await websockets.connect(
            url,
            additional_headers={"Api-Subscription-Key": self._api_key},
            ping_interval=20,
            ping_timeout=10,
        )
        self._recv_task = asyncio.create_task(
            self._recv_loop(), name="sarvam_recv"
        )
        logger.info(
            "SarvamSTT connected (lang=%s model=%s mode=%s)",
            self._language_code, self._model, self._mode,
        )

    async def _recv_loop(self) -> None:
        assert self._ws is not None
        try:
            async for message in self._ws:
                if isinstance(message, bytes):
                    # Sarvam sends text JSON; skip unexpected binary
                    continue
                try:
                    data: dict = json.loads(message)
                    text = (data.get("transcript") or "").strip()
                    if not text:
                        continue
                    is_final = bool(data.get("is_final", True))
                    await self._queue.put(TranscriptResult(
                        text=text,
                        is_final=is_final,
                        language=self._language_code,
                    ))
                except (json.JSONDecodeError, KeyError) as exc:
                    logger.warning("SarvamSTT: message parse error — %s", exc)
        except websockets.ConnectionClosed:
            logger.info("SarvamSTT: server closed connection")
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("SarvamSTT: recv loop crashed — %s", exc)

    async def close(self) -> None:
        if self._ws and not self._ws.closed:
            try:
                # Flush signal tells Sarvam to finalise any buffered audio
                await self._ws.send(json.dumps({"type": "flush"}))
                await asyncio.sleep(0.25)
            except Exception:
                pass
            await self._ws.close()
        self._ws = None

        if self._recv_task and not self._recv_task.done():
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                pass
        self._recv_task = None
        logger.info("SarvamSTT closed")

    async def transcribe_stream(self, audio_chunk: bytes) -> None:
        if not self._ws or self._ws.closed:
            raise RuntimeError("SarvamSTT: call connect() before streaming audio")
        # Sarvam expects raw binary PCM frames
        await self._ws.send(audio_chunk)

    async def results(self) -> AsyncGenerator[TranscriptResult, None]:
        while True:
            yield await self._queue.get()


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

class STTRouter(BaseSTT):
    """
    Selects between DeepgramSTT and SarvamSTT based on:
      1. Declared language at construction time (language='hi' → Sarvam)
      2. Runtime detection: first final transcript with Devanagari or
         Hinglish markers triggers a live switch to SarvamSTT.

    Both connections are lazily opened; only the active one receives audio.
    """

    def __init__(
        self,
        *,
        language: str = "en",
        deepgram_kwargs: dict | None = None,
        sarvam_kwargs: dict | None = None,
    ) -> None:
        self._language = language.lower().rstrip("-in")  # normalise "hi-IN" → "hi"
        self._deepgram = DeepgramSTT(**(deepgram_kwargs or {}))
        self._sarvam = SarvamSTT(**(sarvam_kwargs or {}))
        self._active: BaseSTT | None = None
        self._queue: asyncio.Queue[TranscriptResult] = asyncio.Queue()
        self._drain_tasks: list[asyncio.Task[None]] = []
        self._switching = False  # guard against concurrent switch

    @property
    def active_provider_name(self) -> str:
        """Return the name of the currently active STT provider."""
        if self._active is None:
            return "none"
        return type(self._active).__name__.replace("STT", "").lower()  # "deepgram" | "sarvam"

    def _use_sarvam_initially(self) -> bool:
        return self._language in ("hi", "hinglish", "bn", "gu", "kn", "ml",
                                   "mr", "pa", "ta", "te", "en-in")

    async def connect(self) -> None:
        provider: BaseSTT = (
            self._sarvam if self._use_sarvam_initially() else self._deepgram
        )
        await provider.connect()
        self._active = provider
        self._drain_tasks.append(
            asyncio.create_task(
                self._drain(provider), name=f"router_drain_{type(provider).__name__}"
            )
        )
        logger.info("STTRouter started with %s", type(provider).__name__)

    async def _drain(self, provider: BaseSTT) -> None:
        """Forward results from *provider* into the shared queue, detecting language."""
        async for result in provider.results():
            # Auto-switch: if Deepgram returns Hindi/Hinglish text, hand off to Sarvam
            if provider is self._deepgram and _looks_hindi_or_hinglish(result.text):
                logger.info(
                    "STTRouter: Hinglish detected in '%s' — switching to SarvamSTT",
                    result.text[:40],
                )
                asyncio.create_task(self._switch_to_sarvam())
            await self._queue.put(result)

    async def _switch_to_sarvam(self) -> None:
        if self._active is self._sarvam or self._switching:
            return
        self._switching = True
        try:
            await self._sarvam.connect()
            self._active = self._sarvam
            self._drain_tasks.append(
                asyncio.create_task(
                    self._drain(self._sarvam), name="router_drain_SarvamSTT_switch"
                )
            )
            logger.info("STTRouter: now routing to SarvamSTT")
        except Exception as exc:
            logger.error("STTRouter: switch to SarvamSTT failed — %s", exc)
        finally:
            self._switching = False

    async def close(self) -> None:
        for task in self._drain_tasks:
            task.cancel()
        await asyncio.gather(*self._drain_tasks, return_exceptions=True)

        close_coros = []
        if self._deepgram._connected:
            close_coros.append(self._deepgram.close())
        if self._sarvam._ws is not None:
            close_coros.append(self._sarvam.close())
        if close_coros:
            await asyncio.gather(*close_coros, return_exceptions=True)

        logger.info("STTRouter closed")

    async def transcribe_stream(self, audio_chunk: bytes) -> None:
        if not self._active:
            raise RuntimeError("STTRouter: call connect() before streaming audio")
        await self._active.transcribe_stream(audio_chunk)

    async def results(self) -> AsyncGenerator[TranscriptResult, None]:
        while True:
            yield await self._queue.get()
