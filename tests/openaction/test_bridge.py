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


def test_bridge_handles_set_title_renders_with_label():
    mydeck = MagicMock()
    mydeck.deck = MagicMock()
    mydeck.deck.id = MagicMock(return_value="DECK1")
    mydeck.current_page = lambda: "@HOME"
    mydeck.abs_key = lambda k: k
    mydeck.update_key_image = MagicMock()
    mydeck.render_key_image = MagicMock(return_value=b"x")

    app = AppOpenActionBridge(mydeck, {"plugins_dir": "/tmp/nope"})
    ctx = KeyContext(deck_serial="DECK1", page="@HOME", key=2)
    cmd = ParsedCommand(kind=Command.SET_TITLE, context=ctx.to_token(),
                        payload={"title": "hello"})

    asyncio.run(app._on_command("com.example.mvp", cmd))

    mydeck.render_key_image.assert_called_once()
    # the label "hello" should be in one of the positional args to render_key_image
    assert "hello" in str(mydeck.render_key_image.call_args)
