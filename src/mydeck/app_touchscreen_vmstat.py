from PIL import Image, ImageDraw, ImageFont
from mydeck import MyDeck, TouchAppBase
import subprocess


class AppTouchscreenVmstat(TouchAppBase):
    use_thread: bool = True

    def __init__(self, mydeck: MyDeck, option: dict = {}):
        super().__init__(mydeck, option)
        self.time_to_sleep: float = 1

    def key_setup(self):
        pass

    def set_image_to_touchscreen(self):
        im = Image.new("RGB", (800, 100), (0, 0, 0))
        draw = ImageDraw.Draw(im)
        font = ImageFont.truetype(self.mydeck.font_path, 10)
        cp = subprocess.run(["vmstat", "1", "5"], capture_output=True)
        draw.text((10, 5), text=cp.stdout.decode(),
                  font=font, fill="white")
        self.set_touchscreen(
            {
                "image": im, "x": 0, "y": 0,
                "width": self.touchscreen_width(),
                "height": self.touchscreen_height(),
            }
        )
