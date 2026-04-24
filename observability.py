"""
Observability — per-turn metrics collection and JSONL logging.

TurnMetrics
───────────
  Captures all latency and usage data for one user→AI exchange:
    • STT finalisation latency (ms from audio start to final transcript)
    • LLM time-to-first-token (ms)
    • TTS time-to-first-byte (ms)
    • End-to-end latency (ms from STT final → first audio byte out)
    • Token counts (input / output)
    • TTS characters synthesised
    • Which provider was actually used at each stage

MetricsCollector
────────────────
  One instance per call.  Call record_turn() after every exchange; it:
    1. Appends a JSON line to metrics_log.jsonl
    2. Prints a one-line sidebar to stdout
  Call summary() at call end to print a per-call aggregate.

JSONL schema (one object per line)
───────────────────────────────────
  {
    "call_sid":        str,
    "room_name":       str,
    "turn":            int,
    "timestamp":       "2024-01-01T12:00:00.000Z",
    "user_transcript": str,
    "ai_response":     str,
    "stt_latency_ms":  float | null,
    "llm_latency_ms":  float | null,
    "tts_latency_ms":  float | null,
    "e2e_latency_ms":  float | null,
    "llm_provider":    str,
    "stt_provider":    str,
    "tts_provider":    str,
    "input_tokens":    int | null,
    "output_tokens":   int | null,
    "tts_characters":  int
  }
"""
from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_JSONL_PATH = Path("metrics_log.jsonl")

# Colour codes (ANSI — gracefully ignored on non-TTY)
_CYAN   = "\033[36m"
_DIM    = "\033[2m"
_RESET  = "\033[0m"
_BOLD   = "\033[1m"


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass
class TurnMetrics:
    """All measurable data for one conversation turn."""

    # Identification
    call_sid:        str = ""
    room_name:       str = ""
    turn:            int = 0
    timestamp:       str = ""            # ISO-8601 UTC

    # Content
    user_transcript: str = ""
    ai_response:     str = ""

    # Latencies (milliseconds; None = not measured / unavailable)
    stt_latency_ms:  Optional[float] = None
    llm_latency_ms:  Optional[float] = None   # time-to-first-token
    tts_latency_ms:  Optional[float] = None   # time-to-first-byte
    e2e_latency_ms:  Optional[float] = None   # STT-final → first audio byte

    # Providers
    stt_provider:    str = "deepgram"
    llm_provider:    str = "gemini"
    tts_provider:    str = "cartesia"

    # Usage
    input_tokens:    Optional[int] = None
    output_tokens:   Optional[int] = None
    tts_characters:  int = 0

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------

class MetricsCollector:
    """
    Accumulates TurnMetrics objects for one call session.

    Usage (in telephony_bridge.py or test_pipeline.py):
        mc = MetricsCollector(call_sid="CA123", room_name="my-room")

        # wire into pipeline
        async def on_metrics(m: dict) -> None:
            mc.record_turn(TurnMetrics(**m))

        pipeline.on_turn_metrics = on_metrics

        # at call end
        mc.summary()
    """

    def __init__(
        self,
        *,
        call_sid: str = "",
        room_name: str = "",
        jsonl_path: Path | str = _JSONL_PATH,
    ) -> None:
        self._call_sid  = call_sid
        self._room_name = room_name
        self._jsonl_path = Path(jsonl_path)
        self._turns: list[TurnMetrics] = []
        self._turn_counter = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_turn(self, metrics: TurnMetrics) -> None:
        """Persist one turn: append to JSONL + print sidebar line."""
        self._turn_counter += 1
        metrics.turn      = self._turn_counter
        metrics.call_sid  = metrics.call_sid  or self._call_sid
        metrics.room_name = metrics.room_name or self._room_name
        metrics.timestamp = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.%f"
        )[:-3] + "Z"

        _safe_print(f"[Observability] Recording turn {self._turn_counter}...")

        self._turns.append(metrics)
        self._write_jsonl(metrics)

        if self._turn_counter == 1:
            _safe_print(f"[Observability] Logging to: {self._jsonl_path.absolute()}")

        self._print_sidebar(metrics)

    def summary(self) -> None:
        """Print a human-readable call summary to stdout."""
        if not self._turns:
            _safe_print(f"\n{_DIM}  [Observability] No turns recorded.{_RESET}\n")
            return

        turns = self._turns
        n = len(turns)

        def _avg(vals):
            v = [x for x in vals if x is not None]
            return sum(v) / len(v) if v else None

        def _fmt(v):
            return f"{v:.0f} ms" if v is not None else "—"

        avg_e2e  = _avg(t.e2e_latency_ms  for t in turns)
        avg_llm  = _avg(t.llm_latency_ms  for t in turns)
        avg_tts  = _avg(t.tts_latency_ms  for t in turns)
        avg_stt  = _avg(t.stt_latency_ms  for t in turns)
        tot_in   = sum(t.input_tokens  or 0 for t in turns)
        tot_out  = sum(t.output_tokens or 0 for t in turns)
        tot_chars = sum(t.tts_characters  for t in turns)

        llm_p = turns[-1].llm_provider
        stt_p = turns[-1].stt_provider
        tts_p = turns[-1].tts_provider

        lines = [
            "",
            f"{_BOLD}  ── Call Summary ({'─' * 36}){_RESET}",
            f"  Turns           : {n}",
            f"  Call SID        : {self._call_sid or '(local)'}",
            f"  STT provider    : {stt_p}",
            f"  LLM provider    : {llm_p}",
            f"  TTS provider    : {tts_p}",
            f"  Avg E2E latency : {_fmt(avg_e2e)}",
            f"  Avg LLM TTFT    : {_fmt(avg_llm)}",
            f"  Avg TTS TTFB    : {_fmt(avg_tts)}",
            f"  Avg STT latency : {_fmt(avg_stt)}",
            f"  Total tokens    : {tot_in} in / {tot_out} out",
            f"  TTS characters  : {tot_chars:,}",
            f"  Metrics log     : {self._jsonl_path}",
            f"  {'─' * 46}",
            "",
        ]
        _safe_print("\n".join(lines))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write_jsonl(self, metrics: TurnMetrics) -> None:
        try:
            with self._jsonl_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(metrics.to_dict()) + "\n")
        except Exception as exc:
            logger.warning("MetricsCollector: could not write JSONL — %s", exc)

    @staticmethod
    def _print_sidebar(m: TurnMetrics) -> None:
        # Latency targets per stage (ms).  ✓ = at or below target, ! = over.
        _TARGETS = {"stt": 300, "llm": 400, "tts": 200, "e2e": 840}

        def _ms(label: str, v: float | None) -> str:
            if v is None:
                return ""
            marker = "✓" if v <= _TARGETS.get(label, 9999) else "!"
            return f"{label.upper()}:{v:.0f}ms{marker}"

        latency_parts = [
            _ms("stt", m.stt_latency_ms),
            _ms("llm", m.llm_latency_ms),
            _ms("tts", m.tts_latency_ms),
            _ms("e2e", m.e2e_latency_ms),
        ]
        latency_str = " | ".join(p for p in latency_parts if p)

        providers = f"{m.stt_provider}/{m.llm_provider}/{m.tts_provider}"
        tokens    = ""
        if m.input_tokens is not None and m.output_tokens is not None:
            tokens = f"  tok={m.input_tokens}↑{m.output_tokens}↓"

        # Header line: turn number + providers
        header = (
            f"{_CYAN}  [turn {m.turn:02d}]{_RESET}"
            f"  via={providers}"
            f"{tokens}"
        )
        _safe_print(header)

        # Latency line (only when at least one measurement is available)
        if latency_str:
            _safe_print(f"  {_DIM}[LATENCY]{_RESET}  {latency_str}")


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _safe_print(text: str) -> None:
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode("ascii"), flush=True)
