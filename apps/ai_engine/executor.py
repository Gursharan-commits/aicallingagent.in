"""
GraphExecutor — dynamic AI pipeline engine.

Parses the graph_json stored in AIConfig and wires real provider integrations
instead of stubs. Provider selection is driven entirely by the DB config loaded
at call-start, so changing providers requires no code deployment.

Node types:
    STT     — Deepgram / Sarvam speech-to-text
    LLM     — Gemini / OpenAI language model
    TTS     — Cartesia / Sarvam / OpenAI text-to-speech
    RAG     — Vector DB retrieval (context injection)
    LOGIC   — Business-logic gate / variable setter
    API_TOOL — Generic REST API executor (admin-configured)

Compliance:
    AIConfig.ai_disclosure_enabled → prepends disclosure text to first agent utterance.
"""

import asyncio
import logging
import re
import time
from string import Formatter
from typing import Any

import aiohttp
from channels.layers import get_channel_layer

from pipeline import VoicePipeline, PipelineConfig
from config_manager import (
    LLMConfig,
    STTConfig,
    TTSConfig,
    STTSettings,
    TTSSettings,
    LLMSettings,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Shared graph context
# ─────────────────────────────────────────────────────────────────────────────

class GraphContext:
    """Shared mutable state for a single live call."""

    def __init__(self, call_id: str, compliance_prefix: str = "") -> None:
        self.call_id = call_id
        self.variables: dict[str, Any] = {}
        self.history: list[dict[str, str]] = []
        self.active = True
        self.audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.transcript_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.tts_audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        # Compliance: prepend disclosure on the first bot utterance only.
        self._disclosure_prefix = compliance_prefix
        self._disclosure_sent = False

    def get_disclosure_prefix(self) -> str:
        """Return disclosure text on first call; empty string thereafter."""
        if self._disclosure_prefix and not self._disclosure_sent:
            self._disclosure_sent = True
            return self._disclosure_prefix + " "
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# Base node
# ─────────────────────────────────────────────────────────────────────────────

class BaseNode:
    def __init__(self, node_id: str, config: dict[str, Any]) -> None:
        self.id = node_id
        self.config = config
        self.out_edges: list["BaseNode"] = []
        self.channel_layer = get_channel_layer()

    def add_edge(self, node: "BaseNode") -> None:
        self.out_edges.append(node)

    async def process(self, context: GraphContext, payload: Any = None) -> None:
        raise NotImplementedError

    async def _broadcast(self, context: GraphContext, role: str, text: str) -> None:
        """Send a transcript event to the WebSocket group via Redis."""
        if self.channel_layer:
            await self.channel_layer.group_send(
                f"call_{context.call_id}",
                {"type": "transcript_stream", "role": role, "text": text},
            )

    async def _trigger_downstream(
        self, context: GraphContext, payload: Any
    ) -> None:
        for node in self.out_edges:
            asyncio.create_task(node.process(context, payload=payload))


# ─────────────────────────────────────────────────────────────────────────────
# STT Node — Deepgram / Sarvam
# ─────────────────────────────────────────────────────────────────────────────

class STTNode(BaseNode):
    """
    Listens to context.audio_queue.
    Routes to Deepgram (default) or Sarvam (if language hint is Hindi/Hinglish).
    Uses the real stt_service.STTRouter integration via pipeline.
    """

    async def process(self, context: GraphContext, payload: Any = None) -> None:
        from stt_service import STTRouter, STTConfig as SvcSTTConfig

        provider = self.config.get("provider", "deepgram")
        language = self.config.get("language", "en-IN")
        logger.info("[%s] STT node started — provider=%s", self.id, provider)

        stt_config = SvcSTTConfig(provider=provider, language=language)
        stt = STTRouter(stt_config)

        try:
            await stt.connect()
            while context.active:
                chunk = await context.audio_queue.get()
                if chunk is None:
                    break
                await stt.send_audio(chunk)

                # Poll for results
                result = await stt.get_transcript()
                if result and result.get("is_final"):
                    text = result["text"]
                    context.history.append({"role": "user", "content": text})
                    await self._broadcast(context, "user", text)
                    await self._trigger_downstream(context, text)

        except asyncio.CancelledError:
            logger.info("[%s] STT node cancelled", self.id)
        except Exception as exc:
            logger.exception("[%s] STT node error: %s", self.id, exc)
        finally:
            try:
                await stt.disconnect()
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# LLM Node — Gemini / OpenAI
# ─────────────────────────────────────────────────────────────────────────────

class LLMNode(BaseNode):
    """
    Generates a streaming response from the configured LLM provider.
    Injects compliance disclosure prefix into the first utterance.
    Checks for [TOOL:tool_name] patterns in the response to trigger API tools.
    """

    async def process(self, context: GraphContext, payload: Any = None) -> None:
        if not payload:
            return

        from llm_router import LLMRouter

        user_text: str = str(payload)
        provider = self.config.get("provider", "gemini")
        model = self.config.get("model", "")
        system_prompt = self.config.get("system_prompt", "You are a helpful voice AI assistant.")
        max_tokens = int(self.config.get("max_tokens", 256))
        temperature = float(self.config.get("temperature", 0.7))

        # Prepend any RAG context injected by upstream RAG nodes
        rag_ctx = context.variables.get("rag_context", "")
        if rag_ctx:
            system_prompt = f"{system_prompt}\n\nRelevant context:\n{rag_ctx}"

        llm = LLMRouter()
        llm_config = LLMConfig(
            provider=provider,
            model=model or None,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        # Compliance disclosure prefix for first turn
        disclosure = context.get_disclosure_prefix()
        buffer = disclosure  # seed buffer with disclosure if present
        full_response: list[str] = []

        logger.info("[%s] LLM generating — provider=%s user=%r", self.id, provider, user_text[:60])

        try:
            async for chunk in llm.chat(user_text, config=llm_config):
                if not context.active:
                    break
                full_response.append(chunk)
                buffer += chunk
                await self._broadcast(context, "bot", chunk)
                await self._trigger_downstream(context, buffer if self._should_flush(buffer) else None)
                if self._should_flush(buffer):
                    buffer = ""

            # Flush remainder
            if buffer.strip():
                await self._trigger_downstream(context, buffer.strip())

            complete_text = "".join(full_response)
            context.history.append({"role": "assistant", "content": complete_text})

            # Check for tool call patterns: [TOOL:tool_name key=value ...]
            await self._dispatch_tool_calls(context, complete_text)

        except asyncio.CancelledError:
            logger.info("[%s] LLM node cancelled", self.id)
        except Exception as exc:
            logger.exception("[%s] LLM node error: %s", self.id, exc)

    @staticmethod
    def _should_flush(text: str) -> bool:
        stripped = text.rstrip()
        if not stripped:
            return False
        if stripped[-1] in ".!?":
            return True
        if stripped[-1] == "," and len(stripped.split()) >= 6:
            return True
        if len(stripped.split()) >= 15:
            return True
        return False

    async def _dispatch_tool_calls(
        self, context: GraphContext, text: str
    ) -> None:
        """
        Detect [TOOL:tool_name param=value] markers in the LLM output
        and fire the matching API_TOOL node.
        """
        pattern = re.compile(r"\[TOOL:(\w+)([^\]]*)\]")
        for match in pattern.finditer(text):
            tool_name = match.group(1)
            params_raw = match.group(2).strip()
            # Parse "key=value" pairs
            params: dict[str, str] = {}
            for pair in params_raw.split():
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    params[k] = v
            context.variables.update(params)
            # Find the APIToolNode with this name among out_edges
            for node in self.out_edges:
                if isinstance(node, APIToolNode) and node.config.get("tool_name") == tool_name:
                    asyncio.create_task(node.process(context, payload=tool_name))
                    break


# ─────────────────────────────────────────────────────────────────────────────
# TTS Node — Cartesia / Sarvam / OpenAI
# ─────────────────────────────────────────────────────────────────────────────

class TTSNode(BaseNode):
    """
    Synthesises audio from text segments and pushes bytes to
    context.tts_audio_queue for the telephony bridge to emit.
    """

    async def process(self, context: GraphContext, payload: Any = None) -> None:
        if not payload:
            return

        from tts_service import TTSRouter

        text: str = str(payload)
        provider = self.config.get("provider", "cartesia")
        voice_id = self.config.get("voice_id", "")
        language = self.config.get("language", "en")

        tts = TTSRouter()
        tts_config = type("TTSCfg", (), {
            "provider": provider,
            "voice_id": voice_id,
            "language": language,
        })()

        logger.debug("[%s] TTS synthesising — provider=%s text=%r", self.id, provider, text[:40])

        try:
            async for audio_chunk in tts.synthesize_stream(text, tts_config):
                if not context.active:
                    break
                await context.tts_audio_queue.put(audio_chunk)
        except asyncio.CancelledError:
            logger.info("[%s] TTS node cancelled", self.id)
        except Exception as exc:
            logger.exception("[%s] TTS node error: %s", self.id, exc)


# ─────────────────────────────────────────────────────────────────────────────
# RAG Node
# ─────────────────────────────────────────────────────────────────────────────

class RAGNode(BaseNode):
    """Queries a vector collection and injects context into GraphContext.variables."""

    async def process(self, context: GraphContext, payload: Any = None) -> None:
        collection = self.config.get("collection", "default")
        top_k = int(self.config.get("top_k", 3))
        logger.info("[%s] RAG query — collection=%s query=%r", self.id, collection, str(payload)[:60])

        # TODO: replace with real vector DB client (e.g. Pinecone, Weaviate, pgvector)
        context.variables["rag_context"] = f"[RAG:{collection} top_k={top_k}]"

        await self._trigger_downstream(context, payload)


# ─────────────────────────────────────────────────────────────────────────────
# Logic Node
# ─────────────────────────────────────────────────────────────────────────────

class LogicNode(BaseNode):
    """Sets variables, evaluates conditions, routes flow."""

    async def process(self, context: GraphContext, payload: Any = None) -> None:
        action = self.config.get("action", "passthrough")
        logger.info("[%s] Logic action=%s", self.id, action)

        if action == "set_variable":
            key = self.config.get("key")
            value = self.config.get("value")
            if key:
                context.variables[key] = value

        await self._trigger_downstream(context, payload)


# ─────────────────────────────────────────────────────────────────────────────
# API Tool Node — generic REST executor (TASK 2.5)
# ─────────────────────────────────────────────────────────────────────────────

class APIToolNode(BaseNode):
    """
    Executes a REST API call defined in the AgentTool DB record.

    Config (from graph_json node):
        tool_name   — matches AgentTool.name to look up the tool definition
        ai_config_id — which AIConfig this tool belongs to

    Variable substitution:
        {variable} placeholders in url_template, headers, and body_template
        are resolved from context.variables at call time.
    """

    async def process(self, context: GraphContext, payload: Any = None) -> None:
        tool_name: str = self.config.get("tool_name", "")
        ai_config_id: int | None = self.config.get("ai_config_id")

        if not tool_name or not ai_config_id:
            logger.warning("[%s] APIToolNode missing tool_name or ai_config_id", self.id)
            return

        # Load tool definition from DB (sync → async via sync_to_async)
        tool = await self._load_tool(tool_name, ai_config_id)
        if not tool:
            logger.warning("[%s] AgentTool %r not found for config %s", self.id, tool_name, ai_config_id)
            await self._broadcast(context, "system", f"[Tool {tool_name}: not found]")
            return

        # Resolve {variable} placeholders from context
        vars_: dict[str, str] = {k: str(v) for k, v in context.variables.items()}
        url = self._render(tool.url_template, vars_)
        headers = {k: self._render(str(v), vars_) for k, v in tool.headers.items()}
        body = {k: self._render(str(v), vars_) for k, v in tool.body_template.items()}

        logger.info("[%s] API tool %r → %s %s", self.id, tool_name, tool.method, url)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method=tool.method,
                    url=url,
                    headers=headers,
                    json=body if tool.method not in ("GET", "DELETE") else None,
                    params=body if tool.method in ("GET", "DELETE") else None,
                    timeout=aiohttp.ClientTimeout(total=tool.timeout_sec),
                ) as resp:
                    result_text = await resp.text()
                    status = resp.status

            logger.info("[%s] Tool %r → HTTP %s", self.id, tool_name, status)
            context.variables[f"tool_result_{tool_name}"] = result_text
            await self._broadcast(context, "system", f"[Tool {tool_name}: HTTP {status}]")
            await self._trigger_downstream(context, result_text)

        except aiohttp.ClientError as exc:
            logger.error("[%s] Tool %r HTTP error: %s", self.id, tool_name, exc)
            context.variables[f"tool_result_{tool_name}"] = f"error: {exc}"
            await self._broadcast(context, "system", f"[Tool {tool_name}: request failed]")
        except asyncio.TimeoutError:
            logger.error("[%s] Tool %r timed out after %ss", self.id, tool_name, tool.timeout_sec)
            context.variables[f"tool_result_{tool_name}"] = "error: timeout"

    @staticmethod
    def _render(template: str, variables: dict[str, str]) -> str:
        """Safe string.format_map — leaves unknown keys intact."""
        class _SafeDict(dict):
            def __missing__(self, key: str) -> str:
                return "{" + key + "}"
        return template.format_map(_SafeDict(variables))

    @staticmethod
    async def _load_tool(tool_name: str, ai_config_id: int):
        from asgiref.sync import sync_to_async
        from apps.ai_engine.models import AgentTool

        @sync_to_async
        def _fetch():
            return AgentTool.objects.filter(
                name=tool_name,
                ai_config_id=ai_config_id,
                is_active=True,
            ).first()

        return await _fetch()


# ─────────────────────────────────────────────────────────────────────────────
# GraphExecutor
# ─────────────────────────────────────────────────────────────────────────────

class GraphExecutor:
    """
    Parses graph_json, instantiates nodes, wires edges, and runs the pipeline.

    Compliance: accepts a `compliance_prefix` string that is prepended to the
    first agent utterance when ai_disclosure_enabled is True.
    """

    NODE_REGISTRY: dict[str, type[BaseNode]] = {
        "STT": STTNode,
        "LLM": LLMNode,
        "TTS": TTSNode,
        "LOGIC": LogicNode,
        "RAG": RAGNode,
        "API_TOOL": APIToolNode,
    }

    def __init__(
        self,
        graph_json: dict[str, Any],
        call_id: str,
        compliance_prefix: str = "",
        ai_config_id: int | None = None,
    ) -> None:
        self.graph_json = graph_json
        self.call_id = call_id
        self.ai_config_id = ai_config_id
        self.context = GraphContext(call_id=call_id, compliance_prefix=compliance_prefix)
        self.nodes: dict[str, BaseNode] = {}
        self.entry_nodes: list[BaseNode] = []
        self._build_graph()

    def _build_graph(self) -> None:
        for node_data in self.graph_json.get("nodes", []):
            node_type = node_data.get("type", "").upper()
            node_id = node_data.get("id")
            NodeClass = self.NODE_REGISTRY.get(node_type)
            if not NodeClass:
                raise ValueError(f"Unknown node type: {node_type!r}")

            cfg = dict(node_data.get("config", node_data))
            # Inject ai_config_id so API_TOOL nodes can look up their tool defs.
            if node_type == "API_TOOL" and self.ai_config_id:
                cfg.setdefault("ai_config_id", self.ai_config_id)

            self.nodes[node_id] = NodeClass(node_id=node_id, config=cfg)
            if node_type == "STT":
                self.entry_nodes.append(self.nodes[node_id])

        for edge in self.graph_json.get("edges", []):
            src = self.nodes.get(edge.get("from") or edge.get("source"))
            tgt = self.nodes.get(edge.get("to") or edge.get("target"))
            if src and tgt:
                src.add_edge(tgt)

    async def start(self) -> list[asyncio.Task]:
        logger.info("GraphExecutor starting — call_id=%s", self.call_id)
        self.context.active = True
        return [
            asyncio.create_task(node.process(self.context))
            for node in self.entry_nodes
        ]

    async def push_audio(self, chunk: bytes) -> None:
        if self.context.active:
            await self.context.audio_queue.put(chunk)

    async def stop(self) -> None:
        self.context.active = False
        await self.context.audio_queue.put(None)
        logger.info("GraphExecutor stopped — call_id=%s", self.call_id)
