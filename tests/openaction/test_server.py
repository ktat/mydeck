import asyncio
import json
import pytest
import websockets

from mydeck.openaction.server import OpenActionServer


@pytest.mark.asyncio
async def test_server_accepts_registration():
    server = OpenActionServer(host="127.0.0.1", port=0)
    await server.start()
    registered = asyncio.Event()

    async def on_registered(plugin_uuid: str):
        registered.plugin_uuid = plugin_uuid
        registered.set()

    server.on_registered = on_registered

    async with websockets.connect(f"ws://127.0.0.1:{server.port}") as ws:
        await ws.send(json.dumps({"event": "registerPlugin", "uuid": "com.example.mvp"}))
        await asyncio.wait_for(registered.wait(), timeout=1.0)
        assert registered.plugin_uuid == "com.example.mvp"

    await server.stop()
