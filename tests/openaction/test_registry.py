from pathlib import Path
from mydeck.openaction.registry import ActionRegistry

FIXTURES = Path(__file__).parent / "fixtures"


def test_registry_scans_plugins_dir():
    registry = ActionRegistry.from_directory(FIXTURES)
    entry = registry.lookup("com.example.mvp.ping")
    assert entry is not None
    assert entry.plugin_uuid == "com.example.mvp"
    assert entry.code_path == "bin/plugin.js"


def test_registry_returns_none_for_unknown_uuid():
    registry = ActionRegistry.from_directory(FIXTURES)
    assert registry.lookup("com.nobody.nothing") is None


def test_registry_handles_missing_directory(tmp_path):
    registry = ActionRegistry.from_directory(tmp_path / "does-not-exist")
    assert registry.all_plugins() == []


def test_registry_skips_malformed_plugin(tmp_path, caplog):
    bad = tmp_path / "bad.sdPlugin"
    bad.mkdir()
    (bad / "manifest.json").write_text("{ not json")
    good = tmp_path / "good.sdPlugin"
    good.mkdir()
    (good / "manifest.json").write_text(
        '{"Name":"G","UUID":"com.good","CodePath":"x","Version":"1.0.0.0",'
        '"Author":"t","Icon":"i","Description":"d",'
        '"Actions":[{"UUID":"com.good.a","Name":"A","States":[]}]}'
    )
    registry = ActionRegistry.from_directory(tmp_path)
    assert registry.lookup("com.good.a") is not None
