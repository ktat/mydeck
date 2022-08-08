from cairosvg import svg2png
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

from PIL import Image, ImageDraw, ImageFont
from StreamDeck.ImageHelpers import PILHelper
from StreamDeck.DeviceManager import DeviceManager

class MyStreamDeck:
    """STREAM DECK COnfiguration"""
    deck = None
    config = None
    child_pid = None
    working_apps = {}
    _alert_func = None
    _exit = False
    _current_page = '@HOME'
    _previous_pages = ['@HOME']
    _previous_window=  ''
    _in_alert = 0
    _game_status = 0
    _game_command = {}
    _KEY_CONFIG = {}
    _KEY_CONFIG_GAME = {}
    _KEY_ACTION_APP = {}
    _GAME_KEY_CONFIG = {}
    _config_file = ''
    _config_file_mtime = 0
    _window_title_regexps = [
        [r'^Meet.+Google Chrome$', 'Meet - Google Chrome'],
        [r'^(Slack \|.+?\|.+?\|).+', '\\1'],
    ]

    # path of font
    font_path = "/usr/share/fonts/truetype/freefont/FreeSans.ttf"

    def __init__ (self, opt):
        if opt.get('alert_func'):
            self._alert_func = opt['alert_func']
        if opt.get("font_path"):
            self.font_path = opt["font_path"]
        if opt.get("config"):
            self._config_file = opt.get('config')
            self._KEY_CONFIG_GAME = {}
            self.config = Config(self, self._config_file)

    def init_deck(self, deck):
        self.deck = deck

        deck.open()

        if self.config is not None:
            self.config.reflect_config()

        self.key_setup()


        # Wait until all application threads have terminated (for this example,
        # this is when all deck handles are closed).
        for t in threading.enumerate():
            try:
                t.join()
            except RuntimeError as e:
                print("Error in init_deck", e)
                pass

    def in_game_status(self):
        return self._game_status == 1

    def in_alert(self):
        return self._in_alert == 1

    def key_config(self):
        if self._config_file != '':
            # self.load_conf_from_file()
            self.config.reflect_config()

        return self._KEY_CONFIG

    def set_alert(self, n):
        self._in_alert = n

    def set_game_status(self, n):
        self._game_status = n

    def previous_page(self):
        if len(self._previous_pages) > 0:
            return self._previous_pages[-1]
        else:
            return ''

    def pop_last_previous_page(self):
        print("a:pop_previous_page:")
        print(self._previous_pages)
        if len(self._previous_pages) > 0:
            return self._previous_pages.pop(-1)
        else:
            return '@HOME'

    def set_previous_page(self, name):
        if  name[0] != '~' and (len(self._previous_pages) == 0 or self._previous_pages[-1] != name):
            self._previous_pages.append(name)
            print("b:set_previous_page:"+name)

    def current_page(self):
        return self._current_page

    def set_current_page_without_setup(self, name):
        self.set_previous_page(name)
        self.set_alert(0)
        self._current_page = name

    def set_current_page(self, name):
        print("c:set_current_page:"+name)
        self.set_previous_page(self._current_page)

        if name[0] != "~ALERT":
            self.set_alert(0)

        if name != self._current_page:
            self._current_page = name
            self.set_game_status(0)
            self.deck.reset()
            self.key_setup()

    # display keys and set key callbacks
    def key_setup(self):
        deck = self.deck
        print("Opened '{}' device (serial number: '{}', fw: '{}')".format(
            deck.deck_type(), deck.get_serial_number(), deck.get_firmware_version()
        ))

        # Set initial screen brightness to 30%.
        deck.set_brightness(30)

        current_page = self.current_page()

        # Set initial key images.
        for key in range(deck.key_count()):
            page_configuration = self.key_config().get(self.current_page())
            if page_configuration is not None and page_configuration.get(key):
                self.set_key(key, page_configuration.get(key))

        # Register callback function for the time when a key state changes.
        deck.set_key_callback(lambda deck, key, state: self.key_change_callback(key, state))

    # set key image and label
    def set_key(self, key, conf):
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
                self.update_key_image(key, self.render_key_image(conf["image"], conf.get("label"), conf.get("background_color")))


    def image_url_to_image(self, conf, url=None):
        image_url = conf.get('image_url')
        icon_name = None
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

    def save_image(self, icon_url, icon_file):
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

    def check_icon_file(self, file_path):
        try:
            print("file: {}".format(file_path))
            with wand.image.Image(filename=file_path):
                return True
        except Exception as e:
            print("Error in check_icon_file:", e)
            os.rename(file_path, file_path + '.back')
            return False

    # change key image
    def update_key_image(self, key, image):
        deck = self.deck
        with deck:
            # Update requested key with the generated image.
            deck.set_key_image(key, image)

    # render key image and label
    def render_key_image(self, icon_filename_or_object, label, bg_color, no_label=False):
        deck = self.deck
        font_bg_color = "white"
        if bg_color is None or bg_color == "black":
            bg_color = "black"
        else:
            font_bg_color = "black"
        if label is None:
            label = ""

        icon = icon_filename_or_object
        if type(icon) == str:
            icon = Image.open(icon_filename_or_object)

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
    def key_change_callback(self, key, state):
        deck = self.deck
        # Print new key state
        print("Deck {} Key {} = {}".format(deck.id(), key, state), flush=True)


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
                        for app in self.config.apps:
                            app.stop = True
                        sys.exit()

                elif type(conf.get("command")) is str and self._game_command.get(conf.get("command")):
                    command = self._game_command.get(conf.get("command"))
                    with deck:
                        command(conf)

                elif conf.get("name") == "alert":
                    with deck:
                        set_alert(0)
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
                        for app in self.config.apps:
                            if app.page_key.get(self.current_page()):
                                for key in app.key_command:
                                    if command == key:
                                        found = True
                                        cmd = app.key_command[key]
                                        cmd(app)
                                        break
                            if found:
                                break

                if conf.get("change_page") is not None:
                    with deck:
                        self.check_working_apps()
                        page_name = conf.get("change_page")
                        if page_name == "@previous":
                            print(self._previous_pages)
                            self.set_current_page(self.pop_last_previous_page())
                        else:
                            self.set_current_page(page_name)

    def check_working_apps(self):
        while len(self.working_apps.keys()) > 0:
            print("check_working_apps", self.working_apps)
            time.sleep(0.5)

    # handler to notify alert
    def handler_alert(self):
        self.set_alert(1)
        self.set_current_page("~ALERT")

    # handler to stop alert
    def handler_alert_stop(self):
        if self.current_page() == "~ALERT":
            print("stop alert")
            self.set_alert(0)
            self.set_current_page(self.pop_last_previous_page())

    # get curent window name
    def get_current_window(self):
        result = None
        try:
            window_ids = subprocess.check_output(["xdotool", "getwindowfocus"]).decode().rsplit()
            if window_ids and len(window_ids) > 0:
                window_id = window_ids[0]
                result = subprocess.check_output(["xdotool", "getwindowname", window_id]).decode()
                for reg in self._window_title_regexps:
                    result = re.sub(reg[0], reg[1], result)
                    result = re.sub(r"\n", "", result)
            return result
        except:
            return result

    def set_key_config(self, conf):
        if conf is None:
            conf = {}
        self._KEY_CONFIG = conf

    def set_game_key(self, key, conf):
        self._GAME_KEY_CONFIG[key] = conf
        self.set_key(key, conf)

    def add_game_key_conf(self, conf):
        key_config = self.key_config()
        if key_config.get('@GAME') is None:
            key_config['@GAME'] = {}
        for key in conf.keys():
            key_config['@GAME'][key] = conf[key]
            self._KEY_CONFIG_GAME[key] = conf[key]

    def add_game_command(self, name, command):
        self._game_command[name] = command

    def set_alert_key_conf(self, conf):
        key_config = self.key_config()
        key_config['~ALERT'] = conf

    def exit_game(self):
        self.set_game_status(0)
        self.set_current_page("@GAME")
        self._GAME_KEY_CONFIG = {}

    def set_key_conf(self, page, key, conf):
        if self._KEY_CONFIG.get(page) is None:
            self._KEY_CONFIG[page] = {}
        self._KEY_CONFIG[page][key] = conf

    def check_window_switch(self):
        if not self.in_alert():
            new_result = self.get_current_window()

            if new_result is not None and new_result != self._previous_window:
                print(new_result)
                self._previous_window = new_result
                self.handler_switch(new_result)

    # handler to switch window
    def handler_switch(self, page):
        # enabled when alert is off and not playing game
        if not self.in_alert() and not self.in_game_status():
            current_page = self.current_page()
            previous_page = self.previous_page()

            if self.key_config().get(page):
                self.set_current_page(page)
                # when no configuration for window and current_page is not started with '@', set previous_page
            elif current_page[0:1] != '@':
                self.set_current_page(self.pop_last_previous_page())
            else:
                print(self.current_page())
                print(self.previous_page())

    def deck_start(self):
        streamdecks = DeviceManager().enumerate()
        print("Found {} Stream Deck(s).\n".format(len(streamdecks)))

        for index, deck in enumerate(streamdecks):
            # This example only works with devices that have screens.
            if not deck.is_visual():
                continue

            self.init_deck(deck)

            # Wait until all application threads have terminated (for this example,
            # this is when all deck handles are closed).
            for t in threading.enumerate():
                try:
                    t.join()
                except RuntimeError:
                    pass

        print("deck_start end!")
        sys.exit()

    def thread(self, app):
        while True:
            time.sleep(1)
            app()

    def threading_apps(self, apps):
        time.sleep(0.5)
        for app in apps:
            if app.use_thread:
                t = threading.Thread(target=lambda: app.start(), args=())
                t.start()
        t = threading.Thread(target=lambda: self.check_thread(), args=())
        t.start()

    def check_thread(self):
        while True:
            if self.in_alert() is False:
                self.check_window_switch()

            if self._exit:
                break

            time.sleep(1)

        print("check thread end!")
        sys.exit()

class Config:
    _file_mtime = 0
    _file = ''
    _config_content = {}
    _loaded = {}
    conf = {}
    apps = []
    mydeck = None
    def __init__(self, mydeck, file):
        self.mydeck = mydeck
        self._file = file


    def reflect_config(self):
        loaded = self.load()
        if loaded is not None:
            try:
                self.parse(loaded)
                self.mydeck.threading_apps(self.apps)
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

    def parse(self, conf):
        self.mydeck.set_key_config(conf.get('key_config'))
        alert_config = {}
        self.parse_apps(conf.get('apps'))
        self.parse_games(conf.get('games'))
        self.parse_alert(conf.get('alert'))

    def parse_games(self, games_conf):
        for game in games_conf.keys():
            self.parse_game(game, games_conf[game])

    def parse_game(self, game, game_conf):
        if game_conf is None:
            return False
        game = 'Game' + game
        m = self._load_module(game)
        getattr(m, game)(self.mydeck, game_conf)

    def parse_apps(self, apps_conf):
        for app in self.apps:
            app.stop = True

        # destloy apps
        for app in self.apps:
            del app

        if apps_conf is None:
            return False

        i = 1
        for app_conf in apps_conf:
            app = self.parse_app(app_conf)
            app.index = i
            i += 1

    def parse_app(self, app_conf):
        if app_conf is None:
            return False

        app = app_conf.get('app')
        m = self._load_module(app)
        o = getattr(m, app)(self.mydeck, app_conf.get('option'))
        self.apps.append(o)
        o.key_setup()

        return o

    def parse_alert(self, app_conf):
        if app_conf is None:
            return False

        o = self.parse_app({'app': 'Alert', 'option': app_conf})
        if o is not False:
            o.set_check_func(self.mydeck._alert_func)
            self.mydeck.set_alert_key_conf(app_conf["key_config"])

    def _load_module(self, app):
        module = re.sub('([A-Z])', r'_\1', app)[1:].lower()
        if self._loaded.get(app) is None:
            self._loaded[app] = importlib.import_module('mystreamdeck.' + module, "mystreamdeck")

        return self._loaded[app]
