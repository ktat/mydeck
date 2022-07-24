import time
import os
import sys

class MyStreamDeckAlert:
    # if app reuquire thread, true
    use_thread = True
    # dict: key is page name and value is key number.
    page_key = {}
    # need to stop thread
    stop = False

    _check_function = None
    _previous_checke_time = 0
    in_alert = False

    def __init__ (self, mydeck, check_function, check_interval, alert_key_config):
        self._check_interval = check_interval
        self._previous_checke_time = 0
        self._check_function = check_function
        self.mydeck = mydeck
        mydeck.add_alert_key_conf(alert_key_config)

    def start(self):
        while True:
            current = time.time()
            if current - self._previous_checke_time > self._check_interval:
                self._previous_checke_time = current
                if self._check_function():
                    self.mydeck.handler_alert()
                    self.in_alert = True
                    self.mydeck.set_alert(1)
                else:
                    self.mydeck.handler_alert_stop()
                    self.in_alert =False
                    self.mydeck.set_alert(0)

            if self.mydeck._exit:
                break
            time.sleep(1)
        sys.exit()

    def key_setup(self):
        return True
