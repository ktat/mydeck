import time
import sys

class AppBase:
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

    def __init__(self, mydeck, option={}):
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
            try:
                page = self.mydeck.current_page()
                key  = self.page_key.get(page)
                if key is not None:
                    self.set_image_to_key(key, page)
            except Exception as e:
                print(e)
                pass
            # exit when main process is finished
            if self.mydeck._exit:
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
