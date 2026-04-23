from pathlib import Path
from mydeck.openaction.manifest import load_manifest, PluginManifest, ActionDef

FIXTURE = Path(__file__).parent / "fixtures" / "com.example.mvp.sdPlugin"


def test_load_manifest_parses_required_fields():
    manifest = load_manifest(FIXTURE)
    assert isinstance(manifest, PluginManifest)
    assert manifest.plugin_uuid == "com.example.mvp"
    assert manifest.name == "MVP Plugin"
    assert manifest.code_path == "bin/plugin.js"
    assert manifest.plugin_dir == FIXTURE


def test_load_manifest_parses_actions():
    manifest = load_manifest(FIXTURE)
    assert len(manifest.actions) == 1
    action = manifest.actions[0]
    assert isinstance(action, ActionDef)
    assert action.action_uuid == "com.example.mvp.ping"
    assert action.name == "Ping"
    assert action.state_images == ["icons/ping_key"]


def test_load_manifest_raises_on_missing_file(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        load_manifest(tmp_path / "does-not-exist.sdPlugin")
