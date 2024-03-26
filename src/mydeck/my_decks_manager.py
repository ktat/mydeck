from .web_server import DeckOutputWebHandler
import base64
import http.server
import logging
import random
import re
import time
import traceback
import yaml
import queue
import threading
from .lock import Lock
from PIL import Image
from StreamDeck.DeviceManager import DeviceManager
from StreamDeck.Devices.StreamDeck import StreamDeck
from StreamDeck.Devices.StreamDeckPlus import StreamDeckPlus
from io import BytesIO
from typing import Optional, Dict, Any, Callable
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
        self._dials: int = 0
        self._has_touch_interface: bool = False
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
            has_touchscreen: Optional[bool] = opt.get('has_touchscreen')
            if has_touchscreen is not None and has_touchscreen:
                self._has_touch_interface = has_touchscreen
            num_of_dials: Optional[int] = opt.get('dial_count')
            if num_of_dials is not None and num_of_dials is not None and num_of_dials > 0:
                self._dials = num_of_dials

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

    def dials(self) -> int:
        return self._dials

    def has_touchscreen(self) -> bool:
        return self._has_touch_interface

    def config(self) -> dict:
        return {
            'id': self.id(),
            'key_count': self.key_count(),
            'columns': self.columns(),
            'serial_number': self.serial_number(),
            "dial_count": self.dials(),
            "has_touchscreen": self.has_touchscreen(),
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
          has_touchscreen: true
          dial_count: 2
        2:
          key_count: 6
          columns: 3
          serial_number: 'dummy2'
          has_touchscreen: true
          dial_count: 4
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
        self.is_touch_interface: bool = False
        self._exit: bool = False
        self.touchscreen_image = None
        self._dial_count: int = 0
        self._dial_states: Dict[int, int] = {}
        self.dial_callback: Callable = lambda deck, event, dial, value: None
        self.touchscreen_callback: Callable = lambda deck, event, args: None
        self.key_callback: Callable = lambda deck, key, flag: None

        key_count = opt.get('key_count')
        if type(key_count) is not int:
            raise (ExceptionVirtualDeckConstructor)
        self._key_count: int = key_count
        id: Optional[str] = opt.get('id')
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
        dial_count: Optional[int] = opt.get('dial_count')
        if dial_count is not None and dial_count > 0:
            self._dial_count = dial_count
            for i in range(self._dial_count):
                self._dial_states[i] = 0

        has_touch: Optional[int] = opt.get('has_touchscreen')
        if has_touch is not None and has_touch is True:
            self.is_touch_interface = True
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
        self.update_lock = threading.RLock()

    def __enter__(self):
        if self.has_real_deck():
            self.real_deck.__enter__()
        else:
            self.update_lock.acquire()

    def __exit__(self, type: Any, value: Any, traceback: Any) -> None:
        if self.has_real_deck():
            self.real_deck.__exit__(type, value, traceback)
        else:
            self.update_lock.release()

    def has_real_deck(self) -> bool:
        return self.real_deck is not None

    def is_virtual(self) -> bool:
        """Always returns true."""
        return True

    def is_visual(self) -> bool:
        """Always returns true if not real deck."""
        if self.has_real_deck():
            is_visual: Optional[bool] = self.real_deck.is_visual()
            return is_visual is not None and is_visual

        return True

    def get_serial_number(self) -> str:
        """Returns the serial number of device(real deck value or dummy string or from configuration)."""

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

    def reset_keys(self):
        """Reset key images."""
        self.current_key_status = {}

        # for web server
        DeckOutputWebHandler.reset_keys(self.id(), self.key_count())

        if self.has_real_deck():
            for i in range(self.key_count()):
                Lock.do_with_lock(self.get_serial_number(),
                                  lambda: self.real_deck.set_key_image(i, None))

    def reset(self):
        """Reset key images."""
        self.current_key_status = {}

        # for web server
        DeckOutputWebHandler.reset_keys(self.id(), self.key_count())

        if self.has_real_deck():
            self.real_deck.reset()

    def deck_type(self) -> str:
        """Do nothing."""
        if self.has_real_deck():
            deck_type: Optional[str] = self.real_deck.deck_type()
            if deck_type is not None:
                return deck_type

        return "VirtualDeck"

    def set_brightness(self, d1):
        """Do nothing."""
        if self.has_real_deck():
            return self.real_deck.set_brightness(d1)

    def set_key_callback(self, func):
        """Set key callback"""
        self.key_callback = func
        if self.has_real_deck():
            self.real_deck.set_key_callback(func)

    def set_key_image(self, key, image):
        """Set key image."""
        if self.has_real_deck():
            self.real_deck.set_key_image(
                key, PILHelper.to_native_format(self.real_deck, image))
        if self.current_key_status.get(key) is None:
            self.current_key_status[key] = {}

        self.current_key_status[key]["image"] = image
        self.output.output(self.current_key_status, self.touchscreen_image)

    def set_touchscreen_image(self, image, x_pos=0, y_pos=0, width=0, height=0):
        if self.has_real_deck():
            self.real_deck.set_touchscreen_image(
                image, x_pos, y_pos, width, height)

        self.touchscreen_image = image
        self.output.output(self.current_key_status, self.touchscreen_image)

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

    def close(self):
        """Close deck."""
        self._exit = True

        sn = self.get_serial_number()
        MyDecksManager.ConfigQueue[sn].put({"exit": True})

        if self.has_real_deck():
            self.real_deck.close()

        # for web server
        DeckOutputWebHandler.remove_device(self.id())

    def is_touch(self) -> bool:
        return self.is_touch_interface

    def is_dial(self) -> bool:
        return self.dial_count() > 0

    def touchscreen_image_format(self) -> dict:
        """Format of touchscreen image. Currently it returns fixed dict.

        {
            'size': (800, 100),
            'format': 'png',
            'flip': (None, None),
            'rotation': None,
        }
        """
        plus = StreamDeckPlus
        return {
            'size': (plus.TOUCHSCREEN_PIXEL_WIDTH, plus.TOUCHSCREEN_PIXEL_HEIGHT),
            'format': plus.TOUCHSCREEN_IMAGE_FORMAT,
            'flip': plus.TOUCHSCREEN_FLIP,
            'rotation': plus.TOUCHSCREEN_ROTATION,
        }

    def set_poll_frequency(self, freq: int) -> None:
        if self.has_real_deck():
            self.real_deck.set_poll_frequency(freq)

    def dial_count(self) -> int:
        return self._dial_count

    def set_dial_callback(self, func) -> None:
        self.dial_callback = func
        if self.has_real_deck():
            self.real_deck.set_dial_callback(func)

    def set_touchscreen_callback(self, func) -> None:
        self.touchscreen_callback = func
        if self.has_real_deck():
            self.real_deck.set_touchscreen_callback(func)

    def set_touchscreen_callback_async(self, async_callback, loop=None) -> None:
        if self.has_real_deck():
            self.real_deck.set_touchscreen_callback_async(async_callback)

        import asyncio

        loop = loop or asyncio.get_event_loop()

        def callback(*args):
            asyncio.run_coroutine_threadsafe(async_callback(*args), loop)

        self.set_touchscreen_callback(callback)

    def set_dial_callback_async(self, async_callback, loop=None) -> None:
        if self.has_real_deck():
            self.real_deck.set_dial_callback_async(async_callback)

        import asyncio

        loop = loop or asyncio.get_event_loop()

        def callback(*args):
            asyncio.run_coroutine_threadsafe(async_callback(*args), loop)

        self.set_dial_callback(callback)

    def dial_states(self) -> Dict[Any, Any]:
        return self._dial_states

    def is_closed(self) -> bool:
        return self._exit


class DeckOutput:
    """Deck output base Class. This should not be used directly.
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
    idDeckMap: dict[int, 'VirtualDeck']
    """Subclass of DeckOutput for Web."""

    def __init__(self, opt: dict):
        super().__init__(opt)

    def set_deck(self, deck: 'VirtualDeck'):
        """Set deck ID and deck instance to Globl Variable DeckOutputWebHandleridDeckMap dict."""
        super().set_deck(deck)
        DeckOutputWebHandler.idDeckMap[self.deck.id()] = self.deck

    def output(self, key_status: dict, touchscreen_image):
        """pass key and its image to DeckOutputWebHandler.setKeyImage"""
        id = self.deck.id()
        if id == None:
            return

        _key_status = {}

        for key, v in list(key_status.items()):
            _key_status[key] = v

        for key, v in _key_status.items():
            image_buffer = self.key_image_format(key_status[key]["image"])
            b64_image = base64.b64encode(image_buffer.getvalue())

            DeckOutputWebHandler.setKeyImage(
                id, key, b64_image.decode('utf-8'))

        if touchscreen_image:
            image_buffer = self.touchscreen_image_format(touchscreen_image)
            b64_image = base64.b64encode(image_buffer.getvalue())

            DeckOutputWebHandler.setTouchscreenImage(
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

    def __init__(self):
        pass

    def run(self, port: int):
        with http.server.ThreadingHTTPServer(('', port), DeckOutputWebHandler) as httpd:
            logging.info("serving at port %d", port)
            logging.info("server is started")
            httpd.serve_forever()
            logging.info("server is exited")
