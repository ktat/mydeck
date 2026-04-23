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
    import platform
    code_path = raw.get("CodePath")
    if code_path is None:
        system = platform.system().lower()
        if system == "linux":
            code_path = raw.get("CodePathLin")
        elif system == "darwin":
            code_path = raw.get("CodePathMac")
        elif system == "windows":
            code_path = raw.get("CodePathWin")
    if code_path is None:
        paths = raw.get("CodePaths") or {}
        machine = platform.machine().lower()
        system = platform.system().lower()
        if system == "linux":
            triple = f"{machine}-unknown-linux-gnu"
        elif system == "darwin":
            triple = f"{machine}-apple-darwin"
        elif system == "windows":
            triple = f"{machine}-pc-windows-msvc"
        else:
            triple = None
        code_path = paths.get(triple) if triple else None
    if code_path is None:
        raise KeyError(
            f"manifest.json in {plugin_dir} has no CodePath / CodePath<OS> for current platform"
        )

    plugin_uuid = raw.get("UUID")
    if not plugin_uuid:
        dir_name = plugin_dir.name
        if dir_name.endswith(".sdPlugin"):
            plugin_uuid = dir_name[: -len(".sdPlugin")]
        else:
            plugin_uuid = raw.get("Name")
    if not plugin_uuid:
        raise KeyError(f"manifest.json in {plugin_dir} has no UUID or usable fallback")

    return PluginManifest(
        plugin_uuid=plugin_uuid,
        name=raw.get("Name", plugin_uuid),
        code_path=code_path,
        plugin_dir=plugin_dir,
        actions=actions,
    )
