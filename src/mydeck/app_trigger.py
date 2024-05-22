import datetime
import time
from mydeck import MyDeck, BackgroundAppBase
import logging
import sys


class AppTrigger(BackgroundAppBase):
    # if app reuquire thread, true
    use_thread = True

    def __init__(self, mydeck: MyDeck, config: dict = {}):
        super().__init__(mydeck)
        self.now = datetime.datetime.now()

    def start(self):
        while True:
            # exit when main process is finished
            if self.check_to_stop():
                break

            current_time = datetime.datetime.now()
            if current_time.day != self.now.day:
                for app in self.mydeck.config.apps:
                    if app.use_day_trigger or app.use_hour_trigger or app.use_minute_trigger:
                        logging.debug("trigger day for " + app.name())
                        app.trigger.set()
                        self.now = current_time
            elif current_time.hour != self.now.hour:
                for app in self.mydeck.config.apps:
                    if app.use_hour_trigger or app.use_minute_trigger:
                        logging.debug("trigger hour for " + app.name())
                        app.trigger.set()
                        self.now = current_time
            elif current_time.minute != self.now.minute:
                for app in self.mydeck.config.apps:
                    if app.use_minute_trigger:
                        logging.debug("trigger minute for " + app.name())
                        app.trigger.set()
                        self.now = current_time

            # sleep until next 10 seconds
            time.sleep(datetime.datetime.now().second % 10)

        self.debug("exit in start")
        sys.exit()

    def check_to_stop(self) -> bool:
        """Return true when the deck exists or current page is not in the target of app."""

        return self.mydeck._exit or self._stop
