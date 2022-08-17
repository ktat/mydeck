from mystreamdeck import AppBase, ImageOrFile, MyStreamDeck
from typing import Optional

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
        self.index = {}
        self.page_cache = {}
        self.to_deck: MyStreamDeck
        self.to_deck_config: Optional[dict] = None
        super().__init__(mydeck, option)
        self.to_deck_name: Optional[str] = option.get('to_deck')
        self.to_deck_config: Optional[dict] = option.get('to_deck_config')

    # setup key configuration
    def key_setup(self):
        page = self.mydeck.current_page()
        key = self.page_key.get(page)
        if key is not None:
            self.mydeck.set_key_conf(page, key, self._key_conf)
            conf = self.page_cache.get(page)
            if conf is not None:
                self.mydeck.update_key_image(key, self.mydeck.render_key_image(ImageOrFile(conf["image"]), conf.get("label") or '', conf.get("background_color") or ''))


    def communicate(self):
        to_deck_name: str = self.to_deck_name
        page = self.mydeck.current_page()
        key = self.page_key.get(page)
        if key is not None:
            if to_deck_name is not None:
                to_deck = self.mydeck.mydecks.mydeck(to_deck_name)
                if to_deck is not None:
                    self.to_deck = to_deck

                conf: Optional[dict] = None
                for page in self.to_deck_config.keys():
                    if self.to_deck.current_page() == page:
                        if self.index.get(page) is None:
                            self.index[page] = 0
                        for to_key in self.to_deck_config[page].keys():
                            configs = self.to_deck_config[page][to_key]
                            if len(configs) <= self.index[page]:
                                self.index[page] = 0
                            conf = configs[self.index[page]]
                            self.to_deck.update_key_image(to_key, self.to_deck.render_key_image(ImageOrFile(conf["image"]), conf.get("label") or '', conf.get("background_color") or ''))
                        break
                self.index[page] += 1
                if conf is not None:
                    self.mydeck.update_key_image(key, self.mydeck.render_key_image(ImageOrFile(conf["image"]), conf.get("label") or '', conf.get("background_color") or ''))
                    self.page_cache[page] = conf

