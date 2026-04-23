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
