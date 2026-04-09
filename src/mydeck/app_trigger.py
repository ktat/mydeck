import datetime
import time
from mydeck import MyDeck, BackgroundAppBase
import logging


class AppTrigger(BackgroundAppBase):
    # if app requires thread, true
    use_thread = True

    def __init__(self, mydeck: MyDeck, config: dict = {}):
        super().__init__(mydeck)
        self.last_checked_time = datetime.datetime.now()

    def start(self):
        while not self.check_to_stop():
            current_time = datetime.datetime.now()
            day_changed = current_time.day != self.last_checked_time.day
            hour_changed = current_time.hour != self.last_checked_time.hour
            min_changed = current_time.minute != self.last_checked_time.minute

            if day_changed or hour_changed or min_changed:
                for app in self.mydeck.config.apps:
                    if day_changed and app.use_day_trigger:
                        logging.debug("trigger day for " + app.name())
                        app.trigger.set()
                    elif hour_changed and app.use_hour_trigger:
                        logging.debug("trigger hour for " + app.name())
                        app.trigger.set()
                    elif min_changed and app.use_minute_trigger:
                        logging.debug("trigger minute for " + app.name())
                        app.trigger.set()
                self.last_checked_time = current_time

            time.sleep(1)

        self.debug("exit in start")

    def check_to_stop(self) -> bool:
        """Return true when the deck exists or current page is not in the target of app."""

        return self.mydeck._exit or self._stop
