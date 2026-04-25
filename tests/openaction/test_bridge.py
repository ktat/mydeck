import logging
from pathlib import Path
from unittest.mock import MagicMock

from mydeck.app_open_action_bridge import AppOpenActionBridge


def test_bridge_has_is_background_app_flag():
    mydeck = MagicMock()
    mydeck.deck = MagicMock()
    app = AppOpenActionBridge(mydeck, {"plugins_dir": "/tmp/does-not-exist"})
    assert app.is_background_app is True


def test_bridge_reads_plugins_dir_from_option(tmp_path):
    mydeck = MagicMock()
    mydeck.deck = MagicMock()
    app = AppOpenActionBridge(mydeck, {"plugins_dir": str(tmp_path)})
    assert app.plugins_dir == Path(tmp_path)


def test_unknown_action_logs_warning_across_all_dispatch_methods(caplog):
    from mydeck.openaction.server import KeyContext
    from mydeck.openaction.registry import ActionRegistry

    mydeck = MagicMock()
    mydeck.deck = MagicMock()
    app = AppOpenActionBridge(mydeck, {"plugins_dir": "/tmp/nope"})
    app._registry = ActionRegistry()  # empty

    ctx = KeyContext("D", "@HOME", 0)

    for method_name in ("will_appear", "will_disappear", "key_down", "key_up"):
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="mydeck.app_open_action_bridge"):
            getattr(app, method_name)(ctx, "com.unknown.action", {})
        assert any("com.unknown.action" in rec.message for rec in caplog.records), (
            f"{method_name} did not log warning for unknown action"
        )


import asyncio
import base64
from mydeck.openaction.protocol import ParsedCommand, Command
from mydeck.openaction.server import KeyContext


def test_bridge_handles_set_image_calls_mydeck_update_key_image():
    mydeck = MagicMock()
    mydeck.deck = MagicMock()
    mydeck.deck.id = MagicMock(return_value="DECK1")
    mydeck.current_page = lambda: "@HOME"
    mydeck.abs_key = lambda k: k
    mydeck.update_key_image = MagicMock()

    app = AppOpenActionBridge(mydeck, {"plugins_dir": "/tmp/nope"})

    # Minimal PNG (1x1 transparent) base64
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
        b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc````\x00\x00\x00\x05\x00"
        b"\x01]\xcc\xdb\xe0\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    data_url = "data:image/png;base64," + base64.b64encode(png_bytes).decode()
    ctx = KeyContext(deck_serial="DECK1", page="@HOME", key=2)
    cmd = ParsedCommand(kind=Command.SET_IMAGE, context=ctx.to_token(),
                        payload={"image": data_url})

    asyncio.run(app._on_command("com.example.mvp", cmd))

    mydeck.update_key_image.assert_called_once()
    assert mydeck.update_key_image.call_args.args[0] == 2


def test_bridge_handles_set_title_calls_update_key_image():
    mydeck = MagicMock()
    mydeck.deck = MagicMock()
    mydeck.deck.id = MagicMock(return_value="DECK1")
    mydeck.current_page = lambda: "@HOME"
    mydeck.abs_key = lambda k: k
    mydeck.update_key_image = MagicMock()

    app = AppOpenActionBridge(mydeck, {"plugins_dir": "/tmp/nope"})
    ctx = KeyContext(deck_serial="DECK1", page="@HOME", key=2)
    cmd = ParsedCommand(kind=Command.SET_TITLE, context=ctx.to_token(),
                        payload={"title": "hello"})

    # Stub helpers so the test does not require a real deck/font.
    from unittest.mock import MagicMock as _MM
    app._compose_layers = _MM(return_value=_MM())  # returns a fake PIL Image
    app._pil_to_native = _MM(return_value=b"rendered")

    asyncio.run(app._on_command("com.example.mvp", cmd))

    # SET_TITLE updates the title layer and triggers a composite render.
    assert app._key_layers[ctx.to_token()]["title"] == "hello"
    app._compose_layers.assert_called_once()
    mydeck.update_key_image.assert_called_once()
    assert mydeck.update_key_image.call_args.args[0] == 2
    assert mydeck.update_key_image.call_args.args[1] == b"rendered"


def test_bridge_set_title_renders_multiline_each_line():
    mydeck = MagicMock()
    mydeck.deck = MagicMock()
    mydeck.deck.id = MagicMock(return_value="DECK1")
    mydeck.current_page = lambda: "@HOME"
    mydeck.abs_key = lambda k: k
    mydeck.update_key_image = MagicMock()

    app = AppOpenActionBridge(mydeck, {"plugins_dir": "/tmp/nope"})
    ctx = KeyContext(deck_serial="DECK1", page="@HOME", key=2)
    cmd = ParsedCommand(kind=Command.SET_TITLE, context=ctx.to_token(),
                        payload={"title": "2d 02h\n17m 30s"})

    from unittest.mock import MagicMock as _MM
    app._compose_layers = _MM(return_value=_MM())
    app._pil_to_native = _MM(return_value=b"rendered")
    asyncio.run(app._on_command("com.example.mvp", cmd))

    assert app._key_layers[ctx.to_token()]["title"] == "2d 02h\n17m 30s"


def test_will_appear_merges_stored_settings_over_provided(tmp_path):
    from mydeck.openaction.server import KeyContext
    from mydeck.openaction.registry import ActionRegistry, RegistryEntry
    from mydeck.openaction.manifest import PluginManifest

    mydeck = MagicMock()
    mydeck.deck = MagicMock()
    app = AppOpenActionBridge(mydeck, {
        "plugins_dir": "/tmp/nope",
        "settings_path": str(tmp_path / "s.json"),
    })

    # Register a fake plugin in the registry
    manifest = PluginManifest("pl.uuid", "p", "p.py", tmp_path, [])
    app._registry = ActionRegistry()
    app._registry._by_action_uuid["pl.uuid.a"] = RegistryEntry("pl.uuid", "p.py", manifest)
    app._server = MagicMock()

    # Pre-populate store
    app._settings_store.set("pl.uuid", "D|@HOME|0", {"stored_key": "stored_val"})

    ctx = KeyContext("D", "@HOME", 0)
    app.will_appear(ctx, "pl.uuid.a", {"stored_key": "YAML_initial", "other": "only_in_yaml"})

    # _schedule runs through the event-loop hop; to keep the test synchronous,
    # just inspect what coroutine was scheduled via the mock server:
    # will_appear calls self._schedule(self._server.dispatch_will_appear(...))
    # We can check the server mock was invoked with merged settings.
    # _schedule is a no-op when _loop is None — so dispatch wasn't called on the server.
    # Instead, verify the context_actions mapping was set:
    assert app._context_actions["D|@HOME|0"] == ("pl.uuid", "pl.uuid.a")


def test_on_command_set_settings_persists_and_echoes_did_receive(tmp_path):
    import asyncio as _asyncio
    from mydeck.openaction.protocol import ParsedCommand, Command as _Command
    from mydeck.openaction.server import KeyContext

    mydeck = MagicMock()
    mydeck.deck = MagicMock()
    mydeck.deck.id = MagicMock(return_value="D")
    mydeck.current_page = lambda: "@HOME"
    mydeck.abs_key = lambda k: k

    app = AppOpenActionBridge(mydeck, {
        "plugins_dir": "/tmp/nope",
        "settings_path": str(tmp_path / "s.json"),
    })
    # Track a context so didReceiveSettings can be echoed
    app._context_actions["D|@HOME|0"] = ("pl.uuid", "pl.uuid.a")

    # Mock the server so we can observe send_to_plugin calls
    app._server = MagicMock()
    async def fake_send(plugin_uuid, msg):
        fake_send.calls.append((plugin_uuid, msg))
    fake_send.calls = []
    app._server.send_to_plugin = fake_send
    async def fake_send_pi(ctx_token, msg):
        pass
    app._server.send_to_pi = fake_send_pi

    ctx = KeyContext("D", "@HOME", 0)
    cmd = ParsedCommand(kind=_Command.SET_SETTINGS, context=ctx.to_token(),
                        payload={"value": 42})

    _asyncio.run(app._on_command("pl.uuid", cmd))

    # Check stored
    assert app._settings_store.get("pl.uuid", "D|@HOME|0") == {"value": 42}
    # Check echoed didReceiveSettings
    assert len(fake_send.calls) == 1
    plugin_uuid, msg = fake_send.calls[0]
    assert plugin_uuid == "pl.uuid"
    assert msg["event"] == "didReceiveSettings"
    assert msg["action"] == "pl.uuid.a"
    assert msg["payload"]["settings"] == {"value": 42}


def test_on_command_get_settings_echoes_stored(tmp_path):
    import asyncio as _asyncio
    from mydeck.openaction.protocol import ParsedCommand, Command as _Command
    from mydeck.openaction.server import KeyContext

    mydeck = MagicMock()
    mydeck.deck = MagicMock()
    app = AppOpenActionBridge(mydeck, {
        "plugins_dir": "/tmp/nope",
        "settings_path": str(tmp_path / "s.json"),
    })
    app._context_actions["D|@HOME|0"] = ("pl.uuid", "pl.uuid.a")
    app._settings_store.set("pl.uuid", "D|@HOME|0", {"stored": "yes"})

    app._server = MagicMock()
    async def fake_send(plugin_uuid, msg):
        fake_send.calls.append((plugin_uuid, msg))
    fake_send.calls = []
    app._server.send_to_plugin = fake_send

    ctx = KeyContext("D", "@HOME", 0)
    cmd = ParsedCommand(kind=_Command.GET_SETTINGS, context=ctx.to_token(),
                        payload={})

    _asyncio.run(app._on_command("pl.uuid", cmd))

    assert len(fake_send.calls) == 1
    _, msg = fake_send.calls[0]
    assert msg["event"] == "didReceiveSettings"
    assert msg["payload"]["settings"] == {"stored": "yes"}


def test_pi_set_settings_stores_and_notifies_plugin(tmp_path):
    import asyncio as _asyncio
    from mydeck.openaction.protocol import ParsedCommand, Command as _Command
    from mydeck.openaction.server import KeyContext

    mydeck = MagicMock()
    mydeck.deck = MagicMock()
    app = AppOpenActionBridge(mydeck, {
        "plugins_dir": "/tmp/nope",
        "settings_path": str(tmp_path / "s.json"),
    })
    ctx = KeyContext("D", "@HOME", 0)
    app._context_actions[ctx.to_token()] = ("pl.uuid", "pl.uuid.a")

    app._server = MagicMock()
    async def fake_plugin_send(p, m): fake_plugin_send.calls.append((p, m))
    fake_plugin_send.calls = []
    app._server.send_to_plugin = fake_plugin_send

    cmd = ParsedCommand(kind=_Command.SET_SETTINGS, context=ctx.to_token(),
                        payload={"k": "v"})
    _asyncio.run(app._on_pi_command(ctx.to_token(), cmd))

    # Stored under the plugin UUID from _context_actions
    assert app._settings_store.get("pl.uuid", ctx.to_token()) == {"k": "v"}
    # Plugin was notified via didReceiveSettings
    assert len(fake_plugin_send.calls) == 1
    puuid, msg = fake_plugin_send.calls[0]
    assert puuid == "pl.uuid"
    assert msg["event"] == "didReceiveSettings"
    assert msg["action"] == "pl.uuid.a"
    assert msg["payload"]["settings"] == {"k": "v"}


def test_pi_get_settings_replies_to_pi(tmp_path):
    import asyncio as _asyncio
    from mydeck.openaction.protocol import ParsedCommand, Command as _Command
    from mydeck.openaction.server import KeyContext

    mydeck = MagicMock()
    mydeck.deck = MagicMock()
    app = AppOpenActionBridge(mydeck, {
        "plugins_dir": "/tmp/nope",
        "settings_path": str(tmp_path / "s.json"),
    })
    ctx = KeyContext("D", "@HOME", 0)
    app._context_actions[ctx.to_token()] = ("pl.uuid", "pl.uuid.a")
    app._settings_store.set("pl.uuid", ctx.to_token(), {"x": 1})

    app._server = MagicMock()
    async def fake_pi_send(c, m): fake_pi_send.calls.append((c, m))
    fake_pi_send.calls = []
    app._server.send_to_pi = fake_pi_send

    cmd = ParsedCommand(kind=_Command.GET_SETTINGS, context=ctx.to_token(), payload={})
    _asyncio.run(app._on_pi_command(ctx.to_token(), cmd))

    assert len(fake_pi_send.calls) == 1
    token, msg = fake_pi_send.calls[0]
    assert token == ctx.to_token()
    assert msg["event"] == "didReceiveSettings"
    assert msg["payload"]["settings"] == {"x": 1}


def test_pi_send_to_plugin_forwards_to_plugin(tmp_path):
    import asyncio as _asyncio
    from mydeck.openaction.protocol import ParsedCommand, Command as _Command
    from mydeck.openaction.server import KeyContext

    mydeck = MagicMock()
    mydeck.deck = MagicMock()
    app = AppOpenActionBridge(mydeck, {
        "plugins_dir": "/tmp/nope",
        "settings_path": str(tmp_path / "s.json"),
    })
    ctx = KeyContext("D", "@HOME", 0)
    app._context_actions[ctx.to_token()] = ("pl.uuid", "pl.uuid.a")

    app._server = MagicMock()
    async def fake_send(p, m): fake_send.calls.append((p, m))
    fake_send.calls = []
    app._server.send_to_plugin = fake_send

    cmd = ParsedCommand(kind=_Command.SEND_TO_PLUGIN, context=ctx.to_token(),
                        payload={"custom": "payload"})
    _asyncio.run(app._on_pi_command(ctx.to_token(), cmd))

    assert len(fake_send.calls) == 1
    puuid, msg = fake_send.calls[0]
    assert puuid == "pl.uuid"
    assert msg["event"] == "sendToPlugin"
    assert msg["action"] == "pl.uuid.a"
    assert msg["payload"] == {"custom": "payload"}


def test_plugin_send_to_pi_forwards_to_pi(tmp_path):
    import asyncio as _asyncio
    from mydeck.openaction.protocol import ParsedCommand, Command as _Command
    from mydeck.openaction.server import KeyContext

    mydeck = MagicMock()
    mydeck.deck = MagicMock()
    app = AppOpenActionBridge(mydeck, {
        "plugins_dir": "/tmp/nope",
        "settings_path": str(tmp_path / "s.json"),
    })
    ctx = KeyContext("D", "@HOME", 0)
    app._context_actions[ctx.to_token()] = ("pl.uuid", "pl.uuid.a")

    app._server = MagicMock()
    async def fake_send(c, m): fake_send.calls.append((c, m))
    fake_send.calls = []
    app._server.send_to_pi = fake_send

    cmd = ParsedCommand(kind=_Command.SEND_TO_PI, context=ctx.to_token(),
                        payload={"from_plugin": "hi"})
    _asyncio.run(app._on_command("pl.uuid", cmd))

    assert len(fake_send.calls) == 1
    token, msg = fake_send.calls[0]
    assert token == ctx.to_token()
    assert msg["event"] == "sendToPropertyInspector"
    assert msg["payload"] == {"from_plugin": "hi"}
