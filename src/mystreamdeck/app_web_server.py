import time
import os
import sys
from mystreamdeck import MyStreamDeck, BackgroundAppBase, DeckOutputWebServer

class AppWebServer(BackgroundAppBase):
    # if app reuquire thread, true
    use_thread = True
    # need to stop thread
    stop = False

    def __init__(self, mydeck: MyStreamDeck, config: dict = {}):
        super().__init__(mydeck)
        self.port = config.get('port')
        if self.port is None:
            self.port = 3000

    def start(self):
        server = DeckOutputWebServer()
        server.run(self.port)
