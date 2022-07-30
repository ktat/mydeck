import re
import subprocess
import os
import sys
import yaml
import time
import threading
import requests
import os.path
import wand.image
import importlib

from PIL import Image, ImageDraw, ImageFont
from StreamDeck.ImageHelpers import PILHelper
from StreamDeck.DeviceManager import DeviceManager

class MyStreamDeck:
    """STREAM DECK COnfiguration"""
    deck = ''
    child_pid = None
    apps = []
    _alert_func = None
    _loaded_apps = {}
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
    font_path = "/usr/share/fonts/truetype/freefont/FreeMono.ttf"

    def __init__ (self, opt):
        if opt.get('alert_func'):
            self._alert_func = opt['alert_func']
        if opt.get("font_path"):
            self.font_path = opt["font_path"]
        if opt.get("apps"):
            for app in opt.get("apps"):
                self.apps.append(app(self))
        if opt.get("config"):
            self._config_file = opt.get('config')
            self._KEY_CONFIG_GAME = {}
            self.load_conf_from_file()

    def init_deck(self, deck):
        self.deck = deck

        deck.open()

        self.threading_apps()

        self.key_setup()

        # Wait until all application threads have terminated (for this example,
        # this is when all deck handles are closed).
        for t in threading.enumerate():
            try:
                t.join()
            except RuntimeError as e:
                print(e)
                pass

    def in_game_status(self):
        return self._game_status == 1

    def in_alert(self):
        return self._in_alert == 1

    def key_config(self):
        if self._config_file != '':
            statinfo = os.stat(self._config_file)
            if self._config_file_mtime < statinfo.st_mtime:
                self._config_file_mtime = statinfo.st_mtime
                self.load_conf_from_file()
                print("reload config")

        return self._KEY_CONFIG

    def load_conf_from_file(self):
        statinfo = os.stat(self._config_file)
        if self._config_file_mtime < statinfo.st_mtime:
            f = open(self._config_file)
            conf = yaml.safe_load(f)
            alert_config = {}
            if conf.get("apps"):
                loaded = self._loaded_apps
                for app in conf["apps"].keys():
                    if loaded.get(app):
                        continue
                    m = importlib.import_module('mystreamdeck.' + app, "mystreamdeck")
                    o = getattr(m, app)(self, conf['apps'][app])
                    self.apps.append(o)
                    if app == 'Alert':
                        o.set_check_func(self._alert_func)
                        alert_config = conf["apps"][app]["key_config"]

            if conf.get("games"):
                self._KEY_CONFIG['@GAME'] = {}
                for app in conf["games"].keys():
                    if loaded.get(app):
                        continue
                    m = importlib.import_module('mystreamdeck.Game' + app, "mystreamdeck")
                    getattr(m, 'Game'+app)(self, conf['games'][app])

            self._KEY_CONFIG = conf["key_config"]
            self._KEY_CONFIG['~ALERT'] = alert_config

            for k in self._KEY_CONFIG_GAME.keys():
                self._KEY_CONFIG['@GAME'][k]  = self._KEY_CONFIG_GAME[k]

            for app in self.apps:
                app.key_setup()

            self._config_file_mtime = statinfo.st_mtime

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
            print(self.key_config().get(name))
            self.key_setup()

    # display keys and set key callbacks
    def key_setup(self):
        deck =  self.deck
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
                if conf.get('image') is None and conf.get('image_url') is None:
                    chrome = conf['chrome']
                    url = chrome[-1]
                    icon_url = re.sub(r'^(https?://[^/]+).*$', '\\1/favicon.ico', url)
                    icon = re.sub(r'^https?://([^/]+).*$', '\\1', url)
                    self.save_image(conf, icon_url, '/tmp/' + 'mystreamdeck-' + icon + '.ico')
                elif conf.get("image_url") is not None:
                    chrome = conf['chrome']
                    icon_name = re.sub(r'^https?://([^/]+).*$', '\\1', chrome[-1])
                    ext = re.sub(r'.+(\.\w+)$', '\\1', conf["image_url"])
                    self.save_image(conf, conf["image_url"], '/tmp/' + 'mystreamdeck-' + icon_name + ext)

            self.update_key_image(key, self.render_key_image(conf["image"], conf.get("label"), conf.get("background_color")))


    def save_image(self, conf, icon_url, icon_file):
        if os.path.exists(icon_file) is False:
            print(icon_url)
            res = requests.get(icon_url)
            if res.status_code == requests.codes.ok:
                with open(icon_file, mode="wb") as f:
                    f.write(res.content)
                if self.check_icon_file(icon_file):
                    conf["image"] = icon_file
        else:
            conf["image"] = icon_file

        if conf.get("image") is None:
            conf["image"] = "./src/Assets/world.png"

    def check_icon_file(self, file_path):
        try:
            print("file: {}".format(file_path))
            with wand.image.Image(filename=file_path):
                return True
        except Exception as e:
            print(e)
            os.rename(file_path, file_path + '.back')
            return False

    # change key image
    def update_key_image(self, key, image):
        deck = self.deck
        with deck:
            # Update requested key with the generated image.
            deck.set_key_image(key, image)

    # render key image and label
    def render_key_image(self, icon_filename_or_object, label, bg_color):
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
        image = PILHelper.create_scaled_image(deck, icon, margins=[0, 0, 20, 0], background=bg_color)

        draw = ImageDraw.Draw(image)
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
                        for app in self.apps:
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
                        for app in self.apps:
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
                        page_name = conf.get("change_page")
                        if page_name == "@previous":
                            print(self._previous_pages)
                            self.set_current_page(self.pop_last_previous_page())
                        else:
                            self.set_current_page(page_name)

                        self.key_setup()


    # handler for sigalrm to notify alert
    def handler_alert(self):
        self.set_alert(1)
        self.set_current_page("~ALERT")

    # handler for usr2 to stop alert
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


    def set_game_key(self, key, conf):
        self._GAME_KEY_CONFIG[key] = conf
        self.set_key(key, conf)

    def add_game_key_conf(self, conf):
        key_config = self.key_config()
        for key in conf.keys():
            key_config['@GAME'][key] = conf[key]
            self._KEY_CONFIG_GAME[key] = conf[key]

    def add_game_command(self, name, command):
        self._game_command[name] = command

    def add_alert_key_conf(self, conf):
        key_config = self.key_config()
        key_config['~ALERT'] = conf

    def exit_game(self):
        self.set_game_status(0)
        self.set_current_page("@GAME")
        self._GAME_KEY_CONFIG = {}

    def set_key_conf(self, page, key, conf):
        self._KEY_CONFIG[page][key] = conf

    def check_window_switch(self):
        if not self.in_alert():
            new_result = self.get_current_window()

            if new_result is not None and new_result != self._previous_window:
                print(new_result)
                self._previous_window = new_result
                self.handler_switch(new_result)

    # handler for sigusr1 to switch window
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

    def check_thread(self, mydeck_alert):
        while True:
            time.sleep(1)
            if mydeck.in_alert is False:
                self.check_window_switch()

            if self._exit:
                break

        print("check thread end!")
        sys.exit()

    def threading_apps(self):
        for app in self.apps:
            if app.use_thread:
                t = threading.Thread(target=lambda: app.start(), args=())
                t.start()

