from PIL import Image, ImageDraw
from mystreamdeck import AppBase
import math
import datetime
import time
import sys

# whole image size
X = 100
Y = 100

class Clock(AppBase):
    # if app reuquire thread, true
    use_thread = True

    x = 50
    y = 50
    l = 45
    key_command = {}

    def __init__(self, mydeck, option={}):
        super().__init__(mydeck, option)

    def hour_pos (self, h, m, s):
        if h == 12:
            h = 0
        h *= 5
        h += (m / 12 + s / 60) / 60
        l = self.l * 0.7
        return self._pos(l, h)

    def min_pos(self, m, s):
        l = self.l * 0.9
        m += s / 60
        return self._pos(l, m)

    def sec_pos(self, second):
        return self._pos(self.l, second)

    def _pos (self, l, t):
        x = l * math.cos(2 * math.pi / 60 * (15 - t))
        y = l * math.sin(2 * math.pi / 60 * (15 - t)) * -1
        return [self.x + x, self.y + y]

    def get_current_hms(self):
        now = datetime.datetime.now()
        return [now.hour, now.minute, now.second]

    def get_current_clock_image(self, hms):
        im = Image.new('RGB', (X, Y), (0, 0, 0))
        draw = ImageDraw.Draw(im)

        hour_xy = self.hour_pos(hms[0], hms[1], hms[2])
        min_xy = self.min_pos(hms[1], hms[2])
        sec_xy = self.sec_pos(hms[2])

        draw.line((self.x, self.y, hour_xy[0], hour_xy[1]), width=3, fill=(255,255,255))
        draw.line((self.x, self.y, min_xy[0],  min_xy[1]),  width=2)
        draw.line((self.x, self.y, sec_xy[0],  sec_xy[1]),  width=2, fill=(255,0,0))

        return im

    def set_image_to_key(self, key, page):
        hms = self.get_current_hms()
        im = self.get_current_clock_image(hms)
        self.mydeck.update_key_image(
            key,
            self.mydeck.render_key_image(
                im,
                "{0:02d}:{1:02d}:{2:02d}".format(hms[0], hms[1], hms[2]),
                'black',
            )
        )
