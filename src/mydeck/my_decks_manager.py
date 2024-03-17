from .web_server import DeckOutputWebHandler
import base64
import http.server
import logging
import random
import re
import traceback
import yaml
import queue
from PIL import Image
from StreamDeck.DeviceManager import DeviceManager
from StreamDeck.Devices.StreamDeck import StreamDeck
from io import BytesIO
from typing import Union
from StreamDeck.ImageHelpers import PILHelper


class MyDecksManager:
    """Class to mange multiple decks"""
    ConfigQueue: dict[str, queue.Queue] = {}
    real_decks: list[StreamDeck] = []
    # mydeck_configs = {}

    def __init__(self, config_file: str, no_real_device: bool = False):
        """Pass configration file for veirtual decks, and flag as 2nd argument if you have no real STREAM DECK device."""
        real_decks: list[StreamDeck] = []
        self.devices: list = []
        if config_file is not None:
            self.devices = self.devices_from_config(config_file)
        if no_real_device is False:
            real_decks = DeviceManager().enumerate()
            if len(real_decks) > 0:
                self.devices[len(self.devices):] = self.devices_from_real_decks(
                    real_decks)

    def devices_from_config(self, config_file) -> list['VirtualDeck']:
        """Return virtual decks from virtual deck configuration file"""
        vconfig: 'VirtualDecksConfig' = VirtualDecksConfig(config_file)
        decks: list[VirtualDeck] = []
        vdeck_configs: list[VirtualDeckConfig] = vconfig.parse()

        for c in vdeck_configs:
            input = DeckInput.FromOption(c.input_option())
            output = DeckOutputWeb(c.output_option())
            deck: VirtualDeck = VirtualDeck(c.config(), input, output)
            deck.open()
            decks.append(deck)
            MyDecksManager.ConfigQueue[deck.get_serial_number(
            )] = queue.Queue()

        return decks

    def devices_from_real_decks(self, real_decks) -> list['VirtualDeck']:
        """Return virtual decks from real streamdecks"""
        decks: list[VirtualDeck] = []

        i: int = 0
        for real_deck in real_decks:
            real_deck.open()
            config = VirtualDeckConfig(
                "r" + str(i), {"real_deck": real_deck})

            input = DeckInput.FromOption({})
            output = DeckOutputWeb({})
            deck: VirtualDeck = VirtualDeck(config.config(), input, output)
            deck.real_deck = real_deck
            decks.append(deck)
            MyDecksManager.ConfigQueue[real_deck.get_serial_number(
            )] = queue.Queue()
            i += 1

        return decks


class ExceptionInvalidVirtualDeckConfig(Exception):
    """Exception class when invalid virtual deck configuration is given"""
    pass


class VirtualDeckConfig:
    """Virtual Deck Configuration class"""

    def __init__(self, id: str, opt: dict):
        self.opt = opt
        self._id: str
        self._key_count: int
        self._columns: int
        self._serial_number: str

        real_deck: StreamDeck = opt.get("real_deck")
        if real_deck is not None:
            self._id = id
            self._key_count = real_deck.KEY_COUNT
            self._columns = real_deck.KEY_COLS
            logging.info(real_deck.get_serial_number())
            self._serial_number = real_deck.get_serial_number()
        else:
            key_count = opt.get('key_count')
            if key_count is None or re.match('\D', str(key_count)) is not None:
                raise (ExceptionInvalidVirtualDeckConfig)
            self._key_count = key_count
            columns = opt.get('columns')
            if columns is None or re.match('\D', str(columns)) is not None:
                raise (ExceptionInvalidVirtualDeckConfig)
            self._columns = columns
            serial_number = opt.get('serial_number')
            if serial_number is None:
                raise (ExceptionInvalidVirtualDeckConfig)
            self._serial_number = str(serial_number)
            self._id = id

    def id(self) -> str:
        return self._id

    def key_count(self) -> int:
        return self._key_count

    def columns(self) -> int:
        return self._columns

    def serial_number(self) -> str:
        sn = self._serial_number
        if sn is None:
            logging.critical("serial_nubmer is required")
            exit
        return sn

    def get_random_serial_number(self) -> str:
        return str(random.random())

    def input_option(self) -> dict:
        i = self.opt.get('input')
        if type(i) is not dict:
            return {}
        return i

    def output_option(self) -> dict:
        o = self.opt.get('output')
        if type(o) is not dict:
            return {}
        return o

    def config(self) -> dict:
        return {
            'id': self.id(),
            'key_count': self.key_count(),
            'columns': self.columns(),
            'serial_number': self.serial_number(),
        }


class VirtualDecksConfig:
    """Multiple Virutal Decks Configuration Class"""

    def __init__(self, file: str):
        """Pass file name of yaml file. liek the foolowing:

        example:
        ---
        1:
          key_count: 4
          columns: 2
          serial_number: 'dummy1'
          output:
            use_web: 1
        2:
          key_count: 6
          columns: 3
          serial_number: 'dummy2'
          output:
            use_web: 1
        """
        self.file = file
        self.config: dict = {}

    def parse(self) -> list[VirtualDeckConfig]:
        """Parse virutal deck configuration and return list of VirtualDeckConfig instances."""
        configs: list[VirtualDeckConfig] = []
        with open(self.file) as f:
            try:
                config: dict = yaml.safe_load(f)
                for id in config.keys():
                    opt: dict = config[id]
                    configs.append(VirtualDeckConfig(str(id), opt))
            except Exception as e:
                logging.critical("Error in load: %s", e)
                logging.debug(traceback.format_exc())

        return configs


class ExceptionVirtualDeckConstructor(Exception):
    pass


class VirtualDeck:
    """Virtual Deck Class. It is emmulated Class of StreamDeck.DeviceManager"""

    def __init__(self, opt: dict, input: 'DeckInput', output: 'DeckOutput'):
        """Pass Virutal Deck option, DeckInput instance and DeckOutput instance."""
        self.real_deck: StreamDeck = None
        key_count = opt.get('key_count')
        if type(key_count) is not int:
            raise (ExceptionVirtualDeckConstructor)
        self._key_count: int = key_count
        id = opt.get('id')
        if type(id) is not str:
            raise (ExceptionVirtualDeckConstructor)
        self._id: str = id
        columns = opt.get('columns')
        if type(columns) is not int:
            raise (ExceptionVirtualDeckConstructor)
        self._columns: int = columns
        serial_number = opt.get('serial_number')
        if type(serial_number) is not str:
            raise (ExceptionVirtualDeckConstructor)
        self.serial_number: str = serial_number
        self.firmware_version: str = 'dummy firmware'
        self.input: 'DeckInput' = input
        self.output: 'DeckOutput' = output
        self.current_key_status: dict = {}
        self.output.set_deck(self)
        self.input.set_deck(self)
        self.input.init()
        self.output.init()
        self.reset()

    def has_real_deck(self) -> bool:
        return self.real_deck is not None

    def is_virtual(self) -> bool:
        """Always returns true."""
        return True

    def is_visual(self) -> bool:
        """Always returns true."""
        return True

    def get_serial_number(self) -> str:
        """Returns the serial number of device(dummy string or from configuration)."""
        return self.serial_number

    def open(self):
        """Do nothing."""
        logging.info("OPEN VirtualDeck: " + self.serial_number)
        pass

    def id(self) -> str:
        """Returns id."""
        return self._id

    def columns(self) -> int:
        """Returns column of the device."""
        return self._columns

    def get_firmware_version(self) -> str:
        """Returns the firmware version(dummy string)."""
        return self.firmware_version

    def key_count(self) -> int:
        """Returns number of the key of the virtual devces."""
        return self._key_count

    def reset(self):
        """Reset key images."""
        self.current_key_status = {}

        # for web server
        DeckOutputWebHandler.reset_keys(self.id(), self.key_count())

        if self.has_real_deck():
            self.real_deck.reset()

    def deck_type(self):
        """Do nothing."""
        pass

    def set_brightness(self, d1):
        """Do nothing."""
        pass

    def set_key_callback(self, func):
        """Set key callback"""
        self.key_callback = func
        if self.has_real_deck():
            self.real_deck.set_key_callback(func)

    def set_key_image(self, key, image):
        """Set key image."""
        if self.has_real_deck():
            image2 = PILHelper.to_native_format(self.real_deck, image)
            self.real_deck.set_key_image(key, image2)
        if self.current_key_status.get(key) is None:
            self.current_key_status[key] = {}

        self.current_key_status[key]["image"] = image
        self.output.output(self.current_key_status)

    def key_image_format(self) -> dict:
        """Format of key image. Currently it returns fixed dict.

        {
            'size': (100, 100),
            'format': 'png',
            'flip': (None, None),
            'rotation': None,
        }
        """
        return {
            'size': (100, 100),
            'format': 'png',
            'flip': (None, None),
            'rotation': None,
        }

    def set_brigthness(self):
        """Do nothing."""
        pass

    def close(self):
        """Do nothing."""
        pass


class DeckOutput:
    """Deck output base Class. This should not be used directly.
    use FromOption method and get the intance of the subclass.
    """

    def __init__(self, opt: dict):
        self.key_config: dict = {}
        self.config: dict = opt
        self.deck: VirtualDeck

    def init(self):
        """Implement it in subclass."""
        pass

    def set_deck(self, deck: 'VirtualDeck'):
        """Set virtual deck instance"""
        self.deck = deck
        self.config["id"] = self.deck.id()

    def output(self, key_status: dict):
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
    idDeckMap: dict[int, 'VirtualDeck']
    """Subclass of DeckOutput for Web."""

    def __init__(self, opt: dict):
        super().__init__(opt)

    def set_deck(self, deck: 'VirtualDeck'):
        """Set deck ID and deck instance to Globl Variable DeckOutputWebHandleridDeckMap dict."""
        super().set_deck(deck)
        DeckOutputWebHandler.idDeckMap[self.deck.id()] = self.deck

    def output(self, key_status: dict):
        """pass key and its image to DeckOutputWebHandler.setKeyImage"""
        id = self.deck.id()
        if id == None:
            return

        _key_status = {}

        for key, v in list(key_status.items()):
            _key_status[key] = v

        for key, v in _key_status.items():
            image_buffer = self.format(key_status[key]["image"])

            b64_image = base64.b64encode(image_buffer.getvalue())

            DeckOutputWebHandler.setKeyImage(
                id, key, b64_image.decode('utf-8'))

    def format(self, image):
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

    def __init__(self):
        pass

    def run(self, port: int):
        with http.server.ThreadingHTTPServer(('', port), DeckOutputWebHandler) as httpd:
            logging.info("serving at port %d", port)
            httpd.serve_forever()
            logging.info("server is started")
