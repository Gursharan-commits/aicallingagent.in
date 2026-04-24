import logging
import os

from dotenv import load_dotenv

from livekit import agents
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, room_io
from livekit.plugins import cartesia, deepgram, google, silero

load_dotenv()

logger = logging.getLogger(__name__)


class VoiceAgent(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=(
                "You are a helpful voice AI assistant. "
                "Keep responses concise and conversational. "
                "Avoid markdown, bullet points, emojis, or special symbols — "
                "speak naturally as you would in a phone conversation."
            ),
        )


server = AgentServer()


@server.rtc_session(agent_name=os.getenv("AGENT_NAME", "voice-agent"))
async def entrypoint(ctx: JobContext) -> None:
    logger.info("Agent job started for room: %s", ctx.room.name)

    session = AgentSession(
        stt=deepgram.STT(
            model="nova-2",
            language="en-US",
            api_key=os.environ["DEEPGRAM_API_KEY"],
        ),
        llm=google.LLM(
            model="gemini-2.0-flash-exp",
            api_key=os.environ["GOOGLE_API_KEY"],
        ),
        tts=cartesia.TTS(
            model="sonic-english",
            voice="79a125e8-cd45-4c13-8a67-188112f4dd22",
            api_key=os.environ["CARTESIA_API_KEY"],
        ),
        vad=silero.VAD.load(),
    )

    await session.start(
        room=ctx.room,
        agent=VoiceAgent(),
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                auto_subscribe=True,
            ),
        ),
    )

    logger.info("Session started — agent is live in room: %s", ctx.room.name)

    await session.generate_reply(
        instructions="Greet the caller warmly and ask how you can help them today."
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    agents.cli.run_app(server)
