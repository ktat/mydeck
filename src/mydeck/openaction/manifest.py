import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class ActionDef:
    action_uuid: str
    name: str
    state_images: List[str] = field(default_factory=list)


@dataclass
class PluginManifest:
    plugin_uuid: str
    name: str
    code_path: str
    plugin_dir: Path
    actions: List[ActionDef] = field(default_factory=list)


def load_manifest(plugin_dir: Path) -> PluginManifest:
    manifest_path = plugin_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"manifest.json not found in {plugin_dir}")

    with manifest_path.open() as f:
        raw = json.load(f)

    actions = [
        ActionDef(
            action_uuid=a["UUID"],
            name=a["Name"],
            state_images=[s.get("Image", "") for s in a.get("States", [])],
        )
        for a in raw.get("Actions", [])
    ]
    return PluginManifest(
        plugin_uuid=raw["UUID"],
        name=raw["Name"],
        code_path=raw["CodePath"],
        plugin_dir=plugin_dir,
        actions=actions,
    )
