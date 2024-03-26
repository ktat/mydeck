from PIL import Image, ImageDraw, ImageFont
from mydeck import MyDeck, TouchAppBase
import logging


class AppTouchscreenSample(TouchAppBase):
    _touchscreen_conf = {
        "app_command": "TouchscreenSample",
    }
    touch_command = {
        "TouchscreenSample": lambda app, event, args: app.render_touchscreen_sample_image(args),
    }

    def __init__(self, mydeck: MyDeck, option: dict = {}):
        super().__init__(mydeck, option)

    def key_setup(self):
        page = self.mydeck.current_page()
        self.mydeck.set_touchscreen_conf(page, self._touchscreen_conf)

    def render_touchscreen_sample_image(self, args):
        x: int = args.get("x") or 0
        y: int = args.get("y") or 0
        im = Image.new('RGB', (800, 100), (0, 0, 0))
        draw = ImageDraw.Draw(im)
        font = ImageFont.truetype(self.mydeck.font_path, 25)
        position_text = "Clicked x: {0:d}, y: {1:d}".format(x, y)
        draw.text((250, 35), text=position_text, fill="white", font=font)
        draw.rectangle([x, y, x + 10, y + 10], fill="yellow")
        self.set_touchscreen(
            {
                "image": im, "x": 0, "y": 0,
                "width": self.touchscreen_width(),
                "height": self.touchscreen_height(),
            })
