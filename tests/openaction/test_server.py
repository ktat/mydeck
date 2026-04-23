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


@pytest.mark.asyncio
async def test_server_rejects_non_json_registration():
    server = OpenActionServer(host="127.0.0.1", port=0)
    await server.start()
    try:
        async with websockets.connect(f"ws://127.0.0.1:{server.port}") as ws:
            await ws.send("not json at all")
            # Server should close the connection
            try:
                await asyncio.wait_for(ws.recv(), timeout=1.0)
            except websockets.ConnectionClosed:
                pass
            except asyncio.TimeoutError:
                pytest.fail("server did not close non-JSON registration")
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_server_rejects_wrong_event_registration():
    server = OpenActionServer(host="127.0.0.1", port=0)
    await server.start()
    try:
        async with websockets.connect(f"ws://127.0.0.1:{server.port}") as ws:
            import json as _json
            await ws.send(_json.dumps({"event": "notRegister", "uuid": "x"}))
            try:
                await asyncio.wait_for(ws.recv(), timeout=1.0)
            except websockets.ConnectionClosed:
                pass
            except asyncio.TimeoutError:
                pytest.fail("server did not close bad registration")
    finally:
        await server.stop()
