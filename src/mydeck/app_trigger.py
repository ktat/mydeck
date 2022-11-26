import datetime
import time
from mydeck import MyDeck, BackgroundAppBase
import logging

class AppTrigger(BackgroundAppBase):
    # if app reuquire thread, true
    use_thread = True
    # need to stop thread
    stop = False

    def __init__(self, mydeck: MyDeck, config: dict = {}):
        super().__init__(mydeck)
        self.now = datetime.datetime.now()

    def start(self):
        while True:
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

            # sleep untile next munite
            time.sleep(datetime.datetime.now().second % 60)

