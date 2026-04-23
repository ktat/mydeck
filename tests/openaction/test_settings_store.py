import json
from pathlib import Path

from mydeck.openaction.settings_store import SettingsStore


def test_get_returns_empty_dict_when_missing(tmp_path):
    store = SettingsStore(tmp_path / "s.json")
    assert store.get("plugin.x", "ctx-1") == {}


def test_set_and_get_roundtrip(tmp_path):
    store = SettingsStore(tmp_path / "s.json")
    store.set("plugin.x", "ctx-1", {"a": 1, "b": "hi"})
    assert store.get("plugin.x", "ctx-1") == {"a": 1, "b": "hi"}


def test_set_persists_across_instances(tmp_path):
    path = tmp_path / "s.json"
    SettingsStore(path).set("plugin.x", "ctx-1", {"value": 42})
    other = SettingsStore(path)
    assert other.get("plugin.x", "ctx-1") == {"value": 42}


def test_set_creates_parent_directory(tmp_path):
    path = tmp_path / "nested" / "dir" / "s.json"
    SettingsStore(path).set("p", "c", {"k": "v"})
    assert path.is_file()


def test_get_returns_copy_not_reference(tmp_path):
    store = SettingsStore(tmp_path / "s.json")
    store.set("p", "c", {"k": "v"})
    got = store.get("p", "c")
    got["k"] = "mutated"
    assert store.get("p", "c") == {"k": "v"}


def test_load_handles_corrupt_json(tmp_path, caplog):
    path = tmp_path / "s.json"
    path.write_text("{ not json")
    import logging
    with caplog.at_level(logging.WARNING, logger="mydeck.openaction.settings_store"):
        store = SettingsStore(path)
    assert store.get("p", "c") == {}
