"""
Real-time voice pipeline.

Orchestrates the full flow: Audio → STT → LLM → TTS → Audio output

Streaming strategy:
  - STT final transcripts trigger LLM generation immediately.
  - LLM text is accumulated until a sentence boundary (.?!) then flushed
    to TTS, so audio starts before the full LLM response completes.
  - TTS audio chunks are emitted via on_audio_output as they arrive.

Interruption:
  - An optional InterruptHandler tracks the active LLM→TTS task.
  - process_audio() forwards each chunk for energy-based barge-in detection.
  - _drain_stt() cancels any running response before starting a new one.

Event callbacks (replace with async callables):
  on_transcript(text: str, is_final: bool)
  on_llm_response(chunk: str)
  on_audio_output(audio: bytes)
  on_turn_metrics(metrics: dict)   ← fired once per completed turn
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from interrupt_handler import InterruptHandler
from llm_router import LLMConfig, LLMRouter
from observability import TurnMetrics
from stt_service import STTRouter
from tts_service import TTSConfig, TTSRouter

logger = logging.getLogger(__name__)


def _should_flush(text: str) -> bool:
    """Return True when the accumulated LLM buffer is ready to send to TTS.

    Flush rules (whichever comes first):
      • Text ends with a strong sentence boundary  (.  !  ?)
      • Text ends with a comma — start TTS earlier on long clauses
      • Buffer has grown to ≥ 15 words — prevents a very long sentence
        from blocking TTS until the model finishes the whole thing

    Commas and word-count flushing are the primary drivers of lower TTFB:
    without them the pipeline waits for a full sentence before TTS starts.
    """
    stripped = text.rstrip()
    if not stripped:
        return False
    if stripped[-1] in ".!?":
        return True
    if stripped[-1] == "," and len(stripped.split()) >= 6:
        # only flush on comma after at least 6 words to avoid tiny TTS calls
        return True
    if len(stripped.split()) >= 15:
        return True
    return False

AsyncCallback = Callable[..., Awaitable[None]]


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class PipelineConfig:
    """Top-level configuration wiring all three service layers."""

    language: str = "en"
    # Each "turn" is one user message + one assistant reply = 2 Message objects.
    max_history_turns: int = 10

    tts: TTSConfig = field(default_factory=TTSConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)

    # Pass-through kwargs to underlying providers
    deepgram_kwargs: dict = field(default_factory=dict)
    sarvam_stt_kwargs: dict = field(default_factory=dict)
    cartesia_kwargs: dict = field(default_factory=dict)
    sarvam_tts_kwargs: dict = field(default_factory=dict)
    openai_tts_kwargs: dict = field(default_factory=dict)
    gemini_kwargs: dict = field(default_factory=dict)
    openai_llm_kwargs: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class VoicePipeline:
    """
    End-to-end streaming voice pipeline with barge-in interruption support.

    Typical usage:
        handler = InterruptHandler(energy_threshold=600.0)
        pipeline = VoicePipeline(config, interrupt_handler=handler)
        pipeline.on_transcript   = async_transcript_handler
        pipeline.on_llm_response = async_llm_chunk_handler
        pipeline.on_audio_output = async_audio_handler

        await pipeline.start()
        async for chunk in audio_source:
            await pipeline.process_audio(chunk)
        await pipeline.stop()
    """

    def __init__(
        self,
        config: PipelineConfig | None = None,
        *,
        interrupt_handler: InterruptHandler | None = None,
    ) -> None:
        self._config = config or PipelineConfig()
        cfg = self._config

        self._stt = STTRouter(
            language=cfg.language,
            deepgram_kwargs=cfg.deepgram_kwargs,
            sarvam_kwargs=cfg.sarvam_stt_kwargs,
        )

        # LLM history window: max_history counts Message objects; 2 per turn.
        llm_cfg = cfg.llm
        llm_cfg_with_history = LLMConfig(
            provider=llm_cfg.provider,
            system_prompt=llm_cfg.system_prompt,
            max_tokens=llm_cfg.max_tokens,
            temperature=llm_cfg.temperature,
            max_history=cfg.max_history_turns * 2,
        )
        self._llm = LLMRouter(
            config=llm_cfg_with_history,
            gemini_kwargs=cfg.gemini_kwargs,
            openai_kwargs=cfg.openai_llm_kwargs,
        )

        self._tts = TTSRouter(
            cartesia_kwargs=cfg.cartesia_kwargs,
            sarvam_kwargs=cfg.sarvam_tts_kwargs,
            openai_kwargs=cfg.openai_tts_kwargs,
        )

        self._interrupter: InterruptHandler = interrupt_handler or InterruptHandler()

        # Event callbacks — replace with async callables as needed.
        self.on_transcript: AsyncCallback = _noop
        self.on_llm_response: AsyncCallback = _noop
        self.on_audio_output: AsyncCallback = _noop
        self.on_turn_metrics: AsyncCallback = _noop   # fires with TurnMetrics dict

        self._stt_drain_task: asyncio.Task | None = None
        self._running = False

        # Per-turn timing state (reset at the start of each _run_llm_tts call).
        self._t_e2e_start: float | None = None  # time.monotonic() when STT final arrived
        self._t_llm_ttft_ms: float | None = None   # LLM time-to-first-token (ms)
        self._t_tts_ttfb_ms: float | None = None   # TTS time-to-first-byte (ms)
        self._t_e2e_ms: float | None = None         # total end-to-end latency (ms)
        self._current_transcript: str = ""          # the user text for the active turn

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Connect STT, pre-warm TTS + LLM, then begin background transcript processing.

        All three connections are opened concurrently (asyncio.gather) so that
        Deepgram, Cartesia, and OpenAI handshakes overlap — saving 600–900 ms
        on first-turn latency.  Each provider prints its own timing line.
        """
        print("[SYSTEM] Pre-warming connections...")
        warm_start = time.monotonic()

        warm_coros = [self._stt.connect(), self._warmup_llm()]
        if hasattr(self._tts, "warmup"):
            warm_coros.append(self._tts.warmup())
        await asyncio.gather(*warm_coros)

        warm_ms = int((time.monotonic() - warm_start) * 1000)
        print(f"[SYSTEM] Pre-warm done in {warm_ms}ms")

        self._running = True
        self._stt_drain_task = asyncio.create_task(
            self._drain_stt(), name="pipeline_stt_drain"
        )
        print(f"[SYSTEM] Pipeline ready — listening… (language={self._config.language})")
        logger.info("VoicePipeline started (language=%s)", self._config.language)

    async def _warmup_llm(self) -> None:
        """Fire one token through the LLM to open the TCP connection and warm
        any provider-side cache.  We discard the output — the goal is purely
        to pay the cold-start cost here, not during the first real user turn."""
        t0 = time.monotonic()
        try:
            async for _ in self._llm.chat(
                "hi",
                config=LLMConfig(
                    provider=self._config.llm.provider,
                    system_prompt="Say hi.",
                    max_tokens=1,
                    temperature=0.0,
                ),
            ):
                break  # one token is enough — connection is now open
            # pop the warmup turn so it doesn't pollute real history
            self._llm.history.pop_last_user()
        except Exception as exc:
            logger.warning("LLM warmup failed (non-fatal): %s", exc)
        ms = int((time.monotonic() - t0) * 1000)
        print(f"[SYSTEM] LLM warmup: {ms}ms")

    async def stop(self) -> None:
        """Cancel background tasks, interrupt any active response, close connections."""
        self._running = False

        # Stop any in-progress LLM→TTS chain first.
        await self._interrupter.cancel_active()

        if self._stt_drain_task and not self._stt_drain_task.done():
            self._stt_drain_task.cancel()
            try:
                await self._stt_drain_task
            except asyncio.CancelledError:
                pass

        await self._stt.close()
        # Close the persistent Cartesia WebSocket (no-op if provider lacks close).
        if hasattr(self._tts, "close"):
            await self._tts.close()
        logger.info("VoicePipeline stopped")

    # ------------------------------------------------------------------
    # Audio ingestion
    # ------------------------------------------------------------------

    async def process_audio(self, chunk: bytes) -> None:
        """
        Feed a raw PCM audio chunk into the STT stream.

        Also forwards the chunk to the interrupt handler so energy-based
        barge-in detection can fire without a separate call path.
        """
        if not self._running:
            raise RuntimeError("VoicePipeline: call start() before process_audio()")
        # Energy check: interrupt if bot is speaking and user audio is loud enough.
        await self._interrupter.on_audio(chunk)
        await self._stt.transcribe_stream(chunk)

    # ------------------------------------------------------------------
    # Internal: STT drain loop
    # ------------------------------------------------------------------

    async def _drain_stt(self) -> None:
        """Read STT results; fire callbacks; trigger LLM→TTS on finals."""
        try:
            async for result in self._stt.results():
                if not self._running:
                    break
                await self.on_transcript(result.text, result.is_final)
                if result.is_final and result.text.strip():
                    # Stamp e2e clock with time.monotonic() — same clock used
                    # in _llm_producer and _tts_consumer for accurate deltas.
                    self._t_e2e_start = time.monotonic()
                    self._current_transcript = result.text
                    # Cancel any running response before starting the new one.
                    await self._interrupter.cancel_active()
                    task = asyncio.create_task(
                        self._run_llm_tts(result.text),
                        name="pipeline_llm_tts",
                    )
                    self._interrupter.set_active(task)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("VoicePipeline: STT drain crashed — %s", exc)

    # ------------------------------------------------------------------
    # Internal: LLM → TTS streaming chain
    # ------------------------------------------------------------------

    async def _run_llm_tts(self, user_text: str) -> None:
        """
        Stream an LLM reply for *user_text* with parallel LLM→TTS execution.

        Architecture:
          _llm_producer  — streams LLM chunks, splits on sentence boundaries,
                           pushes sentences into sentence_queue.
          _tts_consumer  — pulls sentences and synthesises them serially so
                           audio output is in order.
          Both run as concurrent tasks so LLM generation overlaps TTS synthesis,
          cutting E2E latency significantly vs. the previous sequential approach.

        Cancellation:
          asyncio.gather() propagates cancellation to both child tasks.
          The producer's finally block sends a sentinel (put_nowait) so the
          consumer always exits cleanly even mid-cancellation.
          pop_last_user() removes the orphaned user turn from history when
          the response was interrupted before the assistant turn was appended.
        """
        logger.info("LLM input: %r", user_text[:80])
        full_response: list[str] = []
        cancelled = False

        # Reset per-turn timing
        self._t_llm_ttft_ms = None
        self._t_tts_ttfb_ms = None
        self._t_e2e_ms = None

        # Bounded queue decouples LLM and TTS; backpressure prevents the LLM
        # from building up more text than TTS can play (keeps memory bounded).
        # maxsize=4: at most 4 flushed segments queued up ahead of TTS.
        text_queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=4)

        async def _llm_producer() -> None:
            buffer = ""
            llm_t0 = time.monotonic()
            first_token = True
            try:
                async for chunk in self._llm.chat(user_text, config=self._config.llm):
                    # Track LLM time-to-first-token and print for visibility.
                    if first_token:
                        ttft = int((time.monotonic() - llm_t0) * 1000)
                        self._t_llm_ttft_ms = float(ttft)
                        print(f"[LATENCY] LLM TTFT:{ttft}ms")
                        first_token = False
                        # Also stamp for E2E calculation
                        if self._t_e2e_start:
                            elapsed = time.monotonic() - self._t_e2e_start
                            self._t_llm_ttft_ms = elapsed * 1000.0

                    await self.on_llm_response(chunk)
                    full_response.append(chunk)
                    buffer += chunk

                    # Flush on sentence end, comma, or 15-word accumulation.
                    # This starts TTS earlier vs. waiting for a full sentence.
                    if _should_flush(buffer):
                        segment = buffer.strip()
                        if segment:
                            await text_queue.put(segment)
                        buffer = ""

                # Flush any trailing fragment.
                if buffer.strip():
                    await text_queue.put(buffer.strip())

            finally:
                # put_nowait so sentinel always arrives even during cancellation.
                try:
                    text_queue.put_nowait(None)
                except asyncio.QueueFull:
                    pass  # consumer is also being cancelled; sentinel not needed

        async def _tts_consumer() -> None:
            tts_t0 = time.monotonic()
            first_chunk = True
            while True:
                segment = await text_queue.get()
                if segment is None:  # sentinel — producer finished
                    break
                # Each segment synthesizes serially so audio stays in order.
                async for audio_chunk in self._tts.synthesize_stream(
                    segment, self._config.tts
                ):
                    if first_chunk:
                        ttfb = int((time.monotonic() - tts_t0) * 1000)
                        self._t_tts_ttfb_ms = float(ttfb)
                        if self._t_e2e_start:
                            self._t_e2e_ms = (
                                time.monotonic() - self._t_e2e_start
                            ) * 1000.0
                            print(
                                f"[LATENCY] TTS TTFB:{ttfb}ms  "
                                f"E2E:{int(self._t_e2e_ms)}ms"
                            )
                        first_chunk = False
                    await self.on_audio_output(audio_chunk)

        producer_task: asyncio.Task | None = None
        consumer_task: asyncio.Task | None = None
        try:
            producer_task = asyncio.create_task(_llm_producer(), name="llm_producer")
            consumer_task = asyncio.create_task(_tts_consumer(), name="tts_consumer")
            # gather propagates CancelledError to both child tasks when this
            # coroutine is cancelled from the outside (e.g. barge-in).
            await asyncio.gather(producer_task, consumer_task)

        except asyncio.CancelledError:
            cancelled = True
            if producer_task and not producer_task.done():
                producer_task.cancel()
            if consumer_task and not consumer_task.done():
                consumer_task.cancel()
            # Wait for both to finish before leaving the try/finally.
            await asyncio.gather(
                *[t for t in (producer_task, consumer_task) if t],
                return_exceptions=True,
            )
            raise

        finally:
            self._interrupter.clear_active()
            if cancelled:
                # Remove the unanswered user turn so the next LLM call doesn't
                # see a dangling user message with no assistant reply.
                self._llm.history.pop_last_user()

            # Fire metrics and print final turn summary.
            if full_response:
                # Final E2E print (in case _tts_consumer didn't get first audio).
                if self._t_e2e_ms is not None:
                    target_ok = self._t_e2e_ms <= 840
                    marker = "✓" if target_ok else "!"
                    print(
                        f"[LATENCY] E2E:{int(self._t_e2e_ms)}ms {marker}  "
                        f"({self._llm.last_provider}/{self._tts.last_provider})"
                    )
                try:
                    metrics = TurnMetrics(
                        user_transcript=user_text,
                        ai_response="".join(full_response),
                        stt_latency_ms=None,
                        llm_latency_ms=self._t_llm_ttft_ms,
                        tts_latency_ms=self._t_tts_ttfb_ms,
                        e2e_latency_ms=self._t_e2e_ms,
                        stt_provider=self._stt.active_provider_name,
                        llm_provider=self._llm.last_provider,
                        tts_provider=self._tts.last_provider,
                        tts_characters=sum(len(s) for s in full_response),
                    )
                    await self.on_turn_metrics(metrics.to_dict())
                except Exception as exc:
                    logger.error("VoicePipeline: on_turn_metrics failed — %s", exc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _noop(*_args, **_kwargs) -> None:
    pass


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

async def _smoke_test() -> None:
    """
    Simulate the LLM→TTS path and an interruption, without real audio hardware.

    Test 1 — normal path: _run_llm_tts produces LLM text and TTS audio.
    Test 2 — interrupt:   an active task is cancelled mid-stream; history stays
                          consistent (no orphaned user message).

    Requires GOOGLE_API_KEY (or OPENAI_API_KEY) and CARTESIA_API_KEY in env.
    """
    from dotenv import load_dotenv
    load_dotenv()

    # ---- Test 1: normal LLM→TTS path --------------------------------
    collected_text: list[str] = []
    collected_audio: list[bytes] = []

    pipeline = VoicePipeline()

    async def on_llm(chunk: str) -> None:
        collected_text.append(chunk)
        print(chunk, end="", flush=True)

    async def on_audio(audio: bytes) -> None:
        collected_audio.append(audio)

    pipeline.on_llm_response = on_llm
    pipeline.on_audio_output = on_audio

    print("--- Test 1: LLM → TTS (normal) ---")
    print("LLM: ", end="")
    await pipeline._run_llm_tts("Hello, what is two plus two?")

    total_audio = sum(len(c) for c in collected_audio)
    print(f"\nLLM chunks={len(collected_text)}  audio_bytes={total_audio}")
    assert collected_text, "FAIL: no LLM response"
    assert total_audio > 0, "FAIL: no TTS audio"
    history_len_after_turn = len(pipeline._llm.history)
    print("PASS\n")

    # ---- Test 2: interrupt cancels task; history stays clean ---------
    print("--- Test 2: barge-in cancellation ---")
    interrupted = asyncio.Event()

    async def on_interrupted() -> None:
        interrupted.set()

    pipeline._interrupter._on_interrupt = on_interrupted

    task = asyncio.create_task(
        pipeline._run_llm_tts("Tell me a long story please."),
        name="test_cancel_task",
    )
    pipeline._interrupter.set_active(task)

    # Let it start, then cancel immediately via the handler.
    await asyncio.sleep(0.05)
    await pipeline._interrupter.interrupt()
    await asyncio.wait_for(interrupted.wait(), timeout=2.0)

    history_len_after_interrupt = len(pipeline._llm.history)
    assert history_len_after_interrupt == history_len_after_turn, (
        f"FAIL: orphaned user message — history grew from "
        f"{history_len_after_turn} to {history_len_after_interrupt}"
    )
    print(f"History length unchanged at {history_len_after_turn}")
    print("PASS")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    asyncio.run(_smoke_test())
