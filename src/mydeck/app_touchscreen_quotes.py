from PIL import Image, ImageDraw, ImageFont
from mydeck import MyDeck, TouchAppBase
import random
import re
import requests


class AppTouchscreenQuotes(TouchAppBase):
    use_thread: bool = True

    def __init__(self, mydeck: MyDeck, option: dict = {}):
        super().__init__(mydeck, option)
        self.time_to_sleep: float = 15
        self._quotes_cache: list[dict] = []  # instance-level to avoid shared state

    def key_setup(self):
        pass

    def _fetch_quotes(self) -> list[dict]:
        if self._quotes_cache:
            return self._quotes_cache
        try:
            response = requests.get(
                "https://api.quotable.io/quotes?limit=500", timeout=10)
            response.raise_for_status()
            data = response.json()
            self._quotes_cache = data.get("results", [])
            return self._quotes_cache
        except (requests.RequestException, ValueError) as e:
            return [{"content": f"Failed to retrieve a quote: {e}", "author": "mydeck"}]

    def set_image_to_touchscreen(self):
        size: tuple[int, int] = self.mydeck.deck.touchscreen_image_format()["size"]
        im = Image.new("RGB", size, (0, 0, 0))
        draw = ImageDraw.Draw(im)
        font = ImageFont.truetype(self.mydeck.font_path, 25)

        quotes = self._fetch_quotes()
        random_quote = random.choice(quotes)
        quote_text = random_quote["content"]
        quote_author = random_quote["author"]

        quote_text = re.sub(
            r'^(.{64}[-\w_,]*[^-\w_,]+)', "\\1\n", quote_text, flags=re.MULTILINE)

        draw.text((10, 10), text=f"{quote_text}\n by {quote_author}",
                  font=font, fill="white")

        self.set_touchscreen(
            {
                "image": im, "x": 0, "y": 0,
                "width": self.touchscreen_width(),
                "height": self.touchscreen_height(),
            }
        )
