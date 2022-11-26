from PIL import Image, ImageDraw, ImageFont
from mydeck import TriggerAppBase, ImageOrFile
import datetime

# whole image size
X: int = 100
Y: int = 100

class AppCalendar(TriggerAppBase):
    use_day_trigger: bool = True

    def set_image_to_key(self, key: int, page: str):
        now = datetime.datetime.now()
        im = Image.new('RGB', (X, Y), (0, 0, 0))
        font = ImageFont.truetype(self.mydeck.font_path, 29)
        draw = ImageDraw.Draw(im)
        wday = now.strftime('%a')
        date_text = "{0:02d}/{1:02d}".format(now.month, now.day)
        color = "white"
        if wday in 'Sun':
            color="red"
        draw.text((12, 5), font=font, text=wday,fill=color)
        draw.text((5, 33), font=font, text=date_text, fill="white")
        font = ImageFont.truetype(self.mydeck.font_path, 25)
        draw.text((10, 67), font=font, text=str(now.year), fill="white")

        self.mydeck.update_key_image(
            key,
            self.mydeck.render_key_image(
                ImageOrFile(im),
                "",
                'black',
                True,
            )
        )
