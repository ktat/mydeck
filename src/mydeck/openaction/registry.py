import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .manifest import PluginManifest, load_manifest


@dataclass
class RegistryEntry:
    plugin_uuid: str
    code_path: str
    manifest: PluginManifest


class ActionRegistry:
    def __init__(self) -> None:
        self._by_action_uuid: Dict[str, RegistryEntry] = {}
        self._plugins: List[PluginManifest] = []

    @classmethod
    def from_directory(cls, plugins_dir: Path) -> "ActionRegistry":
        registry = cls()
        if not plugins_dir.is_dir():
            return registry
        for child in sorted(plugins_dir.iterdir()):
            if not child.is_dir() or not child.name.endswith(".sdPlugin"):
                continue
            try:
                manifest = load_manifest(child)
            except Exception as e:
                logging.warning("skipping malformed plugin %s: %s", child, e)
                continue
            registry._plugins.append(manifest)
            for action in manifest.actions:
                registry._by_action_uuid[action.action_uuid] = RegistryEntry(
                    plugin_uuid=manifest.plugin_uuid,
                    code_path=manifest.code_path,
                    manifest=manifest,
                )
        return registry

    def lookup(self, action_uuid: str) -> Optional[RegistryEntry]:
        return self._by_action_uuid.get(action_uuid)

    def all_plugins(self) -> List[PluginManifest]:
        return list(self._plugins)
