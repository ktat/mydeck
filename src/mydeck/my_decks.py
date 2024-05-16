"""Base module to handle STREAM DECK devices"""

from copy import deepcopy
import wand.image
import re
import subprocess
import os
import sys
import yaml
import time
import threading
import requests
import os.path
import importlib
import logging
import traceback
import shutil
import datetime
import time
import queue
from .my_decks_manager import VirtualDeck, DeckOutputWebHandler

from cairosvg import svg2png
from typing import Any, NoReturn, List, TYPE_CHECKING, Optional, Callable, Dict, Union
from PIL import Image, ImageDraw, ImageFont
from StreamDeck.ImageHelpers import PILHelper
from StreamDeck.Devices import StreamDeckOriginalV2
from .lock import Lock

DEFAULT_PORT: int = 3000
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

if TYPE_CHECKING:
    from .my_decks_app_base import App, AppBase, BackgroundAppBase, HookAppBase


class ExceptionInvalidMyDecksConfig(Exception):
    pass


class MyDecks:
    """The class to manage several STREAM DECK like devices.

    This class manages insteaces of MyDeck class.
    """
    mydecks: Dict[str, 'MyDeck'] = {}

    def __init__(self, config: dict):
        """
        config dict takes the following keys:
        - log_level
        - server_port
        - decks and configs or config

        If you have only one STREAM DECK device, use config. If you have several devices, use decks and configs.
        decks is the following structure.
        {
           name1: 'serial number of deck1',
           name2: 'serial number of deck2',
        }

        configs is the following structure.
        {
           name1: {
             alert_func: function_name_for_alert,
             file: '/path/to/config1.yml'
           },
           name2: {
             file: '/path/to/config2.yml'
           },
        }

        config is the following structure.
        {
           alert_func: function_name_for_alert,
           file: '/path/to/config1.yml'
        }

        """
        self.vdeck_config: Any[None, str] = config.get('vdeck_config')
        if self.vdeck_config is not None and type(self.vdeck_config) is not str:
            raise (ExceptionInvalidMyDecksConfig)

        self._one_deck_only: bool = False
        self.config: Optional[dict]
        self.decks: Optional[dict] = config.get('decks')
        self.server_port: int = config.get('server_port') or DEFAULT_PORT
        self.configs: Optional[dict] = config.get('configs')
        if self.decks is None and self.configs is None:
            self.config = config.get('config')
            self._one_deck_only = True
        log_level: Optional[str] = config.get('log_level')
        if log_level is not None:
            logging.basicConfig(level=log_level)
        else:
            logging.basicConfig(level=logging.INFO)

    def start_decks(self, no_real_device: bool = False) -> NoReturn:
        """Start and display images to buttons according to configuration."""
        from .my_decks_manager import MyDecksManager
        streamdecks = MyDecksManager(self.vdeck_config, no_real_device).devices
        logging.info("Found {} Stream Deck(s).\n".format(len(streamdecks)))

        for index, deck in enumerate(streamdecks):
            # if not deck.is_visual():
            # continue

            serial_number: str = deck.get_serial_number()
            if self._one_deck_only:
                if self.config is not None:
                    alert_func: Optional[Callable] = self.config.get(
                        'alert_func')
                    config_file: Optional[str] = self.config.get('file')
                    mydeck = MyDeck({
                        'mydecks': self,
                        'myname': 'mydeck',
                        "deck": deck,
                        'alert_func': alert_func,
                        'config': config_file
                    }, self.server_port)
                    self.mydecks[serial_number] = mydeck
                    mydeck.init_deck()
                    break
                else:
                    logging.warning(
                        "config{file: '/path/to/config_file'} is required")
                    raise (ExceptionNoConfig)
            elif self.decks is not None:
                sn_alias = self.decks.get(serial_number)
                configs = self.configs
                if sn_alias is not None and configs is not None:
                    sn_config = configs.get(sn_alias)
                    if sn_config is not None:
                        mydeck = MyDeck({
                            'mydecks': self,
                            'myname': sn_alias,
                            "deck": deck,
                            'alert_func': sn_config.get('alert_func'),
                            'config': sn_config.get('file'),
                        }, self.server_port)
                        self.mydecks[sn_alias] = mydeck
                        mydeck.init_deck()
                else:
                    logging.warning(
                        "config is not found for device: {}".format(serial_number))
            else:
                logging.warning("config or (decks and configs) is required")
                raise (ExceptionNoConfig)

        # Wait until all application threads have terminated (for this example,
        # this is when all deck handles are closed).
        for t in threading.enumerate():
            if t != threading.current_thread():
                try:
                    t.join()
                except RuntimeError as e:
                    logging.critical("Error in start_decks {}".format(e))

        logging.info("start_decks end!")
        sys.exit()

    def list_mydecks(self) -> List['MyDeck']:
        """return list of MyDeck instances"""
        return list(self.mydecks.values())

    def list_other_mydecks(self, mydeck: 'MyDeck') -> List['MyDeck']:
        """return list of MyDeck instances"""
        myname = mydeck.myname
        return list(filter(lambda mydeck: mydeck.myname != myname, self.mydecks.values()))

    def mydeck(self, name: str) -> Optional['MyDeck']:
        """Pass name of the device and return the correspond MyDeck instance."""
        mydeck = self.mydecks.get(name)
        if mydeck is not None:
            return mydeck
        else:
            logging.warning('mydeck is None: {}'.format(name))
        return None


class ExceptionNoConfig(Exception):
    """Exception when no configuration is given"""
    pass


class ExceptionNoDeckGiven(Exception):
    """Exception when no deck is given"""
    pass


class MyDeck:
    """Class to control a device like STREAM DECK."""
    mydecks: MyDecks

    def __init__(self, opt: dict, server_port: int):
        deck: Optional[VirtualDeck] = opt.get('deck')
        if deck is None:
            logging.critical("deck is required for MyDeck constructor")
            raise (ExceptionNoDeckGiven)
        self.server_port: int = server_port
        self.deck: VirtualDeck = deck
        self.key_count: int = self.deck.key_count()
        self.columns: int = self.deck.columns()
        self.font_path = "/usr/share/fonts/truetype/freefont/FreeSans.ttf"
        self.config: Optional['Config'] = None
        self.is_background_thread_started: bool = False
        self._alert_func: Optional[Callable] = None
        self._exit: bool = False
        self._current_page: str = '@HOME'
        self._previous_pages: list[str] = ['@HOME']
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
        self.page_apps: dict[str, list[AppBase]] = {}

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
        DeckOutputWebHandler.idCurrentPage[self.deck.id()] = name

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
                self.update_key_image(key, self.render_key_image(ImageOrFile(conf["image"]), conf.get(
                    "label") or '', conf.get("background_color") or ''), use_lock)

    def determine_image_url(self, image_url: Optional[str], url: Optional[str]) -> Optional[str]:
        """Return url for key image"""
        if image_url is None and url is not None:
            image_url = re.sub(
                r'^(https?://[^/]+).*$', '\g<1>/favicon.ico', url)

        return image_url

    def image_url_to_file_name(self, image_url: str) -> str:
        """Return file name from url"""
        icon_name = re.sub(r'^https?://', '', image_url)
        icon_name = re.sub(r'[&=?/.]', '-', icon_name)
        ext = re.sub(r'.+(\.\w+)$', '\g<1>', image_url)
        return '/tmp/' + 'mydeck-' + self.myname + icon_name + ext

    def image_url_to_image(self, conf: Optional[dict], url: Optional[str] = None):
        """If conf has image_url and get it and then save as the file and set its name as image of conf."""
        image_url = None
        icon_file = None
        if conf is not None:
            image_url = self.determine_image_url(conf.get('image_url'), url)
        else:
            conf = {}

        if image_url is not None:
            icon_file_name = self.image_url_to_file_name(image_url)
            icon_file = self.save_image(image_url, icon_file_name)

        if icon_file is not None:
            conf["image"] = icon_file
        else:
            conf["image"] = ROOT_DIR+"/Assets/world.png"

    def save_image(self, icon_url: str, icon_file: str) -> Optional[str]:
        """Get image from icon_url and save it to icon_file"""
        if os.path.exists(icon_file) is False:
            res = requests.get(icon_url)
            if res.status_code == requests.codes.ok:
                icon_data = res.content
                l = Lock(icon_file)
                l.wait()
                if icon_url[-3:len(icon_url)] == 'svg':
                    icon_file = icon_file[0:-4] + '.png'
                    svg2png(bytestring=icon_data, write_to=icon_file)
                    l.unlock()
                else:
                    with open(icon_file, mode="wb") as f:
                        f.write(icon_data)
                        l.unlock()
                if self.check_icon_file(icon_file):
                    return icon_file
        else:
            return icon_file

        return None

    def check_icon_file(self, file_path: str) -> bool:
        """Check whether file_path is image or not"""
        try:
            with wand.image.Image(filename=file_path):
                return True
        except Exception as e:
            self.debug("Error in check_icon_file: {}".format(e))
            os.rename(file_path, file_path + '.back')
            return False

    # change touchscreen image
    def update_touchscreen_image(self, conf: dict, use_lock: bool = True):
        """Update touchscreen image"""
        deck: VirtualDeck = self.deck
        x: int = conf.get("x") or 0
        y: int = conf.get("y") or 0
        width: int = conf.get("width") or 800
        height: int = conf.get("height") or 100
        image = self.render_touchscreen_image(ImageOrFile(conf["image"]))
        if deck is not None:
            if use_lock:
                Lock.do_with_lock(deck.get_serial_number(),
                                  lambda: deck.set_touchscreen_image(image, x, y, width, height))
            else:
                deck.set_touchscreen_image(image, x, y, width, height)

    # change key image
    def update_key_image(self, key: int, image: str, use_lock: bool = True):
        """Update image of key"""
        # to prevent corrupt image drawn in key.
        if (deck := self.deck) is not None:
            key = self.abs_key(key)
            if use_lock:
                # logging.debug("update_key_image: %s => %d" % (self.myname, key))
                # Update requested key with the generated image.
                Lock.do_with_lock(self.deck.get_serial_number(),
                                  lambda: deck.set_key_image(key, image))
            else:
                deck.set_key_image(key, image)

    # render touchscreen image
    def render_touchscreen_image(self, image_filename_or_object: 'ImageOrFile'):
        """Render touchscreen image with image."""
        deck = self.deck
        image = PILHelper.create_scaled_touchscreen_image(
            deck, image_filename_or_object.image, margins=[0, 0, 0, 0], background="black")

        if hasattr(self.deck, 'is_virtual'):
            return image
        else:
            return PILHelper.to_native_format(deck, image)

    # render key image and label
    def render_key_image(self, icon_filename_or_object: 'ImageOrFile', label: str = '', bg_color: str = '', no_label: bool = False):
        """Render key image with image, label and background color."""
        deck = self.deck
        font_bg_color = "white"
        if bg_color == '' or bg_color == "black":
            bg_color = "black"
        else:
            font_bg_color = "black"
        if label == '':
            label = ""

        icon: Image.Image = Image.Image()
        if icon_filename_or_object.is_file:
            icon = Image.open(icon_filename_or_object.file)
        else:
            icon = icon_filename_or_object.image

        margins = [0, 0, 20, 0]
        if no_label:
            margins = [0, 0, 0, 0]

        image = PILHelper.create_scaled_image(
            deck, icon, margins=margins, background=bg_color)

        draw = ImageDraw.Draw(image)
        if no_label is False:
            font_size = 14
            if len(label) > 7:
                font_size = int(14 * 7 / len(label) + 0.999)
            font = ImageFont.truetype(self.font_path, font_size)
            draw.text((image.width / 2, image.height - 5), font=font,
                      text=label, anchor="ms", fill=font_bg_color)

        if hasattr(self.deck, 'is_virtual'):
            return image
        else:
            return PILHelper.to_native_format(deck, image)

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
                                app._stop = True

                        time.sleep(2)

                        # Close deck handle, terminating internal worker threads.
                        deck.close()

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

                                if app.page_key is not None and app.page_key.get(self.current_page()):
                                    for key in app.key_command.keys():
                                        if command == key:
                                            found = True
                                            cmd = app.key_command[key]
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

    def threading_apps(self, apps: List['AppBase'], background_apps: List['BackgroundAppBase']):
        """Run apps in thread"""
        from .app_web_server import AppWebServer

        if self._exit:
            return

        page_name = self.current_page()
        if (page_apps := self.page_apps.get(page_name)) is not None:
            while len(page_apps) > 0:
                app: AppBase = page_apps.pop()
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
        sys.exit()


class Config:
    """STREAM DECK Configuration Class"""

    def __init__(self, mydeck: 'MyDeck', file: str):
        """Pass MyDeck instance as mydeck and configuration file as file"""
        self._file_mtime: float = 0
        self._file: str = ''
        self._config_content_origin: dict = {}
        self._config_content: dict = {}
        self._loaded: dict = {}
        self.conf: dict = {}
        self.apps: List['AppBase'] = []
        self.background_apps: List['BackgroundAppBase'] = []
        self.mydeck: 'MyDeck'
        self.mydeck = mydeck
        self.key_count = mydeck.key_count
        self._file = file

    def save_config(self):
        shutil.copy(self._file, self._file + '.backup')

        with open(self._file, 'w') as f:
            try:
                yaml.safe_dump(self._config_content_origin, f)
                f.close()
            except Exception as e:
                shutil.move(self._file + '.backup', self._file)
                logging.critical("Error in load: %s", e)
                logging.debug(traceback.format_exc())

    def reflect_config(self, force: bool = False):
        """Read configuration file and reset applications and parse content of the configuration file and run apps"""
        loaded = self.load(force)
        if loaded is not None:
            try:
                self.reset_apps()
                self.parse(loaded)
                self.mydeck.threading_apps(self.apps, self.background_apps)
                self.mydeck.key_touchscreen_setup()
            except Exception as e:
                logging.critical("Error in reflect_config: %s", e)
                logging.debug(traceback.format_exc())
                return None

    def load(self, force: bool = False):
        """Load the configuration file, If the file is newer than read before, return the content of the configuration file. Or return None."""
        statinfo = os.stat(self._file)
        if force or self._file_mtime < statinfo.st_mtime:
            self._file_mtime = statinfo.st_mtime
            with open(self._file) as f:
                try:
                    self._config_content_origin = yaml.safe_load(f)
                    self._config_content = deepcopy(
                        self._config_content_origin)
                    return self._config_content
                except Exception as e:
                    logging.critical("Error in load: %s", e)
                    logging.debug(traceback.format_exc())

        return None

    def delete_touchscreen_config(self, page: str) -> bool:
        app_configs: list[dict] = self._config_content_origin.get("apps", [])
        new_app_configs: list[dict] = []
        modified = False
        for app_config in app_configs:
            if app_config.get("option"):
                pages: list = app_config["option"].get("page", [])
                if page in pages:
                    modified = True
                    pages.remove(page)
                if len(pages) > 0:
                    app_config["option"]["page"] = pages
                    new_app_configs.append(app_config)
                else:
                    new_app_configs.append(app_config)
            else:
                modified = True

        if modified:
            self._config_content_origin["apps"] = new_app_configs

        return modified

    def delete_dial_app_config(self, page: str, data: dict) -> bool:
        dial_str: Optional[str] = data.pop('dial', None)

        if dial_str is None or re.match('\D', str(dial_str)) is not None:
            return False
        dial: int = int(dial_str)
        return self.delete_key_dial_app_config("page_dial", page, dial)

    def delete_key_app_config(self, page: str, data: dict) -> bool:
        key_str: Optional[str] = data.pop('key', None)

        if key_str is None or re.match('\D', str(key_str)) is not None:
            return False
        key: int = int(key_str)
        modified: bool = self.delete_key_dial_app_config("page_key", page, key)

        page_configs: Optional[dict] = self._config_content_origin.get(
            "page_config")
        if page_configs is None:
            page_configs = self._config_content_origin["page_configs"] = {}
            modified = True
        page_config: Optional[dict] = page_configs.get(page)
        if page_config is None:
            page_config = page_configs[page] = {"keys": {}}
            modified = True
        if page_config.get("keys") is None:
            page_config["keys"] = {}
            modified = True

        if page_config["keys"].get(key):
            page_config["keys"].pop(key)
            modified = True
        elif key == self.mydeck.key_count and page_config["keys"].get(-1):
            page_config["keys"].pop(-1)
            modified = True

        return modified

    def delete_key_dial_app_config(self, conf_key: str, page: str, key: int) -> bool:
        modified = False

        app_configs: Optional[list] = self._config_content_origin.get("apps")
        if app_configs is not None:
            new_app_configs: list = []
            for app_config in app_configs:
                if app_config.get("option") and app_config["option"].get(conf_key):
                    if app_config["option"][conf_key].get(page) == key:
                        app_config["option"][conf_key].pop(page)
                        modified = True
                    if len(app_config["option"][conf_key]) == 0:
                        modified = True
                    else:
                        new_app_configs.append(app_config)
                else:
                    new_app_configs.append(app_config)
            self._config_content_origin["apps"] = new_app_configs

        return modified

    def update_page_config_content(self, page: str, data: dict) -> bool:
        key_str: Optional[str] = data.pop('key', None)
        if key_str is None or re.match('\D', str(key_str)) is not None:
            return False
        key: int = int(key_str)
        page_config: Optional[dict] = self._config_content_origin.get(
            'page_config')
        if page_config is None or type(page_config) is not dict:
            page_config = self._config_content_origin["page_config"] = {}

        current_page_config: Optional[dict] = page_config.get(page)
        if current_page_config is None or type(current_page_config) is not dict:
            current_page_config = page_config[page] = {"keys": {}}
        key_config: Optional[dict] = current_page_config.get('keys')
        if key_config is None and type(key_config) is not dict:
            key_config = current_page_config['keys'] = {}

        self._config_content_origin['page_config'][page]['keys'][key] = data
        self.check_and_override_app_config(page, key)

        return True

    def check_and_override_app_config(self, page: str, key: int):
        """Check and override app configuration"""
        app_configs: Optional[list] = self._config_content_origin.get("apps")
        if app_configs is not None:
            new_app_configs: list = []
            for config in app_configs:
                if config.get("option") and config["option"].get("page_key"):
                    if config["option"]["page_key"].get(page) == key:
                        config["option"]["page_key"].pop(page)
                    if len(config["option"]["page_key"]) != 0:
                        new_app_configs.append(config)
                else:
                    new_app_configs.append(config)
            self._config_content_origin["apps"] = new_app_configs

    def update_game_config(self, data: dict):
        if not self._config_content_origin.get("games") or self._config_content_origin["games"] != data:
            self._config_content_origin["games"] = data
            return True

        return False

    def update_app_config_content(self, page: str, data: dict) -> bool:
        app_name: Optional[str] = data.pop('app', None)
        if app_name is None:
            return False

        for_touchscreen: bool = data.pop('for_touchscreen', False)
        for_dial: bool = data.pop('for_dial', False)

        app_data: dict = {
            "app": app_name,
            "option": {}
        }
        for config_key in data["config"].keys():
            if config_key != "page_key" and config_key != "page":
                app_data['option'][config_key] = data["config"][config_key]

        if for_touchscreen:
            return self.unify_touchscreen_app_config(page, app_data)
        elif for_dial:
            dial_str: Optional[str] = data.pop('dial', None)
            if dial_str is None or re.match('\D', str(dial_str)) is not None:
                return False

            dial: int = int(dial_str)
            return self.unify_dial_app_config(page, dial, app_data)
        else:
            key_str: Optional[str] = data.pop('key', None)
            if key_str is None or re.match('\D', str(key_str)) is not None:
                return False

            key: int = int(key_str)
            return self.unify_key_app_config(page, key, app_data)

    def unify_key_app_config(self, page: str, key: int, new_app_config: dict) -> bool:
        modify_status: int = self.unify_app_config(
            "page_key", page, key, new_app_config)

        if modify_status > 0:
            self.check_and_override_page_config(page, key)
            return True

        return False

    def unify_dial_app_config(self, page: str, key: int, new_app_config: dict) -> bool:
        return self.unify_app_config("page_dial", page, key, new_app_config)

    def unify_app_config(self, conf_key: str, page: str, key: int, new_app_config: dict) -> bool:
        MODIFY: int = 1
        ADD: int = 2
        modify_status = ADD

        new_page_key = new_app_config["option"].pop(conf_key, {})

        app_config: Optional[list] = self._config_content_origin.get("apps")
        if app_config is None:
            app_config = []
        self._config_content_origin["apps"] = app_config
        for existing_config in app_config:
            # if same app config exists
            if existing_config["app"] == new_app_config["app"]:
                origin_page_key = existing_config["option"].pop(conf_key, {})
                # if option exists except page_key is same
                if existing_config["option"] == new_app_config["option"]:
                    new_app_config["option"][conf_key] = new_page_key
                    # same setting and same key
                    if origin_page_key.get(page) and origin_page_key[page] == key:
                        # same setting and same key, do nothing
                        logging.debug(
                            "### 1. Same setting and same key, do nothing")
                        return False
                    else:
                        existing_config["option"][conf_key] = origin_page_key
                        # same setting and different page and key, add new_app_config
                        if existing_config["option"][conf_key].get(page):
                            existing_config["option"][conf_key][page] = key
                            modify_status = MODIFY
                            logging.debug(
                                "### 2. Same setting and different page and key, add new_app_config")
                        else:
                            existing_config["option"][conf_key][page] = key
                            modify_status = MODIFY
                            logging.debug(
                                "### 3. Same config, add different page key")

                elif origin_page_key.get(page) and origin_page_key[page] == key:
                    # same app and different config and same key
                    del origin_page_key[page]
                    logging.debug(
                        "### 4. Different config and same key, remove existing config")

                existing_config["option"][conf_key] = origin_page_key
            elif existing_config.get("option") is not None and existing_config["option"].get(conf_key) is not None:
                # different app already exists on the key in the page
                if existing_config["option"][conf_key].get(page) == key:
                    # remove page from page_key
                    existing_config["option"][conf_key].pop(page, None)
                    if len(existing_config["option"][conf_key]) == 0:
                        # if page_key is empty, remove the app and add new app at last
                        app_config.remove(existing_config)
                        logging.debug(
                            "### 5. If page_key is empty, remove the app and add new app at last")

            if modify_status == MODIFY:
                break

        app_config[:] = list(filter(lambda c: c.get("option") and c["option"].get(
            conf_key) and len(c['option'][conf_key].keys()) > 0, app_config))

        if modify_status == ADD:
            new_app_config["option"][conf_key] = {page: key}
            app_config.append(new_app_config)

        return modify_status > 0

    def unify_touchscreen_app_config(self, page: str, new_app_config: dict) -> bool:
        MODIFY: int = 1
        ADD: int = 2
        modify_status = ADD  # 1: modify, 2: add new app

        app_config: Optional[list] = self._config_content_origin.get("apps")
        if app_config is None:
            app_config = []
        self._config_content_origin["apps"] = app_config
        for existing_config in app_config:
            # if same app config exists
            if existing_config["app"] == new_app_config["app"]:
                origin_page: Optional[list] = existing_config["option"].pop(
                    "page", None)
                if origin_page is not None:
                    if page in origin_page:
                        # same setting and same page, do nothing
                        logging.debug(
                            "a. same setting and same page, do nothing")
                        return False
                    else:
                        logging.debug("b. append exsiting config")
                        origin_page.append(page)
                        modify_status = MODIFY
                else:
                    # not touchscreen app
                    pass

                existing_config["option"]["page"] = origin_page
            elif existing_config.get("option") is not None:
                if existing_config["option"].get("page") is not None:
                    # different app already exists in the page
                    if page in existing_config["option"]["page"]:
                        existing_config["option"]["page"].remove(page)
                        logging.debug("c. remove page from existing config")

            if modify_status == MODIFY:
                break

        app_config[:] = list(filter(lambda c: c.get("option") and c["option"].get(
            "page") and len(c['option']["page"]) > 0, app_config))

        if modify_status == ADD:
            new_app_config["option"]["page"] = [page]
            app_config.append(new_app_config)

        return modify_status > 0

    def check_and_override_page_config(self, page: str, key: int):
        """Check and override key configuration"""
        page_config: Optional[dict] = self._config_content_origin.get(
            "page_config")
        if page_config is not None and page_config.get(page) is not None and page_config[page].get("keys") is not None:
            # remove the key from the page
            if page_config[page]["keys"].get(key) is not None:
                page_config[page]["keys"].pop(key)
            if key == self.mydeck.key_count and page_config[page]["keys"].get(-1):
                page_config[page]["keys"].pop(-1)

    def parse(self, conf: dict):
        """Parse configuration file."""
        if self.mydeck is not None:
            page_config: Optional[dict[str, dict]] = conf.get('page_config')
            if page_config is not None:
                for page in page_config.keys():
                    key_config = page_config[page].get('keys')
                    if key_config is not None:
                        self.mydeck.set_key_config(
                            self.modify_key_config_with_page(page, key_config))
                    touch_config = page_config[page].get('touch')
                    if touch_config is not None:
                        self.mydeck.set_touchscreen_config(
                            self.modify_touchscreen_config_with_page(page, touch_config))
                    dial_config = page_config[page].get('dials')
                    if dial_config is not None:
                        self.mydeck.set_dial_config(
                            self.modify_dial_config_with_page(page, dial_config))
                    command_config = page_config[page].get('commands')
                    if command_config is not None:
                        self.mydeck.set_command_config(page, command_config)

        apps_conf = conf.get('apps')
        if apps_conf is not None:
            self.parse_apps(apps_conf)
        games_conf = conf.get('games')
        if games_conf is not None:
            self.parse_games(games_conf)

    def parse_games(self, games_conf: list):
        """Apply the configuration of games"""

        key_config = self.mydeck.key_config()
        for page_name in list(key_config.keys()):
            if page_name.startswith("@GAME"):
                del key_config[page_name]

        for game_conf in games_conf:
            self.parse_game(game_conf["game"], game_conf)

    def parse_game(self, game: str, game_conf: dict = {}):
        """Apply the configuration of a game"""
        game = 'Game' + game
        m = self._load_module(game)
        getattr(m, game)(self.mydeck, game_conf)

    def reset_apps(self):
        """Reset apps"""
        for app in self.apps:
            app._stop = True
            if app.use_trigger:
                app.trigger.set()

        # destloy apps
        for app in self.apps:
            del app
        for app in self.background_apps:
            del app

        self.apps = []
        self.background_apps = []
        self.hook_apps: Dict[str, List['HookAppBase']] = {}
        self.is_background_thread_started = False

    def parse_apps(self, apps_conf: List[dict]):
        """Apply the configuration of apss"""
        if apps_conf is None:
            return False

        for app_conf in apps_conf:
            self.parse_app(app_conf)

        self.parse_app({"app": "Trigger"})

    def append_hook_app(self, app: 'HookAppBase'):
        """Append hook apps"""
        on = app.on
        on_apps = self.hook_apps.get(on)
        if on_apps is None:
            self.hook_apps[on] = []
        self.hook_apps[on].append(app)

    def parse_app(self, app_conf: dict):
        """Apply the configuration of an aps"""
        if app_conf is None:
            return False

        app = app_conf.get('app')
        if app is not None:
            app = 'App' + app
            m = self._load_module(app)
            o = getattr(m, app)(self.mydeck, app_conf.get('option'))
            if o.is_background_app:
                self.background_apps.append(o)
                if app_conf['app'] == 'Alert' and self.mydeck is not None:
                    o.set_check_func(self.mydeck._alert_func)
                    self.mydeck.set_alert_key_conf(
                        self.modify_key_config(app_conf['option']["key_config"]))
            elif o.is_hook_app:
                self.append_hook_app(o)
            elif o.is_dial_app():
                self.apps.append(o)
                o.dial_setup()
            else:
                self.apps.append(o)
                o.key_setup()

        return o

    def _load_module(self, app: str):
        module = re.sub('([A-Z])', r'_\1', app)[1:].lower()
        if self._loaded.get(app) is None:
            self._loaded[app] = importlib.import_module(
                'mydeck.' + module, "mydeck")

        return self._loaded[app]

    def not_working_apps(self) -> List['AppBase']:
        """Return the list of the apps not working"""
        return list(filter(lambda app: app.use_thread and app.is_in_target_page() and not app.in_working, self.apps))

    def modify_key_config_with_page(self, page: str, conf: dict):
        """Modify key configuration according to conf whose key is page name and value is configuration dict."""

        if self.mydeck._PAGE_CONFIG['keys'].get(page) is None:
            self.mydeck._PAGE_CONFIG['keys'][page] = {}

        self.mydeck._PAGE_CONFIG['keys'][page] = self.modify_key_config(conf)

        return self.mydeck._PAGE_CONFIG['keys']

    def modify_dial_config_with_page(self, page: str, conf: dict):
        """Modify dial configuration according to conf whose key is page name and value is configuration dict."""

        if self.mydeck._PAGE_CONFIG['dials'].get(page) is None:
            self.mydeck._PAGE_CONFIG['dials'][page] = {}

        self.mydeck._PAGE_CONFIG['dials'][page] = conf

        return self.mydeck._PAGE_CONFIG['dials']

    def modify_key_config(self, conf: dict):
        """Modify key configuration with conf whose key is number of key and value is configuration dict."""
        key_count = self.key_count
        new_config = {}
        for _key in conf.keys():
            key = _key
            if _key < 0:
                key = key_count + _key
            new_config[key] = conf[_key]
        return new_config

    def modify_touchscreen_config_with_page(self, page: str, conf: dict):
        """Modify touchscreen configuration according to conf whose key is page name and value is configuration dict."""

        if self.mydeck._PAGE_CONFIG['touch'].get(page) is None:
            self.mydeck._PAGE_CONFIG['touch'][page] = {}

        self.mydeck._PAGE_CONFIG['touch'][page] = conf

        return self.mydeck._PAGE_CONFIG['touch']


class ImageOrFile:
    """Class to represent Image instannce or a file path."""
    is_file = False

    def __init__(self, file_or_image: Any):
        """Constructor. Pass Image.Image instance or file path."""
        self.image: Image.Image
        self.file: str = ''

        if type(file_or_image) != str and type(file_or_image) != Image.Image:
            logging.warning(file_or_image)
            raise (ExceptionWrongTypeGiven)

        if type(file_or_image) == str:
            self.file = file_or_image
            self.is_file = True
        elif type(file_or_image) == Image.Image:
            self.image = file_or_image


class ExceptionWrongTypeGiven(Exception):
    """Exception when wrong type is given to ImageOrFile constructor."""
    pass
