"""
Configuration manager — Pydantic-based settings for the Voice AI Platform.

Two-layer design
────────────────
  Secrets   (.env)         → _Secrets(BaseSettings)   — API keys, URLs, tokens
  Settings  (config.yaml)  → _YamlSettings(BaseModel) — provider choices, models,
                                                         prompts, thresholds

Both are merged into a single frozen AppConfig that every module imports.

Usage
─────
    from config_manager import load_config
    cfg = load_config()          # raises ConfigError with a clear message if
                                 # any required key is missing
    print(cfg.livekit_url)
    print(cfg.llm.model)

Error format
────────────
    ConfigError: Missing CARTESIA_API_KEY — check your .env file
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Literal

import yaml
from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

_HERE = Path(__file__).parent


# ---------------------------------------------------------------------------
# Public exception
# ---------------------------------------------------------------------------

class ConfigError(RuntimeError):
    """Raised when a required value is missing or invalid."""


# ---------------------------------------------------------------------------
# Secrets — loaded from .env
# ---------------------------------------------------------------------------

class _Secrets(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="ignore",
    )

    # LiveKit
    livekit_url: str
    livekit_api_key: str
    livekit_api_secret: str

    # STT
    deepgram_api_key: str
    sarvam_api_key: str          # shared: STT (Hindi) + TTS (Indian voices)

    # TTS
    cartesia_api_key: str

    # LLM — either GEMINI_API_KEY or GOOGLE_API_KEY is accepted
    gemini_api_key: str = Field(
        validation_alias=AliasChoices("gemini_api_key", "google_api_key")
    )
    openai_api_key: str          # shared: LLM fallback + TTS fallback

    # Twilio
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_phone_number: str
    twilio_stream_url: str = ""  # public HTTPS base URL; set to your ngrok/server URL

    # Server
    host: str = "0.0.0.0"
    port: int = 8000


# ---------------------------------------------------------------------------
# Settings — loaded from config.yaml (no secrets)
# ---------------------------------------------------------------------------

class STTSettings(BaseModel):
    provider: Literal["deepgram", "sarvam"] = "deepgram"
    language: str = "en-US"
    # Deepgram-specific tuning (FIX 1 — latency optimisation)
    model: str = "nova-3"
    endpointing_ms: int = Field(default=300, ge=0, le=3000)
    interim_results: bool = True
    vad_events: bool = True
    utterance_end_ms: int = Field(default=1000, ge=100, le=5000)

    @property
    def deepgram_kwargs(self) -> dict:
        """Return kwargs that map directly onto DeepgramSTT.__init__ parameters."""
        return {
            "model": self.model,
            "language": self.language,
            "endpointing": self.endpointing_ms,
            "interim_results": self.interim_results,
            "vad_events": self.vad_events,
            "utterance_end_ms": self.utterance_end_ms,
        }


class TTSSettings(BaseModel):
    provider: Literal["cartesia", "sarvam", "openai"] = "cartesia"
    voice: str = "f786b574-daa5-4673-aa0c-cbe3e8534c02"  # Cartesia voice UUID
    speed: float = Field(default=1.0, ge=0.25, le=4.0)


class LLMSettings(BaseModel):
    provider: Literal["gemini", "openai"] = "gemini"
    model: str = "gemini-2.0-flash"
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=80, ge=10, le=4096)
    system_prompt: str = (
        "You are a helpful, friendly voice assistant on a phone call. "
        "Keep every response to ONE or TWO short sentences — never more. "
        "Do NOT use markdown, bullet points, numbered lists, headers, or emojis. "
        "Do NOT use asterisks, parentheses for emphasis, or any special symbols. "
        "Speak naturally, as if talking to a person on the phone. "
        "If you don't know something, say so briefly and offer to help another way."
    )


class PipelineSettings(BaseModel):
    interruption_enabled: bool = True
    conversation_history_length: int = Field(default=10, ge=1, le=50)


class VADSettings(BaseModel):
    silence_timeout_ms: int = Field(default=700, ge=100, le=5000)
    energy_threshold: float = Field(default=600.0, ge=0.0)


class _YamlSettings(BaseModel):
    stt: STTSettings = Field(default_factory=STTSettings)
    tts: TTSSettings = Field(default_factory=TTSSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    pipeline: PipelineSettings = Field(default_factory=PipelineSettings)
    vad: VADSettings = Field(default_factory=VADSettings)


# ---------------------------------------------------------------------------
# AppConfig — merged, frozen, single source of truth
# ---------------------------------------------------------------------------

class AppConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    # ── secrets ────────────────────────────────────────────────────────────
    livekit_url: str
    livekit_api_key: str
    livekit_api_secret: str
    deepgram_api_key: str
    sarvam_api_key: str
    cartesia_api_key: str
    gemini_api_key: str
    openai_api_key: str
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_phone_number: str
    twilio_stream_url: str
    host: str
    port: int

    # ── settings ───────────────────────────────────────────────────────────
    stt: STTSettings
    tts: TTSSettings
    llm: LLMSettings
    pipeline: PipelineSettings
    vad: VADSettings


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_config(
    env_file: str = ".env",
    yaml_file: str = "config.yaml",
) -> AppConfig:
    """
    Load, validate, and merge secrets + settings into a frozen AppConfig.

    Raises ConfigError immediately on any missing required key so the
    process fails at startup rather than mid-call.
    """
    # ── 1. Load secrets from .env ──────────────────────────────────────────
    try:
        secrets = _Secrets(_env_file=env_file)
    except PydanticValidationError as exc:
        _raise_missing(exc)

    # Expose the key under GEMINI_API_KEY so GeminiLLM can find it without
    # triggering the "both keys set" SDK warning that GOOGLE_API_KEY causes.
    os.environ.setdefault("GEMINI_API_KEY", secrets.gemini_api_key)

    # ── 2. Load settings from config.yaml (fall back to all defaults) ──────
    yaml_settings = _load_yaml(yaml_file)

    # ── 3. Merge into AppConfig ────────────────────────────────────────────
    cfg = AppConfig(
        livekit_url=secrets.livekit_url,
        livekit_api_key=secrets.livekit_api_key,
        livekit_api_secret=secrets.livekit_api_secret,
        deepgram_api_key=secrets.deepgram_api_key,
        sarvam_api_key=secrets.sarvam_api_key,
        cartesia_api_key=secrets.cartesia_api_key,
        gemini_api_key=secrets.gemini_api_key,
        openai_api_key=secrets.openai_api_key,
        twilio_account_sid=secrets.twilio_account_sid,
        twilio_auth_token=secrets.twilio_auth_token,
        twilio_phone_number=secrets.twilio_phone_number,
        twilio_stream_url=secrets.twilio_stream_url,
        host=secrets.host,
        port=secrets.port,
        stt=yaml_settings.stt,
        tts=yaml_settings.tts,
        llm=yaml_settings.llm,
        pipeline=yaml_settings.pipeline,
        vad=yaml_settings.vad,
    )

    _print_startup_banner(cfg)
    return cfg


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_yaml(path: str) -> _YamlSettings:
    """Parse config.yaml; return all-defaults _YamlSettings if file absent."""
    p = Path(path)
    if not p.exists():
        return _YamlSettings()
    with p.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    try:
        return _YamlSettings.model_validate(raw)
    except PydanticValidationError as exc:
        raise ConfigError(f"Invalid config.yaml:\n{exc}") from exc


def _raise_missing(exc: PydanticValidationError) -> None:
    """Convert a pydantic ValidationError into readable ConfigError messages."""
    lines: list[str] = []
    for err in exc.errors():
        if err["type"] in ("missing", "value_error", "string_type"):
            raw_loc = err["loc"][0] if err["loc"] else "unknown"
            env_name = str(raw_loc).upper()
            lines.append(f"  Missing {env_name} — check your .env file")
    if lines:
        raise ConfigError(
            "Configuration error — required environment variables are missing:\n"
            + "\n".join(lines)
        ) from exc
    raise ConfigError(str(exc)) from exc


def _print_startup_banner(cfg: AppConfig) -> None:
    """Print a human-readable startup summary to stdout."""
    llm_primary = f"Gemini ({cfg.llm.model})" if cfg.llm.provider == "gemini" else f"OpenAI ({cfg.llm.model})"
    llm_fallback = "OpenAI (gpt-4o-mini)" if cfg.llm.provider == "gemini" else "Gemini (gemini-1.5-flash)"
    tts_primary = f"Cartesia (sonic-3)" if cfg.tts.provider == "cartesia" else f"{cfg.tts.provider.title()}"

    lines = [
        "",
        "  Voice AI Platform — ready",
        "  " + "─" * 48,
        f"  \u2713 LiveKit connected:    {cfg.livekit_url}",
        f"  \u2713 STT: Deepgram (primary) | Sarvam (Hindi fallback)",
        f"  \u2713 TTS: {tts_primary} (primary) | Sarvam (Indian) | OpenAI (fallback)",
        f"  \u2713 TTS speed:            {cfg.tts.speed}",
        f"  \u2713 LLM: {llm_primary} (primary) | {llm_fallback} (fallback)",
        f"  \u2713 Twilio outbound ready: {cfg.twilio_phone_number}",
        f"  \u2713 Server:               http://{cfg.host}:{cfg.port}",
        "  " + "─" * 48,
        "",
    ]
    text = "\n".join(lines)
    try:
        print(text, file=sys.stdout, flush=True)
    except UnicodeEncodeError:
        # Fall back to pure ASCII for narrow-encoding terminals (e.g. Windows CP1252).
        ascii_text = text.encode("ascii", errors="replace").decode("ascii")
        print(ascii_text, file=sys.stdout, flush=True)
