import time

from mystreamdeck import MyStreamDeck, HookAppBase
from typing import Optional, Dict

class AppSyncDeckPage(HookAppBase):
    on = 'page_change_any'
    """Open the same name of current page on other decks."""
    def __init__(self, mydeck: MyStreamDeck, option: dict = {}):
        super().__init__(mydeck, option)

    def execute_on_hook(self):
        page = self.mydeck.current_page()
        for deck in self.mydeck.mydecks.list_mydecks():
            if deck.myname != self.mydeck.myname:
                deck.set_current_page(page)
