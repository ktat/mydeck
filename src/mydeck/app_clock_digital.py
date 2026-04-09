from PIL import Image, ImageDraw, ImageFont
from mydeck import ThreadAppBase, ImageOrFile
import datetime

# whole image size
X: int = 100
Y: int = 100


class AppClockDigital(ThreadAppBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self._font = ImageFont.truetype(self.mydeck.font_path, 25)
        except (IOError, AttributeError):
            self._font = ImageFont.load_default()

    def set_image_to_key(self, key: int, page: str):
        if not self.is_in_target_page():
            return

        now = datetime.datetime.now()
        im = Image.new('RGB', (X, Y), (0, 0, 0))
        draw = ImageDraw.Draw(im)
        time_text = f"{now.hour:02d}:{now.minute:02d}:{now.second:02d}"
        draw.text((2, 33), font=self._font, text=time_text, fill="white")

        self.update_key_image(
            key,
            self.mydeck.render_key_image(
                ImageOrFile(im),
                "",
                'black',
                True,
            )
        )
