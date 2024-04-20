from PIL import Image, ImageDraw, ImageFont
from mydeck import MyDeck, DialAppBase
import logging


class AppDialSample(DialAppBase):
    _dial_conf = {
        "app_command": "DialSample",
    }
    dial_command = {
        "DialSample": lambda app, dial_num, event, value: app.render_dial(dial_num, event, value),
    }

    def __init__(self, mydeck: MyDeck, option: dict = {}):
        super().__init__(mydeck, option)

    def key_setup(self):
        page = self.mydeck.current_page()
        dial_num = self.page_dial.get(page)
        if dial_num is not None:
            self.mydeck.set_dial_conf(page, dial_num, self._dial_conf)

    def render_dial(self, dial_num, event, value):
        size: tuple[int, int] = self.mydeck.deck.touchscreen_image_format()[
            "size"]
        im = Image.new('RGB', size, (0, 0, 0))
        draw = ImageDraw.Draw(im)
        font = ImageFont.truetype(self.mydeck.font_path, 25)
        position_text = "{}".format([dial_num, event, value])
        draw.text((250, 35), text=position_text, fill="white", font=font)
        self.set_touchscreen(
            {
                "image": im, "x": 0, "y": 0,
                "width": self.touchscreen_width(),
                "height": self.touchscreen_height(),
            })
