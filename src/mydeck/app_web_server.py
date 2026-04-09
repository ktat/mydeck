from mydeck import MyDeck, BackgroundAppBase, DeckOutputWebServer
import logging


class AppWebServer(BackgroundAppBase):
    # if app requires thread, set it to True
    use_thread = True
    # class-level flag used externally (e.g. my_decks.py) to check if server is running
    IS_ALREADY_WORKING: bool = False

    def __init__(self, mydeck: MyDeck, config: dict = {}):
        super().__init__(mydeck)
        self.port = config.get('port', 3000)

    def start(self):
        if AppWebServer.IS_ALREADY_WORKING:
            logging.debug("Duplicate call of AppWebServer.start() is ignored.")
            return

        AppWebServer.IS_ALREADY_WORKING = True
        try:
            server = DeckOutputWebServer()
            server.run(self.port)
            logging.info("exit in start")
            self.stop(True)
        finally:
            AppWebServer.IS_ALREADY_WORKING = False
