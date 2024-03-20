from PIL import Image, ImageDraw, ImageFont
from mydeck import MyDeck, ThreadAppBase, ImageOrFile
import logging

# whole image size
X: int = 800
Y: int = 100


class AppTouchscreenSample(ThreadAppBase):
    use_thread = False
    _touchscreen_conf = {
        "app_command": "TouchScreenSample",
    }
    touch_command = {
        "TouchScreenSample": lambda app, event, args: app.render_touchscreen_sample_image(args),
    }

    def __init__(self, mydeck: MyDeck, option: dict = {}):
        super().__init__(mydeck, option)

    def key_setup(self):
        page = self.mydeck.current_page()
        logging.debug(self._touchscreen_conf)
        self.mydeck.set_touchscreen_conf(page, self._touchscreen_conf)

    def render_touchscreen_sample_image(self, args):
        x: int = args.get("x") or 0
        y: int = args.get("y") or 0
        im = Image.new('RGB', (800, 100), (0, 0, 0))
        draw = ImageDraw.Draw(im)
        font = ImageFont.truetype(self.mydeck.font_path, 25)
        position_text = "Clicked x: {0:d}, y: {1:d}".format(x, y)
        draw.text((250, 35), text=position_text, fill="white", font=font)
        self.mydeck.set_touchscreen(
            {"image": im, "x": 0, "y": 0, "width": 800, "height": 100})
