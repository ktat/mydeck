from PIL import Image, ImageDraw, ImageFont
from mystreamdeck import AppBase, ImageOrFile, MyStreamDeck
from typing import NoReturn, Optional
import math
import datetime
import time
import threading
import sys

class CommunicateDeck(AppBase):
    _key_conf = {
        "app_command": "MyStreamDeckCommunicateDeck",
        "image": "./src/Assets/world.png",
        "label": "Communicate",
    }
    key_command = {
        "MyStreamDeckCommunicateDeck": lambda app: app.communicate(),
    }

    def __init__(self, mydeck: MyStreamDeck, option: dict = {}):
        self.index = 0
        self.to_deck: MyStreamDeck
        self.to_deck_config: Optional[dict] = None
        super().__init__(mydeck, option)
        to_deck: Optional[str] = option.get('to_deck')
        if to_deck is not None:
            mydeck = self.mydeck.mydecks.mydeck(to_deck)
            if mydeck is not None:
                self.to_deck = mydeck
            self.to_deck_config = option.get('to_deck_config')

    # setup key configuration
    def key_setup(self):
        page = self.mydeck.current_page()
        key = self.page_key.get(page)
        if key is not None:
            self.mydeck.set_key_conf(page, key, self._key_conf)

    def communicate(self):
        if self.to_deck_config is not None:
            for page in self.to_deck_config.keys():
                if self.to_deck.current_page() == page:
                    for key in self.to_deck_config[page].keys():
                        configs = self.to_deck_config[page][key]
                        if len(configs) <= self.index:
                            self.index = 0
                        conf = configs[self.index]
                        self.to_deck.update_key_image(key, self.to_deck.render_key_image(ImageOrFile(conf["image"]), conf.get("label") or '', conf.get("background_color") or ''))
                        self.index += 1
                        
                    break
