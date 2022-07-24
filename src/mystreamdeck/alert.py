import time
import os
import signal

class MyStreamDeckAlert:
    _check_function = None

    def __init__ (self, mydeck, check_interval=60, alert_key_config={}):
        self._check_interval = check_interval
        self._previous_checke_time = 0
        self._mydeck = mydeck
        mydeck.add_alert_key_conf(alert_key_config)

    def register_check_function(self, check_function):
        self._check_function = check_function

    def check_alert(self):
        current = time.time()
        if current - self._previous_checke_time > self._check_interval:
            self._previous_checke_time = current
            child_pid = self._mydeck.child_pid
            if self._check_function():
                # sigalrm to raise alert
                os.kill(child_pid, signal.SIGALRM)
            else:
                # sigusr2 to cancel alert
                os.kill(child_pid, signal.SIGUSR2)


