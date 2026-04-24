# Voice AI Platform — Project Context

## Architecture
Multi-agent voice pipeline: Audio → STT → LLM → TTS → Audio

## CRITICAL RULES
- ALWAYS fetch docs via Firecrawl MCP before implementing any integration
- ALWAYS use WebSocket streaming (never blocking/REST for audio)
- Audio format: PCM/WAV 16kHz for Sarvam, follow each provider's spec
- All services must be async Python
- Use Sarvam for Hindi/Hinglish, Deepgram otherwise

## Doc Registry (fetch ONLY from these)
- LiveKit: https://docs.livekit.io/agents/
- Deepgram: https://developers.deepgram.com/docs/
- Sarvam: https://docs.sarvam.ai/api-reference-docs/
- Cartesia: https://docs.cartesia.ai/
- Gemini: https://ai.google.dev/
- OpenAI: https://platform.openai.com/docs
- Piopiy: http://doc.piopiy.com/piopiy/docs/

## Provider Priority
- STT: Deepgram (primary) → Sarvam (Hindi/Hinglish)
- TTS: Cartesia (primary) → Sarvam (Indian) → OpenAI (fallback)
- LLM: Gemini (primary) → GPT-4o-mini (fallback)

## File Structure
agent.py / stt_service.py / tts_service.py / llm_router.py / 
pipeline.py / interrupt_handler.py / telephony_bridge.py / config_manager.py