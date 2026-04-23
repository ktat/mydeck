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
