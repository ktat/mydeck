import time
import sys
import datetime
import traceback
from threading import Event
import logging
import re

from typing import NoReturn, TYPE_CHECKING, Any
from . import MyDeck


class ExceptionNoDeck(Exception):
    pass


class App:
    """Commn base class of an application and a game."""

    class AppType:
        KEY = 1
        DIAL = 2
        TOUCHSCREEN = 3

    # app type
    app_type: int = AppType.KEY
    # if app reuquires thread, true
    use_thread: bool = False
    # if app works in background, set True
    is_background_app: bool = False
    # if app works on a specfic timing, set True
    is_hook_app: bool = False
    # if use day, hour, minute trigger, set True
    use_day_trigger: bool = False
    use_hour_trigger: bool = False
    use_minute_trigger: bool = False
    use_trigger: bool = False

    key_command: dict = {}
    touch_command: dict = {}

    def __init__(self, mydeck: 'MyDeck'):
        """Constructor pass MyDeck instance."""
        self.mydeck: 'MyDeck'
        # sleep sec in thread
        self.time_to_sleep: float = 1
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
        # list: contains page names
        self.page: list = []
        # trigger for trigger app
        self.trigger: Any[None, Event] = None
        # if first time in loop
        self.is_first: bool = True

        self.previous_page: str = ''
        self.previous_date: str = ''
        self.mydeck = mydeck
        if self.mydeck.deck is None:
            raise ExceptionNoDeck

    def name(self) -> str:
        return "%s" % self.__class__.__name__

    def is_key_app(self) -> bool:
        return self.app_type == App.AppType.KEY

    def is_dial_app(self) -> bool:
        return self.app_type == App.AppType.DIAL

    def is_touchscreen_app(self) -> bool:
        return self.app_type == App.AppType.TOUCHSCREEN

    def init_app_flag(self) -> bool:
        self.stop = False
        self.is_first = True
        self.in_working = False
        return True

    def debug(self, message: str) -> None:
        app_address: str = "(unknown)"
        search = re.search(r'at ([^>]+)>', str(self))
        if search is not None:
            app_address = search.group(1)
        logging.debug("[%s] %s %s in %s at %s (%s)", self.mydeck.deck.id(),
                      self.name(), message, self.mydeck.current_page(), datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), app_address)

    def touchscreen_width(self) -> int:
        if self.mydeck.deck.is_touch():
            if (size := self.mydeck.deck.touchscreen_image_format().get("size")) is not None:
                return int(size[0])
        return 0

    def touchscreen_height(self) -> int:
        if self.mydeck.deck.is_touch():
            if (size := self.mydeck.deck.touchscreen_image_format().get("size")) is not None:
                return int(size[1])
        return 0


class GameAppBase(App):
    """Base class of a game application"""
    require_key_count: int
    enable: bool = True

    def __init__(self, mydeck: MyDeck, start_key_num: int = 0):
        """Constructor. pass MyDeck instance and key number of put game."""
        super().__init__(mydeck)
        self.data: dict = {}
        if self.require_key_count > mydeck.key_count:
            self.enable = False


class AppBase(App):
    """Base class of a normal application"""

    def __init__(self, mydeck: 'MyDeck', option: dict = {}):
        """Constructor. Pass MyDeck instance and app configuration."""
        super().__init__(mydeck)

        self.temp_wait = 0
        self.mydeck = mydeck
        if option.get("page_key") is not None:
            self.page_key = option["page_key"]
        if option.get("page") is not None:
            self.page = option["page"]
        if option.get("command") is not None:
            self.command = option["command"]

    # implment it in subclass
    def set_image_to_key(self, key: int, page: str):
        """Set image to key. Implement this method in subclass."""
        logging.critical(
            "Implemnt set_image_to_key in subclass for app to use thread anytime.")

    # implment it in subclass
    def set_image_to_touchscreen(self):
        """Set image to key. Implement this method in subclass."""
        logging.critical(
            "Implemnt set_image_to_key in subclass for app to use thread anytime.")

    # check current page is whther app's target or not
    def is_in_target_page(self) -> bool:
        """Return true when the current page is the target of the app."""
        page = self.mydeck.current_page()
        key = self.page_key.get(page)
        if key is not None:
            return True
        else:
            self.in_other_page = True
            return False

    # if use_thread is true, this method is call in thread
    def start(self) -> NoReturn:
        """Start application when the current page is the target of the app."""

        while True:
            self.debug("working")
            self.in_working = True

            # exit when main process is finished
            if self.check_to_stop():
                self.debug("should be stopped")
                break

            try:
                page = self.mydeck.current_page()
                if self.is_key_app():
                    key = self.page_key.get(page)
                    if key is not None:
                        self.set_image_to_key(key, page)
                elif self.is_touchscreen_app():
                    self.set_image_to_touchscreen()
            except Exception as e:
                logging.critical(
                    '[{}] Error in app_base.start {} {} at {}'.format(self.mydeck.deck.id(), type(self), e, self.mydeck.current_page()))
                logging.debug(traceback.format_exc())
                break

            if self.use_trigger:
                self.trigger.wait()
                self.debug("triggered")
                self.trigger.clear()

            time.sleep(self.time_to_sleep)
            self.is_first = False

        self.debug("finished")
        self.init_app_flag()
        sys.exit()

    def check_to_stop(self) -> bool:
        """Return true when the deck exists or current page is not in the target of app."""

        if self.mydeck._exit or self.stop or not self.is_in_target_page():
            self.stop_app()
            return True

        return False

    def stop_app(self):
        """Stop application. It must be called within app."""
        self.stop = True
        if self.use_trigger:
            self.trigger.set()

    def key_setup(self):
        """Setup app keys. If command is given as option, set key to command."""
        if self.command is not None:
            key_config = self.mydeck.key_config()
            for page_value in self.page_key.items():
                if key_config.get(page_value[0]) is None:
                    key_config[page_value[0]] = {}

                key_config[page_value[0]][page_value[1]] = {
                    "command": self.command,
                    "no_image": True,
                }

    def is_required_process_hourly(self) -> bool:
        """Check whether processing is required or not(hourly)"""
        now = datetime.datetime.now()
        return self._is_required_process(now.month, now.day, now.hour)

    def is_required_process_daily(self) -> bool:
        """Check whether processing is required or not(daily)"""
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


class ThreadAppBase(AppBase):
    use_thread: bool = True


class TriggerAppBase(AppBase):
    use_thread: bool = True

    def __init__(self, mydeck: MyDeck, config: dict = {}):
        super().__init__(mydeck, config)
        if self.use_day_trigger or self.use_hour_trigger or self.use_minute_trigger:
            self.use_trigger = True
        self.trigger = Event()


class BackgroundAppBase(App):
    """Base class of the application which works in background."""
    use_thread: bool = True

    def __init__(self, mydeck: MyDeck, config: dict = {}):
        """Pass MyDeck instance and configuration"""
        super().__init__(mydeck)
        # need to stop thread
        self.stop: bool = False
        # sleep time in thread
        self.sleep: float = 1

        self.in_working = False
        self.is_background_app = True

    def execute_in_thread(self):
        """Execute the app in thread. It should be imlemented in subclass."""
        logging.critical("implement in subclass")
        raise Exception

    def start(self):
        """Start application in thread."""
        mydeck = self.mydeck
        while True:
            if mydeck.in_alert() is False:
                self.execute_in_thread()

            if mydeck._exit:
                break

            time.sleep(self.sleep)

        self.debug("app exit")
        self.init_app_flag()
        sys.exit()


class HookAppBase(App):
    """Base class of the application which works is a specific timing."""
    use_thread: bool = False
    on: str

    def __init__(self, mydeck: MyDeck, config: dict = {}):
        """Pass MyDeck instance and configuration"""
        super().__init__(mydeck)
        if config is not None:
            on = config.get('on')
            if on is not None:
                self.on = on
        self.in_working = False
        self.is_hook_app = True

    def execute_on_hook(self):
        """Execute the app on hook point. It should be imlemented in subclass."""
        logging.critical("implement in subclass")
        raise Exception

    def do(self, hookname: str):
        """Run application on a hook."""
        if self.on == hookname:
            self.execute_on_hook()

        sys.exit()


class TouchAppBase(AppBase):
    app_type: int = App.AppType.TOUCHSCREEN

    def key_setup(self):
        """Setup app keys. If command is given as option, set key to command."""
        if self.command is not None:
            touchscreen_config = self.mydeck.touchscreen_config()
            # TODO

    # check current page is whther app's target or not
    def is_in_target_page(self) -> bool:
        """Return true when the current page is the target of the app."""

        page = self.mydeck.current_page()

        if page in self.page:
            return True
        else:
            self.in_other_page = True
            return False


class DialAppBase(AppBase):
    app_type: int = App.AppType.DIAL
