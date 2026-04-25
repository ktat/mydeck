import asyncio
import logging
import os
import threading
from pathlib import Path
from typing import Optional

from mydeck import BackgroundAppBase, MyDeck
from mydeck.openaction.context import KeyContext
from mydeck.openaction.registry import ActionRegistry
from mydeck.openaction.server import OpenActionServer
from mydeck.openaction.settings_store import SettingsStore

log = logging.getLogger(__name__)

# Sentinel for _update_layers to tell "no update" apart from "clear to None".
_UNSET = object()

DEFAULT_PLUGINS_DIR = Path(os.path.expanduser("~/.config/mydeck/plugins"))
DEFAULT_SETTINGS_PATH = Path(os.path.expanduser("~/.config/mydeck/openaction-settings.json"))


class AppOpenActionBridge(BackgroundAppBase):
    use_thread = True
    IS_ALREADY_WORKING: bool = False

    def __init__(self, mydeck: MyDeck, config: Optional[dict] = None):
        super().__init__(mydeck)
        config = config or {}
        self.plugins_dir = Path(config.get("plugins_dir", DEFAULT_PLUGINS_DIR))
        self.port = int(config.get("port", 0))
        self.settings_path = Path(config.get("settings_path", DEFAULT_SETTINGS_PATH))
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._server: Optional[OpenActionServer] = None
        self._registry: Optional[ActionRegistry] = None
        # plugin_uuid -> handle (asyncio.subprocess.Process or PageHandle).
        # Was previously a list; switched to dict for hot-reload so we can
        # terminate a single plugin by uuid (Web UI uninstall).
        self._plugin_procs: dict = {}
        self._started = threading.Event()
        self._settings_store = SettingsStore(self.settings_path)
        self._context_actions: dict = {}  # context_token -> (plugin_uuid, action_uuid)
        self._playwright = None
        self._browser = None
        # Per-key render state: token -> {"image": PIL.Image, "title": str}
        # setImage sets the background, setTitle overlays text — Elgato treats
        # them as independent layers, so we composite both when either changes.
        self._key_layers: dict = {}

    def start(self):
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
        self._server.on_pi_command = self._on_pi_command
        await self._server.start()
        log.info("OpenAction bridge listening on port %d", self._server.port)
        # Wait briefly for additional MyDeck instances to be added to the
        # session. The bridge is a BackgroundApp started from one MyDeck's
        # YAML, so on multi-deck setups the other decks are still being
        # initialised when _serve() runs. We poll _all_mydecks() for up to
        # 3 seconds, settling once the count has been stable for a few ticks.
        prev_count = 0
        stable = 0
        for _ in range(30):
            n = len(self._all_mydecks())
            if n == prev_count and n > 0:
                stable += 1
                if stable >= 3:
                    break
            else:
                stable = 0
            prev_count = n
            await asyncio.sleep(0.1)
        # Register with every MyDeck BEFORE spawning plugins so the attribute is
        # always available to set_key calls that race with plugin startup.
        # Multi-deck sessions share one bridge instance; whichever MyDeck's
        # BackgroundApp won the IS_ALREADY_WORKING race becomes the bridge's
        # owner, but all other MyDecks still need to be able to dispatch into
        # it from their key_change_callback / set_key paths.
        for md in self._all_mydecks():
            md._openaction_bridge = self
        devices = self._build_devices(log_each=True)

        # Start a headless browser if any plugin uses an HTML CodePath.
        from pathlib import Path as _Path
        needs_browser = any(
            (_Path(m.plugin_dir) / m.code_path).suffix == ".html"
            for m in self._registry.all_plugins()
        )
        if needs_browser:
            await self._start_browser()

        for manifest in self._registry.all_plugins():
            try:
                proc = await self._server.launch_plugin(
                    manifest, devices=devices, browser=self._browser)
                self._plugin_procs[manifest.plugin_uuid] = proc
            except Exception as e:
                log.warning("failed to spawn plugin %s: %s", manifest.plugin_uuid, e)

        # Give newly-spawned plugins up to 5 seconds to complete the
        # registerPlugin handshake before re-triggering key setup — otherwise
        # the very first willAppear events would be sent before the plugin
        # socket exists in self._server._plugin_sockets and silently dropped.
        # HTML plugins (browser-based) may take longer to connect than native ones.
        plugin_uuids = {m.plugin_uuid for m in self._registry.all_plugins()}
        for _ in range(50):
            if plugin_uuids.issubset(set(self._server._plugin_sockets.keys())):
                break
            await asyncio.sleep(0.1)

        # After the bridge is fully ready (server running, bridge registered
        # on every MyDeck, plugins spawned and registered), re-run
        # key_touchscreen_setup on each MyDeck. This fires willAppear for any
        # action: key that was set up during the startup race before the
        # bridge attribute became available.
        for md in self._all_mydecks():
            try:
                md.key_touchscreen_setup()
            except Exception as e:
                log.warning("re-setup failed for %s: %s",
                            getattr(md, "myname", "?"), e)

        self._started.set()
        # block until shutdown
        while not self.mydeck._exit:
            await asyncio.sleep(0.5)
        await self._shutdown()

    def _all_mydecks(self) -> list:
        """Return every MyDeck in the current session, or just self.mydeck.

        Only descend into the MyDecks manager if its ``mydecks`` attribute is
        a real ``dict`` — otherwise we'd treat MagicMock fakes as valid in
        tests and break the fallback to the bridge's own MyDeck.
        """
        manager = getattr(self.mydeck, "mydecks", None)
        if manager is not None:
            inner = getattr(manager, "mydecks", None)
            if isinstance(inner, dict) and inner:
                return list(inner.values())
        return [self.mydeck]

    def _build_devices(self, log_each: bool = False) -> list:
        """Snapshot the current MyDecks as the Elgato -info devices array.
        Plugins drop events for unknown device IDs, so this list must reflect
        every connected deck at spawn time."""
        devices: list = []
        for md in self._all_mydecks():
            deck = getattr(md, "deck", None)
            if deck is None:
                continue
            try:
                dev_id = str(deck.id())
                key_count = md.key_count
                columns = getattr(md, "columns", 5)
                rows = max(1, key_count // max(1, columns))
            except Exception as e:
                log.warning("failed to read deck info for %s: %s",
                            getattr(md, "myname", "?"), e)
                continue
            devices.append({
                "id": dev_id,
                "name": getattr(md, "myname", dev_id),
                "size": {"columns": columns, "rows": rows},
                "type": 0,
            })
            if log_each:
                log.info("registered device for plugins: id=%s name=%s",
                         dev_id, getattr(md, "myname", dev_id))
        return devices

    async def spawn_plugin(self, manifest):
        """Spawn one plugin after the bridge is already running (Web UI hot-reload).

        Mirrors the relevant parts of _serve(): start the headless browser if
        the new plugin is HTML-based and we don't already have one, launch the
        plugin process / page, wait briefly for it to register, then re-run
        key_touchscreen_setup so any keys already configured for this plugin's
        actions emit willAppear and pick up an icon.
        """
        if manifest.plugin_uuid in self._plugin_procs:
            log.info("plugin %s already running; skip spawn", manifest.plugin_uuid)
            return
        from pathlib import Path as _Path
        is_html = (_Path(manifest.plugin_dir) / manifest.code_path).suffix == ".html"
        if is_html and self._browser is None:
            await self._start_browser()
        try:
            proc = await self._server.launch_plugin(
                manifest, devices=self._build_devices(), browser=self._browser)
            self._plugin_procs[manifest.plugin_uuid] = proc
        except Exception as e:
            log.warning("hot-reload spawn failed for %s: %s", manifest.plugin_uuid, e)
            return
        for _ in range(50):
            if manifest.plugin_uuid in self._server._plugin_sockets:
                break
            await asyncio.sleep(0.1)
        for md in self._all_mydecks():
            try:
                md.key_touchscreen_setup()
            except Exception as e:
                log.warning("hot-reload re-setup failed for %s: %s",
                            getattr(md, "myname", "?"), e)

    async def terminate_plugin(self, plugin_uuid: str):
        """Stop a running plugin and drop its socket. Used by Web UI uninstall."""
        proc = self._plugin_procs.pop(plugin_uuid, None)
        if proc is None:
            return
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
        except Exception:
            pass
        # Forget any per-key state tied to actions of this plugin.
        stale = [tok for tok, (puuid, _) in self._context_actions.items()
                 if puuid == plugin_uuid]
        for tok in stale:
            self._context_actions.pop(tok, None)
            self._key_layers.pop(tok, None)

    def spawn_plugin_sync(self, manifest, timeout: float = 15.0) -> bool:
        """Cross-thread entry point — schedule spawn_plugin onto the bridge's
        asyncio loop and block until it completes (or timeout)."""
        if self._loop is None:
            return False
        fut = asyncio.run_coroutine_threadsafe(self.spawn_plugin(manifest), self._loop)
        try:
            fut.result(timeout=timeout)
            return True
        except Exception as e:
            log.warning("spawn_plugin_sync failed: %s", e)
            return False

    def terminate_plugin_sync(self, plugin_uuid: str, timeout: float = 10.0) -> bool:
        if self._loop is None:
            return False
        fut = asyncio.run_coroutine_threadsafe(
            self.terminate_plugin(plugin_uuid), self._loop)
        try:
            fut.result(timeout=timeout)
            return True
        except Exception as e:
            log.warning("terminate_plugin_sync failed: %s", e)
            return False

    def _mydeck_for_serial(self, serial: str):
        """Find the MyDeck whose deck serial matches ``serial``. Fallback to
        ``self.mydeck`` if no match so MVP single-deck tests still work."""
        for md in self._all_mydecks():
            deck = getattr(md, "deck", None)
            if deck is None:
                continue
            try:
                if str(deck.id()) == serial:
                    return md
            except Exception:
                continue
        # Fallback: if we couldn't find a match (e.g. because tests don't set
        # deck.id() or only one MyDeck is present), return self.mydeck so MVP
        # single-deck flows keep working.
        return self.mydeck

    async def _start_browser(self):
        try:
            from playwright.async_api import async_playwright
            import shutil
            self._playwright = await async_playwright().start()
            # Prefer a system browser when Playwright's own Chromium is not
            # available (e.g. unsupported OS version).
            system_chrome = (
                shutil.which("google-chrome")
                or shutil.which("chromium")
                or shutil.which("chromium-browser")
            )
            kwargs = dict(
                headless=True,
                args=["--allow-file-access-from-files", "--disable-web-security"],
            )
            if system_chrome:
                kwargs["executable_path"] = system_chrome
            self._browser = await self._playwright.chromium.launch(**kwargs)
            log.info("headless browser started for HTML plugins (%s)",
                     system_chrome or "playwright-bundled")
        except ImportError:
            log.warning("playwright not installed; HTML plugins will be skipped. "
                        "Install with: uv tool install --with playwright mydeck && "
                        "playwright install chromium")

    async def _shutdown(self):
        procs = list(self._plugin_procs.values())
        for proc in procs:
            try:
                proc.terminate()
            except Exception:
                pass
        for proc in procs:
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    pass
            except Exception:
                pass
        self._plugin_procs.clear()
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception:
                pass
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:
                pass
        if self._server is not None:
            await self._server.stop()

    async def _on_command(self, plugin_uuid: str, cmd):
        from mydeck.openaction.context import KeyContext
        from mydeck.openaction.protocol import (
            Command, make_did_receive_settings, make_send_to_pi,
        )

        try:
            ctx = KeyContext.from_token(cmd.context)
        except Exception:
            log.warning("malformed context token: %r", cmd.context)
            return

        # Settings commands can fire even if the user has switched pages; handle
        # them before the page-check so persistence still works.
        if cmd.kind == Command.SET_SETTINGS:
            self._settings_store.set(plugin_uuid, cmd.context, cmd.payload or {})
            tracked = self._context_actions.get(cmd.context)
            if tracked is not None:
                _puuid, action_uuid = tracked
                msg = make_did_receive_settings(
                    action_uuid, cmd.context, ctx.deck_serial, 0, ctx.key, cmd.payload or {})
                await self._server.send_to_plugin(plugin_uuid, msg)
                # Mirror the update to an attached Property Inspector, if any.
                await self._server.send_to_pi(cmd.context, msg)
            return

        if cmd.kind == Command.GET_SETTINGS:
            stored = self._settings_store.get(plugin_uuid, cmd.context)
            tracked = self._context_actions.get(cmd.context)
            if tracked is not None:
                _puuid, action_uuid = tracked
                msg = make_did_receive_settings(
                    action_uuid, cmd.context, ctx.deck_serial, 0, ctx.key, stored)
                await self._server.send_to_plugin(plugin_uuid, msg)
            return

        if cmd.kind == Command.SEND_TO_PI:
            tracked = self._context_actions.get(cmd.context)
            action_uuid = tracked[1] if tracked else ""
            await self._server.send_to_pi(
                cmd.context,
                make_send_to_pi(action_uuid, cmd.context, cmd.payload or {}),
            )
            return

        if cmd.kind == Command.LOG_MESSAGE:
            log.info("[plugin %s log] %s", plugin_uuid,
                     (cmd.payload or {}).get("message", ""))
            return

        # Rendering commands: route to the MyDeck that owns the serial in ctx.
        mydeck = self._mydeck_for_serial(ctx.deck_serial)
        if mydeck is None or mydeck.deck is None:
            return
        if mydeck.current_page() != ctx.page:
            return

        key = mydeck.abs_key(ctx.key)

        if cmd.kind == Command.SET_IMAGE:
            image_field = cmd.payload.get("image", "")
            if image_field == "":
                # Elgato semantics: empty image means "clear / use default".
                # We clear the image layer so a subsequent setTitle still
                # composites onto a black background.
                self._update_layers(cmd.context, image=None)
            elif image_field.startswith("data:"):
                pil = self._decode_image_data_url(image_field, plugin_uuid)
                if pil is None:
                    return
                self._update_layers(cmd.context, image=pil)
            else:
                log.warning("unsupported setImage image format: %r", image_field[:40])
                return
            composite = self._compose_layers(mydeck, cmd.context)
            mydeck.update_key_image(key, self._pil_to_native(mydeck, composite), True)
        elif cmd.kind == Command.SET_TITLE:
            title = cmd.payload.get("title", "")
            self._update_layers(cmd.context, title=title)
            composite = self._compose_layers(mydeck, cmd.context)
            mydeck.update_key_image(key, self._pil_to_native(mydeck, composite), True)

    async def _on_pi_command(self, context_token: str, cmd):
        """Handle commands from a Property Inspector socket.

        The PI identifies itself by the per-key context token (same token
        the plugin sees). We look up the plugin UUID from _context_actions.
        """
        from mydeck.openaction.context import KeyContext
        from mydeck.openaction.protocol import (
            Command, make_did_receive_settings, make_send_to_plugin,
        )

        tracked = self._context_actions.get(context_token)
        if tracked is None:
            log.warning("PI command for unknown context %s", context_token)
            return
        plugin_uuid, action_uuid = tracked
        try:
            ctx = KeyContext.from_token(context_token)
        except Exception:
            log.warning("malformed context token from PI: %r", context_token)
            return

        if cmd.kind == Command.SET_SETTINGS:
            self._settings_store.set(plugin_uuid, context_token, cmd.payload or {})
            # Inform the plugin of the new settings — matches Elgato behavior
            # where PI-driven setSettings triggers didReceiveSettings on plugin.
            msg = make_did_receive_settings(
                action_uuid, context_token, ctx.deck_serial, 0, ctx.key, cmd.payload or {})
            await self._server.send_to_plugin(plugin_uuid, msg)
            return

        if cmd.kind == Command.GET_SETTINGS:
            stored = self._settings_store.get(plugin_uuid, context_token)
            msg = make_did_receive_settings(
                action_uuid, context_token, ctx.deck_serial, 0, ctx.key, stored)
            await self._server.send_to_pi(context_token, msg)
            return

        if cmd.kind == Command.SEND_TO_PLUGIN:
            await self._server.send_to_plugin(
                plugin_uuid,
                make_send_to_plugin(action_uuid, context_token, cmd.payload or {}),
            )
            return

        if cmd.kind == Command.LOG_MESSAGE:
            log.info("[PI %s log] %s", context_token,
                     (cmd.payload or {}).get("message", ""))
            return

        log.debug("PI command not handled: %s from %s", cmd.kind, context_token)

    def _decode_image_data_url(self, image_field: str, plugin_uuid: str):
        import base64
        import io
        from PIL import Image
        header, _, b64 = image_field.partition(",")
        mime = header.split(":", 1)[1].split(";", 1)[0] if ":" in header else ""
        raw = base64.b64decode(b64)
        if mime == "image/svg+xml" or raw.lstrip().startswith(b"<"):
            try:
                import cairosvg
                png = cairosvg.svg2png(bytestring=raw, output_width=144, output_height=144)
                return Image.open(io.BytesIO(png)).convert("RGBA")
            except Exception as e:
                log.warning("failed to render SVG setImage for %s: %s", plugin_uuid, e)
                return None
        try:
            return Image.open(io.BytesIO(raw)).convert("RGBA")
        except Exception as e:
            log.warning("failed to decode setImage for %s: %s", plugin_uuid, e)
            return None

    def _update_layers(self, token: str, image=_UNSET, title=_UNSET):
        layers = self._key_layers.setdefault(token, {"image": None, "title": ""})
        if image is not _UNSET:
            layers["image"] = image
        if title is not _UNSET:
            layers["title"] = title

    def _compose_layers(self, mydeck, token: str):
        """Return a PIL Image that layers the current title on top of the image.

        Mirrors Elgato semantics: setImage is the background, setTitle is
        text drawn over it. Both persist independently until replaced.
        """
        from PIL import Image, ImageDraw, ImageFont
        layers = self._key_layers.get(token) or {}
        bg = layers.get("image")
        title = layers.get("title") or ""
        if bg is None:
            canvas = Image.new("RGB", (144, 144), "black")
        else:
            canvas = bg.convert("RGB").resize((144, 144))
        if title:
            lines = title.split("\n")
            longest = max((len(line) for line in lines), default=0) or 1
            base = 28  # Larger base than _render_title_image since canvas is 144, not 72
            font_size = base if longest <= 7 else max(20, int(base * 7 / longest + 0.999))
            draw = ImageDraw.Draw(canvas)
            font = ImageFont.truetype(mydeck.font_path, font_size)
            line_h = font_size + 4
            total_h = line_h * len(lines)
            start_y = max(0, (canvas.height - total_h) // 2) + line_h // 2
            for i, line in enumerate(lines):
                # Draw a black stroke behind white text so it remains readable
                # over any image.
                x = canvas.width / 2
                y = start_y + i * line_h
                draw.text((x, y), font=font, text=line, anchor="mm",
                          fill="white", stroke_width=2, stroke_fill="black")
        return canvas

    def _pil_to_native(self, mydeck, pil_image):
        """Return image in the format expected by update_key_image.

        Mirrors render_key_image: virtual decks (MyDecksManager wrappers)
        call PILHelper.to_native_format internally in their set_key_image, so
        we must pass a PIL Image. Real decks expect pre-converted native bytes.
        """
        from StreamDeck.ImageHelpers import PILHelper
        deck = mydeck.deck
        try:
            scaled = PILHelper.create_scaled_key_image(deck, pil_image, margins=[0, 0, 0, 0], background="black")
        except Exception:
            scaled = pil_image
        if hasattr(deck, 'is_virtual'):
            return scaled
        try:
            return PILHelper.to_native_key_format(deck, scaled)
        except Exception:
            import io
            buf = io.BytesIO()
            scaled.save(buf, format="PNG")
            return buf.getvalue()

    def _render_title_image(self, mydeck, title: str):
        """Render a title string onto a black PIL Image sized for a key.

        Returns a PIL Image (not bytes); the caller must convert to native
        format via _pil_to_native before passing to update_key_image.
        """
        from PIL import Image, ImageDraw, ImageFont

        lines = title.split("\n") if title else [""]
        longest = max((len(line) for line in lines), default=0) or 1

        base = 14
        font_size = base if longest <= 7 else max(10, int(base * 7 / longest + 0.999))

        image = Image.new("RGB", (72, 72), "black")
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype(mydeck.font_path, font_size)

        line_h = font_size + 2
        total_h = line_h * len(lines)
        start_y = max(0, (image.height - total_h) // 2) + line_h // 2
        for i, line in enumerate(lines):
            draw.text(
                (image.width / 2, start_y + i * line_h),
                font=font, text=line, anchor="mm", fill="white",
            )

        return image

    # Thread-safe entry points called from MyDeck main thread
    def _schedule(self, coro):
        if self._loop is None:
            return
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)

        def _report(f):
            if f.cancelled():
                return
            exc = f.exception()
            if exc is not None:
                log.warning("bridge dispatch error: %s", exc)

        fut.add_done_callback(_report)

    def _merged_settings(self, plugin_uuid: str, token: str, provided: Optional[dict]) -> dict:
        """Stored settings win over YAML-provided settings.

        Every event sent to a plugin (willAppear/willDisappear/keyDown/keyUp)
        must carry the plugin's current persisted settings in payload.settings,
        per Elgato protocol. Plugins rely on this to drive per-keystroke state.
        """
        stored = self._settings_store.get(plugin_uuid, token)
        return {**(provided or {}), **stored}

    def will_appear(self, key_ctx: KeyContext, action_uuid: str, settings: dict):
        if self._registry is None:
            return
        entry = self._registry.lookup(action_uuid)
        if entry is None:
            log.warning("unknown action uuid: %s", action_uuid)
            return
        token = key_ctx.to_token()
        self._context_actions[token] = (entry.plugin_uuid, action_uuid)
        merged = self._merged_settings(entry.plugin_uuid, token, settings)
        log.info("willAppear plugin=%s action=%s ctx=%s",
                 entry.plugin_uuid, action_uuid, token)
        self._schedule(self._server.dispatch_will_appear(
            entry.plugin_uuid, action_uuid, key_ctx, merged))

    def will_disappear(self, key_ctx: KeyContext, action_uuid: str, settings: dict):
        if self._registry is None:
            return
        entry = self._registry.lookup(action_uuid)
        if entry is None:
            log.warning("unknown action uuid: %s", action_uuid)
            return
        token = key_ctx.to_token()
        merged = self._merged_settings(entry.plugin_uuid, token, settings)
        self._context_actions.pop(token, None)
        self._key_layers.pop(token, None)
        self._schedule(self._server.dispatch_will_disappear(
            entry.plugin_uuid, action_uuid, key_ctx, merged))

    def key_down(self, key_ctx: KeyContext, action_uuid: str, settings: dict):
        if self._registry is None:
            return
        entry = self._registry.lookup(action_uuid)
        if entry is None:
            log.warning("unknown action uuid: %s", action_uuid)
            return
        merged = self._merged_settings(entry.plugin_uuid, key_ctx.to_token(), settings)
        self._schedule(self._server.dispatch_key_down(
            entry.plugin_uuid, action_uuid, key_ctx, merged))

    def key_up(self, key_ctx: KeyContext, action_uuid: str, settings: dict):
        if self._registry is None:
            return
        entry = self._registry.lookup(action_uuid)
        if entry is None:
            log.warning("unknown action uuid: %s", action_uuid)
            return
        merged = self._merged_settings(entry.plugin_uuid, key_ctx.to_token(), settings)
        self._schedule(self._server.dispatch_key_up(
            entry.plugin_uuid, action_uuid, key_ctx, merged))
