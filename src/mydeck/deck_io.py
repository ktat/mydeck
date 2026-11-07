import base64
import http.server
import logging
from io import BytesIO
from typing import TYPE_CHECKING
from PIL import Image
from .web_server import DeckOutputWebHandler

if TYPE_CHECKING:
    from .my_decks_manager import VirtualDeck


class DeckOutput:
    """Deck output base Class. This should not be used directly.
    """

    def __init__(self, opt: dict):
        self.key_config: dict = {}
        self.config: dict = opt
        self.deck: 'VirtualDeck'

    def init(self):
        """Implement it in subclass."""
        pass

    def set_deck(self, deck: 'VirtualDeck'):
        """Set virtual deck instance"""
        self.deck = deck
        self.config["id"] = self.deck.id()

    def output(self, key_status: dict, touchscreen_image):
        pass


class DeckInput:
    """Deck input base Class. This should not be used directly.
    use FromOption method and get the intance of the subclass.

    But, currently it does nothing.
    """

    def __init__(self, opt: dict):
        self.key_config: dict = {}
        self.config = opt
        self. deck = None

    def init(self):
        pass

    def set_deck(self, deck):
        self.deck = deck

    def input(self, page: str):
        pass

    @staticmethod
    def FromOption(opt: dict):
        return DeckInput({})


class DeckOutputWeb(DeckOutput):
    id_deck_map: dict[int, 'VirtualDeck']
    """Subclass of DeckOutput for Web."""

    def __init__(self, opt: dict):
        super().__init__(opt)

    def set_deck(self, deck: 'VirtualDeck'):
        """Set deck ID and deck instance to Globl Variable DeckOutputWebHandlerid_deck_map dict."""
        super().set_deck(deck)
        DeckOutputWebHandler.id_deck_map[self.deck.id()] = self.deck

    def output(self, key_status: dict, touchscreen_image):
        """pass key and its image to DeckOutputWebHandler.set_key_image"""
        id = self.deck.id()
        if id == None:
            return

        _key_status = {}

        for key, v in list(key_status.items()):
            _key_status[key] = v

        for key, v in _key_status.items():
            if key_status[key]["image"] is None:
                key_status[key]["image"] = Image.new(
                    'RGBA', (100, 100), (0, 0, 0, 127))

            image_buffer = self.key_image_format(key_status[key]["image"])
            b64_image = base64.b64encode(image_buffer.getvalue())

            DeckOutputWebHandler.set_key_image(
                id, key, b64_image.decode('utf-8'))

        if touchscreen_image:
            image_buffer = self.touchscreen_image_format(touchscreen_image)
            b64_image = base64.b64encode(image_buffer.getvalue())

            DeckOutputWebHandler.set_touchscreen_image(
                id, b64_image.decode('utf-8'))

    def key_image_format(self, image):
        """return image as BytesIO binary stream"""
        image_format = self.deck.key_image_format()

        if image_format['rotation']:
            image = image.rotate(image_format['rotation'])

        if image_format['flip'][0]:
            image = image.transpose(Image.FLIP_LEFT_RIGHT)

        if image_format['flip'][1]:
            image = image.transpose(Image.FLIP_TOP_BOTTOM)

        if image.size != image_format['size']:
            image.thumbnail(image_format['size'])

        buffered = BytesIO()
        image.save(buffered, image_format["format"], quality=100)

        return buffered

    def touchscreen_image_format(self, image):
        """return image as BytesIO binary stream"""
        image_format = self.deck.touchscreen_image_format()

        if image_format['rotation']:
            image = image.rotate(image_format['rotation'])

        if image_format['flip'][0]:
            image = image.transpose(Image.FLIP_LEFT_RIGHT)

        if image_format['flip'][1]:
            image = image.transpose(Image.FLIP_TOP_BOTTOM)

        if image.size != image_format['size']:
            image.thumbnail(image_format['size'])

        buffered = BytesIO()
        image.save(buffered, image_format["format"], quality=100)

        return buffered


class DeckInputWeb(DeckInput):
    """Currently no use"""

    def __init__(self, opt: dict):
        super().__init__(opt)

    def init(self):
        pass

    def input(self, page: str):
        pass


class DeckOutputWebServer:
    """virtual deck server"""
    httpd = None

    def __init__(self):
        pass

    @staticmethod
    def shutdown():
        if DeckOutputWebServer.httpd is not None:
            DeckOutputWebServer.httpd.shutdown()

    def run(self, port: int):
        with http.server.ThreadingHTTPServer(('', port), DeckOutputWebHandler) as httpd:
            DeckOutputWebServer.httpd = httpd
            logging.info("serving at port %d", port)
            logging.info("server is started")
            httpd.serve_forever()
            logging.info("server is exited")
