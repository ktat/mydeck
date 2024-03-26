from mydeck import MyDeck, BackgroundAppBase, DeckOutputWebServer
import logging
import sys


class AppWebServer(BackgroundAppBase):
    # if app requires thread, set it to True
    use_thread = True
    # class variable
    IS_ALREADY_WORKING: bool = False

    def __init__(self, mydeck: MyDeck, config: dict = {}):
        super().__init__(mydeck)
        self.port = config.get('port')
        if self.port is None:
            self.port = 3000

    def start(self):
        if AppWebServer.IS_ALREADY_WORKING:
            logging.debug("Duplicate call of AppWebServer.start() is ignored.")
        else:
            AppWebServer.IS_ALREADY_WORKING = True

            server = DeckOutputWebServer()
            server.run(self.port)
            logging.info("exit in start")
            self.stop(True)
            sys.exit()
