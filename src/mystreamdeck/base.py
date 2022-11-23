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

from cairosvg import svg2png
from typing import Any, NoReturn, List, TYPE_CHECKING, Optional, Callable, Dict, Union
from PIL import Image, ImageDraw, ImageFont
from StreamDeck.ImageHelpers import PILHelper
from StreamDeck.DeviceManager import DeviceManager
from StreamDeck.Devices import StreamDeckOriginalV2
from .my_decks import MyDecks

if TYPE_CHECKING:
    from . import App, AppBase, BackgroundAppBase, HookAppBase

class ExceptionInvalidMyStreamDecksConfig(Exception):
    pass

class MyStreamDecks:
    """The class to manage several STREAM DECK devices.

    This class manages insteaces of MyStreamDeck class.
    """
    def __init__(self, config: dict):
        """
        config dict takes the following keys:
        - log_level
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
        vdeck_config = config.get('vdeck_config')
        if type(vdeck_config) is not str:
            raise(ExceptionInvalidMyStreamDecksConfig)
        self.vdeck_config: str = vdeck_config
        self.mystreamdecks: Dict[str, 'MyStreamDeck'] = {}
        self._one_deck_only: bool = False
        self.config: Optional[dict]
        self.decks: Optional[dict] = config.get('decks')
        self.configs: Optional[dict] = config.get('configs')
        if self.decks is None and self.configs is None:
            self.config = config.get('config')
            self._one_deck_only = True
        log_level: Optional[str] = config.get('log_level')
        if log_level is not None:
            logging.basicConfig(level=log_level)

    def start_decks(self, no_real_device: bool = False) -> NoReturn:
        """Start and display images to STREAM DECK buttons according to configuration."""
        streamdecks = MyDecks(self.vdeck_config, no_real_device).devices
        logging.debug("Found {} Stream Deck(s).\n".format(len(streamdecks)))

        for index, deck in enumerate(streamdecks):
            # if not deck.is_visual():
            # continue

            deck.open()
            serial_number: str = deck.get_serial_number()

            if self._one_deck_only:
                if self.config is not None:
                    alert_func :Optional[Callable] = self.config.get('alert_func')
                    config_file: Optional[str] = self.config.get('file')
                    mydeck = MyStreamDeck({
                        'mydecks': self,
                        'myname': 'mydeck',
                        "deck": deck,
                        'alert_func': alert_func,
                        'config': config_file
                    })
                    self.mystreamdecks[serial_number] = mydeck
                    mydeck.init_deck()
                    break
                else:
                    logging.warning("config{file: '/path/to/config_file'} is required")
                    raise(ExceptionNoConfig)
            elif self.decks is not None:
                sn_alias = self.decks.get(serial_number)
                configs = self.configs
                if sn_alias is not None and configs is not None:
                    sn_config = configs.get(sn_alias)
                    if sn_config is not None:
                        mydeck = MyStreamDeck({
                            'mydecks': self,
                            'myname': sn_alias,
                            "deck": deck,
                            'alert_func': sn_config.get('alert_func'),
                            'config': sn_config.get('file'),
                        })
                        self.mystreamdecks[sn_alias] = mydeck
                        mydeck.init_deck()
                else:
                    logging.warning("config is not found for device: {}".format(serial_number))
            else:
                logging.warning("config or (decks and configs) is required")
                raise(ExceptionNoConfig)

        # Wait until all application threads have terminated (for this example,
        # this is when all deck handles are closed).
        for t in threading.enumerate():
            try:
                t.join()
            except RuntimeError as e:
                print("Error in start_decks", e)

        print("start_decks end!")
        sys.exit()

        # Wait until all application threads have terminated (for this example,
        # this is when all deck handles are closed).
        for t in threading.enumerate():
            try:
                t.join()
            except RuntimeError as e:
                print("Error in start_decks", e)

        print("start_decks end!")
        sys.exit()

    def list_mydecks(self) -> List['MyStreamDeck']:
        """return list of MyStreamDeck instances"""
        return list(self.mystreamdecks.values())

    def list_other_mydecks(self, mydeck: 'MyStreamDeck') -> List['MyStreamDeck']:
        """return list of MyStreamDeck instances"""
        myname = mydeck.myname
        return list(filter(lambda mydeck: mydeck.myname != myname, self.mystreamdecks.values()))

    def mydeck (self, name: str) -> Optional['MyStreamDeck']:
        """Pass name of the device and return the correspond MyStreamDeck instance."""
        mydeck = self.mystreamdecks.get(name)
        if mydeck is not None:
            return mydeck
        else:
            logging.warning('mydeck is None: {}'.format(name))
        return None

class ExceptionNoConfig(Exception):
    """Exception when no configuration is given"""
    pass

class MyStreamDeck:
    """Class to control a STREAM DECK device."""
    mydecks: MyStreamDecks
    # path of font

    def __init__ (self, opt: dict):
        deck = opt.get('deck')
        self.deck: StreamDeckOriginalV2 = deck
        self.key_count: int = self.deck.key_count()
        self.font_path = "/usr/share/fonts/truetype/freefont/FreeSans.ttf"
        self.config: Optional['Config'] = None
        self.is_background_thread_started: bool = False
        self._alert_func: Optional[Callable] = None
        self._exit: bool = False
        self._current_page: str = '@HOME'
        self._previous_pages: list[str] = ['@HOME']
        self._previous_window: str =  ''
        self._in_alert: bool = False
        self._game_status: bool = False
        self._game_command: dict = {}
        self._PAGE_CONFIG: dict = {
            'keys': {},
            'commands': {},
        }
        self._KEY_CONFIG_GAME: dict = {}
        self._KEY_ACTION_APP: dict  = {}
        self._GAME_KEY_CONFIG: dict = {}
        self._config_file: str = ''
        self._config_file_mtime: float = 0

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
            self._KEY_CONFIG_GAME = {}
            self.config = Config(self, self._config_file)

    def init_deck(self):
        """Initialize deck. Reflect configuration and setup keys."""
        if self.config is not None:
            self.config.reflect_config()

        self.key_setup()

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
        if  name[0] != '~' and (len(self._previous_pages) == 0 or self._previous_pages[-1] != name):
            self._previous_pages.append(name)
        logging.debug(self._previous_pages)

    def current_page(self) -> str:
        """Return current page name"""
        return self._current_page

    def set_current_page_without_setup(self, name: str):
        """Set given page name as current_page. but don't setup keys."""
        self.set_previous_page(name)
        self.set_alert_off()
        self._current_page = name

    def set_current_page(self, name: str, add_previous: bool = True):
        """Set given page name as current_page and setup keys."""

        if name[0] != "~ALERT":
            self.set_alert_off()

        if self.deck is not None and name != self._current_page and self.has_page_key_config(name):
            self.set_previous_page(self._current_page)
            self.stop_working_apps()
            self._current_page = name
            self.set_game_status_off()
            self.deck.reset()
            self.key_setup()
            self.run_page_command(name)
            self.run_hook_apps('page_change')
            if self.config is not None:
                self.threading_apps(self.config.apps, self.config.background_apps)

        # run hook page_change_any whenever set_current_page is called.
        self.run_hook_apps('page_change_any')

    def has_page_key_config(self, name: str) -> bool:
        """return true when page key config exists"""
        return self._PAGE_CONFIG['keys'].get(name) is not None

    # display keys and set key callbacks
    def key_setup(self):
        """setup keys"""
        deck = self.deck
        logging.warn("Opened '{}' device (serial number: '{}', fw: '{}', page: '{}')".format(
            deck.deck_type(), deck.get_serial_number(), deck.get_firmware_version(), self.current_page()
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
                    self.set_key(key, page_configuration.get(key))

                    # Register callback function for the time when a key state changes.
                    deck.set_key_callback(lambda deck, key, state: self.key_change_callback(key, state))

    # set key image and label
    def set_key(self, key: int, conf: dict):
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
                self.update_key_image(key, self.render_key_image(ImageOrFile(conf["image"]), conf.get("label") or '', conf.get("background_color") or ''))

    def determine_image_url(self, image_url: Optional[str], url: Optional[str]) -> Optional[str]:
        """Return url for key image"""
        if image_url is None and url is not None:
            image_url = re.sub(r'^(https?://[^/]+).*$', '\g<1>/favicon.ico', url)

        return image_url

    def image_url_to_file_name(self, image_url: str) -> str:
        """Return file name from url"""
        icon_name = re.sub(r'^https?://', '', image_url)
        icon_name = re.sub(r'[&=?/.]', '-', icon_name)
        ext = re.sub(r'.+(\.\w+)$', '\g<1>', image_url)
        return '/tmp/' + 'mystreamdeck-' + self.myname + icon_name + ext

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
            conf["image"] = "./src/Assets/world.png"

    def save_image(self, icon_url: str, icon_file: str) -> Optional[str]:
        """Get image from icon_url and save it to icon_file"""
        if os.path.exists(icon_file) is False:
            res = requests.get(icon_url)
            if res.status_code == requests.codes.ok:
                icon_data = res.content
                if icon_url[-3:len(icon_url)] == 'svg':
                    icon_file = icon_file[0:-4] + '.png'
                    svg2png(bytestring=icon_data,write_to=icon_file)
                else:
                    with open(icon_file, mode="wb") as f:
                        f.write(icon_data)
                if self.check_icon_file(icon_file):
                    return icon_file
        else:
            return icon_file

        return None

    def check_icon_file(self, file_path: str) -> bool:
        """Check whether file_path is image or not"""
        try:
            print("file: {}".format(file_path))
            with wand.image.Image(filename=file_path):
                return True
        except Exception as e:
            print("Error in check_icon_file:", e)
            os.rename(file_path, file_path + '.back')
            return False

    # change key image
    def update_key_image(self, key: int, image: str):
        """Update image of key"""
        key = self.abs_key(key)
        deck = self.deck
        if deck is not None:
            # Update requested key with the generated image.
            deck.set_key_image(key, image)

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

        image = PILHelper.create_scaled_image(deck, icon, margins=margins, background=bg_color)

        draw = ImageDraw.Draw(image)
        if no_label is False:
            font_size = 14
            if len(label) > 7:
                font_size = int(14 * 7 / len(label) + 0.999)
            font = ImageFont.truetype(self.font_path, font_size)
            draw.text((image.width / 2, image.height - 5), font=font, text=label, anchor="ms", fill=font_bg_color)

        if hasattr(self.deck, 'is_virtual'):
            return image
        else:
            return PILHelper.to_native_format(deck, image)


    # Prints key state change information, updates rhe key image and performs any
    # associated actions when a key is pressed.
    def key_change_callback(self, key: int, state: bool):
        """Call a callback according to a key is pushed"""
        deck = self.deck
        if deck is not None:
            # Print new key state
            print("Deck {} Key {} = {}, page = {}".format(deck.id(), key, state, self.current_page()), flush=True)


        # Check if the key is changing to the pressed state.
        if state:
            conf = self.key_config().get(self.current_page()).get(key)

            # When an exit button is pressed, close the application.
            if conf is not None:
                if conf.get("exit") == 1:
                    # Use a scoped-with on the deck to ensure we're the only thread
                    # using it right now.
                    with deck:
                        # Reset deck, clearing all button images.
                        deck.reset()

                        # Close deck handle, terminating internal worker threads.
                        deck.close()

                        # informa program is end to other thread
                        self._exit = True
                        if self.config is not None:
                            for app in self.config.apps:
                                app.stop = True
                        sys.exit()

                elif type(conf.get("command")) is str and self._game_command.get(conf.get("command")):
                    command = self._game_command.get(conf.get("command"))
                    if command is not None:
                        command(conf)

                elif conf.get("name") == "alert":
                    with deck:
                        self.set_alert_off()
                        self.key_setup()

                elif conf.get("command"):
                    command = conf.get("command")
                    subprocess.Popen(command)

                elif conf.get("chrome"):
                    chrome = conf.get('chrome')
                    command = ['google-chrome', '--profile-directory=' + chrome[0], chrome[1]]
                    subprocess.Popen(command)
                else:
                    command = conf.get("app_command")
                    if command is not None:
                        found = False
                        if self.config is not None:
                            for app in self.config.apps:
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
                        self.set_current_page(self.pop_last_previous_page(), False)
                    else:
                        self.set_current_page(page_name)


    def stop_working_apps(self):
        """Try to stop working apps and wait until all of them are stopped."""
        for app in self.config.apps:
            if app.in_working:
                app.in_working = False

        i = 0
        # when app is stopped, app make stop False
        while sum( 1 for e in self.config.working_apps()) > 0:
            for app in self.config.working_apps():
                if app.in_working:
                    time.sleep(0.01)
                    i += 1
                    if i > 200:
                        print(type(app), 'still waiting to stop working apps')


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

    def set_command_config(self, page: str, conf):
        """Set page command configuration."""
        if conf is None:
            conf = {}
        self._PAGE_CONFIG['commands'][page] = conf

    def set_game_key(self, key: int, conf: dict):
        """Set game key configuration for one key"""
        key = self.abs_key(key)
        self._GAME_KEY_CONFIG[key] = conf
        self.set_key(key, conf)

    def add_game_key_conf(self, conf: dict):
        """Add game confiruration for keys"""
        key_config = self.key_config()
        if key_config.get('@GAME') is None:
            key_config['@GAME'] = {}
        for key in conf.keys():
            key_config['@GAME'][key] = conf[key]
            self._KEY_CONFIG_GAME[key] = conf[key]

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
        self.set_current_page("@GAME", False)
        self._GAME_KEY_CONFIG = {}

    def set_key_conf(self, page: str, key: int, conf: dict):
        """Set a configuration of a key"""
        if self._PAGE_CONFIG.get('keys') is None:
            self._PAGE_CONFIG['keys'] = {}
        if self._PAGE_CONFIG['keys'].get(page) is None:
            self._PAGE_CONFIG['keys'][page] = {}
        self._PAGE_CONFIG['keys'][page][key] = conf

    def threading_apps(self, apps: List['AppBase'], background_apps: List['BackgroundAppBase']):
        """Run apps in thread"""
        for app in apps:
            if app.use_thread and app.is_in_target_page():
                t = threading.Thread(target=lambda: app.start(), args=())
                t.start()
        if not self.is_background_thread_started:
            self.is_background_thread_started = True
            for bg_app in background_apps:
                t = threading.Thread(target=lambda: bg_app.start(), args=())
                t.start()

        t = threading.Thread(target=lambda: self.update_config(), args=())
        t.start()

        time.sleep(0.5)

        i = 0
        if self.config is not None:
            while sum( 1 for e in self.config.not_working_apps() ) > 0:
                for app in self.config.not_working_apps():
                    if app.is_in_target_page() and not app.in_working:
                        time.sleep(0.01)
                        i += 1
                        if i > 200:
                            print(type(app), 'still waiting to start app')


    def abs_key(self, key: int) -> int:
        """If key is negative number, chnage it as positive number"""
        if key < 0:
            key = self.key_count + key
        return key

    def run_hook_apps(self, on: str):
        hook_apps :List['HookAppBase'] = []
        if self.config is not None:
            apps = self.config.hook_apps.get(on)
            if apps is not None:
                for app in apps:
                    app.execute_on_hook()

    def update_config(self):
        while True:
            sn = self.deck.get_serial_number()
            if MyDecks.ConfigQueue.get(sn) is not None:
                data = MyDecks.ConfigQueue[sn].get()
                if self.config.update_page_config_content(self.current_page(), data):
                    self.config.save_config()
                    self.config.reflect_config(True)

class Config:
    """STREAM DECK Configuration Class"""

    def __init__(self, mydeck: 'MyStreamDeck', file: str):
        """Pass MyStreamDeck instance as mydeck and configuration file as file"""
        self._file_mtime: float = 0
        self._file: str = ''
        self._config_content_origin: dict = {}
        self._config_content: dict = {}
        self._loaded: dict = {}
        self.conf: dict = {}
        self.apps: List['AppBase'] = []
        self.background_apps: List['BackgroundAppBase'] = []
        self.mydeck: 'MyStreamDeck'
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
                print("Error in load", e)
                print(traceback.format_exc())


    def reflect_config(self, force: bool = False):
        """Read configuration file and reset applications and parse content of the configuration file and run apps"""
        loaded = self.load(force)
        if loaded is not None:
            try:
                self.reset_apps()
                self.parse(loaded)
                self.mydeck.threading_apps(self.apps, self.background_apps)
                self.mydeck.key_setup()
            except Exception as e:
                print("Error in reflect_config", e)
                print(traceback.format_exc())
                return None

    def load(self, force :bool = False):
        """Load the configuration file, If the file is newer than read before, return the content of the configuration file. Or return None."""
        statinfo = os.stat(self._file)
        if force or self._file_mtime < statinfo.st_mtime:
            self._file_mtime = statinfo.st_mtime
            with open(self._file) as f:
                try:
                    self._config_content_origin = yaml.safe_load(f)
                    self._config_content = deepcopy(self._config_content_origin)
                    return self._config_content
                except Exception as e:
                    print("Error in load", e)
                    print(traceback.format_exc())

        return None

    def update_page_config_content(self, page: str, data: dict) -> bool:
        key = data.pop('key', None)
        if key is None or re.match('\D', str(key)) is not None:
            print(key)
            return False
        key = int(key)
        print("{} - {} - {}".format(page,key,data))
        page_config: Optional[dict] = self._config_content_origin.get('page_config')
        if page_config is None or type(page_config) is not dict:
            print(page_config)
            return False
        current_page_config: Optional[dict] = page_config.get(page)
        if current_page_config is None or type(current_page_config) is not dict:
            print(current_page_config)
            return False
        key_config: Optional[dict] = current_page_config.get('keys')
        if key_config is None and type(key_config) is not dict:
            print(key_config)
            return False

        self._config_content_origin['page_config'][page]['keys'][key] = data
        return True

    def parse(self, conf: dict):
        """Parse configuration file."""
        if self.mydeck is not None:
            page_config = conf.get('page_config')
            if page_config is not None:
                for page in page_config.keys():
                    key_config = page_config[page].get('keys')
                    if key_config is not None:
                        self.mydeck.set_key_config(self.modify_key_config_with_page(page, key_config))
                    command_config = page_config[page].get('commands')
                    if command_config is not None:
                        self.mydeck.set_command_config(page, command_config)

        apps_conf = conf.get('apps')
        if apps_conf is not None:
            self.parse_apps(apps_conf)
        games_conf = conf.get('games')
        if games_conf is not None:
            self.parse_games(games_conf)

    def parse_games(self, games_conf: dict):
        """Apply the configuration of games"""
        for game in games_conf.keys():
            self.parse_game(game, games_conf[game])

    def parse_game(self, game: str, game_conf: dict = {}):
        """Apply the configuration of a game"""
        if game_conf is None:
            return False
        game = 'Game' + game
        m = self._load_module(game)
        getattr(m, game)(self.mydeck, game_conf)

    def reset_apps(self):
        """Reset apps"""
        for app in self.apps:
            app.stop = True

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
            app = self.parse_app(app_conf)

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
                    self.mydeck.set_alert_key_conf(self.modify_key_config(app_conf['option']["key_config"]))
            elif o.is_hook_app:
                self.append_hook_app(o)
            else:
                self.apps.append(o)
                o.key_setup()

        return o

    def _load_module(self, app: str):
        module = re.sub('([A-Z])', r'_\1', app)[1:].lower()
        if self._loaded.get(app) is None:
            self._loaded[app] = importlib.import_module('mystreamdeck.' + module, "mystreamdeck")

        return self._loaded[app]

    def not_working_apps(self) -> List['AppBase']:
        """Return the list of the apps not working"""
        return list(filter(lambda app: app.use_thread and app.is_in_target_page() and not app.in_working, self.apps))

    def working_apps(self) -> List['AppBase']:
        """Return the list of the working apps"""
        return list(filter(lambda app: app.use_thread and app.is_in_target_page() and app.in_working, self.apps))

    def modify_key_config_with_page(self, page: str, conf: dict):
        """Modify key configuration according to conf whose key is page name and value is configuration dict."""

        if self.mydeck._PAGE_CONFIG['keys'].get(page) is None:
            self.mydeck._PAGE_CONFIG['keys'][page] = {}

        self.mydeck._PAGE_CONFIG['keys'][page] = self.modify_key_config(conf)

        return self.mydeck._PAGE_CONFIG['keys']

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

class ImageOrFile:
    """Class to represent Image instannce or a file path."""
    is_file = False
    def __init__(self, file_or_image: Any):
        """Constructor. Pass Image.Image instance or file path."""
        self.image: Image.Image
        self.file: str = ''

        if type(file_or_image) != str and type(file_or_image) != Image.Image:
            logging.warning(file_or_image)
            raise(ExceptionWrongTypeGiven)

        if type(file_or_image) == str:
            self.file = file_or_image
            self.is_file = True
        elif type(file_or_image) == Image.Image:
            self.image = file_or_image

class ExceptionWrongTypeGiven(Exception):
    """Exception when wrong type is given to ImageOrFile constructor."""
    pass
