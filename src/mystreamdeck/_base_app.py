import time
import sys
import datetime
from typing import NoReturn, TYPE_CHECKING
from mystreamdeck import MyStreamDeck

class ExceptionNoDeck(Exception):
    pass

class App:
    # if app reuquires thread, true
    use_thread: bool = False
    # if app works in background, set True
    is_background_app: bool = False

    key_command: dict = {}

    def __init__(self, mydeck: 'MyStreamDeck'):
        self.mydeck: 'MyStreamDeck'
        # sleep sec in thread
        self.time_to_sleep: int = 1
        # execute command when button pushed
        self.command = None
        # not in target page
        self.in_other_page: bool = True
        # app is running now
        self.in_working: bool = False
        # need to stop thread
        self.stop: bool = False
        # dict: key is page name and value is key number.
        self.page_key: dict = {}

        self.previous_page: str = ''
        self.previous_date: str = ''
        self.mydeck = mydeck
        if self.mydeck.deck is None:
            raise ExceptionNoDeck

class GameAppBase(App):
    require_key_count: int
    enable: bool = True
    def __init__ (self, mydeck :MyStreamDeck, start_key_num :int = 0):
        super().__init__(mydeck)
        self.data: dict = {}
        if self.require_key_count > mydeck.key_count:
            self.enable = False

class AppBase(App):
    def __init__(self, mydeck: 'MyStreamDeck', option: dict = {}):
        super().__init__(mydeck)

        self.temp_wait = 0
        self.mydeck = mydeck
        if option.get("page_key") is not None:
            self.page_key = option["page_key"]
        if option.get("command") is not None:
            self.command = option["command"]

    # implment it in subclass
    def set_image_to_key(self, key: int, page: str):
        print("Implemnt set_image_to_key in subclass for app to use thread anytime.")

    # check current page is whther app's target or not
    def is_in_target_page(self):
        page = self.mydeck.current_page()
        key  = self.page_key.get(page)
        if key is not None:
            return True
        else:
            self.in_other_page = True
            return False

    # if use_thread is true, this method is call in thread
    def start(self) -> NoReturn:
        if not self.is_in_target_page():
            sys.exit()
            return

        while True:
            self.in_working = True

            try:
                page = self.mydeck.current_page()
                key  = self.page_key.get(page)
                if key is not None:
                    self.set_image_to_key(key, page)
            except Exception as e:
                print('Error in app_base.start', type(self), e)

            # exit when main process is finished
            if self.check_to_stop():
                break

            time.sleep(self.time_to_sleep)
        sys.exit()

    def check_to_stop(self) -> bool:
        if self.mydeck._exit or self.stop or not self.is_in_target_page():
            self.stop_app()
            return True
        return False

    def stop_app(self):
        if self.in_working:
            self.stop = False
            self.in_working = False

    # if command is given as option, set key to command
    def key_setup(self):
        if self.command is not None:
            key_config =self.mydeck.key_config()
            for page_value in self.page_key.items():
                key_config[page_value[0]][page_value[1]] = {
                    "command": self.command,
                    "no_image": True,
                }

    # check whether processing is required or not(hourly)
    def is_required_process_hourly(self) -> bool:
        now = datetime.datetime.now()
        return self._is_required_process(now.month, now.day, now.hour)

    # check whether processing is required or not(daily)
    def is_required_process_daily(self):
        now = datetime.datetime.now()
        return self._is_required_process(now.month, now.day)

    def _is_required_process(self, m: int, d: int, h: int = 0) -> bool:
        now = datetime.datetime.now()
        page = self.mydeck.current_page()
        date_text = "{0:02d}/{1:02d}/{2:02d}".format(m, d, h)

        # quit when page and date is not changed
        if self.in_other_page or page != self.previous_page or date_text != self.previous_date:
            self.in_other_page = False
            self.previous_page = page
            self.previous_date = date_text
            return True
        else:
            return False

class BackgroundAppBase(App):
    use_thread: bool = True

    def __init__ (self, mydeck, config={}):
        super().__init__(mydeck)
        # need to stop thread
        self.stop: bool = False
        # sleep time in thread
        self.sleep: int  = 1

        self.in_working = False
        self.is_background_app = True

    def execute_in_thread(self):
        print("implement in subclass")
        raise Exception

    def start(self):
        mydeck = self.mydeck
        while True:
            if mydeck.in_alert() is False:
                self.execute_in_thread()

            if mydeck._exit:
                break

            time.sleep(self.sleep)

        sys.exit()