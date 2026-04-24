"""
Barge-in / interruption detection for the voice pipeline.

Detection strategy
──────────────────
Every incoming audio chunk is checked for RMS energy. When the bot is
currently speaking (LLM→TTS task is active) and the user's audio energy
exceeds the threshold, the active task is cancelled immediately via
asyncio.Task.cancel() — no sleep loops, no polling.

A second trigger fires automatically inside the pipeline: whenever a new
STT final transcript arrives, any still-running response task is cancelled
first so the bot never speaks over itself answering a stale question.

Integration contract (pipeline.py calls these methods)
───────────────────────────────────────────────────────
  set_active(task)     — register the current _run_llm_tts task
  clear_active()       — called when task ends normally (finally block)
  on_audio(chunk)      — called from process_audio() for every PCM chunk
  cancel_active()      — called from _drain_stt() before a new response starts

  on_interrupt         — async callback fired whenever an interrupt occurs;
                         set this to notify the caller (e.g. pipeline events)
"""
from __future__ import annotations

import array
import asyncio
import logging
import math
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

AsyncCallback = Callable[[], Awaitable[None]]


async def _noop() -> None:
    pass


def _rms_energy(pcm_s16le: bytes) -> float:
    """
    Root-mean-square energy of a PCM signed-16-bit little-endian buffer.
    Returns 0.0 for empty / too-short buffers.
    Uses only the stdlib array module — no numpy required.
    """
    if len(pcm_s16le) < 2:
        return 0.0
    samples = array.array("h", pcm_s16le)
    mean_sq = sum(s * s for s in samples) / len(samples)
    return math.sqrt(mean_sq)


class InterruptHandler:
    """
    Cancels the active LLM→TTS asyncio Task on barge-in.

    Parameters
    ──────────
    energy_threshold : float
        RMS amplitude (0–32 767 for s16le) above which incoming audio is
        classified as speech while the bot is talking. Default 500 ≈ a
        quiet room speaking voice; tune upward in noisy environments.
    min_interrupt_interval : float
        Seconds to wait after an interrupt before allowing another. Prevents
        rapid-fire cancellations on a single continuous utterance.
    on_interrupt : async callable
        Fired once each time the bot is successfully interrupted. Use this to
        update UI state, log metrics, etc.
    """

    def __init__(
        self,
        *,
        energy_threshold: float = 500.0,
        min_interrupt_interval: float = 1.0,
        on_interrupt: AsyncCallback = _noop,
    ) -> None:
        self._energy_threshold = energy_threshold
        self._min_interrupt_interval = min_interrupt_interval
        self._on_interrupt = on_interrupt

        self._active_task: asyncio.Task | None = None
        self._last_interrupt_time: float = 0.0

    # ------------------------------------------------------------------
    # Task registration (called by pipeline._run_llm_tts)
    # ------------------------------------------------------------------

    def set_active(self, task: asyncio.Task) -> None:
        """Register the LLM→TTS task that is currently producing audio."""
        self._active_task = task
        logger.debug("InterruptHandler: task registered — %s", task.get_name())

    def clear_active(self) -> None:
        """
        Mark the pipeline as no longer speaking.
        Called from the finally block of _run_llm_tts regardless of how it ends.
        """
        self._active_task = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def bot_speaking(self) -> bool:
        """True only while an active, non-done LLM→TTS task is registered."""
        return self._active_task is not None and not self._active_task.done()

    # ------------------------------------------------------------------
    # Hooks called by pipeline
    # ------------------------------------------------------------------

    async def on_audio(self, chunk: bytes) -> None:
        """
        Called by pipeline.process_audio() for every incoming PCM chunk.

        Triggers an interrupt if:
          • the bot is currently speaking, AND
          • the chunk's RMS energy exceeds the threshold, AND
          • enough time has passed since the last interrupt.
        """
        if not self.bot_speaking:
            return

        loop = asyncio.get_running_loop()
        now = loop.time()
        if now - self._last_interrupt_time < self._min_interrupt_interval:
            return  # still in cool-down

        if _rms_energy(chunk) > self._energy_threshold:
            logger.info(
                "InterruptHandler: barge-in detected (energy=%.0f > threshold=%.0f)",
                _rms_energy(chunk), self._energy_threshold,
            )
            await self.interrupt()

    async def cancel_active(self) -> None:
        """
        Cancel any running response task before starting a new one.
        Called by _drain_stt() every time a new final transcript arrives.
        This guarantees the bot never answers two questions simultaneously.
        """
        if self.bot_speaking:
            logger.info(
                "InterruptHandler: new transcript arrived — cancelling stale response"
            )
            await self.interrupt()

    # ------------------------------------------------------------------
    # Core cancellation
    # ------------------------------------------------------------------

    async def interrupt(self) -> None:
        """
        Cancel the active LLM→TTS task and fire the on_interrupt callback.

        Uses asyncio.Task.cancel() + await so the cancelled coroutine's
        finally blocks run before we return. Never uses sleep.
        """
        task = self._active_task
        if task is None or task.done():
            return

        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            # CancelledError is expected; log anything else but don't re-raise.
            pass

        loop = asyncio.get_running_loop()
        self._last_interrupt_time = loop.time()
        self._active_task = None

        try:
            await self._on_interrupt()
        except Exception as exc:
            logger.error("InterruptHandler: on_interrupt callback raised — %s", exc)
