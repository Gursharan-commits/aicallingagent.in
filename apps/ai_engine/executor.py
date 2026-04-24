import asyncio
import logging
from typing import Any, Dict, List, Optional
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)

class GraphContext:
    """Shared state across the execution of the graph for a single call."""
    def __init__(self, call_id: str):
        self.call_id = call_id
        self.variables: Dict[str, Any] = {}
        self.history: List[Dict[str, str]] = []  # LLM conversation history
        self.active = True
        self.audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.transcript_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()

class BaseNode:
    """Base interface for all nodes in the Graph JSON."""
    def __init__(self, node_id: str, config: Dict[str, Any]):
        self.id = node_id
        self.config = config
        self.out_edges: List['BaseNode'] = []
        self.channel_layer = get_channel_layer()

    def add_edge(self, node: 'BaseNode'):
        self.out_edges.append(node)

    async def process(self, context: GraphContext, payload: Any = None):
        """Implement node-specific processing logic."""
        raise NotImplementedError

class STTNode(BaseNode):
    """Listens to context.audio_queue and yields transcripts."""
    async def process(self, context: GraphContext, payload: Any = None):
        logger.info(f"[{self.id}] Starting STT Node (provider={self.config.get('provider')})")
        # In reality, this connects to Deepgram/Sarvam via WebSockets
        try:
            while context.active:
                chunk = await context.audio_queue.get()
                if chunk is None:
                    break
                # Dummy simulation of transcript generation
                transcript = "Simulated user speech"
                is_final = True
                await context.transcript_queue.put({"text": transcript, "is_final": is_final})
                
                # If final, trigger downstream nodes
                if is_final:
                    # Broadcast STT transcript to WebSocket via Redis
                    if self.channel_layer:
                        await self.channel_layer.group_send(
                            f"call_{context.call_id}",
                            {
                                'type': 'transcript_stream',
                                'role': 'user',
                                'text': transcript
                            }
                        )
                    
                    for node in self.out_edges:
                        asyncio.create_task(node.process(context, payload=transcript))
        except asyncio.CancelledError:
            logger.info(f"[{self.id}] STT Node Cancelled")

class LLMNode(BaseNode):
    """Takes transcript, generates response chunks, passes to TTS."""
    async def process(self, context: GraphContext, payload: Any = None):
        if not payload:
            return
            
        user_text = payload
        logger.info(f"[{self.id}] Generating LLM response for: {user_text}")
        context.history.append({"role": "user", "content": user_text})
        
        # Simulate LLM streaming chunks
        simulated_chunks = ["Hello! ", "I am your AI agent. ", "How can I help?"]
        
        for chunk in simulated_chunks:
            if not context.active:
                break
            await asyncio.sleep(0.1) # Simulate network latency
            
            # Broadcast LLM chunk to WebSocket via Redis
            if self.channel_layer:
                await self.channel_layer.group_send(
                    f"call_{context.call_id}",
                    {
                        'type': 'transcript_stream',
                        'role': 'bot',
                        'text': chunk
                    }
                )

            for node in self.out_edges:
                asyncio.create_task(node.process(context, payload=chunk))

class TTSNode(BaseNode):
    """Takes text chunks, synthesizes audio, pushes to LiveKit/Twilio."""
    async def process(self, context: GraphContext, payload: Any = None):
        if not payload:
            return
            
        text_chunk = payload
        logger.info(f"[{self.id}] Synthesizing TTS for: {text_chunk}")
        # In reality, sends text to Cartesia/OpenAI WebSocket and receives audio
        await asyncio.sleep(0.1)
        # Emit audio bytes (simulated)
        audio_bytes = b"..." 
        # (Pass audio_bytes back to the telephony bridge)

class LogicNode(BaseNode):
    """Executes arbitrary business logic or function calls."""
    async def process(self, context: GraphContext, payload: Any = None):
        action = self.config.get("action")
        logger.info(f"[{self.id}] Executing logic action: {action}")
        # Next nodes in the chain
        for node in self.out_edges:
            asyncio.create_task(node.process(context, payload=payload))

class RAGNode(BaseNode):
    """Queries Vector DB and injects context."""
    async def process(self, context: GraphContext, payload: Any = None):
        collection = self.config.get("collection")
        logger.info(f"[{self.id}] Querying RAG collection: {collection} with payload: {payload}")
        context.variables["rag_context"] = f"Context from {collection}"
        for node in self.out_edges:
            asyncio.create_task(node.process(context, payload=payload))


class GraphExecutor:
    """Parses graph_json and orchestrates the AI pipeline."""
    
    NODE_REGISTRY = {
        "STT": STTNode,
        "LLM": LLMNode,
        "TTS": TTSNode,
        "LOGIC": LogicNode,
        "RAG": RAGNode,
    }

    def __init__(self, graph_json: Dict[str, Any], call_id: str):
        self.graph_json = graph_json
        self.call_id = call_id
        self.context = GraphContext(call_id=call_id)
        self.nodes: Dict[str, BaseNode] = {}
        self.entry_nodes: List[BaseNode] = []
        
        self._build_graph()

    def _build_graph(self):
        """Instantiate nodes and connect edges."""
        # 1. Instantiate Nodes
        for node_data in self.graph_json.get("nodes", []):
            node_type = node_data.get("type")
            node_id = node_data.get("id")
            NodeClass = self.NODE_REGISTRY.get(node_type)
            if not NodeClass:
                raise ValueError(f"Unknown node type: {node_type}")
                
            self.nodes[node_id] = NodeClass(node_id=node_id, config=node_data.get("config", node_data))
            
            # Convention: STT nodes are entry points for audio streams
            if node_type == "STT":
                self.entry_nodes.append(self.nodes[node_id])

        # 2. Connect Edges
        for edge in self.graph_json.get("edges", []):
            from_node = self.nodes.get(edge.get("from"))
            to_node = self.nodes.get(edge.get("to"))
            if from_node and to_node:
                from_node.add_edge(to_node)

    async def start(self):
        """Starts the entry nodes (e.g., STT listening loop)."""
        logger.info(f"Starting GraphExecutor for call {self.call_id}")
        self.context.active = True
        tasks = []
        for node in self.entry_nodes:
            tasks.append(asyncio.create_task(node.process(self.context)))
        return tasks

    async def push_audio(self, chunk: bytes):
        """Push raw PCM audio from transport (LiveKit) to the graph."""
        if self.context.active:
            await self.context.audio_queue.put(chunk)

    async def stop(self):
        """Gracefully stop execution."""
        self.context.active = False
        await self.context.audio_queue.put(None)
        logger.info(f"Stopped GraphExecutor for call {self.call_id}")
