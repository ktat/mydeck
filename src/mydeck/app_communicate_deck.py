from mydeck import AppBase, ImageOrFile, MyDeck
from typing import Optional, Dict


class AppCommunicateDeck(AppBase):
    """Sample application to communicate other deck"""
    _key_conf = {
        "app_command": "MyDeckCommunicateDeck",
        "image": "./src/Assets/world.png",
        "label": "Communicate",
    }
    key_command = {
        "MyDeckCommunicateDeck": lambda app: app.communicate(),
    }

    def __init__(self, mydeck: MyDeck, option: dict = {}):
        super().__init__(mydeck, option)
        self.index: Dict[str, Dict[int, int]] = {}
        self.page_cache: Dict[str, dict] = {}
        self.to_deck: MyDeck
        self.to_deck_name: Optional[str] = option.get('to_deck')
        self.to_deck_config: Optional[dict] = option.get('to_deck_config')

    def key_setup(self):
        page: str = self.mydeck.current_page()
        key: int = self.page_key.get(page)
        if key is not None:
            self.mydeck.set_key_conf(page, key, self._key_conf)
            conf = self.page_cache.get(page)
            if conf is not None:
                self.mydeck.update_key_image(key, self.mydeck.render_key_image(ImageOrFile(
                    conf["image"]), conf.get("label") or '', conf.get("background_color") or ''))

    def communicate(self):
        to_deck_name: str = self.to_deck_name
        page: str = self.mydeck.current_page()
        key: int = self.page_key.get(page)
        if key is not None and to_deck_name is not None:
            to_deck = self.mydeck.mydecks.mydeck(to_deck_name)
            if to_deck is None:
                return
            self.to_deck = to_deck

            conf: Optional[dict] = None
            for page in self.to_deck_config.keys():
                if self.to_deck.current_page() == page:
                    if self.index.get(page) is None:
                        self.index[page] = {}
                    for to_key in self.to_deck_config[page].keys():
                        if self.index[page].get(to_key) is None:
                            self.index[page][to_key] = 0

                        configs = self.to_deck_config[page][to_key]
                        if len(configs) <= self.index[page][to_key]:
                            self.index[page][to_key] = 0
                        conf = configs[self.index[page][to_key]]
                        self.to_deck.update_key_image(to_key, self.to_deck.render_key_image(ImageOrFile(
                            conf["image"]), conf.get("label") or '', conf.get("background_color") or ''))
                        self.index[page][to_key] += 1

                    if conf is not None:
                        self.mydeck.update_key_image(key, self.mydeck.render_key_image(ImageOrFile(
                            conf["image"]), conf.get("label") or '', conf.get("background_color") or ''))
                        self.page_cache[page] = conf
                    break
