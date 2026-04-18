import time
import sys
from mydeck import MyDeck, BackgroundAppBase
from typing import Callable, Optional


class AppAlert(BackgroundAppBase):
    # if app reuquire thread, true
    use_thread = True

    _check_function: Optional[Callable] = None
    _check_interval: int = 300
    _retry_interval: int = 60
    _previous_check_time: int = 0
    in_alert = False
    in_working = False
    is_background_app = True

    def __init__(self, mydeck: MyDeck, config: dict):
        alert_key_config: dict = {}
        self._check_interval = self._get_config_val(config, "check_interval", self._check_interval, int)
        self._retry_interval = self._get_config_val(config, "retry_interval", self._retry_interval, int)
        conf: Optional[dict] = config.get("key_config")
        if isinstance(conf, dict):
            alert_key_config = conf

        self._previous_check_time = 0
        self.mydeck = mydeck

    def _get_config_val(self, config: dict, key: str, default, expected_type):
        val = config.get(key)
        return val if isinstance(val, expected_type) else default

    def set_check_func(self, f):
        self._check_function = f

    def set_conf(self, conf):
        self.mydeck.key_config()['~ALERT'] = conf

    def start(self):
        if self._check_function is None:
            return

        while not self.mydeck._exit:
            try:
                current = time.time()
                interval = self._retry_interval if self.in_alert else self._check_interval

                if current - self._previous_check_time > interval:
                    self._previous_check_time = current

                    try:
                        alert_triggered = self._check_function()
                    except Exception as e:
                        print(f"Error executing check function: {e}")
                        alert_triggered = False

                    if alert_triggered:
                        self.mydeck.handler_alert()
                        self.in_alert = True
                        self.mydeck.set_alert_on()
                    else:
                        self.mydeck.handler_alert_stop()
                        self.in_alert = False
                        self.mydeck.set_alert_off()

                time.sleep(1)
            except Exception as e:
                print(f"Unexpected error in AppAlert loop: {e}")
                time.sleep(5)
