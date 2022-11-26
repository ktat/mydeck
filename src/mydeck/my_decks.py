from contextlib import nullcontext
import json
import base64
import http.server
import logging
import random
import re
import traceback
import yaml
from PIL import Image
from StreamDeck.DeviceManager import DeviceManager
from io import BytesIO
from typing import Union
import queue
import glob

# 100 x 100 blank image
BLANK_IMAGE = "iVBORw0KGgoAAAANSUhEUgAAAGQAAABkCAQAAADa613fAAAAaUlEQVR42u3PQREAAAgDoC251Y" \
            + "3g34MGNJMXKiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIi" \
            + "IiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiJyWeRuMgFyCP0cAAAAAElFTkSuQmCC"

class MyDecksManager:
    """Class to mange multiple decks"""
    ConfigQueue: dict[str, queue.Queue] = {}
    # mydeck_configs = {}
    def __init__(self, config_file: str, no_real_device: bool = False):
        """Pass configration file for veirtual decks, and flag as 2nd argument if you have no real STREAM DECK device."""
        real_decks = []
        if no_real_device is False:
            real_decks = DeviceManager().enumerate()
        self.devices: list = []
        virtual_devices: list = []
        if config_file is not None:
            virtual_devices = self.devices_from_config(config_file)
        for l in [real_decks, virtual_devices]:
            if len(l) > 0:
                self.devices[len(self.devices):] = l

    def devices_from_config(self, config_file) -> list['VirtualDeck']:
        """Return virtual decks from virtual deck configuration file"""
        vconfig: 'VirtualDecksConfig' = VirtualDecksConfig(config_file)
        decks: list[VirtualDeck] = []
        vdeck_configs: list[VirtualDeckConfig] = vconfig.parse()

        for c in vdeck_configs:
            i = DeckInput.FromOption(c.input_option())
            o = DeckOutput.FromOption(c.output_option())
            deck: VirtualDeck = VirtualDeck(c.config(), i, o)
            decks.append(deck)
            MyDecksManager.ConfigQueue[deck.get_serial_number()] = queue.Queue()

        return decks

class ExceptionInvalidVirtualDeckConfig(Exception):
    """Exception class when invalid virtual deck configuration is given"""
    pass

class VirtualDeckConfig:
    """Virtual Deck Configuration class"""
    def __init__(self, id: str, opt: dict):
        self.opt = opt
        key_count = opt.get('key_count')
        if key_count is None or re.match('\D', str(key_count)) is not None:
            raise(ExceptionInvalidVirtualDeckConfig)
        self._key_count: int = key_count
        columns = opt.get('columns')
        if columns is None or re.match('\D', str(columns)) is not None:
            raise(ExceptionInvalidVirtualDeckConfig)
        self._columns: int = columns
        serial_number = opt.get('serial_number')
        if serial_number is None:
            raise(ExceptionInvalidVirtualDeckConfig)
        self._serial_number: str = str(serial_number)
        self._id: str = id

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
        key_count = opt.get('key_count')
        if type(key_count) is not int:
            raise(ExceptionVirtualDeckConstructor)
        self._key_count: int = key_count
        id = opt.get('id')
        if type(id) is not str:
            raise(ExceptionVirtualDeckConstructor)
        self._id: str = id
        columns = opt.get('columns')
        if type(columns) is not int:
            raise(ExceptionVirtualDeckConstructor)
        self._columns: int = columns
        serial_number = opt.get('serial_number')
        if type(serial_number) is not str:
            raise(ExceptionVirtualDeckConstructor)
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
        k = 0

        # for web server
        h = DeckOutputWebHandler
        id = self.id()
        if h.pathKeyMap.get(id) is None:
            h.pathKeyMap[id] = {}

        while k < self.key_count():
            h.pathKeyMap[id][k] = BLANK_IMAGE
            k += 1

    def deck_type(self):
        """Do nothing."""
        pass

    def set_brightness(self, d1):
        """Do nothing."""
        pass

    def set_key_callback(self, func):
        """Set key callback"""
        self.key_callback = func

    def set_key_image(self, key, image):
        """Set key image."""
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

    @staticmethod
    def FromOption(opt: dict) -> Union['DeckOutput', 'DeckOutputWeb']:
        """Returns DeckOutput instance from configuration"""
        if opt.get("use_web") is not None:
            return DeckOutputWeb(opt)
        return DeckOutput(opt)

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

            DeckOutputWebHandler.setKeyImage(id, key, b64_image.decode('utf-8'))

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
            logging.info("serving at port", port)
            httpd.serve_forever()
            logging.info("server is started")

class DeckOutputWebHandler(http.server.BaseHTTPRequestHandler):
    pathKeyMap: dict = {}
    idDeckMap: dict = {}

    @staticmethod
    def setKeyImage(id: str, key: str, image: str):
        self = DeckOutputWebHandler
        if self.pathKeyMap.get(id) == None:
            self.pathKeyMap[id] = {}
        if self.pathKeyMap[id].get(key) == None:
            self.pathKeyMap[id][key] = None
        self.pathKeyMap[id][key] = image

    def call_key_call_back(self, id, key):
        deck :VirtualDeck = self.idDeckMap[id]
        deck.key_callback(deck, key, True)
        deck.key_callback(deck, key, False)

    def do_GET(self):
        if self.path == '/':
            return self.res_vdeck_html()
        elif self.path == '/apps':
            return self.res_apps()
        elif self.path == '/device_info':
            return self.res_device_info()
        elif self.path == '/images':
            return self.res_images()
        elif (m := re.search("(/src/Assets/[^/]+\.(\w+))", self.path)) is not None and m.group(2) is not None:
            image_path = m.group(1)
            ext = m.group(2)
            with open('.' + image_path, mode="rb") as f:
                try:
                    return self.response_image(f, ext)
                except Exception as e:
                    pass
        elif (m := re.search('^/([^/]+)(?:/(\d+))?$', self.path)) is not None:
            id: str = m.group(1)
            # /id/key_num
            if m.group(2) is not None:
                key: int = int(m.group(2))
                return self.res_key_tapped(id, key)
            # /id
            elif (image_info := self.pathKeyMap.get(id)) is not None:
                return self.res_deck_images(image_info)

        self.response_404()

    def do_POST(self):
        # /key_setting/: update configuration YAML file
        if self.path == '/key_setting/':
            return self.res_key_setting()

        self.response_404()

    def text_headers(self, status: int = 200, type: str = "html; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", 'text/' + type)
        self.end_headers()

    def api_headers(self, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", 'application/json')
        self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin"))
        self.end_headers()

    def api_json_response(self, data: dict):
        self.api_headers()
        str = json.dumps(data)
        self.wfile.write(str.encode('utf-8'))

    def response_404(self):
        self.text_headers(404, 'plain')
        self.wfile.write(bytes("404 not found: {}".format(self.path), 'ascii'))

    def response_image(self, f, ext):
        self.send_response(200)
        self.send_header("Content-Type", 'image/' + ext)
        self.end_headers()
        self.wfile.write(f.read())

    def res_vdeck_html(self):
        self.text_headers()
        f = open('src/html/index.html', 'r+b')
        self.wfile.write(f.read())

    def res_device_info(self):
        json_data: dict = {}
        for key in self.idDeckMap.keys():
            deck: VirtualDeck = self.idDeckMap[key]
            json_data[deck.id()] = {
                "key_count": deck.key_count(),
                "serial_number": deck.get_serial_number(),
                "columns": deck.columns(),
            }
        self.api_json_response(json_data)

    def res_apps(self):
        pass
        #for key in self.idDeckMap.keys():
        #    deck: VirtualDeck = self.idDeckMap[key]

    def res_images(self):
        json_data: list = glob.glob("./src/Assets/*.png", recursive=False)
        self.api_json_response(json_data)

    def res_key_tapped(self, id: str, key: int):
        self.call_key_call_back(id, key)
        self.text_headers(200, 'plain')
        self.wfile.write(b"Tapped")

    def res_deck_images(self, image_info: dict):
        self.api_json_response(image_info)

    def res_key_setting(self):
        self.api_json_response({})

        content_length = int(self.headers['content-length'])
        json_str = self.rfile.read(content_length).decode('utf-8')

        data: dict = json.loads(json_str)
        deck_id :Union[str,None] = data.pop('id', None)
        if deck_id is not None:
            deck = self.idDeckMap[deck_id]
            sn: str = deck.get_serial_number()
            MyDecksManager.ConfigQueue[sn].put(data)