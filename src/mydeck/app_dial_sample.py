from PIL import Image, ImageDraw, ImageFont
from PIL.ImageFont import FreeTypeFont, ImageFont as PILImageFont
from typing import Optional, Union
from mydeck import MyDeck, DialAppBase
import logging


class AppDialSample(DialAppBase):
    _dial_conf = {
        "app_command": "DialSample",
    }
    dial_command = {
        "DialSample": lambda app, dial_num, event, value: app.render_dial(dial_num, event, value),
    }

    def __init__(self, mydeck: MyDeck, option: Optional[dict] = None):
        if option is None:
            option = {}
        super().__init__(mydeck, option)
        self._font: Union[FreeTypeFont, PILImageFont]
        try:
            self._font = ImageFont.truetype(self.mydeck.font_path, 25)
        except (OSError, AttributeError) as e:
            logging.warning(f"Could not load custom font, using default. Error: {e}")
            self._font = ImageFont.load_default()

    def key_setup(self):
        page = self.mydeck.current_page()
        dial_num = self.page_dial.get(page)
        if dial_num is not None:
            self.mydeck.set_dial_conf(page, dial_num, self._dial_conf)

    def render_dial(self, dial_num: int, event: str, value: float) -> None:
        size: tuple[int, int] = self.mydeck.deck.touchscreen_image_format()["size"]
        im = Image.new('RGB', size, (0, 0, 0))
        draw = ImageDraw.Draw(im)
        position_text = f"Dial: {dial_num} | Event: {event} | Value: {value}"
        draw.text((250, 35), text=position_text, fill="white", font=self._font)
        self.set_touchscreen(
            {
                "image": im, "x": 0, "y": 0,
                "width": self.touchscreen_width(),
                "height": self.touchscreen_height(),
            })
