import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mydeck.app_open_action_bridge import AppOpenActionBridge
from mydeck.openaction.server import KeyContext


FIXTURES = Path(__file__).parent / "openaction" / "fixtures"


@pytest.mark.asyncio
async def test_end_to_end_key_down_triggers_set_title():
    # Fake MyDeck that captures update_key_image calls
    mydeck = MagicMock()
    mydeck.deck = MagicMock()
    mydeck.deck.id = MagicMock(return_value="TESTDECK")
    mydeck.current_page = lambda: "@HOME"
    mydeck.abs_key = lambda k: k
    mydeck.update_key_image = MagicMock()
    mydeck.render_key_image = MagicMock(return_value=b"img")
    mydeck._exit = False

    app = AppOpenActionBridge(mydeck, {"plugins_dir": str(FIXTURES)})

    # Build a minimal manifest pointing at the Python mock plugin fixture
    from mydeck.openaction.manifest import PluginManifest, ActionDef
    from mydeck.openaction.registry import ActionRegistry, RegistryEntry
    from mydeck.openaction.server import OpenActionServer

    manifest = PluginManifest(
        plugin_uuid="com.example.mock",
        name="mock",
        code_path="mock_plugin.py",
        plugin_dir=FIXTURES,
        actions=[ActionDef(action_uuid="com.example.mock.x", name="X", state_images=[])],
    )

    reg = ActionRegistry()
    reg._plugins.append(manifest)
    reg._by_action_uuid["com.example.mock.x"] = RegistryEntry(
        plugin_uuid=manifest.plugin_uuid,
        code_path=manifest.code_path,
        manifest=manifest,
    )

    app._registry = reg
    app._server = OpenActionServer()
    app._server.on_command = app._on_command
    await app._server.start()

    env = os.environ.copy()
    env["MOCK_PLUGIN_SCRIPT"] = "echo-key"
    proc = await app._server.launch_plugin(manifest, python_executable=sys.executable, env=env)
    app._plugin_procs.append(proc)

    try:
        # Wait for plugin registration
        for _ in range(50):
            if manifest.plugin_uuid in app._server._plugin_sockets:
                break
            await asyncio.sleep(0.1)
        assert manifest.plugin_uuid in app._server._plugin_sockets, "plugin never registered"

        ctx = KeyContext("TESTDECK", "@HOME", 0)
        await app._server.dispatch_key_down(
            manifest.plugin_uuid, "com.example.mock.x", ctx, {}
        )

        # Wait for setTitle to round-trip and update_key_image to be invoked
        for _ in range(50):
            if mydeck.update_key_image.called:
                break
            await asyncio.sleep(0.1)

        assert mydeck.update_key_image.called, "update_key_image was not called"
    finally:
        await app._shutdown()
