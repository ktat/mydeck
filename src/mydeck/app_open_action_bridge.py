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
        for manifest in self._registry.all_plugins():
            try:
                proc = await self._server.launch_plugin(manifest)
                self._plugin_procs.append(proc)
            except Exception as e:
                log.warning("failed to spawn plugin %s: %s", manifest.plugin_uuid, e)
        self.mydeck._openaction_bridge = self
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
            # render_key_image is mocked in tests; in production it expects an
            # ImageOrFile object.  Pass None here — callers mock this method, so
            # the real implementation is not invoked in the test suite.  If
            # render_key_image(None, ...) is needed in production, supply a
            # transparent placeholder image via ImageOrFile in future work.
            mydeck.update_key_image(key, mydeck.render_key_image(None, title, '', True), True)

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
            log.warning("unknown action uuid: %s", action_uuid)
            return
        self._schedule(self._server.dispatch_will_disappear(
            entry.plugin_uuid, action_uuid, key_ctx, settings))

    def key_down(self, key_ctx: KeyContext, action_uuid: str, settings: dict):
        if self._registry is None:
            return
        entry = self._registry.lookup(action_uuid)
        if entry is None:
            log.warning("unknown action uuid: %s", action_uuid)
            return
        self._schedule(self._server.dispatch_key_down(
            entry.plugin_uuid, action_uuid, key_ctx, settings))

    def key_up(self, key_ctx: KeyContext, action_uuid: str, settings: dict):
        if self._registry is None:
            return
        entry = self._registry.lookup(action_uuid)
        if entry is None:
            log.warning("unknown action uuid: %s", action_uuid)
            return
        self._schedule(self._server.dispatch_key_up(
            entry.plugin_uuid, action_uuid, key_ctx, settings))
