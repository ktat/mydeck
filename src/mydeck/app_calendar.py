from PIL import Image, ImageDraw, ImageFont
from mydeck import TriggerAppBase, ImageOrFile
import datetime

# whole image size
X: int = 100
Y: int = 100


class AppCalendar(TriggerAppBase):
    use_day_trigger: bool = True
    sample_data = {
        "command": [
            "google-chrome",
            "--profile-directory=Default",
            "https://calendar.google.com/calendar/u/0/",
        ]
    }

    def set_image_to_key(self, key: int, page: str):
        now = datetime.datetime.now()
        im = Image.new('RGB', (X, Y), (0, 0, 0))
        font_large = ImageFont.truetype(self.mydeck.font_path, 29)
        font_small = ImageFont.truetype(self.mydeck.font_path, 25)
        draw = ImageDraw.Draw(im)
        wday = now.strftime('%a')
        date_text = now.strftime('%m/%d')
        color = "red" if wday == "Sun" else "white"
        draw.text((12, 5), font=font_large, text=wday, fill=color)
        draw.text((5, 33), font=font_large, text=date_text, fill="white")
        draw.text((10, 67), font=font_small, text=str(now.year), fill="white")

        self.update_key_image(
            key,
            self.mydeck.render_key_image(
                ImageOrFile(im),
                "",
                'black',
                True,
            )
        )
