from PIL import Image, ImageDraw, ImageFont
from mydeck import MyDeck, TouchAppBase
import random
import re
import requests


class AppTouchscreenQuotes(TouchAppBase):
    use_thread: bool = True
    quotes: dict = {"results": []}

    def __init__(self, mydeck: MyDeck, option: dict = {}):
        super().__init__(mydeck, option)
        self.time_to_sleep: float = 15

    def key_setup(self):
        pass

    def set_image_to_touchscreen(self):
        size: tuple[int, int] = self.mydeck.deck.touchscreen_image_format()[
            "size"]
        im = Image.new("RGB", size, (0, 0, 0))
        draw = ImageDraw.Draw(im)
        font = ImageFont.truetype(self.mydeck.font_path, 25)
        quotes = AppTouchscreenQuotes.quotes

        if len(quotes["results"]) == 0:
            try:
                response = requests.get(
                    "https://api.quotable.io/quotes?limit=500")

                if response.status_code == 200:
                    quotes = response.json()
                else:
                    quotes["results"] = [
                        {
                            "content": "Failed to retrieve a quote: " + str(response.status_code),
                            "author": "mydeck"
                        }
                    ]
            except Exception as e:
                quotes["results"] = [
                    {
                        "content": "Failed to retrieve a quote: " + str(e),
                        "author": "mydeck"
                    }
                ]

        random_quote = random.choice(quotes["results"])
        quote_text = random_quote["content"]
        quote_author = random_quote["author"]

        quote_text = re.sub(
            r'^(.{64}[-\w_,]*[^-\w_,]+)', "\\1\n", quote_text, flags=re.MULTILINE)

        draw.text((10, 10), text=quote_text + "\n by " +
                  quote_author, font=font, fill="white")

        self.set_touchscreen(
            {
                "image": im, "x": 0, "y": 0,
                "width": self.touchscreen_width(),
                "height": self.touchscreen_height(),
            }
        )
