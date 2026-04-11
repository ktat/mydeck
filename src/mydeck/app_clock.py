import math
import datetime
import time

from PIL import Image, ImageDraw
from typing import Tuple
from mydeck import MyDeck, ThreadAppBase, ImageOrFile

# whole image size
X: int = 100
Y: int = 100

XY = tuple[float, float]
HMS = tuple[int, int, int]


class AppClock(ThreadAppBase):
    """Show an analog clock on a key"""

    center_x: int = 50
    center_y: int = 50
    hand_length: int = 45

    def __init__(self, mydeck: MyDeck, option: dict = {}):
        super().__init__(mydeck, option)

    def _hand_end_point(self, length: float, time_units: float) -> XY:
        # Convert time units to radians; subtract pi/2 so 0 points up (12 o'clock)
        angle = (time_units * (2 * math.pi / 60)) - (math.pi / 2)
        x = self.center_x + length * math.cos(angle)
        y = self.center_y + length * math.sin(angle)
        return (x, y)

    def hour_pos(self, h: float, m: int, s: int) -> XY:
        if h == 12:
            h = 0
        h *= 5
        h += m / 12 + s / 720
        return self._hand_end_point(self.hand_length * 0.7, h)

    def min_pos(self, m: float, s: int) -> XY:
        m += s / 60
        return self._hand_end_point(self.hand_length * 0.9, m)

    def sec_pos(self, second: float) -> XY:
        return self._hand_end_point(self.hand_length, second)

    def get_current_hms(self) -> HMS:
        now = datetime.datetime.now()
        return (now.hour, now.minute, now.second)

    def get_current_clock_image(self, hms: Tuple[int, int, int]) -> Image.Image:
        im = Image.new('RGB', (X, Y), (0, 0, 0))
        draw = ImageDraw.Draw(im)

        hour_xy = self.hour_pos(hms[0], hms[1], hms[2])
        min_xy = self.min_pos(hms[1], hms[2])
        sec_xy = self.sec_pos(hms[2])

        draw.line(
            (self.center_x, self.center_y, hour_xy[0], hour_xy[1]), width=3, fill=(255, 255, 255))
        draw.line((self.center_x, self.center_y, min_xy[0], min_xy[1]), width=2)
        draw.line((self.center_x, self.center_y, sec_xy[0], sec_xy[1]), width=2, fill=(255, 0, 0))

        return im

    def set_image_to_key(self, key: int, page: str):
        hms = self.get_current_hms()
        im = self.get_current_clock_image(hms)
        self.update_key_image(
            key,
            self.mydeck.render_key_image(
                ImageOrFile(im),
                f"{hms[0]:02d}:{hms[1]:02d}:{hms[2]:02d}",
                'black',
            )
        )
