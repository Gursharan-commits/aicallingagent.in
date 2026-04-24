import asyncio
from django.test import TestCase
from apps.ai_engine.executor import GraphExecutor

DUMMY_GRAPH = {
    "nodes": [
        {"id": "stt_1", "type": "STT", "config": {"provider": "deepgram"}},
        {"id": "llm_1", "type": "LLM", "config": {"provider": "gemini"}},
        {"id": "tts_1", "type": "TTS", "config": {"provider": "cartesia"}},
        {"id": "logic_1", "type": "LOGIC", "config": {"condition": "wait"}}
    ],
    "edges": [
        {"from": "stt_1", "to": "llm_1"},
        {"from": "llm_1", "to": "tts_1"},
        {"from": "stt_1", "to": "logic_1"}
    ]
}

class GraphExecutorTests(TestCase):
    def test_graph_parsing_and_edges(self):
        """Test that the JSON is parsed correctly and nodes are linked."""
        executor = GraphExecutor(graph_json=DUMMY_GRAPH, call_id="test_call_1")
        
        # Check node instantiation
        self.assertEqual(len(executor.nodes), 4)
        self.assertIn("stt_1", executor.nodes)
        self.assertIn("llm_1", executor.nodes)
        self.assertIn("tts_1", executor.nodes)
        self.assertIn("logic_1", executor.nodes)
        
        # Check edges
        stt_node = executor.nodes["stt_1"]
        self.assertEqual(len(stt_node.out_edges), 2)
        out_ids = [n.id for n in stt_node.out_edges]
        self.assertIn("llm_1", out_ids)
        self.assertIn("logic_1", out_ids)

        llm_node = executor.nodes["llm_1"]
        self.assertEqual(len(llm_node.out_edges), 1)
        self.assertEqual(llm_node.out_edges[0].id, "tts_1")

        tts_node = executor.nodes["tts_1"]
        self.assertEqual(len(tts_node.out_edges), 0)

    async def test_graph_audio_push(self):
        """Test the audio push queue behavior."""
        executor = GraphExecutor(graph_json=DUMMY_GRAPH, call_id="test_call_1")
        await executor.push_audio(b"fake_audio_chunk")
        
        # The context queue should have the chunk
        chunk = await asyncio.wait_for(executor.context.audio_queue.get(), timeout=1.0)
        self.assertEqual(chunk, b"fake_audio_chunk")
