from PIL import Image, ImageDraw, ImageFont
from mystreamdeck import MyStreamDeck, AppBase, ImageOrFile
import time
import sys
import datetime

# whole image size
X = 100
Y = 100

class Calendar(AppBase):
    # if app reuquire thread, true
    use_thread = True

    previous_page = ''
    previous_date = ''

    def __init__(self, mydeck: MyStreamDeck, option: dict = {}):
        super().__init__(mydeck, option)

    def set_image_to_key(self, key: int, page: str):
        if self.is_required_process_daily() is False:
            return False

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
