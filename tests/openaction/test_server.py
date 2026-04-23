import asyncio
import json
import os
import sys
from pathlib import Path

import pytest
import websockets

from mydeck.openaction.manifest import PluginManifest
from mydeck.openaction.server import KeyContext, OpenActionServer


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


@pytest.mark.asyncio
async def test_server_spawns_plugin_and_receives_registration():
    fixtures = Path(__file__).parent / "fixtures"
    manifest = PluginManifest(
        plugin_uuid="com.example.mock",
        name="mock",
        code_path="mock_plugin.py",
        plugin_dir=fixtures,
        actions=[],
    )

    server = OpenActionServer()
    await server.start()
    registered = asyncio.Event()

    async def on_registered(uuid: str):
        registered.plugin_uuid = uuid
        registered.set()

    server.on_registered = on_registered

    env = os.environ.copy()
    env["MOCK_PLUGIN_SCRIPT"] = "noop"
    proc = await server.launch_plugin(manifest, python_executable=sys.executable, env=env)
    try:
        await asyncio.wait_for(registered.wait(), timeout=3.0)
        assert registered.plugin_uuid == "com.example.mock"
    finally:
        proc.terminate()
        await proc.wait()
        await server.stop()


def test_key_context_roundtrip():
    ctx = KeyContext(deck_serial="DEV1", page="@HOME", key=3)
    token = ctx.to_token()
    parsed = KeyContext.from_token(token)
    assert parsed == ctx


def test_key_context_is_stable():
    a = KeyContext("D", "P", 1).to_token()
    b = KeyContext("D", "P", 1).to_token()
    assert a == b


@pytest.mark.asyncio
async def test_dispatch_key_down_roundtrips_setTitle():
    fixtures = Path(__file__).parent / "fixtures"
    manifest = PluginManifest(
        plugin_uuid="com.example.mock",
        name="mock",
        code_path="mock_plugin.py",
        plugin_dir=fixtures,
        actions=[],
    )

    server = OpenActionServer()
    await server.start()
    registered = asyncio.Event()
    commands_received: list = []

    async def on_registered(uuid: str):
        registered.set()

    async def on_command(uuid: str, cmd):
        commands_received.append((uuid, cmd))

    server.on_registered = on_registered
    server.on_command = on_command

    env = os.environ.copy()
    env["MOCK_PLUGIN_SCRIPT"] = "echo-key"
    proc = await server.launch_plugin(manifest, python_executable=sys.executable, env=env)
    try:
        await asyncio.wait_for(registered.wait(), timeout=3.0)
        ctx = KeyContext("D", "@HOME", 0)
        await server.dispatch_key_down(
            plugin_uuid="com.example.mock",
            action_uuid="com.example.mock.x",
            context=ctx,
            settings={},
        )
        # wait for the mock plugin to echo back setTitle
        for _ in range(30):
            if commands_received:
                break
            await asyncio.sleep(0.1)
        assert len(commands_received) == 1
        _, cmd = commands_received[0]
        assert cmd.payload["title"] == "pressed"
    finally:
        proc.terminate()
        await proc.wait()
        await server.stop()
