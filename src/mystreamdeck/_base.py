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

from cairosvg import svg2png
from typing import Any, NoReturn, List, TYPE_CHECKING, Optional, Callable, Dict
from PIL import Image, ImageDraw, ImageFont
from StreamDeck.ImageHelpers import PILHelper
from StreamDeck.DeviceManager import DeviceManager
from StreamDeck.Devices import StreamDeckOriginalV2
if TYPE_CHECKING:
    from mystreamdeck import App, AppBase, BackgroundAppBase

class MyStreamDecks:
    mystreamdecks: Dict[str, 'MyStreamDeck'] = {}
    one_deck_only: bool = False
    decks: Optional[dict]
    configs: Optional[dict]
    conifg: Optional[dict]
    def __init__(self, config: dict):
        self.decks: Optional[dict] = config.get('decks')
        self.configs: Optional[dict] = config.get('configs')
        if self.decks is None and self.configs is None:
            self.config = config.get('config')
            self.one_deck_only = True

    def start_decks(self) -> NoReturn:
        streamdecks = DeviceManager().enumerate()
        print("Found {} Stream Deck(s).\n".format(len(streamdecks)))

        for index, deck in enumerate(streamdecks):
            if not deck.is_visual():
                continue

            deck.open()
            serial_number: str = deck.get_serial_number()

            if self.one_deck_only:
                if self.config is not None:
                    alert_func :Optional[Callable] = self.config.get('alert_func')
                    config_file: Optional[str] = self.config.get('file')
                    mydeck = MyStreamDeck({
                        'mydecks': self,
                        "deck": deck,
                        'alert_func': alert_func,
                        'config': config_file
                    })
                    self.mystreamdecks[serial_number] = mydeck
                    mydeck.init_deck(deck)
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
                            "deck": deck,
                            'alert_func': sn_config.get('alert_func'),
                            'config': sn_config.get('file'),
                        })
                        self.mystreamdecks[sn_alias] = mydeck
                        mydeck.init_deck(deck)
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

    def mydeck (self, name: str) -> 'MyStreamDeck':
        mydeck = self.mystreamdecks.get(name)
        if mydeck is not None:
            return mydeck
        else:
            logging.warning('mydeck is None')
            raise(ExceptionNoDevice)

class ExceptionNoConfig(Exception):
    pass

class ExceptionNoDevice(Exception):
    pass

class MyStreamDeck:
    """STREAM DECK Configuration"""
    mydecks: MyStreamDecks
    # path of font

    def __init__ (self, opt: dict):
        deck = opt.get('deck')
        self.deck: StreamDeckOriginalV2 = deck
        self.key_count = self.deck.key_count()
        self.font_path = "/usr/share/fonts/truetype/freefont/FreeSans.ttf"
        self.config: Optional['Config'] = None
        self.is_background_thread_started: bool = False
        self.key_count: int
        self._alert_func: Optional[Callable] = None
        self._exit: bool = False
        self._current_page: str = '@HOME'
        self._previous_pages: list[str] = ['@HOME']
        self._previous_window: str =  ''
        self._in_alert: bool = False
        self._game_status: bool = False
        self._game_command: dict = {}
        self._KEY_CONFIG: dict = {}
        self._KEY_CONFIG_GAME: dict = {}
        self._KEY_ACTION_APP: dict  = {}
        self._GAME_KEY_CONFIG: dict = {}
        self._config_file: str = ''
        self._config_file_mtime: int = 0

        if opt.get('mydecks') is not None:
            self.mydecks = opt.get('mydecks')
        if opt.get('alert_func') is not None:
            self._alert_func = opt['alert_func']
        if opt.get("font_path") is not None:
            self.font_path = opt["font_path"]
        if opt.get("config") is not None:
            self._config_file = opt.get('config') or ''
            self._KEY_CONFIG_GAME = {}
            self.config = Config(self, self._config_file)

    def init_deck(self, deck: StreamDeckOriginalV2):
        if self.config is not None:
            self.config.reflect_config()

        self.key_setup()

    def in_game_status(self):
        return self._game_status == 1

    def in_alert(self):
        return self._in_alert == 1

    def key_config(self):
        if self._config_file != '':
            self.config.reflect_config()

        return self._KEY_CONFIG

    def set_alert_on(self):
        self._in_alert = True

    def set_alert_off(self):
        self._in_alert = False

    def set_game_status_on(self):
        self._game_status = True

    def set_game_status_off(self):
        self._game_status = False

    def previous_page(self):
        if len(self._previous_pages) > 0:
            return self._previous_pages[-1]
        else:
            return ''

    def pop_last_previous_page(self):
        if len(self._previous_pages) > 0:
            return self._previous_pages.pop(-1)
        else:
            return '@HOME'

    def set_previous_page(self, name: str):
        if  name[0] != '~' and (len(self._previous_pages) == 0 or self._previous_pages[-1] != name):
            self._previous_pages.append(name)

    def current_page(self):
        return self._current_page

    def set_current_page_without_setup(self, name: str):
        self.set_previous_page(name)
        self.set_alert_off()
        self._current_page = name

    def set_current_page(self, name: str):
        self.set_previous_page(self._current_page)

        if name[0] != "~ALERT":
            self.set_alert_off()

        if name != self._current_page and self.deck is not None:
            self.stop_working_apps()
            self._current_page = name
            self.set_game_status_off()
            self.deck.reset()
            self.key_setup()
            if self.config is not None:
                self.threading_apps(self.config.apps, self.config.background_apps)

    # display keys and set key callbacks
    def key_setup(self):
        deck = self.deck
        print("Opened '{}' device (serial number: '{}', fw: '{}', page: '{}')".format(
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


    def image_url_to_image(self, conf: dict = {}, url: str = ''):
        image_url = conf.get('image_url')
        icon_name = ''
        if image_url is None and url is not None:
            image_url = re.sub(r'^(https?://[^/]+).*$', '\\1/favicon.ico', url)
            icon = re.sub(r'^https?://([^/]+).*$', '\\1', url)
            icon_name = icon + '.ico'
        elif image_url is not None:
            icon_name = ""
            if url is None:
                icon_name = re.sub(r'^https?://', '', image_url)
                icon_name = re.sub(r'[&=?/.]', '-', icon_name)
            else:
                icon_name = re.sub(r'^https?://([^/]+).*$', '\\1', url)
            ext = re.sub(r'.+(\.\w+)$', '\\1', image_url)
            icon_name += ext

        icon_file = self.save_image(image_url, '/tmp/' + 'mystreamdeck-' + icon_name)

        if icon_file is not None:
            conf["image"] = icon_file
        else:
            conf["image"] = "./src/Assets/world.png"

    def save_image(self, icon_url: str, icon_file: str):
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

    def check_icon_file(self, file_path: str):
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
        key = self.abs_key(key)
        deck = self.deck
        if deck is not None:
            # Update requested key with the generated image.
            deck.set_key_image(key, image)

    # render key image and label
    def render_key_image(self, icon_filename_or_object: 'ImageOrFile', label: str = '', bg_color: str = '', no_label: bool = False):
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

        return PILHelper.to_native_format(deck, image)


    # Prints key state change information, updates rhe key image and performs any
    # associated actions when a key is pressed.
    def key_change_callback(self, key: int, state: bool):
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

                if conf.get("change_page") is not None:
                    with deck:
                        page_name = conf.get("change_page")
                        if page_name == "@previous":
                            self.set_current_page(self.pop_last_previous_page())
                        else:
                            self.set_current_page(page_name)


    def stop_working_apps(self):
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
        self.set_alert_on()
        self.set_current_page("~ALERT")

    # handler to stop alert
    def handler_alert_stop(self):
        if self.current_page() == "~ALERT":
            self.set_alert_off()
            self.set_current_page(self.pop_last_previous_page())

    def set_key_config(self, conf):
        if conf is None:
            conf = {}
        self._KEY_CONFIG = conf

    def set_game_key(self, key: int, conf: dict):
        key = self.abs_key(key)
        self._GAME_KEY_CONFIG[key] = conf
        self.set_key(key, conf)

    def add_game_key_conf(self, conf: dict):
        key_config = self.key_config()
        if key_config.get('@GAME') is None:
            key_config['@GAME'] = {}
        for key in conf.keys():
            key_config['@GAME'][key] = conf[key]
            self._KEY_CONFIG_GAME[key] = conf[key]

    def add_game_command(self, name: str, command):
        self._game_command[name] = command

    def set_alert_key_conf(self, conf: dict):
        key_config = self.key_config()
        key_config['~ALERT'] = conf

    def exit_game(self):
        self.set_game_status_off()
        self.set_current_page("@GAME")
        self._GAME_KEY_CONFIG = {}

    def set_key_conf(self, page: str, key: int, conf: dict):
        if self._KEY_CONFIG.get(page) is None:
            self._KEY_CONFIG[page] = {}
        self._KEY_CONFIG[page][key] = conf

    def threading_apps(self, apps: List['AppBase'], background_apps: List['BackgroundAppBase']):
        for app in apps:
            if app.use_thread and app.is_in_target_page():
                t = threading.Thread(target=lambda: app.start(), args=())
                t.start()
        if not self.is_background_thread_started:
            self.is_background_thread_started = True
            for bg_app in background_apps:
                t = threading.Thread(target=lambda: bg_app.start(), args=())
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


    def abs_key(self, key: int):
        if key < 0:
            key = self.key_count + key
        return key

class Config:
    def __init__(self, mydeck: 'MyStreamDeck', file: str):
        self._file_mtime: int = 0
        self._file: str = ''
        self._config_content: dict = {}
        self._loaded: dict = {}
        self.conf: dict = {}
        self.apps: List['AppBase'] = []
        self.background_apps: List['BackgroundAppBase'] = []
        self.mydeck: 'MyStreamDeck'
        self.mydeck = mydeck
        self.key_count = mydeck.key_count
        self._file = file

    def reflect_config(self):
        loaded = self.load()
        if loaded is not None:
            try:
                self.reset_apps()
                self.parse(loaded)
                self.mydeck.threading_apps(self.apps, self.background_apps)
            except Exception as e:
                print("Error in reflect_config", e)
                return None

    def load(self):
        statinfo = os.stat(self._file)
        if self._file_mtime < statinfo.st_mtime:
            self._file_mtime = statinfo.st_mtime
            with open(self._file) as f:
                try:
                    self._config_content = yaml.safe_load(f)
                    return self._config_content
                except Exception as e:
                    print("Error in load", e)

        return None

    def parse(self, conf: dict):
        if self.mydeck is not None:
            self.mydeck.set_key_config(self.modify_key_config_with_page(conf.get('key_config')))
            # alert_config: dict = {}
        apps_conf = conf.get('apps')
        if apps_conf is not None:
            self.parse_apps(apps_conf)
        games_conf = conf.get('games')
        if games_conf is not None:
            self.parse_games(games_conf)

    def parse_games(self, games_conf: dict):
        for game in games_conf.keys():
            self.parse_game(game, games_conf[game])

    def parse_game(self, game: str, game_conf: dict = {}):
        if game_conf is None:
            return False
        game = 'Game' + game
        m = self._load_module(game)
        getattr(m, game)(self.mydeck, game_conf)

    def reset_apps(self):
        for app in self.apps:
            app.stop = True

        # destloy apps
        for app in self.apps:
            del app
        for app in self.background_apps:
            del app

        self.apps = []
        self.background_apps = []
        self.is_background_thread_started = False

    def parse_apps(self, apps_conf: List[dict]):
        if apps_conf is None:
            return False

        for app_conf in apps_conf:
            app = self.parse_app(app_conf)

    def parse_app(self, app_conf: dict):
        if app_conf is None:
            return False

        app = app_conf.get('app')
        if app is not None:
            m = self._load_module(app)
            o = getattr(m, app)(self.mydeck, app_conf.get('option'))
            if not o.is_background_app:
                self.apps.append(o)
                o.key_setup()
            else:
                self.background_apps.append(o)
                if app_conf['app'] == 'Alert' and self.mydeck is not None:
                    o.set_check_func(self.mydeck._alert_func)
                    self.mydeck.set_alert_key_conf(self.modify_key_config(app_conf['option']["key_config"]))

        return o

    def _load_module(self, app: str):
        module = re.sub('([A-Z])', r'_\1', app)[1:].lower()
        if self._loaded.get(app) is None:
            self._loaded[app] = importlib.import_module('mystreamdeck.' + module, "mystreamdeck")

        return self._loaded[app]

    def not_working_apps(self):
        return filter(lambda app: app.use_thread and app.is_in_target_page() and not app.in_working, self.apps)

    def working_apps(self):
        return filter(lambda app: app.use_thread and app.is_in_target_page() and app.in_working, self.apps)

    def modify_key_config_with_page(self, conf: dict):
        new_config = {}
        for page in conf.keys():
            new_config[page] = self.modify_key_config(conf[page])
        return new_config

    def modify_key_config(self, conf: dict):
        key_count = self.key_count
        new_config = {}
        for _key in conf.keys():
            key = _key
            if _key < 0:
                key = key_count + _key
            new_config[key] = conf[_key]
        return new_config

class ImageOrFile:
    file: str = ''
    image: Image.Image
    is_file = False
    def __init__(self, file_or_image: Any):
        if type(file_or_image) != str and type(file_or_image) != Image.Image:
            logging.warning(file_or_image)
            raise(ExceptionWrongTypeGiven)

        if type(file_or_image) == str:
            self.file = file_or_image
            self.is_file = True
        elif type(file_or_image) == Image.Image:
            self.image = file_or_image

class ExceptionWrongTypeGiven(Exception):
    pass