import time
import os
import sys
from mydeck import MyDeck, BackgroundAppBase, DeckOutputWebServer

class AppWebServer(BackgroundAppBase):
    # if app reuquire thread, true
    use_thread = True
    # need to stop thread
    stop = False

    def __init__(self, mydeck: MyDeck, config: dict = {}):
        super().__init__(mydeck)
        self.port = config.get('port')
        if self.port is None:
            self.port = 3000

    def start(self):
        server = DeckOutputWebServer()
        server.run(self.port)
