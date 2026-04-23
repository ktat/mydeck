import asyncio
import json
import logging
from typing import Awaitable, Callable, Dict, Optional

import websockets
from websockets.asyncio.server import ServerConnection

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
