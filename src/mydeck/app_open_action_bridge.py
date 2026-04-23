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
        self._plugin_procs: list = []
        self._started = threading.Event()
        self._settings_store = SettingsStore(self.settings_path)
        self._context_actions: dict = {}  # context_token -> (plugin_uuid, action_uuid)

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
        await self._server.start()
        log.info("OpenAction bridge listening on port %d", self._server.port)
        # Register with MyDeck BEFORE spawning plugins so the attribute is always
        # available to set_key calls that race with plugin startup.
        self.mydeck._openaction_bridge = self
        for manifest in self._registry.all_plugins():
            try:
                proc = await self._server.launch_plugin(manifest)
                self._plugin_procs.append(proc)
            except Exception as e:
                log.warning("failed to spawn plugin %s: %s", manifest.plugin_uuid, e)
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
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    pass
            except Exception:
                pass
        if self._server is not None:
            await self._server.stop()

    async def _on_command(self, plugin_uuid: str, cmd):
        from mydeck.openaction.context import KeyContext
        from mydeck.openaction.protocol import Command, make_did_receive_settings

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

        # Rendering commands: only the bridge's own MyDeck for MVP.
        mydeck = self.mydeck
        if mydeck.deck is None or str(mydeck.deck.id()) != ctx.deck_serial:
            return
        if mydeck.current_page() != ctx.page:
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
            from PIL import Image
            from mydeck.my_decks import ImageOrFile
            placeholder = ImageOrFile(Image.new("RGB", (72, 72), "black"))
            mydeck.update_key_image(key, mydeck.render_key_image(placeholder, title, '', True), True)

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
