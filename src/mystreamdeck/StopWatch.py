from PIL import Image, ImageDraw, ImageFont
import math
import datetime
import time
import threading
import sys

# whole image size
X = 100
Y = 100

class StopWatch:
    # if app reuquire thread, true
    use_thread = False
    # dict: key is page name and value is key number.
    page_key = {}
    # need to stop thread
    stop = False

    _key_conf = {
        "start": {
            "app_command": "MyStreamDeckStopWatchStart",
            "image": "./src/Assets/stopwatch.png",
            "label": "Stop Watch",
        },
        "stop": {
            "app_command": "MyStreamDeckStopWatchStop",
            "image": "./src/Assets/stopwatch.png",
            "label": "Stop Watch",
        }
    }
    key_command = {
        "MyStreamDeckStopWatchStart": lambda app: app.do_start(),
        "MyStreamDeckStopWatchStop":  lambda app: app.do_stop(),
    }

    def __init__(self, mydeck, option={}):
        self.mydeck = mydeck
        if option.get("page_key"):
            self.page_key = option["page_key"]

    # setup key configuration
    def key_setup(self):
        for page in self.page_key.keys():
            key = self.page_key[page]
            self.mydeck.set_key_conf(page, key, self._key_conf["start"])

    def do_start(self):
        print("do_start")
        self.stop = False        
        page = self.mydeck.current_page()
        key = self.page_key[page]
        self.mydeck.set_key_conf(page, key, self._key_conf["stop"])
        t = threading.Thread(target=lambda : self.count_up(key), args=())
        t.start()


    def count_up(self, key):
        t = time.time()
        font = ImageFont.truetype(self.mydeck.font_path, 35)
        while True:
            time.sleep(0.1)
            if self.mydeck.current_page() in self.page_key.keys():
                im = Image.new('RGB', (X, Y), (0, 0, 0))
                draw = ImageDraw.Draw(im)
                n = "{0:02.2f}".format(int((time.time() - t) * 100) / 100)
                draw.text((0,45), text=n, font = font, andhor="ms", fill="white")
                self.mydeck.update_key_image(key, self.mydeck.render_key_image(im, "STOP/START", "black"))
            if self.stop or self.mydeck._exit:
                break
        sys.exit()
            
    def do_stop(self):
        self.stop = True
        self.key_setup()
