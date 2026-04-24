import asyncio
import logging
from executor import GraphExecutor

# Configure logging to see the node execution steps
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# Dummy Graph simulating a standard voice bot pipeline
DUMMY_GRAPH = {
    "nodes": [
        {"id": "stt_1", "type": "STT", "config": {"provider": "deepgram"}},
        {"id": "rag_1", "type": "RAG", "config": {"collection": "product_knowledge"}},
        {"id": "llm_1", "type": "LLM", "config": {"provider": "gemini"}},
        {"id": "tts_1", "type": "TTS", "config": {"provider": "cartesia"}}
    ],
    "edges": [
        {"from": "stt_1", "to": "rag_1"},
        {"from": "rag_1", "to": "llm_1"},
        {"from": "llm_1", "to": "tts_1"}
    ]
}

async def run_test():
    print("=== INITIALIZING GRAPH EXECUTOR ===")
    executor = GraphExecutor(graph_json=DUMMY_GRAPH, call_id="test_call_001")
    
    print("\n=== STARTING ENGINE ===")
    # Starts entry nodes (STT node)
    tasks = await executor.start()
    
    print("\n=== PUSHING SIMULATED AUDIO ===")
    # Simulate LiveKit sending a PCM audio chunk
    await executor.push_audio(b"simulated_pcm_audio_bytes")
    
    # Give the async events time to propagate through the nodes
    await asyncio.sleep(1)
    
    print("\n=== STOPPING ENGINE ===")
    await executor.stop()
    
    # Wait for STT listening loop to cleanly exit
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
        
    print("\n=== TEST COMPLETE ===")

if __name__ == "__main__":
    asyncio.run(run_test())
