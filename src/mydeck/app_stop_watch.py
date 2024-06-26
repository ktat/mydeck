import time
import threading
import sys

from PIL import Image, ImageDraw, ImageFont
from mydeck import AppBase, ImageOrFile, MyDeck, ROOT_DIR

# whole image size
X: int = 100
Y: int = 100


class AppStopWatch(AppBase):
    _key_conf = {
        "app_command": "MyDeckStopWatchToggle",
        "image": ROOT_DIR + "/Assets/stopwatch.png",
        "label": "Stop Watch",
    }
    key_command = {
        "MyDeckStopWatchToggle": lambda app: app.toggle_count(),
    }

    def __init__(self, mydeck: MyDeck, option: dict = {}):
        super().__init__(mydeck, option)

    # setup key configuration
    def key_setup(self):
        page = self.mydeck.current_page()
        key = self.page_key.get(page)
        if key is not None:
            self.mydeck.set_key_conf(page, key, self._key_conf)

    def do_start(self):
        self.stop(False)
        page = self.mydeck.current_page()
        key = self.page_key.get(page)
        if key is not None:
            self.mydeck.set_key_conf(page, key, self._key_conf)
            t = threading.Thread(target=lambda: self.count_up(key), args=())
            t.start()

    def count_up(self, key: int) -> None:
        t = time.time()
        font = ImageFont.truetype(self.mydeck.font_path, 35)
        while True:
            self.in_working = True

            time.sleep(0.1)

            # exit when main process is finished
            if self.check_to_stop():
                self.stop_app()
                self.key_setup()
                break

            if self.mydeck.current_page() in self.page_key.keys():
                im = Image.new('RGB', (X, Y), (0, 0, 0))
                draw = ImageDraw.Draw(im)
                n = "{0:02.2f}".format(int((time.time() - t) * 100) / 100)
                draw.text((0, 45), text=n, font=font,
                          andhor="ms", fill="white")
                self.mydeck.update_key_image(key, self.mydeck.render_key_image(
                    ImageOrFile(im), "STOP/START", "black"), False)
        self.init_app_flag()
        sys.exit()

    def toggle_count(self):
        if self.in_working:
            self.stop(True)
        else:
            self.do_start()
