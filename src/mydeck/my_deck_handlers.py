"""Handlers / setup / config-writers mixin for MyDeck."""

import logging
import subprocess
import sys
import time
from typing import Any, Callable, Dict, List, NoReturn, Optional, Union, TYPE_CHECKING

from .my_decks_manager import VirtualDeck

if TYPE_CHECKING:
    from .my_decks_app_base import AppBase, BackgroundAppBase


class MyDeckHandlersMixin:
    """Setup, callback, and config-write methods for MyDeck.

    Depends on attributes (`self.deck`, `self.config`, `self._current_page`,
    etc.) and methods (`self.current_page()`, `self.update_key_image()`, ...)
    on MyDeck and MyDeckImageMixin.
    """

    def has_page_key_config(self, name: str) -> bool:
        """return true when page key config exists"""
        return self._PAGE_CONFIG['keys'].get(name) is not None

    # display keys/touchscreen and set key/touchscreen callbacks
    def key_touchscreen_setup(self):
        """setup keys & touchscreen"""
        deck: VirtualDeck = self.deck
        logging.debug("Opened '{}' device (serial number: '{}', fw: '{}', page: '{}')".format(
            deck.deck_type(), deck.get_serial_number(
            ), deck.get_firmware_version(), self.current_page()
        ))

        # Set initial screen brightness to 30%.
        deck.set_brightness(30)

        current_page = self.current_page()

        key_count = self.key_count
        # Set initial key images.
        for key in range(deck.key_count()):
            page_configuration = self.key_config().get(self.current_page())
            if page_configuration is not None:
                if page_configuration.get(key) is not None:
                    logging.debug(
                        "[%s] draw key %d on page %s",
                        deck.id(), key, self.current_page())
                    self.set_key(key, page_configuration.get(key), True)

                    # Register callback function for the time when a key state changes.
                    deck.set_key_callback(
                        lambda deck, key, state: self.key_change_callback(key, state))
        if self.deck.is_touch_interface:
            self.touchscreen_setup()
        if self.deck.is_dial():
            self.dial_setup()

    def touchscreen_setup(self):
        """setup touchscreen"""
        deck: VirtualDeck = self.deck

        current_page = self.current_page()

        page_configuration = self.touchscreen_config().get(self.current_page())
        if page_configuration is not None:
            self.set_touchscreen(page_configuration, True)

        # Register callback function for the time when a key state changes.
        deck.set_touchscreen_callback(
            lambda deck, event, args: self.touchscreen_change_callback(event, args))

    def set_touchscreen(self, conf: dict, use_lock: bool = True):
        """Set touchscreen image"""
        if conf.get('image') is not None:
            self.update_touchscreen_image(conf, use_lock)

    def dial_setup(self):
        """setup dial"""
        deck: VirtualDeck = self.deck

        current_page = self.current_page()

        page_configuration = self.dial_config().get(self.current_page())
        if page_configuration is not None:
            self.set_dial(page_configuration, True)

        # Register callback function for the time when a key state changes.
        deck.set_dial_callback(
            lambda deck, dial_num, event, value: self.dial_change_callback(dial_num, event, value))

    def set_dial(self, conf: dict, use_lock: bool = True):
        """Set dial"""
        # TODO
        pass

    # set key image and label

    def set_key(self, key: int, conf: dict, use_lock: bool = True):
        """Set a key and its configuration."""
        from .my_decks import ImageOrFile  # lazy to avoid circular import
        key = self.abs_key(key)
        deck = self.deck
        if conf is not None:
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
                image_source = conf.get("image")
                icon = ImageOrFile(image_source) if image_source is not None else None
                self.update_key_image(key, self.render_key_image(icon, conf.get(
                    "label") or '', conf.get("background_color") or ''), use_lock)

    def touchscreen_change_callback(self, event, pos: dict):
        """Call a callback according to a touchscreen is touched"""

        deck = self.deck
        conf = self.touchscreen_config().get(self.current_page())
        if conf is not None and (command := conf.get("app_command")) is not None:
            found = False
            if self.config is not None:
                for app in self.config.apps:
                    if not app.is_touchscreen_app():
                        continue

                    if app.page is not None and self.current_page() in app.page:
                        for key in app.touch_command.keys():
                            if command == key:
                                found = True
                                cmd = app.touch_command[key]
                                cmd(app, event, pos)
                                break
                    if found:
                        break

    def dial_change_callback(self, dial_num: int, event, value: int):
        """Call a callback according to a dial is changed"""

        deck = self.deck
        dial_conf = self.dial_config().get(self.current_page())
        if dial_conf is None:
            return

        conf: Optional[dict] = dial_conf.get(dial_num)
        if conf is not None and (command := conf.get("app_command")) is not None:
            found = False
            if self.config is not None:
                for app in self.config.apps:
                    if not app.is_dial_app():
                        continue

                    if app.page_dial is not None and app.page_dial.get(self.current_page()) == dial_num:
                        for key in app.dial_command.keys():
                            if command == key:
                                found = True
                                cmd = app.dial_command[key]
                                cmd(app, dial_num, event, value)
                                break
                    if found:
                        break

    # Prints key state change information, updates rhe key image and performs any
    # associated actions when a key is pressed.

    def key_change_callback(self, key: int, state: bool):
        """Call a callback according to a key is pushed"""

        deck = self.deck
        if deck is not None:
            # Print new key state
            self.debug("Key %s = %s" % (key, state))

        # Check if the key is changing to the pressed state.
        if state:
            current_page: str = self.current_page()
            conf: Optional[dict] = None
            if self.key_config().get(current_page) is not None:
                conf = self.key_config()[current_page].get(key)

            # When an exit button is pressed, close the application.
            if conf is not None:
                if conf.get("exit") == 1:
                    # Use a scoped-with on the deck to ensure we're the only thread
                    # using it right now.

                    with deck:
                        # Reset deck, clearing all button images.
                        deck.reset()

                        # informa program is end to other thread
                        self._exit = True

                        if self.config is not None:
                            for app in self.config.apps:
                                self.debug("stop app: %s" % app.name())
                                app.stop_app()
                            for app in self.config.background_apps:
                                self.debug("stop background app: %s" % app.name())
                                app.stop(True)

                        time.sleep(2)

                        # Close deck handle, terminating internal worker threads.
                        deck.close()

                    # Exit key on the physical deck -> terminate the whole
                    # mydeck process. sys.exit here (vs. os._exit) lets atexit
                    # hooks run on the main thread; daemon threads are killed.
                    sys.exit()

                elif type(conf.get("command")) is str and self._game_command.get(conf.get("command")):
                    command = self._game_command.get(conf.get("command"))
                    if command is not None:
                        command(conf)

                elif conf.get("name") == "alert":
                    with deck:
                        self.set_alert_off()
                        self.key_touchscreen_setup()

                elif conf.get("command"):
                    cmd = conf["command"]
                    subprocess.Popen(cmd)

                elif conf.get("chrome"):
                    chrome: list = conf['chrome']
                    chrome_command = ['google-chrome',
                                      '--profile-directory=' + chrome[0], chrome[1]]
                    subprocess.Popen(chrome_command)
                else:
                    command = conf.get("app_command")
                    if command is not None:
                        found = False
                        if self.config is not None:
                            for app in self.config.apps:
                                if not app.is_key_app():
                                    continue

                                placement = None
                                if app.page_key is not None:
                                    placement = app.page_key.get(self.current_page())
                                # match the pressed key (key 0 is valid, so no truthiness check)
                                if placement is not None and placement == key:
                                    for cmd_name in app.key_command.keys():
                                        if command == cmd_name:
                                            found = True
                                            cmd = app.key_command[cmd_name]
                                            cmd(app)
                                            break
                                if found:
                                    break

                page_name = conf.get("change_page")
                if page_name is not None:
                    if page_name == "@previous":
                        self.set_current_page(
                            self.pop_last_previous_page(), False)
                    else:
                        self.set_current_page(page_name)

    def set_key_config(self, conf):
        """Set key configuration."""
        if conf is None:
            conf = {}
        self._PAGE_CONFIG['keys'] = conf

    def set_dial_config(self, conf):
        """Set dial configuration."""
        if conf is None:
            conf = {}
        self._PAGE_CONFIG['dials'] = conf

    def set_touchscreen_config(self, conf):
        """Set touchscreen configuration."""
        if conf is None:
            conf = {}
        self._PAGE_CONFIG['touch'] = conf

    def set_command_config(self, page: str, conf):
        """Set page command configuration."""
        if conf is None:
            conf = {}
        self._PAGE_CONFIG['commands'][page] = conf

    def set_game_key(self, key: int, conf: dict):
        """Set game key configuration for one key"""
        key = self.abs_key(key)
        self._GAME_KEY_CONFIG[key] = conf
        self.set_key(key, conf, False)

    def add_game_key_conf(self, configs: list):
        """Add game confiruration for keys"""
        from .my_decks import ROOT_DIR  # lazy to avoid circular import
        key_config = self.key_config()

        page_index: int = 1
        page_name_default: str = "@GAME"
        page_name: str = page_name_default
        while True:
            if key_config.get(page_name) is None or len(key_config[page_name].keys()) < self.key_count:
                break

            page_index += 1
            page_name = page_name_default + str(page_index)

        prev_conf = {
            "change_page": "@previous",
            "image": ROOT_DIR+"/Assets/back.png",
            "label": "Back",
        }

        if key_config.get(page_name) is None:
            key_config[page_name] = {
                self.key_count - 1: prev_conf
            }

        for conf in configs:
            start_index = len(key_config[page_name].keys()) - 1
            if start_index >= (self.key_count - 2):
                old_page_name = page_name
                start_index = 0
                page_index += 1
                page_name = page_name_default + str(page_index)
                key_config[old_page_name][self.key_count - 2] = {
                    "change_page": page_name,
                    "image": ROOT_DIR+"/Assets/game.png",
                    "label": "game" + str(page_index),
                }
                key_config[page_name] = {
                    self.key_count - 1: prev_conf
                }

            key_config[page_name][start_index] = conf

    def add_game_command(self, name: str, command):
        """Add command for a game"""
        self._game_command[name] = command

    def set_alert_key_conf(self, conf: dict):
        """Set configuration of keys on alert"""
        key_config = self.key_config()
        key_config['~ALERT'] = conf

    def exit_game(self):
        """call it on exiting game"""
        self.set_game_status_off()
        self.set_current_page(self.pop_last_previous_page(), False)
        self._GAME_KEY_CONFIG = {}

    def set_key_conf(self, page: str, key: int, conf: dict):
        """Set a configuration of a key"""
        if self._PAGE_CONFIG.get('keys') is None:
            self._PAGE_CONFIG['keys'] = {}
        if self._PAGE_CONFIG['keys'].get(page) is None:
            self._PAGE_CONFIG['keys'][page] = {}
        self._PAGE_CONFIG['keys'][page][key] = conf

    def set_touchscreen_conf(self, page: str, conf: dict):
        """Set a configuration of a touchscreen"""
        if self._PAGE_CONFIG.get('touch') is None:
            self._PAGE_CONFIG['touch'] = {}
        if self._PAGE_CONFIG['touch'].get(page) is None:
            self._PAGE_CONFIG['touch'][page] = {}

        self._PAGE_CONFIG['touch'][page] = conf

    def set_dial_conf(self, page: str, dial_num: int, conf: dict):
        """Set a configuration of a touchscreen"""
        if self._PAGE_CONFIG.get('dials') is None:
            self._PAGE_CONFIG['dials'] = {}
        if self._PAGE_CONFIG['dials'].get(page) is None:
            self._PAGE_CONFIG['dials'][page] = {}

        self._PAGE_CONFIG['dials'][page][dial_num] = conf
