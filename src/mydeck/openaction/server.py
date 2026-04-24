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


class PageHandle:
    """Wraps a Playwright Page with the same terminate/kill/wait interface as
    asyncio.subprocess.Process so _shutdown can treat both uniformly."""

    def __init__(self, page):
        self._page = page

    def terminate(self):
        pass

    def kill(self):
        pass

    async def wait(self):
        try:
            await self._page.close()
        except Exception:
            pass


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
                if cmd is None:
                    continue
                if self.on_command is not None:
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
        devices: Optional[list] = None,
        browser=None,
    ):
        code = _Path(manifest.plugin_dir) / manifest.code_path
        info = {
            "application": {
                "font": "",
                "language": "en",
                "platform": "linux",
                "platformVersion": "",
                "version": "6.0.0",
            },
            "plugin": {
                "uuid": manifest.plugin_uuid,
                "version": "1.0.0",
            },
            "devicePixelRatio": 1,
            "devices": list(devices) if devices else [],
            "colors": {
                "buttonPressedBackgroundColor": "#303030FF",
                "buttonPressedBorderColor": "#646464FF",
                "buttonPressedTextColor": "#969696FF",
                "disabledColor": "#F7821B59",
                "highlightColor": "#F7821BFF",
                "mouseDownColor": "#CF6304FF",
            },
        }
        if code.suffix == ".html" and browser is not None:
            return await self._launch_html_plugin(manifest, code, info, browser)

        if code.suffix == ".py":
            argv = [python_executable, str(code)]
        elif code.suffix in (".js", ".mjs", ".cjs"):
            argv = [node_executable, str(code)]
        else:
            # Native executable (compiled binary). Ensure it's marked executable.
            try:
                code.chmod(code.stat().st_mode | 0o111)
            except OSError:
                pass
            argv = [str(code)]
        argv += [
            "-port", str(self.port),
            "-pluginUUID", manifest.plugin_uuid,
            "-registerEvent", "registerPlugin",
            "-info", json.dumps(info),
        ]
        return await asyncio.create_subprocess_exec(*argv, env=env or _os.environ.copy())

    async def _launch_html_plugin(self, manifest, code_path: _Path, info: dict, browser) -> "PageHandle":
        page = await browser.new_page()
        # Forward browser console messages to Python log for diagnostics.
        page.on("console", lambda msg: log.debug("[%s console %s] %s",
                                                  manifest.plugin_uuid, msg.type, msg.text))
        page.on("pageerror", lambda err: log.warning("[%s pageerror] %s",
                                                      manifest.plugin_uuid, err))
        await page.goto(f"file://{code_path}")
        # Wait until connectElgatoStreamDeckSocket (or connectSocket legacy) is
        # available — scripts may finish executing slightly after "load".
        try:
            await page.wait_for_function(
                "typeof connectElgatoStreamDeckSocket === 'function' || "
                "typeof connectSocket === 'function'",
                timeout=5000,
            )
        except Exception:
            log.warning("connectElgatoStreamDeckSocket not found in %s after 5s",
                        manifest.plugin_uuid)
            return PageHandle(page)
        # Call the plugin's registration entry-point with the same args the
        # Elgato software would pass.
        try:
            await page.evaluate(
                """(args) => {
                    const fn = window.connectElgatoStreamDeckSocket || window.connectSocket;
                    if (fn) fn(args.port, args.uuid, args.event, args.info);
                }""",
                {
                    "port": self.port,
                    "uuid": manifest.plugin_uuid,
                    "event": "registerPlugin",
                    "info": json.dumps(info),
                },
            )
        except Exception as e:
            log.warning("failed to invoke connectElgatoStreamDeckSocket for %s: %s",
                        manifest.plugin_uuid, e)
        return PageHandle(page)

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
