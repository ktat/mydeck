from PIL import Image, ImageDraw, ImageFont
from mydeck import ThreadAppBase, ImageOrFile
import datetime

# whole image size
X: int = 100
Y: int = 100


class AppClockDigital(ThreadAppBase):
    def set_image_to_key(self, key: int, page: str):
        if not self.is_in_target_page():
            return

        now = datetime.datetime.now()
        im = Image.new('RGB', (X, Y), (0, 0, 0))
        font = ImageFont.truetype(self.mydeck.font_path, 25)
        draw = ImageDraw.Draw(im)
        time_text = "{0:02d}:{1:02d}:{2:02d}".format(
            now.hour, now.minute, now.second)
        draw.text((2, 33), font=font, text=time_text, fill="white")

        self.update_key_image(
            key,
            self.mydeck.render_key_image(
                ImageOrFile(im),
                "",
                'black',
                True,
            )
        )
