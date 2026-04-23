# OpenAction (Elgato-compatible) Plugin Bridge — MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new `BackgroundApp` to MyDeck that speaks the Elgato Stream Deck SDK WebSocket protocol so that unmodified Elgato / OpenAction plugins can be assigned to keys via a new `action:` YAML key type.

**Architecture:** The bridge is implemented as `AppOpenActionBridge(BackgroundAppBase)`, which runs an asyncio WebSocket server on a dedicated port in its own thread. On startup it scans `~/.config/mydeck/plugins/*.sdPlugin/manifest.json` to build an Action registry, then spawns one Node.js process per plugin with the standard Elgato CLI arguments (`-port`, `-pluginUUID`, `-registerEvent`, `-info`). The bridge translates between Elgato's WebSocket JSON protocol and MyDeck's internal key lifecycle (page change → `willAppear`/`willDisappear`; physical press → `keyDown`/`keyUp`; `setImage`/`setTitle` from plugin → MyDeck's existing key-rendering pipeline). MVP scope: enough to run a plugin that sets an image and reacts to key presses. **Out of scope (future plans):** Property Inspector HTML UI, `setSettings` persistence, multi-state toggles (`setState`), `switchToProfile`, first-time setup prompt, dials/encoders, Web UI plugin browser.

**Tech Stack:** Python 3.10+, `websockets` library (new optional dependency), Node.js 20+ (runtime requirement for plugins, user-installed), existing MyDeck core (`BackgroundAppBase`, `MyDeck.set_key`, `MyDeck.key_change_callback`), pytest for tests.

---

## File Structure

**New files:**
- `src/mydeck/app_open_action_bridge.py` — `AppOpenActionBridge(BackgroundAppBase)` entry point; boots the asyncio event loop inside the thread, owns the WebSocket server, plugin subprocesses, and the context→key map.
- `src/mydeck/openaction/__init__.py` — sub-package marker.
- `src/mydeck/openaction/manifest.py` — parse a single `manifest.json` into a typed dict (`PluginManifest`, `ActionDef`).
- `src/mydeck/openaction/registry.py` — scan a plugins directory, build an `ActionRegistry` mapping `action_uuid → (plugin_uuid, code_path, manifest)`.
- `src/mydeck/openaction/protocol.py` — pure functions that build Elgato WebSocket messages (`make_will_appear`, `make_key_down`, `make_key_up`, `make_will_disappear`) and parse incoming commands (`parse_set_image`, `parse_set_title`).
- `src/mydeck/openaction/server.py` — `OpenActionServer` class: WebSocket server, registration handshake, plugin process lifecycle, dispatch API consumed by the BackgroundApp.
- `tests/openaction/__init__.py`
- `tests/openaction/test_manifest.py`
- `tests/openaction/test_registry.py`
- `tests/openaction/test_protocol.py`
- `tests/openaction/test_server.py`
- `tests/openaction/fixtures/com.example.mvp.sdPlugin/manifest.json` — minimal valid manifest for tests.
- `tests/openaction/fixtures/mock_plugin.py` — tiny in-process mock plugin (WebSocket client) for integration tests (no Node.js required in CI).

**Modified files:**
- `pyproject.toml` — add `websockets` as an optional extra `[project.optional-dependencies] openaction = ["websockets>=12"]`.
- `src/mydeck/__init__.py` — re-export `AppOpenActionBridge` so YAML short name `OpenActionBridge` resolves.
- `src/mydeck/my_decks.py` — in `set_key()` (~line 635): when `conf.get("action")` is present, skip the default image/label rendering and call `self.mydeck._openaction_will_appear(key, conf)` instead; in `key_change_callback()` (~line 852): when `conf.get("action")` is present, call `self.mydeck._openaction_key_down(key, conf)` on press and `_openaction_key_up()` on release; expose three helper methods on `MyDeck` (`_openaction_will_appear`, `_openaction_will_disappear`, `_openaction_key_down`, `_openaction_key_up`) that no-op when no bridge is registered.
- `docs/make_your_app.md` — append a section pointing to the new doc.
- `docs/openaction_plugins.md` — new user-facing doc (created in final task).

**Rationale for decomposition:** `manifest.py` / `registry.py` / `protocol.py` have no runtime I/O — they are pure data and are cheap to test. `server.py` has all the asyncio + subprocess I/O and is exercised via fake plugins. `app_open_action_bridge.py` is the thin integration layer that plugs `OpenActionServer` into MyDeck's BackgroundApp lifecycle. Keeping each file under ~250 lines.

---

## Task 1: Add optional dependency and sub-package skeleton

**Files:**
- Modify: `pyproject.toml` (optional-dependencies section, ~line 39-40)
- Create: `src/mydeck/openaction/__init__.py` (empty marker)
- Create: `tests/openaction/__init__.py` (empty marker)

- [ ] **Step 1: Add optional dependency to pyproject.toml**

Edit `pyproject.toml`. Replace the `[project.optional-dependencies]` block:

```toml
[project.optional-dependencies]
dev = ["pytest", "mypy", "build", "twine"]
openaction = ["websockets>=12"]
```

- [ ] **Step 2: Create empty sub-package markers**

```bash
mkdir -p src/mydeck/openaction tests/openaction tests/openaction/fixtures
touch src/mydeck/openaction/__init__.py tests/openaction/__init__.py
```

- [ ] **Step 3: Verify package is still importable**

Run: `PYTHONPATH=src python3 -c "import mydeck.openaction; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml src/mydeck/openaction/__init__.py tests/openaction/__init__.py
git commit -m "chore: scaffold openaction sub-package and optional dep"
```

---

## Task 2: Manifest parser

Parse a single Elgato-style `manifest.json` into a typed structure. Extract the fields MVP needs: plugin UUID, name, CodePath (per-OS or single), list of Actions (UUID + Name + States[].Image).

**Files:**
- Create: `src/mydeck/openaction/manifest.py`
- Create: `tests/openaction/test_manifest.py`
- Create: `tests/openaction/fixtures/com.example.mvp.sdPlugin/manifest.json`

- [ ] **Step 1: Create the fixture manifest**

Create `tests/openaction/fixtures/com.example.mvp.sdPlugin/manifest.json`:

```json
{
  "Name": "MVP Plugin",
  "Version": "1.0.0.0",
  "Author": "test",
  "UUID": "com.example.mvp",
  "CodePath": "bin/plugin.js",
  "Icon": "icons/plugin",
  "Description": "Test fixture",
  "OS": [{"Platform": "linux", "MinimumVersion": "22.04"}],
  "Software": {"MinimumVersion": "6.0"},
  "SDKVersion": 2,
  "Actions": [
    {
      "UUID": "com.example.mvp.ping",
      "Name": "Ping",
      "Icon": "icons/ping",
      "States": [{"Image": "icons/ping_key"}]
    }
  ]
}
```

- [ ] **Step 2: Write failing test**

Create `tests/openaction/test_manifest.py`:

```python
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/openaction/test_manifest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mydeck.openaction.manifest'`

- [ ] **Step 4: Implement parser**

Create `src/mydeck/openaction/manifest.py`:

```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/openaction/test_manifest.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add src/mydeck/openaction/manifest.py tests/openaction/test_manifest.py tests/openaction/fixtures/com.example.mvp.sdPlugin/manifest.json
git commit -m "feat(openaction): parse Elgato plugin manifest.json"
```

---

## Task 3: Action registry

Scan a directory of `*.sdPlugin/` folders, merge their manifests into a lookup table keyed by action UUID. Ignore malformed plugins (log and skip).

**Files:**
- Create: `src/mydeck/openaction/registry.py`
- Create: `tests/openaction/test_registry.py`

- [ ] **Step 1: Write failing test**

Create `tests/openaction/test_registry.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/openaction/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mydeck.openaction.registry'`

- [ ] **Step 3: Implement registry**

Create `src/mydeck/openaction/registry.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/openaction/test_registry.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/mydeck/openaction/registry.py tests/openaction/test_registry.py
git commit -m "feat(openaction): scan plugin directory into action registry"
```

---

## Task 4: Protocol message builders

Pure functions that produce Elgato-compatible JSON message dicts. No I/O, trivially testable. Also implement a parser that dispatches incoming messages to a callback by event name.

**Files:**
- Create: `src/mydeck/openaction/protocol.py`
- Create: `tests/openaction/test_protocol.py`

- [ ] **Step 1: Write failing test**

Create `tests/openaction/test_protocol.py`:

```python
from mydeck.openaction.protocol import (
    make_will_appear,
    make_will_disappear,
    make_key_down,
    make_key_up,
    parse_command,
    Command,
)


def test_make_will_appear_has_required_fields():
    msg = make_will_appear(
        action_uuid="com.example.mvp.ping",
        context="ctx-1",
        device="dev-1",
        row=0,
        column=2,
        settings={"foo": "bar"},
    )
    assert msg["event"] == "willAppear"
    assert msg["action"] == "com.example.mvp.ping"
    assert msg["context"] == "ctx-1"
    assert msg["device"] == "dev-1"
    assert msg["payload"]["coordinates"] == {"row": 0, "column": 2}
    assert msg["payload"]["settings"] == {"foo": "bar"}
    assert msg["payload"]["state"] == 0
    assert msg["payload"]["controller"] == "Keypad"


def test_make_will_disappear_mirrors_will_appear():
    msg = make_will_disappear(
        action_uuid="com.example.mvp.ping",
        context="ctx-1",
        device="dev-1",
        row=1,
        column=0,
        settings={},
    )
    assert msg["event"] == "willDisappear"
    assert msg["action"] == "com.example.mvp.ping"


def test_make_key_down_and_up():
    down = make_key_down("com.example.mvp.ping", "ctx-1", "dev-1", 0, 0, {"x": 1})
    up = make_key_up("com.example.mvp.ping", "ctx-1", "dev-1", 0, 0, {"x": 1})
    assert down["event"] == "keyDown"
    assert up["event"] == "keyUp"
    assert down["payload"]["settings"] == {"x": 1}


def test_parse_command_set_image():
    raw = {
        "event": "setImage",
        "context": "ctx-1",
        "payload": {"image": "data:image/png;base64,AAA", "target": 0, "state": None},
    }
    cmd = parse_command(raw)
    assert cmd.kind == Command.SET_IMAGE
    assert cmd.context == "ctx-1"
    assert cmd.payload["image"] == "data:image/png;base64,AAA"


def test_parse_command_set_title():
    raw = {
        "event": "setTitle",
        "context": "ctx-1",
        "payload": {"title": "Hi", "target": 0},
    }
    cmd = parse_command(raw)
    assert cmd.kind == Command.SET_TITLE
    assert cmd.payload["title"] == "Hi"


def test_parse_command_unknown_event_returns_none():
    raw = {"event": "somethingElse", "context": "c"}
    assert parse_command(raw) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/openaction/test_protocol.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mydeck.openaction.protocol'`

- [ ] **Step 3: Implement protocol module**

Create `src/mydeck/openaction/protocol.py`:

```python
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional


class Command(Enum):
    SET_IMAGE = "setImage"
    SET_TITLE = "setTitle"


@dataclass
class ParsedCommand:
    kind: Command
    context: str
    payload: Dict[str, Any]


def _appear_payload(
    action_uuid: str,
    context: str,
    device: str,
    row: int,
    column: int,
    settings: Dict[str, Any],
    event: str,
) -> Dict[str, Any]:
    return {
        "event": event,
        "action": action_uuid,
        "context": context,
        "device": device,
        "payload": {
            "settings": settings,
            "coordinates": {"row": row, "column": column},
            "state": 0,
            "controller": "Keypad",
            "isInMultiAction": False,
        },
    }


def make_will_appear(action_uuid, context, device, row, column, settings):
    return _appear_payload(action_uuid, context, device, row, column, settings, "willAppear")


def make_will_disappear(action_uuid, context, device, row, column, settings):
    return _appear_payload(action_uuid, context, device, row, column, settings, "willDisappear")


def make_key_down(action_uuid, context, device, row, column, settings):
    return _appear_payload(action_uuid, context, device, row, column, settings, "keyDown")


def make_key_up(action_uuid, context, device, row, column, settings):
    return _appear_payload(action_uuid, context, device, row, column, settings, "keyUp")


def parse_command(raw: Dict[str, Any]) -> Optional[ParsedCommand]:
    event = raw.get("event")
    try:
        kind = Command(event)
    except ValueError:
        return None
    return ParsedCommand(
        kind=kind,
        context=raw.get("context", ""),
        payload=raw.get("payload", {}) or {},
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/openaction/test_protocol.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/mydeck/openaction/protocol.py tests/openaction/test_protocol.py
git commit -m "feat(openaction): protocol message builders and parser"
```

---

## Task 5: OpenActionServer skeleton with registration handshake

The WebSocket server. It starts on a port, accepts a single plugin connection, and recognizes the Elgato registration message (`{"event": "registerPlugin", "uuid": "<uuid>"}`). The server exposes a `dispatch(context, message)` coroutine for sending events into plugins and an `on_command` callback that receives `ParsedCommand`s from plugins. This task only implements registration; events/commands come in later tasks.

**Files:**
- Create: `src/mydeck/openaction/server.py`
- Create: `tests/openaction/test_server.py`
- Create: `tests/openaction/fixtures/mock_plugin.py`

- [ ] **Step 1: Create the mock plugin fixture**

Create `tests/openaction/fixtures/mock_plugin.py`:

```python
"""Minimal in-process mock of an Elgato plugin (WebSocket client).

Run as: python mock_plugin.py -port <port> -pluginUUID <uuid> -registerEvent registerPlugin -info '<json>'
"""
import argparse
import asyncio
import json
import os
import sys

import websockets


async def run(port: int, plugin_uuid: str, register_event: str, info_json: str, script: str):
    uri = f"ws://127.0.0.1:{port}"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"event": register_event, "uuid": plugin_uuid}))
        if script == "echo-key":
            async for raw in ws:
                msg = json.loads(raw)
                if msg.get("event") == "keyDown":
                    await ws.send(json.dumps({
                        "event": "setTitle",
                        "context": msg["context"],
                        "payload": {"title": "pressed", "target": 0},
                    }))
        elif script == "noop":
            await asyncio.Event().wait()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-port", type=int, required=True)
    parser.add_argument("-pluginUUID", required=True)
    parser.add_argument("-registerEvent", required=True)
    parser.add_argument("-info", required=True)
    args = parser.parse_args()
    script = os.environ.get("MOCK_PLUGIN_SCRIPT", "noop")
    asyncio.run(run(args.port, args.pluginUUID, args.registerEvent, args.info, script))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write failing test**

Create `tests/openaction/test_server.py`:

```python
import asyncio
import json
import pytest
import websockets

from mydeck.openaction.server import OpenActionServer


@pytest.mark.asyncio
async def test_server_accepts_registration():
    server = OpenActionServer(host="127.0.0.1", port=0)
    await server.start()
    registered = asyncio.Event()

    async def on_registered(plugin_uuid: str):
        registered.plugin_uuid = plugin_uuid
        registered.set()

    server.on_registered = on_registered

    async with websockets.connect(f"ws://127.0.0.1:{server.port}") as ws:
        await ws.send(json.dumps({"event": "registerPlugin", "uuid": "com.example.mvp"}))
        await asyncio.wait_for(registered.wait(), timeout=1.0)
        assert registered.plugin_uuid == "com.example.mvp"

    await server.stop()
```

Also add `asyncio_mode = "auto"` support: create `tests/conftest.py` or `pyproject.toml` pytest config. Simplest is to add to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

Add `pytest-asyncio` to dev deps in `pyproject.toml`:

```toml
dev = ["pytest", "pytest-asyncio", "mypy", "build", "twine"]
```

- [ ] **Step 3: Install dev deps and run test to verify it fails**

```bash
pip install -e '.[dev,openaction]'
PYTHONPATH=src pytest tests/openaction/test_server.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'mydeck.openaction.server'`

- [ ] **Step 4: Implement server**

Create `src/mydeck/openaction/server.py`:

```python
import asyncio
import json
import logging
from typing import Awaitable, Callable, Dict, Optional

import websockets
from websockets.server import WebSocketServerProtocol

from .protocol import ParsedCommand, parse_command

log = logging.getLogger(__name__)


class OpenActionServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        self._host = host
        self._requested_port = port
        self._server: Optional[websockets.WebSocketServer] = None
        self._plugin_sockets: Dict[str, WebSocketServerProtocol] = {}
        self.on_registered: Optional[Callable[[str], Awaitable[None]]] = None
        self.on_command: Optional[Callable[[str, ParsedCommand], Awaitable[None]]] = None

    @property
    def port(self) -> int:
        if self._server is None:
            raise RuntimeError("server not started")
        return self._server.sockets[0].getsockname()[1]

    async def start(self) -> None:
        self._server = await websockets.serve(self._handle, self._host, self._requested_port)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handle(self, ws: WebSocketServerProtocol) -> None:
        plugin_uuid: Optional[str] = None
        try:
            raw = await ws.recv()
            msg = json.loads(raw)
            if msg.get("event") != "registerPlugin" or "uuid" not in msg:
                log.warning("rejecting connection: bad registration %r", msg)
                return
            plugin_uuid = msg["uuid"]
            self._plugin_sockets[plugin_uuid] = ws
            if self.on_registered:
                await self.on_registered(plugin_uuid)

            async for raw in ws:
                try:
                    cmd = parse_command(json.loads(raw))
                except json.JSONDecodeError:
                    log.warning("bad json from plugin %s", plugin_uuid)
                    continue
                if cmd is not None and self.on_command is not None:
                    await self.on_command(plugin_uuid, cmd)
        except websockets.ConnectionClosed:
            pass
        finally:
            if plugin_uuid is not None:
                self._plugin_sockets.pop(plugin_uuid, None)

    async def send_to_plugin(self, plugin_uuid: str, message: dict) -> None:
        ws = self._plugin_sockets.get(plugin_uuid)
        if ws is None:
            log.warning("no plugin connection for %s", plugin_uuid)
            return
        await ws.send(json.dumps(message))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/openaction/test_server.py -v`
Expected: 1 passed

- [ ] **Step 6: Commit**

```bash
git add src/mydeck/openaction/server.py tests/openaction/test_server.py tests/openaction/fixtures/mock_plugin.py pyproject.toml
git commit -m "feat(openaction): websocket server with registration handshake"
```

---

## Task 6: Plugin process lifecycle

`OpenActionServer.launch_plugin(manifest)` spawns a child process with the four CLI args Elgato's protocol mandates (`-port`, `-pluginUUID`, `-registerEvent`, `-info`). For MVP we default to `python <plugin_dir>/<code_path>` if the code_path ends in `.py` (so our mock plugin works in CI without Node.js), otherwise `node <plugin_dir>/<code_path>`. The spawned PID is tracked and killed on `stop()`.

**Files:**
- Modify: `src/mydeck/openaction/server.py`
- Modify: `tests/openaction/test_server.py`

- [ ] **Step 1: Write failing test**

Append to `tests/openaction/test_server.py`:

```python
import os
import sys
from pathlib import Path

from mydeck.openaction.manifest import PluginManifest


@pytest.mark.asyncio
async def test_server_spawns_plugin_and_receives_registration():
    fixtures = Path(__file__).parent / "fixtures"
    manifest = PluginManifest(
        plugin_uuid="com.example.mock",
        name="mock",
        code_path="mock_plugin.py",
        plugin_dir=fixtures,
        actions=[],
    )

    server = OpenActionServer()
    await server.start()
    registered = asyncio.Event()

    async def on_registered(uuid: str):
        registered.plugin_uuid = uuid
        registered.set()

    server.on_registered = on_registered

    env = os.environ.copy()
    env["MOCK_PLUGIN_SCRIPT"] = "noop"
    proc = await server.launch_plugin(manifest, python_executable=sys.executable, env=env)
    try:
        await asyncio.wait_for(registered.wait(), timeout=3.0)
        assert registered.plugin_uuid == "com.example.mock"
    finally:
        proc.terminate()
        await proc.wait()
        await server.stop()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/openaction/test_server.py::test_server_spawns_plugin_and_receives_registration -v`
Expected: FAIL — `AttributeError: 'OpenActionServer' object has no attribute 'launch_plugin'`

- [ ] **Step 3: Implement launch_plugin**

Add to `src/mydeck/openaction/server.py`:

```python
import asyncio
import json as _json
import os as _os
from pathlib import Path as _Path
from typing import Optional as _Optional

# ... inside OpenActionServer class ...

    async def launch_plugin(
        self,
        manifest,
        python_executable: str = "python3",
        node_executable: str = "node",
        env: _Optional[dict] = None,
    ) -> asyncio.subprocess.Process:
        code = _Path(manifest.plugin_dir) / manifest.code_path
        if code.suffix == ".py":
            argv = [python_executable, str(code)]
        else:
            argv = [node_executable, str(code)]
        argv += [
            "-port", str(self.port),
            "-pluginUUID", manifest.plugin_uuid,
            "-registerEvent", "registerPlugin",
            "-info", _json.dumps({"plugin": {"uuid": manifest.plugin_uuid}}),
        ]
        return await asyncio.create_subprocess_exec(*argv, env=env or _os.environ.copy())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/openaction/test_server.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/mydeck/openaction/server.py tests/openaction/test_server.py
git commit -m "feat(openaction): spawn plugin subprocess with Elgato CLI args"
```

---

## Task 7: Context map and event dispatch

Keys are identified by a triple `(deck_serial, page_label, key_num)`. Build a bidirectional map between these triples and opaque context IDs so plugin-emitted `context` strings can be resolved back to `(deck, key)` for rendering.

**Files:**
- Modify: `src/mydeck/openaction/server.py`
- Modify: `tests/openaction/test_server.py`

- [ ] **Step 1: Write failing test**

Append to `tests/openaction/test_server.py`:

```python
from mydeck.openaction.server import KeyContext


def test_key_context_roundtrip():
    ctx = KeyContext(deck_serial="DEV1", page="@HOME", key=3)
    token = ctx.to_token()
    parsed = KeyContext.from_token(token)
    assert parsed == ctx


def test_key_context_is_stable():
    a = KeyContext("D", "P", 1).to_token()
    b = KeyContext("D", "P", 1).to_token()
    assert a == b
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/openaction/test_server.py -v -k key_context`
Expected: FAIL — `ImportError: cannot import name 'KeyContext' from 'mydeck.openaction.server'`

- [ ] **Step 3: Implement KeyContext**

Add to top of `src/mydeck/openaction/server.py` (before `OpenActionServer`):

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class KeyContext:
    deck_serial: str
    page: str
    key: int

    def to_token(self) -> str:
        return f"{self.deck_serial}|{self.page}|{self.key}"

    @classmethod
    def from_token(cls, token: str) -> "KeyContext":
        deck, page, key = token.rsplit("|", 2)
        return cls(deck_serial=deck, page=page, key=int(key))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/openaction/test_server.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/mydeck/openaction/server.py tests/openaction/test_server.py
git commit -m "feat(openaction): KeyContext token for plugin context ids"
```

---

## Task 8: High-level server API (willAppear/keyDown/keyUp dispatch)

Add convenience methods on `OpenActionServer` that take a `KeyContext` + action UUID + settings and send the appropriate protocol message to the right plugin. This is the API that `AppOpenActionBridge` will call.

**Files:**
- Modify: `src/mydeck/openaction/server.py`
- Modify: `tests/openaction/test_server.py`

- [ ] **Step 1: Write failing test**

Append to `tests/openaction/test_server.py`:

```python
@pytest.mark.asyncio
async def test_dispatch_key_down_roundtrips_setTitle():
    fixtures = Path(__file__).parent / "fixtures"
    manifest = PluginManifest(
        plugin_uuid="com.example.mock",
        name="mock",
        code_path="mock_plugin.py",
        plugin_dir=fixtures,
        actions=[],
    )

    server = OpenActionServer()
    await server.start()
    registered = asyncio.Event()
    commands_received: list = []

    async def on_registered(uuid: str):
        registered.set()

    async def on_command(uuid: str, cmd):
        commands_received.append((uuid, cmd))

    server.on_registered = on_registered
    server.on_command = on_command

    env = os.environ.copy()
    env["MOCK_PLUGIN_SCRIPT"] = "echo-key"
    proc = await server.launch_plugin(manifest, python_executable=sys.executable, env=env)
    try:
        await asyncio.wait_for(registered.wait(), timeout=3.0)
        ctx = KeyContext("D", "@HOME", 0)
        await server.dispatch_key_down(
            plugin_uuid="com.example.mock",
            action_uuid="com.example.mock.x",
            context=ctx,
            settings={},
        )
        # wait for the mock plugin to echo back setTitle
        for _ in range(30):
            if commands_received:
                break
            await asyncio.sleep(0.1)
        assert len(commands_received) == 1
        _, cmd = commands_received[0]
        assert cmd.payload["title"] == "pressed"
    finally:
        proc.terminate()
        await proc.wait()
        await server.stop()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/openaction/test_server.py::test_dispatch_key_down_roundtrips_setTitle -v`
Expected: FAIL — `AttributeError: 'OpenActionServer' object has no attribute 'dispatch_key_down'`

- [ ] **Step 3: Implement dispatch helpers**

Add to `OpenActionServer` class:

```python
    async def dispatch_will_appear(self, plugin_uuid, action_uuid, context, settings):
        from .protocol import make_will_appear
        await self.send_to_plugin(plugin_uuid, make_will_appear(
            action_uuid, context.to_token(), context.deck_serial, 0, context.key, settings))

    async def dispatch_will_disappear(self, plugin_uuid, action_uuid, context, settings):
        from .protocol import make_will_disappear
        await self.send_to_plugin(plugin_uuid, make_will_disappear(
            action_uuid, context.to_token(), context.deck_serial, 0, context.key, settings))

    async def dispatch_key_down(self, plugin_uuid, action_uuid, context, settings):
        from .protocol import make_key_down
        await self.send_to_plugin(plugin_uuid, make_key_down(
            action_uuid, context.to_token(), context.deck_serial, 0, context.key, settings))

    async def dispatch_key_up(self, plugin_uuid, action_uuid, context, settings):
        from .protocol import make_key_up
        await self.send_to_plugin(plugin_uuid, make_key_up(
            action_uuid, context.to_token(), context.deck_serial, 0, context.key, settings))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/openaction/test_server.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/mydeck/openaction/server.py tests/openaction/test_server.py
git commit -m "feat(openaction): dispatch helpers for willAppear/keyDown/keyUp"
```

---

## Task 9: `AppOpenActionBridge` BackgroundApp — skeleton

The MyDeck-side integration. Subclasses `BackgroundAppBase`. In `execute_in_thread()` it runs asyncio, starts the `OpenActionServer`, loads the `ActionRegistry` from `~/.config/mydeck/plugins/`, launches all discovered plugins, and blocks until shutdown. Exposes `bridge.will_appear(key_ctx, conf)` / `key_down` / `key_up` / `will_disappear` as thread-safe entry points that schedule the async dispatch on the bridge's event loop.

**Files:**
- Create: `src/mydeck/app_open_action_bridge.py`
- Modify: `src/mydeck/__init__.py`
- Create: `tests/openaction/test_bridge.py`

- [ ] **Step 1: Write failing test**

Create `tests/openaction/test_bridge.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/openaction/test_bridge.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mydeck.app_open_action_bridge'`

- [ ] **Step 3: Implement skeleton**

Create `src/mydeck/app_open_action_bridge.py`:

```python
import asyncio
import logging
import os
import threading
from pathlib import Path
from typing import Optional

from mydeck import BackgroundAppBase, MyDeck
from mydeck.openaction.registry import ActionRegistry
from mydeck.openaction.server import KeyContext, OpenActionServer

log = logging.getLogger(__name__)

DEFAULT_PLUGINS_DIR = Path(os.path.expanduser("~/.config/mydeck/plugins"))


class AppOpenActionBridge(BackgroundAppBase):
    use_thread = True
    IS_ALREADY_WORKING: bool = False

    def __init__(self, mydeck: MyDeck, config: Optional[dict] = None):
        super().__init__(mydeck)
        config = config or {}
        self.plugins_dir = Path(config.get("plugins_dir", DEFAULT_PLUGINS_DIR))
        self.port = int(config.get("port", 0))
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._server: Optional[OpenActionServer] = None
        self._registry: Optional[ActionRegistry] = None
        self._plugin_procs: list = []
        self._started = threading.Event()

    def execute_in_thread(self):
        if AppOpenActionBridge.IS_ALREADY_WORKING:
            log.debug("duplicate AppOpenActionBridge start ignored")
            return
        AppOpenActionBridge.IS_ALREADY_WORKING = True
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self._serve())
        finally:
            AppOpenActionBridge.IS_ALREADY_WORKING = False

    async def _serve(self):
        self._registry = ActionRegistry.from_directory(self.plugins_dir)
        self._server = OpenActionServer(port=self.port)
        self._server.on_command = self._on_command
        await self._server.start()
        log.info("OpenAction bridge listening on port %d", self._server.port)
        for manifest in self._registry.all_plugins():
            try:
                proc = await self._server.launch_plugin(manifest)
                self._plugin_procs.append(proc)
            except Exception as e:
                log.warning("failed to spawn plugin %s: %s", manifest.plugin_uuid, e)
        self.mydeck._openaction_bridge = self  # register on MyDeck
        self._started.set()
        # block until shutdown
        while not self.mydeck._exit:
            await asyncio.sleep(0.5)
        await self._shutdown()

    async def _shutdown(self):
        for proc in self._plugin_procs:
            try:
                proc.terminate()
            except Exception:
                pass
        for proc in self._plugin_procs:
            try:
                await proc.wait()
            except Exception:
                pass
        if self._server is not None:
            await self._server.stop()

    async def _on_command(self, plugin_uuid: str, cmd):
        # Handlers wired in Task 11/12
        pass

    # Thread-safe entry points called from MyDeck main thread
    def _schedule(self, coro):
        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(coro, self._loop)

    def will_appear(self, key_ctx: KeyContext, action_uuid: str, settings: dict):
        if self._registry is None:
            return
        entry = self._registry.lookup(action_uuid)
        if entry is None:
            log.warning("unknown action uuid: %s", action_uuid)
            return
        self._schedule(self._server.dispatch_will_appear(
            entry.plugin_uuid, action_uuid, key_ctx, settings))

    def will_disappear(self, key_ctx: KeyContext, action_uuid: str, settings: dict):
        if self._registry is None:
            return
        entry = self._registry.lookup(action_uuid)
        if entry is None:
            return
        self._schedule(self._server.dispatch_will_disappear(
            entry.plugin_uuid, action_uuid, key_ctx, settings))

    def key_down(self, key_ctx: KeyContext, action_uuid: str, settings: dict):
        if self._registry is None:
            return
        entry = self._registry.lookup(action_uuid)
        if entry is None:
            return
        self._schedule(self._server.dispatch_key_down(
            entry.plugin_uuid, action_uuid, key_ctx, settings))

    def key_up(self, key_ctx: KeyContext, action_uuid: str, settings: dict):
        if self._registry is None:
            return
        entry = self._registry.lookup(action_uuid)
        if entry is None:
            return
        self._schedule(self._server.dispatch_key_up(
            entry.plugin_uuid, action_uuid, key_ctx, settings))
```

- [ ] **Step 4: Add re-export to `src/mydeck/__init__.py`**

Open `src/mydeck/__init__.py`. Find the line `from .app_web_server import *` (around line 56) and add immediately below it:

```python
from .app_open_action_bridge import AppOpenActionBridge
```

- [ ] **Step 5: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/openaction/test_bridge.py -v`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add src/mydeck/app_open_action_bridge.py src/mydeck/__init__.py tests/openaction/test_bridge.py
git commit -m "feat(openaction): AppOpenActionBridge BackgroundApp skeleton"
```

---

## Task 10: Wire `action:` YAML keys into `MyDeck.set_key`

When a key's config contains `action: <UUID>`, skip default image rendering and call the bridge's `will_appear()` instead. Also add a helper method `_openaction_will_appear()` on `MyDeck` that no-ops when no bridge is registered.

**Files:**
- Modify: `src/mydeck/my_decks.py`
- Create: `tests/test_openaction_integration.py`

- [ ] **Step 1: Write failing integration test**

Create `tests/test_openaction_integration.py`:

```python
from unittest.mock import MagicMock

from mydeck.openaction.server import KeyContext


def test_set_key_with_action_calls_bridge_will_appear():
    from mydeck import MyDeck

    bridge = MagicMock()
    mydeck = MyDeck.__new__(MyDeck)
    mydeck.deck = MagicMock()
    mydeck.deck.id = MagicMock(return_value="DECK1")
    mydeck._exit = False
    mydeck._openaction_bridge = bridge
    mydeck._current_page = "@HOME"
    mydeck.abs_key = lambda k: k

    # Minimal fake conf: action + settings only, no image
    conf = {"action": "com.example.mvp.ping", "settings": {"foo": "bar"}}
    mydeck.set_key(0, conf, use_lock=False)

    bridge.will_appear.assert_called_once()
    call_args = bridge.will_appear.call_args
    ctx = call_args.args[0]
    assert isinstance(ctx, KeyContext)
    assert ctx.key == 0
    assert call_args.args[1] == "com.example.mvp.ping"
    assert call_args.args[2] == {"foo": "bar"}


def test_set_key_without_action_uses_default_path():
    from mydeck import MyDeck

    bridge = MagicMock()
    mydeck = MyDeck.__new__(MyDeck)
    mydeck.deck = MagicMock()
    mydeck.deck.id = MagicMock(return_value="DECK1")
    mydeck._exit = False
    mydeck._openaction_bridge = bridge
    mydeck.abs_key = lambda k: k
    mydeck.update_key_image = MagicMock()
    mydeck.render_key_image = MagicMock(return_value=b"x")

    conf = {"image": "foo.png", "label": "Foo"}
    mydeck.set_key(0, conf, use_lock=False)

    bridge.will_appear.assert_not_called()
    mydeck.update_key_image.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_openaction_integration.py -v`
Expected: FAIL — the first test fails because `set_key` does not dispatch to the bridge.

- [ ] **Step 3: Modify `MyDeck.set_key` in `src/mydeck/my_decks.py`**

In `src/mydeck/my_decks.py`, locate `set_key` (around line 635). Replace the method with:

```python
    def set_key(self, key: int, conf: dict, use_lock: bool = True):
        """Set a key and its configuration."""
        key = self.abs_key(key)
        deck = self.deck
        if conf is None:
            return

        if conf.get("action") is not None:
            from mydeck.openaction.server import KeyContext
            ctx = KeyContext(
                deck_serial=str(deck.id()) if deck is not None else "unknown",
                page=self.current_page(),
                key=key,
            )
            bridge = getattr(self, "_openaction_bridge", None)
            if bridge is not None:
                bridge.will_appear(ctx, conf["action"], conf.get("settings") or {})
            return

        if conf.get('chrome'):
            chrome = conf['chrome']
            url = chrome[-1]
            if conf.get('image') is None and conf.get('image_url') is None:
                self.image_url_to_image(conf, url)
            elif conf.get("image_url") is not None:
                self.image_url_to_image(conf)
        elif conf.get("image") is None and conf.get('image_url') is not None:
            self.image_url_to_image(conf)

        if conf.get('no_image') is None:
            self.update_key_image(key, self.render_key_image(ImageOrFile(conf["image"]), conf.get(
                "label") or '', conf.get("background_color") or ''), use_lock)
```

Also add a default initialization of `_openaction_bridge` at the end of `MyDeck.__init__()` — find `def __init__(self, opt: dict, server_port: int):` (around line 270) and at the end of that method, add:

```python
        self._openaction_bridge = None
```

Add `current_page` early-return protection: the `set_key` helper may be called before pages exist during tests. This is fine because we fallback to `"unknown"`. If `self.current_page()` is called on a bare instance it may fail — add a `try/except` guard in the `action` branch only if that test breaks.

- [ ] **Step 4: Adjust test to stub current_page**

Update `test_set_key_with_action_calls_bridge_will_appear` — add `mydeck.current_page = lambda: "@HOME"` before the call. Re-check `test_set_key_without_action_uses_default_path` still passes (no current_page needed because it doesn't hit the action branch).

- [ ] **Step 5: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/test_openaction_integration.py -v`
Expected: 2 passed

Also verify nothing else regressed:

Run: `PYTHONPATH=src pytest tests/ -v`
Expected: all previously-passing tests still pass

- [ ] **Step 6: Commit**

```bash
git add src/mydeck/my_decks.py tests/test_openaction_integration.py
git commit -m "feat: dispatch action: keys to OpenAction bridge on willAppear"
```

---

## Task 11: Wire keyDown/keyUp into `key_change_callback`

When a physical key is pressed and its conf has `action:`, dispatch `keyDown` / `keyUp` to the plugin. Do not fall through to the default `command`/`chrome`/exit handling for that key.

**Files:**
- Modify: `src/mydeck/my_decks.py`
- Modify: `tests/test_openaction_integration.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_openaction_integration.py`:

```python
def test_key_change_callback_with_action_dispatches_key_down():
    from mydeck import MyDeck

    bridge = MagicMock()
    mydeck = MyDeck.__new__(MyDeck)
    mydeck.deck = MagicMock()
    mydeck.deck.id = MagicMock(return_value="DECK1")
    mydeck._exit = False
    mydeck._openaction_bridge = bridge
    mydeck.current_page = lambda: "@HOME"
    mydeck.abs_key = lambda k: k
    mydeck.debug = lambda *a, **kw: None
    mydeck.key_config = lambda: {"@HOME": {0: {"action": "com.example.mvp.ping", "settings": {"a": 1}}}}
    mydeck.config = None

    # Press
    mydeck.key_change_callback(0, True)
    bridge.key_down.assert_called_once()
    assert bridge.key_down.call_args.args[1] == "com.example.mvp.ping"
    # Release
    mydeck.key_change_callback(0, False)
    bridge.key_up.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_openaction_integration.py::test_key_change_callback_with_action_dispatches_key_down -v`
Expected: FAIL — `bridge.key_down.assert_called_once()` fails because the callback does not dispatch.

- [ ] **Step 3: Modify `key_change_callback` in `src/mydeck/my_decks.py`**

Locate `key_change_callback` (around line 852). After the existing lookup of `conf`, **before** the `if state:` block that checks for `exit`, add:

```python
        # OpenAction plugin dispatch — bypass built-in handlers
        if conf is not None and conf.get("action") is not None:
            from mydeck.openaction.server import KeyContext
            bridge = getattr(self, "_openaction_bridge", None)
            if bridge is not None:
                ctx = KeyContext(
                    deck_serial=str(deck.id()) if deck is not None else "unknown",
                    page=self.current_page(),
                    key=self.abs_key(key),
                )
                settings = conf.get("settings") or {}
                if state:
                    bridge.key_down(ctx, conf["action"], settings)
                else:
                    bridge.key_up(ctx, conf["action"], settings)
            return
```

This must come after the lookup `conf = ...` is done. Concretely the current structure is:

```python
        if state:
            current_page: str = self.current_page()
            conf: Optional[dict] = None
            if self.key_config().get(current_page) is not None:
                conf = self.key_config()[current_page].get(key)
            ...
```

The `if state:` guard means `conf` is only computed on press. For `action:` we also need `conf` on release. Refactor: hoist the lookup so it runs for both press and release:

```python
    def key_change_callback(self, key: int, state: bool):
        """Call a callback according to a key is pushed"""
        deck = self.deck
        if deck is not None:
            self.debug("Key %s = %s" % (key, state))

        current_page: str = self.current_page()
        conf: Optional[dict] = None
        if self.key_config().get(current_page) is not None:
            conf = self.key_config()[current_page].get(key)

        # OpenAction plugin dispatch — bypass built-in handlers
        if conf is not None and conf.get("action") is not None:
            from mydeck.openaction.server import KeyContext
            bridge = getattr(self, "_openaction_bridge", None)
            if bridge is not None:
                ctx = KeyContext(
                    deck_serial=str(deck.id()) if deck is not None else "unknown",
                    page=current_page,
                    key=self.abs_key(key),
                )
                settings = conf.get("settings") or {}
                if state:
                    bridge.key_down(ctx, conf["action"], settings)
                else:
                    bridge.key_up(ctx, conf["action"], settings)
            return

        # existing behavior: press-only handling
        if state:
            # (existing exit/command/chrome/app_command dispatch unchanged — keep the block as-is)
            ...
```

Leave the rest of the method body (the existing `if state:` block with all the `exit` / `command` / `chrome` etc. branches) unchanged below this insertion.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/test_openaction_integration.py -v`
Expected: 3 passed

Also run full suite:

Run: `PYTHONPATH=src pytest tests/ -v`
Expected: no regressions

- [ ] **Step 5: Commit**

```bash
git add src/mydeck/my_decks.py tests/test_openaction_integration.py
git commit -m "feat: dispatch action: key press/release to OpenAction bridge"
```

---

## Task 12: Handle `setImage` and `setTitle` commands from plugin

When the plugin sends `setImage`, decode base64, render via MyDeck's existing `update_key_image`. When it sends `setTitle`, re-render the key with the new label. The bridge must resolve a `context` token back to `(deck_serial, page, key)` and find the correct `MyDeck` instance to call.

**Files:**
- Modify: `src/mydeck/app_open_action_bridge.py`
- Modify: `tests/openaction/test_bridge.py`

- [ ] **Step 1: Write failing test**

Append to `tests/openaction/test_bridge.py`:

```python
import asyncio
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
    import base64
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
    # the label we passed should be the second positional arg
    assert "hello" in str(mydeck.render_key_image.call_args)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/openaction/test_bridge.py -v`
Expected: FAIL — `_on_command` is a no-op; `update_key_image` not called.

- [ ] **Step 3: Implement command handlers**

In `src/mydeck/app_open_action_bridge.py`, replace the `_on_command` stub with:

```python
    async def _on_command(self, plugin_uuid: str, cmd):
        from mydeck.openaction.protocol import Command
        from mydeck.openaction.server import KeyContext

        try:
            ctx = KeyContext.from_token(cmd.context)
        except Exception:
            log.warning("malformed context token: %r", cmd.context)
            return

        # Only the bridge's own MyDeck for MVP; multi-deck routing is future work.
        mydeck = self.mydeck
        if str(mydeck.deck.id()) != ctx.deck_serial:
            return
        if mydeck.current_page() != ctx.page:
            # key is on a different page — drop the command
            return

        key = mydeck.abs_key(ctx.key)

        if cmd.kind == Command.SET_IMAGE:
            image_field = cmd.payload.get("image", "")
            if image_field.startswith("data:"):
                import base64
                _, _, b64 = image_field.partition(",")
                raw = base64.b64decode(b64)
                mydeck.update_key_image(key, raw, True)
            else:
                log.warning("unsupported setImage image format: %r", image_field[:40])
        elif cmd.kind == Command.SET_TITLE:
            title = cmd.payload.get("title", "")
            from mydeck.my_decks import ImageOrFile
            # No image source on title-only update — use a 1x1 transparent placeholder
            # by deferring to a cached last-image per context would be ideal; for MVP
            # re-render with label over whatever image the plugin last set. Fall back
            # to None image and let render_key_image handle it.
            mydeck.update_key_image(key, mydeck.render_key_image(None, title, '', True), True)
```

Note: the `render_key_image(None, title, '', True)` call assumes the `no_label=True` 4th arg handles missing image gracefully. If this isn't the case, adjust per `render_key_image` signature at my_decks.py:763.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/openaction/test_bridge.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/mydeck/app_open_action_bridge.py tests/openaction/test_bridge.py
git commit -m "feat(openaction): handle setImage and setTitle commands from plugins"
```

---

## Task 13: End-to-end smoke test (mock plugin via subprocess → real bridge → mocked MyDeck)

Run the full flow: bridge starts, spawns the Python mock plugin, the mock plugin responds to `keyDown` with `setTitle`, and `update_key_image` on the mocked MyDeck is called. This test validates the whole pipeline outside of real hardware.

**Files:**
- Create: `tests/test_openaction_end_to_end.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_openaction_end_to_end.py`:

```python
import asyncio
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mydeck.app_open_action_bridge import AppOpenActionBridge
from mydeck.openaction.server import KeyContext


FIXTURES = Path(__file__).parent / "openaction" / "fixtures"


@pytest.mark.asyncio
async def test_end_to_end_key_down_triggers_set_title():
    # Wire a fake MyDeck that captures update_key_image calls
    mydeck = MagicMock()
    mydeck.deck = MagicMock()
    mydeck.deck.id = MagicMock(return_value="TESTDECK")
    mydeck.current_page = lambda: "@HOME"
    mydeck.abs_key = lambda k: k
    mydeck.update_key_image = MagicMock()
    mydeck.render_key_image = MagicMock(return_value=b"img")
    mydeck._exit = False

    # Use the fixtures dir as the plugins dir; mock_plugin.py is the "plugin"
    # with a dummy .sdPlugin shell linked to it.
    app = AppOpenActionBridge(mydeck, {"plugins_dir": str(FIXTURES)})

    env = os.environ.copy()
    env["MOCK_PLUGIN_SCRIPT"] = "echo-key"
    # Patch launch_plugin to set our env variable for the spawn.
    # (Simpler: inject via fixture manifest CodePath pointing at mock_plugin.py)

    # Run the bridge in a background task
    async def exit_after(delay):
        await asyncio.sleep(delay)
        mydeck._exit = True

    # point the plugin at our mock_plugin.py
    from mydeck.openaction.manifest import PluginManifest, ActionDef
    manifest = PluginManifest(
        plugin_uuid="com.example.mock",
        name="mock",
        code_path="mock_plugin.py",
        plugin_dir=FIXTURES,
        actions=[ActionDef(action_uuid="com.example.mock.x", name="X", state_images=[])],
    )

    # replace registry with a registry containing just this manifest
    from mydeck.openaction.registry import ActionRegistry, RegistryEntry
    reg = ActionRegistry()
    reg._plugins.append(manifest)
    reg._by_action_uuid["com.example.mock.x"] = RegistryEntry(
        plugin_uuid=manifest.plugin_uuid,
        code_path=manifest.code_path,
        manifest=manifest,
    )

    async def serve_with_registry():
        app._registry = reg
        from mydeck.openaction.server import OpenActionServer
        app._server = OpenActionServer()
        app._server.on_command = app._on_command
        await app._server.start()
        proc = await app._server.launch_plugin(manifest, python_executable=sys.executable, env=env)
        app._plugin_procs.append(proc)

        # wait for registration by polling the sockets dict
        for _ in range(50):
            if manifest.plugin_uuid in app._server._plugin_sockets:
                break
            await asyncio.sleep(0.1)
        assert manifest.plugin_uuid in app._server._plugin_sockets

        ctx = KeyContext("TESTDECK", "@HOME", 0)
        await app._server.dispatch_key_down(
            manifest.plugin_uuid, "com.example.mock.x", ctx, {})

        # wait for setTitle to round-trip and update_key_image to be invoked
        for _ in range(50):
            if mydeck.update_key_image.called:
                break
            await asyncio.sleep(0.1)

        await app._shutdown()

    await serve_with_registry()
    assert mydeck.update_key_image.called
```

- [ ] **Step 2: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/test_openaction_end_to_end.py -v`
Expected: 1 passed (may be slow; allow ~5s).

If it hangs, ensure `mock_plugin.py` closes cleanly on SIGTERM — the subprocess is terminated by `_shutdown()`.

- [ ] **Step 3: Commit**

```bash
git add tests/test_openaction_end_to_end.py
git commit -m "test(openaction): end-to-end smoke test with mock plugin subprocess"
```

---

## Task 14: User-facing documentation

Write a new doc explaining how to enable OpenAction, where to install plugins, and show a YAML snippet. Cross-link from README.

**Files:**
- Create: `docs/openaction_plugins.md`
- Modify: `README.md` (add a line under "Third-party apps (plugins)" section)

- [ ] **Step 1: Create `docs/openaction_plugins.md`**

```markdown
# OpenAction / Elgato-compatible Plugins (experimental)

MyDeck can run unmodified Elgato Stream Deck plugins (or OpenAction plugins)
via the `AppOpenActionBridge` background app. This is an **alpha** feature and
supports only a subset of the SDK (key-type actions, `setImage`, `setTitle`).
Dials, Property Inspector HTML, `switchToProfile`, and `setSettings` persistence
are not yet implemented.

## Prerequisites

- Install Node.js 20 or 24 (required by most Elgato plugins).
- Install MyDeck with the `openaction` extra:

```
pip install '.[openaction]'
```

## Installing a plugin

Place the plugin's `.sdPlugin/` folder under `~/.config/mydeck/plugins/`:

```
~/.config/mydeck/plugins/
  com.example.soundboard.sdPlugin/
    manifest.json
    bin/plugin.js
    ...
```

## Enabling the bridge

Add the bridge to your `apps:` in the per-device YAML:

```yaml
apps:
  - app: OpenActionBridge
    option:
      plugins_dir: ~/.config/mydeck/plugins
```

## Assigning an action to a key

Use the new `action:` key type in `page_config`:

```yaml
page_config:
  "@HOME":
    keys:
      0:
        action: "com.example.soundboard.play"
        settings:
          file: /path/to/ding.wav
          volume: 0.8
```

The plugin draws the button image and title dynamically via `setImage` /
`setTitle`.

## Limitations in MVP

- Property Inspector HTML is not rendered; configure via the YAML `settings:`
  field by hand.
- `setSettings` from the plugin is not persisted back to YAML.
- Only one deck is supported per bridge instance.
- Multi-state (`setState`) is not yet wired through to re-render.
- Dial/touchscreen actions are out of scope.
```

- [ ] **Step 2: Update README.md**

In `README.md`, find the line `### Third-party apps (plugins)` (around line 107). At the end of that section (before `### Custom script`), add:

```markdown
**Elgato-compatible plugins (experimental):** MyDeck can also run unmodified
Stream Deck / OpenAction plugins. See [`docs/openaction_plugins.md`](docs/openaction_plugins.md).
```

- [ ] **Step 3: Commit**

```bash
git add docs/openaction_plugins.md README.md
git commit -m "docs: document experimental OpenAction plugin bridge"
```

---

## Self-Review Summary

**Spec coverage check:**
- WebSocket server as BackgroundApp → Task 9 ✓
- YAML `action:` + `settings:` key type → Task 10 ✓
- Registration handshake → Task 5 ✓
- Plugin spawn with CLI args → Task 6 ✓
- willAppear/willDisappear dispatch → Task 10 (willAppear), Task 9 (willDisappear hook wired but page-change emission is deferred — see Out-of-scope)
- keyDown/keyUp → Task 11 ✓
- setImage / setTitle from plugin → Task 12 ✓
- `~/.config/mydeck/plugins/` convention → Task 9 (default) + Task 14 (docs) ✓
- Property Inspector → explicitly out-of-scope per plan header ✓
- `setSettings` persistence → out-of-scope ✓
- First-time setup prompt → out-of-scope ✓

**Known gap:** `willDisappear` is implemented on the bridge (`will_disappear()`) but the plan does not wire page-change events in MyDeck core to call it. For MVP, plugins will see `willAppear` on every page setup but no corresponding `willDisappear`. This is acceptable for demo plugins; a follow-up plan should hook into `set_current_page()` to emit `willDisappear` for prior-page `action:` keys.

**Execution note:** This plan should be executed on a feature branch, ideally in a worktree:

```bash
git worktree add ../mystreamdeck-openaction -b feat/openaction-bridge main
cd ../mystreamdeck-openaction
```
