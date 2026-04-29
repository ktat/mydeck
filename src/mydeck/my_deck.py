"""MyDeck core class. Methods are split across mixins:
- MyDeckImageMixin (image / rendering)
- MyDeckHandlersMixin (setup / callbacks / config writers)
"""

import logging
import os
import sys
import threading
import time
import traceback
from typing import Any, Callable, Dict, List, NoReturn, Optional, TYPE_CHECKING, Union

import datetime
import subprocess

from PIL import Image, ImageDraw, ImageFont
from StreamDeck.Devices import StreamDeckOriginalV2

from .lock import Lock
from .my_deck_handlers import MyDeckHandlersMixin
from .my_deck_image import MyDeckImageMixin
from .my_decks_manager import VirtualDeck, DeckOutputWebHandler

if TYPE_CHECKING:
    from .my_decks_app_base import App, AppBase, BackgroundAppBase, HookAppBase
    from .my_decks import Config, ImageOrFile


class MyDeck(MyDeckImageMixin, MyDeckHandlersMixin):
    """Class to control a device like STREAM DECK."""
    mydecks: 'MyDecks'

    @staticmethod
    def _find_font(candidates: list[str]) -> str:
        """Return the first font path that exists, or the first candidate as fallback."""
        for path in candidates:
            if os.path.isfile(path):
                return path
        logging.warning(
            "No font found from candidates: %s. "
            "Please set 'font_path' in your config, or install a font package.", candidates)
        return candidates[0]

    def __init__(self, opt: dict, server_port: int):
        from .my_decks import ExceptionNoDeckGiven, Config
        deck: Optional[VirtualDeck] = opt.get('deck')
        if deck is None:
            logging.critical("deck is required for MyDeck constructor")
            raise ExceptionNoDeckGiven()
        self.server_port: int = server_port
        self.deck: VirtualDeck = deck
        self.key_count: int = self.deck.key_count()
        self.columns: int = self.deck.columns()
        self.font_path = self._find_font([
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",          # Debian/Ubuntu: fonts-freefont-ttf
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",  # Debian/Ubuntu: fonts-liberation
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",          # Debian/Ubuntu: fonts-dejavu-core
            "/usr/share/fonts/TTF/DejaVuSans.ttf",                      # Arch Linux
            "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf",        # Fedora/RHEL
            "/System/Library/Fonts/Helvetica.ttc",                      # macOS
            "/System/Library/Fonts/Arial.ttf",                          # macOS
        ])
        self.config: Optional['Config'] = None
        self.is_background_thread_started: bool = False
        self._alert_func: Optional[Callable] = None
        self._exit: bool = False
        self._current_page: str = '@HOME'
        self._previous_pages: list[str] = ['@HOME']
        self._pre_disconnect_page: Optional[str] = None
        self._previous_window: str = ''
        self._in_alert: bool = False
        self._game_status: bool = False
        self._game_command: dict = {}
        self._PAGE_CONFIG: dict = {
            'keys': {},
            'commands': {},
            'touch': {},
            'dials': {},
        }
        self._KEY_ACTION_APP: dict = {}
        self._GAME_KEY_CONFIG: dict = {}
        self._config_file: str = ''
        self._config_file_mtime: float = 0
        self.page_apps: dict[str, list['AppBase']] = {}

        myname: Optional[str] = opt.get('myname')
        if myname is not None:
            self.myname = myname
        mydecks = opt.get('mydecks')
        if mydecks is not None:
            self.mydecks = mydecks
        if opt.get('alert_func') is not None:
            self._alert_func = opt['alert_func']
        if opt.get("font_path") is not None:
            self.font_path = opt["font_path"]
        if opt.get("config") is not None:
            self._config_file = opt.get('config') or ''
            self.config = Config(self, self._config_file)

    def debug(self, message: str):
        """Output debug message"""
        logging.debug("[%s] %s in %s at %s", self.deck.id(
        ), message, self.current_page(), datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def init_deck(self):
        """Initialize deck. Reflect configuration and setup keys."""
        if self.config is not None:
            self.config.reflect_config()

        self.key_touchscreen_setup()

    def in_game_status(self) -> bool:
        """True if deck is in game mode"""
        return self._game_status

    def in_alert(self) -> bool:
        """True if deck is in alert mode"""
        return self._in_alert

    def key_config(self):
        """Return deck key configuration"""
        if self._config_file != '':
            self.config.reflect_config()

        return self._PAGE_CONFIG.get('keys')

    def dial_config(self):
        """Return deck dial configuration"""
        if self._config_file != '':
            self.config.reflect_config()

        return self._PAGE_CONFIG.get('dials')

    def touchscreen_config(self):
        """Return deck touchscreen configuration"""
        if self._config_file != '':
            self.config.reflect_config()

        return self._PAGE_CONFIG.get('touch')

    def run_page_command(self, page):
        """Return deck page command configuration"""
        page_commands = self._PAGE_CONFIG.get('commands')
        if page_commands is not None:
            commands = page_commands.get(page)
            if commands is not None:
                for cmd in commands:
                    subprocess.Popen(cmd)

    def set_alert_on(self):
        """Set deck alert status on"""
        self._in_alert = True

    def set_alert_off(self):
        """Set deck alert status off"""
        self._in_alert = False

    def set_game_status_on(self):
        """Set deck game status on"""
        self._game_status = True

    def set_game_status_off(self):
        """Set deck game status off"""
        self._game_status = False

    def previous_page(self) -> str:
        """Return previous page"""
        if len(self._previous_pages) > 0:
            return self._previous_pages[-1]
        else:
            return ''

    def pop_last_previous_page(self) -> str:
        """Return and remove last previous page."""
        if len(self._previous_pages) > 0:
            return self._previous_pages.pop(-1)
        else:
            return '@HOME'

    def set_previous_page(self, name: str):
        """Set given page name as previous page"""
        if name[0] != '~' and (len(self._previous_pages) == 0 or self._previous_pages[-1] != name):
            self._previous_pages.append(name)

        self.debug("previous page %s" % self._previous_pages)

    def current_page(self) -> str:
        """Return current page name"""
        return self._current_page

    def _set_current_page(self, name: str):
        """Set current page name"""
        self._current_page = name
        DeckOutputWebHandler.id_current_page[self.deck.id()] = name

    def set_current_page_without_setup(self, name: str, add_previous: bool = True):
        """Set given page name as current_page. but don't setup keys."""
        if add_previous:
            self.set_previous_page(self.current_page())
        self.set_alert_off()
        self._set_current_page(name)

    def set_current_page(self, name: str, add_previous: bool = True):
        """Set given page name as current_page and setup keys."""
        if name[0] != "~ALERT":
            self.set_alert_off()
        if self.deck is not None and name != self._current_page:
            if not self.has_page_key_config(name):
                pass
            if add_previous:
                self.set_previous_page(self._current_page)
            self._set_current_page(name)
            Lock.do_with_lock(self.deck.get_serial_number(),
                              lambda: self.stop_working_apps())
            self.set_game_status_off()
            self.deck.reset_keys()
            self.run_page_command(name)
            self.run_hook_apps('page_change')
            if self.config is not None:
                self.threading_apps(
                    self.config.apps, self.config.background_apps)
            self.key_touchscreen_setup()

        # run hook page_change_any whenever set_current_page is called.
        self.run_hook_apps('page_change_any')

    def on_disconnect(self) -> None:
        """Called when the physical device is detected as disconnected.

        Saves the current page and switches to the reserved ``~DISCONNECTED``
        page. Injects a home-key config on key 0 so the Web UI still has a
        way to navigate back to ``@HOME`` while the physical deck is offline;
        existing app threads observe the page change via ``check_to_stop``
        and exit cleanly.
        """
        if self._current_page == '~DISCONNECTED':
            return
        self._pre_disconnect_page = self._current_page
        logging.info("[%s] device disconnected; saving page %s",
                     self.deck.id(), self._current_page)
        self._ensure_disconnected_page_config()
        self.set_current_page('~DISCONNECTED', add_previous=False)

    def _ensure_disconnected_page_config(self) -> None:
        """Ensure the ``~DISCONNECTED`` page has a home key on index 0.

        The page is otherwise empty by design; without this, the Web UI shows
        no clickable keys and the user cannot return to ``@HOME`` until the
        device reconnects.
        """
        from .my_decks import ROOT_DIR  # lazy to avoid circular import
        keys_config = self._PAGE_CONFIG.setdefault('keys', {})
        page_keys = keys_config.setdefault('~DISCONNECTED', {})
        if 0 not in page_keys:
            page_keys[0] = {
                'image': ROOT_DIR + '/Assets/home.png',
                'label': 'HOME',
                'change_page': '@HOME',
            }

    def on_reconnect(self) -> None:
        """Called when the physical device is re-attached via supervisor.

        reattach() has already re-opened the device, issued reset()+
        set_brightness(), and re-registered callbacks. Here we restore the
        application-level page state directly: reset key images, redraw for
        the pre-disconnect page, and restart the per-page apps. Bypasses
        set_current_page so we can log each step and avoid the full
        page-change machinery that may hang on stale state.
        """
        target: str = self._pre_disconnect_page or '@HOME'
        self._pre_disconnect_page = None
        logging.info("[%s] device reconnected; restoring page %s",
                     self.deck.id(), target)

        # Restore the logical current_page without running the full
        # set_current_page side effects.
        self._set_current_page(target)
        self.set_alert_off()
        self.set_game_status_off()

        logging.info("[%s] reconnect: resetting keys", self.deck.id())
        try:
            self.deck.reset_keys()
        except Exception as e:
            logging.error("reconnect reset_keys failed: %s", e)

        logging.info("[%s] reconnect: drawing keys for %s",
                     self.deck.id(), target)
        try:
            self.key_touchscreen_setup()
        except Exception as e:
            logging.error("reconnect key_touchscreen_setup failed: %s", e)

        logging.info("[%s] reconnect: restarting page apps", self.deck.id())
        if self.config is not None:
            try:
                self.threading_apps(
                    self.config.apps, self.config.background_apps)
            except Exception as e:
                logging.error("reconnect threading_apps failed: %s", e)

        logging.info("[%s] reconnect: complete", self.deck.id())

    def set_previouse_page_if_current_page_is_empty(self):
        """Set previous page if current page is empty."""
        current_page: str = self.current_page()

        key_config = self.config._config_content["page_config"].get(
            current_page)
        apps_config = self.config._config_content["apps"]
        set_previouse = True
        if key_config is not None and key_config.get("keys") and len(key_config["keys"].keys()) > 0:
            set_previouse = False

        if apps_config is not None:
            for app in apps_config:
                option = app.get("option")
                if option is None:
                    continue
                if option.get("page") is not None and current_page in option["page"]:
                    set_previouse = False
                    break
                if option.get("page_key") is not None and current_page in option["page_key"]:
                    set_previouse = False
                    break
                if option.get("page_dial") is not None and current_page in option["page_dial"]:
                    set_previouse = False
                    break

        if set_previouse:
            self.set_current_page(self.pop_last_previous_page(), False)

    def stop_working_apps(self):
        """Try to stop working apps and wait until all of them are stopped."""
        for app in self.config.apps:
            app.stop_app()

    # handler to notify alert
    def handler_alert(self):
        """Handling alert is caused."""
        self.set_alert_on()
        self.set_current_page("~ALERT", False)

    # handler to stop alert
    def handler_alert_stop(self):
        """Handling alert is stopped."""
        if self.current_page() == "~ALERT":
            self.set_alert_off()
            self.set_current_page(self.pop_last_previous_page(), False)

    def threading_apps(self, apps: List['AppBase'], background_apps: List['BackgroundAppBase']):
        """Run apps in thread"""
        from .app_web_server import AppWebServer

        if self._exit:
            return

        page_name = self.current_page()
        if (page_apps := self.page_apps.get(page_name)) is not None:
            while len(page_apps) > 0:
                app: 'AppBase' = page_apps.pop()
                app.debug("try to stop!")
                app.stop_app()

        self.page_apps[page_name] = []

        for app in filter(lambda app: app.is_in_target_page() and app.can_work(), apps):
            if app.use_thread:
                app.init_app_flag()
                t = threading.Thread(
                    target=lambda: app.start(), args=())
                t.start()
                self.page_apps[page_name].append(app)
                if app.use_trigger:
                    app.trigger.set()
            else:
                app.key_setup()

        if not self.is_background_thread_started:
            self.is_background_thread_started = True
            for bg_app in background_apps:
                self.debug("start background app: %s" % bg_app.name())
                t = threading.Thread(target=lambda: bg_app.start(), args=())
                t.start()

        # Automatically load AppWebServer when it is not loaded yet.
        if AppWebServer.IS_ALREADY_WORKING is False:
            web_server_app = AppWebServer(self, {"port": self.server_port})
            t = threading.Thread(
                target=lambda: web_server_app.start(), args=())
            t.start()

        t2 = threading.Thread(
            target=lambda: self.update_config(), args=())
        t2.start()

    def abs_key(self, key: int) -> int:
        """If key is negative number, chnage it as positive number"""
        if key < 0:
            key = self.key_count + key
        return key

    def run_hook_apps(self, on: str):
        hook_apps: List['HookAppBase'] = []
        if self.config is not None:
            apps = self.config.hook_apps.get(on)
            if apps is not None:
                for app in apps:
                    app.execute_on_hook()

    def update_config(self):
        from .my_decks_manager import MyDecksManager
        sn: str = self.deck.get_serial_number()

        while True:
            if self.deck.is_closed():
                break

            if MyDecksManager.ConfigQueue.get(sn) is not None:
                data: dict = MyDecksManager.ConfigQueue[sn].get()
                if data.get('exit'):
                    break

                target_page = data.get("target_page", self.current_page())

                save: bool = False
                if data.get("delete"):
                    if data.pop("for_touchscreen", False):
                        save = self.config.delete_touchscreen_config(
                            target_page)
                    elif data.pop("for_dial", False):
                        save = self.config.delete_dial_app_config(
                            target_page, data)
                    else:
                        self.deck.set_key_image(data['key'], None)
                        save = self.config.delete_key_app_config(
                            target_page, data)

                elif data.get("app"):
                    save = self.config.update_app_config_content(
                        target_page, data)
                elif data.get("games"):
                    save = self.config.update_game_config(data.get("games"))
                else:
                    save = self.config.update_page_config_content(
                        target_page, data)

                if save:
                    self.config.save_config()
                    self.config.reflect_config(True)
                    self.set_previouse_page_if_current_page_is_empty()

        self.debug("update_config is exited")
