from PIL import Image, ImageDraw, ImageFont
from mystreamdeck import AppBase
import datetime
import time
import sys

# whole image size
X = 100
Y = 100

class Calendar(AppBase):
    # if app reuquire thread, true
    use_thread = True

    previous_page = ''
    previous_date = ''

    def __init__(self, mydeck, option={}):
        super().__init__(mydeck, option)

    def set_image_to_key(self, key, page):
        now = datetime.datetime.now()
        date_text = "{0:02d}/{1:02d}".format(now.month, now.day)

        # quit when page and date is not changed
        if self.in_other_page or page != self.previous_page or date_text != self.previous_date:
            self.previous_page = page
            self.previous_date = date_text
        else:
            return False

        im = Image.new('RGB', (X, Y), (0, 0, 0))
        font = ImageFont.truetype(self.mydeck.font_path, 29)
        draw = ImageDraw.Draw(im)
        wday = now.strftime('%a')
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
                im,
                "",
                'black',
                True,
            )
        )
