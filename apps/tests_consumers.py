import json
import pytest
from channels.testing import WebsocketCommunicator
from backend.asgi import application


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_websocket_connect_and_receive():
    """Test that a frontend client can connect to a call room."""
    communicator = WebsocketCommunicator(application, "/ws/calls/test_call_ws/")
    connected, subprotocol = await communicator.connect()
    assert connected is True
    await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_websocket_human_takeover_event():
    """Test that sending a human_takeover action is handled without error."""
    communicator = WebsocketCommunicator(application, "/ws/calls/test_call_ws/")
    await communicator.connect()

    # Drain the initial connection_ready handshake sent by the consumer
    initial = await communicator.receive_json_from(timeout=3)
    assert initial["type"] == "connection_ready"

    # Send a human takeover command from the frontend
    await communicator.send_json_to({"action": "human_takeover"})

    # Should receive the echoed control event
    response = await communicator.receive_json_from(timeout=3)
    assert response["type"] == "control"
    assert response["action"] == "HUMAN_TAKEOVER"

    await communicator.disconnect()
