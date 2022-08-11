import sys
import time

class BackgroundAppBase:
    use_thread = True
    # need to stop thread
    stop = False
    # sleep time in thread
    sleep  = 1

    in_working = False
    is_background_app = True

    def __init__ (self, mydeck, config={}):
        self.mydeck = mydeck

    def start(self):
        mydeck = self.mydeck
        while True:
            if mydeck.in_alert() is False:
                self.execute_in_thread()

            if mydeck._exit:
                break

            time.sleep(self.sleep)

        sys.exit()
