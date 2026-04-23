import asyncio
import json
import logging
import os as _os
from pathlib import Path as _Path
from typing import Awaitable, Callable, Dict, Optional

import websockets
from websockets.asyncio.server import ServerConnection

from .context import KeyContext  # re-exported so existing imports still work
from .protocol import ParsedCommand, parse_command

log = logging.getLogger(__name__)


class OpenActionServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        self._host = host
        self._requested_port = port
        self._server: Optional[websockets.asyncio.server.Server] = None
        self._plugin_sockets: Dict[str, ServerConnection] = {}
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

    async def _handle(self, ws: ServerConnection) -> None:
        plugin_uuid: Optional[str] = None
        try:
            raw = await ws.recv()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                log.warning("rejecting connection: non-JSON registration")
                await ws.close()
                return
            if msg.get("event") != "registerPlugin" or "uuid" not in msg:
                log.warning("rejecting connection: bad registration %r", msg)
                await ws.close()
                return
            plugin_uuid = msg["uuid"]
            if plugin_uuid in self._plugin_sockets:
                log.warning("duplicate registration for uuid %s; replacing", plugin_uuid)
            self._plugin_sockets[plugin_uuid] = ws
            if self.on_registered:
                try:
                    await self.on_registered(plugin_uuid)
                except Exception as exc:
                    log.warning("on_registered raised for plugin %s: %s", plugin_uuid, exc)

            async for raw in ws:
                try:
                    cmd = parse_command(json.loads(raw))
                except json.JSONDecodeError:
                    log.warning("bad json from plugin %s", plugin_uuid)
                    continue
                if cmd is not None and self.on_command is not None:
                    try:
                        await self.on_command(plugin_uuid, cmd)
                    except Exception as exc:
                        log.warning("on_command raised for plugin %s: %s", plugin_uuid, exc)
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

    async def launch_plugin(
        self,
        manifest,
        python_executable: str = "python3",
        node_executable: str = "node",
        env: Optional[dict] = None,
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
            "-info", json.dumps({"plugin": {"uuid": manifest.plugin_uuid}}),
        ]
        return await asyncio.create_subprocess_exec(*argv, env=env or _os.environ.copy())

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
