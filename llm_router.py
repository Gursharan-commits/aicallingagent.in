"""
LLM abstraction layer for the voice pipeline.

Providers:
  GeminiLLM  — streaming via google-genai SDK (primary)
  OpenAILLM  — streaming via openai SDK (fallback)
  LLMRouter  — Gemini primary, OpenAI on error, shared conversation history

Voice-specific design choices:
  • Responses are capped at 2 sentences / ~60 tokens by the system prompt.
  • Markdown, bullet points, and lists are forbidden in the system prompt
    because TTS reads punctuation literally.
  • Conversation history is managed here so both providers share the same
    rolling context window.
"""
from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from typing import AsyncGenerator

from google import genai
from google.genai import types as genai_types
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Voice-optimised default system prompt
# ---------------------------------------------------------------------------

_DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful, friendly voice assistant on a phone call. "
    "Keep every response to ONE or TWO short sentences — never more. "
    "Do NOT use markdown, bullet points, numbered lists, headers, or emojis. "
    "Do NOT use asterisks, parentheses for emphasis, or any special symbols. "
    "Speak naturally, as if talking to a person on the phone. "
    "If you don't know something, say so briefly and offer to help another way."
)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Message:
    """A single conversation turn."""
    role: str    # "user" | "assistant" | "system"
    content: str


@dataclass
class LLMConfig:
    """Generation parameters shared across providers."""
    system_prompt: str = _DEFAULT_SYSTEM_PROMPT
    max_tokens: int = 80        # ~2 short sentences; voice output stays snappy
    temperature: float = 0.7
    max_history: int = 20       # number of message objects (not turns) to keep
    provider: str = "gemini"    # "gemini" | "openai" — controls which client is used


# ---------------------------------------------------------------------------
# Conversation history manager
# ---------------------------------------------------------------------------

class ConversationHistory:
    """
    Rolling window of conversation messages.

    Stores plain Message objects. Provider-specific conversion happens in
    each LLM implementation so history remains provider-agnostic.
    """

    def __init__(self, max_messages: int = 20) -> None:
        self._messages: deque[Message] = deque(maxlen=max_messages)

    def add_user(self, text: str) -> None:
        self._messages.append(Message(role="user", content=text))

    def add_assistant(self, text: str) -> None:
        self._messages.append(Message(role="assistant", content=text))

    def messages(self) -> list[Message]:
        return list(self._messages)

    def clear(self) -> None:
        self._messages.clear()

    def pop_last_user(self) -> None:
        """Remove the most recent user message if it has no assistant reply yet.
        Called after a cancelled LLM turn to keep role alternation consistent."""
        if self._messages and self._messages[-1].role == "user":
            self._messages.pop()

    def __len__(self) -> int:
        return len(self._messages)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class BaseLLM(ABC):
    """Common streaming interface for all LLM providers."""

    @abstractmethod
    async def generate(
        self,
        messages: list[Message],
        config: LLMConfig,
    ) -> AsyncGenerator[str, None]:
        """
        Async generator that yields text chunks as they are produced.
        `messages` is the full conversation including the latest user turn.
        System prompt is taken from config.system_prompt.
        """
        yield ""  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------

class GeminiLLM(BaseLLM):
    """
    Streaming LLM via Google Gemini (google-genai SDK).

    History format expected by Gemini:
      contents = [
        {"role": "user",  "parts": [{"text": "..."}]},
        {"role": "model", "parts": [{"text": "..."}]},
        ...
      ]
    Note: Gemini uses "model" where OpenAI uses "assistant".

    System prompt is passed via GenerateContentConfig.system_instruction,
    NOT as a conversation turn.

    Thinking is disabled (thinking_level="none") for minimal voice latency.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "gemini-2.0-flash",
    ) -> None:
        # Prefer GEMINI_API_KEY; fall back to GOOGLE_API_KEY for legacy envs.
        self._api_key = (
            api_key
            or os.environ.get("GEMINI_API_KEY")
            or os.environ["GOOGLE_API_KEY"]
        )
        self._model = model
        self._client = genai.Client(api_key=self._api_key)

    @staticmethod
    def _to_gemini_contents(messages: list[Message]) -> list[dict]:
        """Convert Message list to Gemini contents format, skipping system messages."""
        contents = []
        for msg in messages:
            if msg.role == "system":
                continue  # system prompt goes in GenerateContentConfig
            gemini_role = "model" if msg.role == "assistant" else "user"
            contents.append({
                "role": gemini_role,
                "parts": [{"text": msg.content}],
            })
        return contents

    async def generate(
        self,
        messages: list[Message],
        config: LLMConfig,
    ) -> AsyncGenerator[str, None]:
        contents = self._to_gemini_contents(messages)
        if not contents:
            logger.warning("GeminiLLM: no contents to generate from")
            return

        gen_config = genai_types.GenerateContentConfig(
            system_instruction=config.system_prompt,
            temperature=config.temperature,
            max_output_tokens=config.max_tokens,
            thinking_config=genai_types.ThinkingConfig(
                thinking_budget=0,  # disable thinking for voice latency
            ),
        )

        try:
            # generate_content_stream is a coroutine that returns an AsyncIterator,
            # so it must be awaited before iterating.
            stream = await self._client.aio.models.generate_content_stream(
                model=self._model,
                contents=contents,
                config=gen_config,
            )
            async for chunk in stream:
                text = chunk.text
                if text:
                    yield text
        except Exception as exc:
            logger.error("GeminiLLM generation error: %s", exc)
            raise


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

class OpenAILLM(BaseLLM):
    """
    Streaming LLM via OpenAI Chat Completions (AsyncOpenAI).

    History format:
      messages = [
        {"role": "system",    "content": "..."},  # prepended from config
        {"role": "user",      "content": "..."},
        {"role": "assistant", "content": "..."},
        ...
      ]

    Delta text is in chunk.choices[0].delta.content (can be None — guarded).
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
    ) -> None:
        self._api_key = api_key or os.environ["OPENAI_API_KEY"]
        self._model = model
        self._client = AsyncOpenAI(api_key=self._api_key)

    @staticmethod
    def _to_openai_messages(
        messages: list[Message],
        system_prompt: str,
    ) -> list[dict]:
        """Build OpenAI message list with system prompt prepended."""
        result: list[dict] = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            if msg.role == "system":
                continue  # system prompt already prepended above
            result.append({"role": msg.role, "content": msg.content})
        return result

    async def generate(
        self,
        messages: list[Message],
        config: LLMConfig,
    ) -> AsyncGenerator[str, None]:
        oai_messages = self._to_openai_messages(messages, config.system_prompt)

        try:
            stream = await self._client.chat.completions.create(
                model=self._model,
                messages=oai_messages,  # type: ignore[arg-type]
                stream=True,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
            )
            async for chunk in stream:
                content = chunk.choices[0].delta.content
                if content:
                    yield content
        except Exception as exc:
            logger.error("OpenAILLM generation error: %s", exc)
            raise


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

class LLMRouter:
    """
    Routes LLM requests to Gemini (primary) or OpenAI (fallback).

    Maintains a shared ConversationHistory so both providers see the same
    context. The caller drives the history by calling add_user_turn() before
    generate() and add_assistant_turn() after collecting the full response.

    Typical call pattern:
        router = LLMRouter()
        router.history.add_user(user_text)
        full_response = ""
        async for chunk in router.generate():
            full_response += chunk
            send_to_tts(chunk)
        router.history.add_assistant(full_response)
    """

    def __init__(
        self,
        *,
        config: LLMConfig | None = None,
        gemini_kwargs: dict | None = None,
        openai_kwargs: dict | None = None,
    ) -> None:
        self._config = config or LLMConfig()
        provider = self._config.provider

        # Only instantiate the client(s) actually needed.
        # This prevents the Gemini SDK from touching GOOGLE_API_KEY / GEMINI_API_KEY
        # env-var detection when the operator has chosen OpenAI as the primary.
        self._gemini: GeminiLLM | None = (
            GeminiLLM(**(gemini_kwargs or {})) if provider == "gemini" else None
        )
        self._openai: OpenAILLM | None = (
            OpenAILLM(**(openai_kwargs or {})) if provider in ("gemini", "openai") else None
        )
        self.history = ConversationHistory(max_messages=self._config.max_history)
        self.last_provider: str = provider   # updated after every generate() call

        # Warn if the system prompt is unusually large — long prompts raise TTFT.
        # ~4 chars per token is a conservative estimate; 200 tokens ≈ 800 chars.
        _prompt_chars = len(self._config.system_prompt)
        if _prompt_chars > 800:
            logger.warning(
                "LLMRouter: system_prompt is %d chars (~%d tokens) — "
                "prompts >200 tokens add latency; consider shortening.",
                _prompt_chars, _prompt_chars // 4,
            )
        logger.info(
            "LLMRouter initialised (provider=%s, model=%s, max_tokens=%d, "
            "temperature=%.2f, system_prompt=%d chars)",
            provider,
            getattr(self._gemini, "_model", None) or getattr(self._openai, "_model", None),
            self._config.max_tokens,
            self._config.temperature,
            _prompt_chars,
        )

    @property
    def config(self) -> LLMConfig:
        return self._config

    @config.setter
    def config(self, value: LLMConfig) -> None:
        self._config = value
        self.history = ConversationHistory(max_messages=value.max_history)

    async def generate(
        self,
        *,
        config: LLMConfig | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Generate a streamed response from the current conversation history.

        Routing logic (controlled by config.provider / LLMConfig.provider):
          "openai"  → OpenAI directly, no Gemini attempted.
          "gemini"  → Gemini primary; falls back to OpenAI on any error.

        The caller is responsible for calling history.add_assistant() with
        the accumulated full response after iteration completes.
        """
        cfg = config or self._config
        messages = self.history.messages()

        if not messages or messages[-1].role != "user":
            logger.warning("LLMRouter.generate() called without a pending user turn")
            return

        # ── OpenAI primary (no Gemini involved) ───────────────────────────
        if cfg.provider == "openai":
            if self._openai is None:
                logger.error("LLMRouter: OpenAI not initialised (provider mismatch)")
                return
            self.last_provider = "openai"
            try:
                async for chunk in self._openai.generate(messages, cfg):
                    yield chunk
            except Exception as exc:
                logger.error("LLMRouter: OpenAI failed — %s", exc)
            return

        # ── Gemini primary with OpenAI fallback ───────────────────────────
        if self._gemini is None:
            logger.error("LLMRouter: Gemini not initialised (provider mismatch)")
            return

        self.last_provider = "gemini"
        try:
            async for chunk in self._gemini.generate(messages, cfg):
                yield chunk
            return
        except Exception as exc:
            logger.warning(
                "LLMRouter: Gemini failed ('%s') — falling back to OpenAI", exc
            )

        if self._openai is None:
            logger.error("LLMRouter: OpenAI fallback not available")
            return

        self.last_provider = "openai"
        try:
            async for chunk in self._openai.generate(messages, cfg):
                yield chunk
        except Exception as exc:
            logger.error("LLMRouter: OpenAI fallback also failed — %s", exc)

    async def chat(
        self,
        user_text: str,
        *,
        config: LLMConfig | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Convenience wrapper: adds the user turn, streams the response, and
        automatically appends the assistant turn to history.

        Usage:
            async for chunk in router.chat("Hello"):
                print(chunk, end="", flush=True)
        """
        self.history.add_user(user_text)
        full_response: list[str] = []

        async for chunk in self.generate(config=config):
            full_response.append(chunk)
            yield chunk

        if full_response:
            self.history.add_assistant("".join(full_response))
