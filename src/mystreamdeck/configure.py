import re
import subprocess
import signal
import os
import yaml
import time

from PIL import Image, ImageDraw, ImageFont
from StreamDeck.ImageHelpers import PILHelper

class MyStreamDeck:
    """STREAM DECK COnfiguration"""
    deck = ''
    child_pid = None
    _current_page = '@HOME'
    _previous_pages = ['@HOME']
    _previous_window=  ''
    _in_alert = 0
    _game_status = 0
    _game_command = {}
    _KEY_CONFIG = {}
    _KEY_CONFIG_GAME = {}
    _KEY_CONFIG_ALERT = {}
    _GAME_KEY_CONFIG = {}
    _config_file = ''
    _config_file_mtime = 0

    # path of font
    font_path = "/usr/share/fonts/truetype/freefont/FreeMono.ttf"

    def __init__ (self, opt):
        if opt.get("font_path"):
            self.font_path = opt["font_path"]
        if opt.get("config"):
            self._config_file = opt.get('config')
            self._KEY_CONFIG_GAME = {}
            self._KEY_CONFIG_ALERT = {}
            self.load_conf_from_file()

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
                print("reload conifg")

        return self._KEY_CONFIG

    def load_conf_from_file(self):
        f = open(self._config_file)
        self._KEY_CONFIG = yaml.safe_load(f)
        statinfo = os.stat(self._config_file)
        self._config_file_mtime = statinfo.st_mtime
        for k in self._KEY_CONFIG_GAME.keys():
            self._KEY_CONFIG['@GAME'][k]  = self._KEY_CONFIG_GAME[k]
        self._KEY_CONFIG['~ALERT'] = self._KEY_CONFIG_ALERT
            
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
        self._current_page = name

    def set_current_page(self, name):
        print("c:set_current_page:"+name)
        if name[0] != "~":
            self.set_alert(0)
            self.set_previous_page(self._current_page)

        if name != self._current_page:
            self._current_page = name
            self.set_game_status(0)
            self.deck.reset()
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
        if current_page[0:5] == "GAME_" or current_page == "@GAME":
            self._current_page = "@GAME"

        # Set initial key images.
        for key in range(deck.key_count()):
            configuration = self.key_config().get(self.current_page()).get(key)
            if configuration:
                self.set_key(key, configuration)

        # Register callback function for when a key state changes.
        deck.set_key_callback(lambda deck, key, state: self.key_change_callback(key, state))

    # set key image and label
    def set_key(self, key, conf):
        deck = self.deck
        if conf is not None:
            self.update_key_image(key, self.render_key_image(conf["image"], conf.get("label")))

    # change key image
    def update_key_image(self, key, image):
        deck = self.deck
        with deck:
            # Update requested key with the generated image.
            deck.set_key_image(key, image)

    # render key image and label
    def render_key_image(self, icon_filename, label):
        deck = self.deck
        if label is None:
            label = ""

        icon = Image.open(icon_filename)
        image = PILHelper.create_scaled_image(deck, icon, margins=[0, 0, 20, 0])

        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype(self.font_path, 14)
        draw.text((image.width / 2, image.height - 5), font=font, text=label, anchor="ms", fill="white")

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
                if conf.get("name") == "exit":
                    # Use a scoped-with on the deck to ensure we're the only thread
                    # using it right now.
                    with deck:
                        # Reset deck, clearing all button images.
                        deck.reset()

                        # Close deck handle, terminating internal worker threads.
                        deck.close()

                elif type(conf.get("command")) is str and self._game_command.get(conf.get("command")):
                    command = self._game_command.get(conf.get("command"))
                    with deck:
                        command(conf)

                elif conf.get("name") == "alert":
                    with deck:
                        set_alert(0)
                        self.key_setup()

                elif conf:
                    command = conf.get("command")
                    if command:
                        print(command)
                        subprocess.Popen(command)

                if conf.get("change_panel") is not None:
                    with deck:
                        page_name = conf.get("change_panel")
                        if page_name == "@previous":
                            print(self._previous_pages)
                            self.set_current_page(self.pop_last_previous_page())
                        else:
                            self.set_current_page(page_name)

                        self.key_setup()


    # sgnal handler for sigusr1 to switch window
    def handler_switch(self, signum, frame):
      # enabled when alert is off and not playing game
      if not self.in_alert() and not self.in_game_status():
          page = self.get_current_window()

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

    # signal handler for sigalrm to notify alert
    def handler_alert(self, signum, frame):
        self.set_alert(1)
        self.set_current_page("~ALERT")

    # signal handler for usr2 to stop alert
    def handler_alert_stop(self, signum, frame):
        if self.current_page() == "~ALERT":
            print("reset")
            self.set_alert(0)
            self.set_current_page(self.pop_last_previous_page())

    # signal hanlder for sigchld
    def handler_sigchld(self, signum, frame):
        os.waitpid(-1, os.WNOHANG)

    # get curent window name
    def get_current_window(self):
        result = None
        window_ids = subprocess.check_output(["xdotool", "getwindowfocus"]).decode().rsplit()
        if window_ids and len(window_ids) > 0:
            window_id = window_ids[0]
            result = subprocess.check_output(["xdotool", "getwindowname", window_id]).decode()
            result = re.sub(r'^Meet.+Google Chrome$', 'Meet - Google Chrome', result)
            result = re.sub(r"\n", "", result)
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
        self._KEY_CONFIG_ALERT = conf

    def exit_game(self):
        self.set_game_status(0)
        self.set_current_page("@GAME")
        self._GAME_KEY_CONFIG = {}

    def register_singal_handler(self):
        _handler_switch     = lambda signum, frame: self.handler_switch(signum, frame)
        _handler_alert      = lambda signum, frame: self.handler_alert(signum, frame)
        _handler_alert_stop = lambda signum, frame: self.handler_alert_stop(signum, frame)
        signal.signal(signal.SIGUSR1, _handler_switch)     # sinbal to check active window switching
        signal.signal(signal.SIGALRM, _handler_alert)      # signal for alert
        signal.signal(signal.SIGUSR2, _handler_alert_stop) # signal top cancel alert

    def register_singal_handler_for_parent(self):
        signal.signal(signal.SIGCHLD, lambda signum, frame: self.handler_sigchld(signum, frame))

    def check_window_switch(self):
        if not self.in_alert():
            new_result = self.get_current_window()

            if new_result is not None and new_result != self._previous_window:
                print(new_result)
                self._previous_window = new_result
                # send sigusr1 when active window is switched
                os.kill(self.child_pid, signal.SIGUSR1)

