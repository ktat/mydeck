import time
import sys
import datetime

class AppBase:
    index = None
    # if app reuquire thread, true
    use_thread = False
    # dict: key is page name and value is key number.
    page_key = {}
    # need to stop thread
    stop = False
    # sleep sec in thread
    time_to_sleep = 1
    # execute command when button pushed
    command = None
    # not in target page
    in_other_page = True

    def __init__(self, mydeck, option={}):
        self.temp_wait = 0
        self.mydeck = mydeck
        if option.get("page_key") is not None:
            self.page_key = option["page_key"]
        if option.get("command") is not None:
            self.command = option["command"]

    # implment it in subclass
    def set_iamge_to_key(self, key, page):
        print("Implemnt set_image_to_key in subclass.")
        pass

    # if use_thread is true, this method is call in thread
    def start(self):
        while True:
            self.mydeck.working_apps[self.index] = True
            
            # exit when main process is finished
            if self.mydeck._exit or self.stop:
                print("STOP")
                if self.mydeck.working_apps.get(self.index):
                    del self.mydeck.working_apps[self.index]

                break

            try:
                page = self.mydeck.current_page()
                key  = self.page_key.get(page)
                if key is not None:
                    self.set_image_to_key(key, page)
                else:
                    self.in_other_page = True
            except Exception as e:
                print('Error in app_base.start', type(self), e)
                pass

            # exit when main process is finished
            if self.mydeck._exit or self.stop:
                break
            time.sleep(self.time_to_sleep)
        sys.exit()

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
    def is_required_process_hourly(self):
        now = datetime.datetime.now()
        return self._is_required_process(now.month, now.day, now.hour)

    # check whether processing is required or not(daily)
    def is_required_process_daily(self):
        now = datetime.datetime.now()
        return self._is_required_process(now.month, now.day)

    def _is_required_process(self, m, d, h=0):
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
