import time
import sys
from mydeck import MyDeck, BackgroundAppBase
from typing import Callable, Optional

class AppAlert(BackgroundAppBase):
    # if app reuquire thread, true
    use_thread = True
    # need to stop thread
    stop = False

    _check_function: Optional[Callable] = None
    _check_interval: int = 300
    _retry_interval: int = 60
    _previous_checke_time: int = 0
    in_alert = False
    in_working = False
    is_background_app = True

    def __init__ (self, mydeck: MyDeck, config: dict):
        alert_key_config: dict = {}
        check_interval = config.get("check_interval")
        if check_interval is not None and type(check_interval) == int:
            self._check_interval = check_interval
        retry_interval = config.get("retry_interval")
        if retry_interval is not None and type(retry_interval) == int:
            self._retry_interval = retry_interval
        conf = config.get("key_cofnig")
        if conf is not None and type(conf) == dict:
            alert_key_config = conf

        self._previous_checke_time = 0
        self.mydeck = mydeck

    def set_check_func(self, f):
        self._check_function = f

    def set_conf(self, conf):
        self.mydeck.key_config()['~ALERT'] = conf

    def start(self):
        if self._check_function is None:
            return

        while True:
            current = time.time()
            interval = self._check_interval
            if self.in_alert:
                interval = self._retry_interval
            if current - self._previous_checke_time > interval:
                self._previous_checke_time = current
                if self._check_function():
                    self.mydeck.handler_alert()
                    self.in_alert = True
                    self.mydeck.set_alert_on()
                else:
                    self.mydeck.handler_alert_stop()
                    self.in_alert =False
                    self.mydeck.set_alert_off()

            if self.mydeck._exit:
                break
            time.sleep(1)
        sys.exit()
