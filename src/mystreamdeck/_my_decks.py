from contextlib import nullcontext
import json
import base64
import http.server
import logging
from random import random
import re
import traceback
import yaml
from PIL import Image
from StreamDeck.DeviceManager import DeviceManager
from io import BytesIO

# 100 x 100 blank image
BLANK_IMAGE =  "iVBORw0KGgoAAAANSUhEUgAAAGQAAABkCAQAAADa613fAAAAaUlEQVR42u3PQREAAAgDoC251Y3g34MGNJMXKiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiJyWeRuMgFyCP0cAAAAAElFTkSuQmCC"

class MyDecks:
    def __init__(self, config_file, no_real_device: bool = False):
        real_decks = []
        if no_real_device is False:
            real_decks = DeviceManager().enumerate()
        self.devices = []
        if config_file is not None:
            virutal_devices = self.devices_from_config(config_file)
        for l in [real_decks, virutal_devices]:
            if len(l) > 0:
                self.devices[len(self.devices):] = l

    def devices_from_config(self, config_file) -> list['VirtualDeck']:
        vconfig: 'VirtualDecksConfig' = VirtualDecksConfig(config_file)
        decks: list[VirtualDeck] = []
        vdeck_configs = vconfig.parse()

        for c in vdeck_configs:
            i = DeckInput.FromOption(c.input_option())
            o = DeckOutput.FromOption(c.output_option())
            deck = VirtualDeck(c.config(), i, o)
            decks.append(deck)

        return decks

class VirtualDeckConfig:
    def __init__(self, id: str, opt: dict):
        self.opt = opt
        self._id = id

    def id(self) -> str:
        return self._id

    def key_count(self) -> int:
        return self.opt.get('key_count')

    def columns(self) -> int:
        return self.opt.get('columns')

    def serial_number(self) -> str:
        sn = self.opt.get('serial_number')
        if sn is None:
            logging.critical("serial_nubmer is required")
            exit
        return sn

    def get_random_serial_number(self) -> str:
        return str(random())

    def input_option(self) -> dict:
        i = self.opt.get('input')
        if i is None:
            return {}
        return i

    def output_option(self) -> dict:
        o = self.opt.get('output')
        if o is None:
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
    def __init__(self, file: str):
        self.file = file
        self.config = {}

    def parse(self) -> list[VirtualDeckConfig]:
        configs: list[VirtualDeckConfig] = []
        with open(self.file) as f:
            try:
                config: dict = yaml.safe_load(f)
                for id in config.keys():
                    opt: dict = config[id]
                    configs.append(VirtualDeckConfig(str(id), opt))
            except Exception as e:
                print("Error in load", e)
                print(traceback.format_exc())

        return configs

class VirtualDeck:
    def __init__(self, opt: dict, input: 'DeckInput', output: 'DeckOutput'):
        self._mydeck = opt.get('mydeck')
        self._key_count: int = opt.get('key_count')
        self._id: str = opt.get('id')
        self._columns: int = opt.get('columns')
        self.serial_number: str = opt.get('serial_number')
        self.firmware_version: str = 'dummy firmware'
        self.input = input
        self.output = output
        self.current_key_status = {}
        self.output.set_deck(self)
        self.input.set_deck(self)
        self.input.init()
        self.output.init()
        self.reset()

    def is_virtual(self):
        return True

    def is_visual(self):
        return True

    def get_serial_number(self):
        return self.serial_number

    def open(self):
        print("OPEN VirtualDeck: " + self.serial_number)
        pass

    def id(self) -> str:
        return self._id

    def columns(self) -> int:
        return self._columns

    def get_firmware_version(self) -> str:
        return self.firmware_version

    def get_serial_number(self) -> str:
        return self.serial_number

    def key_count(self) -> int:
        return self._key_count

    def reset(self):
        self.current_key_status = {}
        k = 0

        # for web server
        h = DeckOutputWebGetHandler
        id = self.id()
        if h.pathKeyMap.get(id) is None:
            h.pathKeyMap[id] = {}

        while k < self.key_count():
            h.pathKeyMap[id][k] = BLANK_IMAGE
            k += 1

    def deck_type(self):
        pass

    def set_brightness(self, d1):
        pass

    def set_key_callback(self, func):
        self.key_callback = func

    def set_key_image(self, key, image):
        if self.current_key_status.get(key) is None:
            self.current_key_status[key] = {}
        self.current_key_status[key]["image"] = image
        self.output.output(self.current_key_status)

    def key_image_format(self):
        return {
            'size': (100, 100),
            'format': 'png',
            'flip': (None, None),
            'rotation': None,
        }

    def set_brigthness(self):
        pass

    def close(self):
        pass

class DeckOutput:
    def __init__(self, opt: dict):
        self.key_config = {}
        self.config = opt
        self.deck = None

    def init(self):
        pass

    def set_deck(self, deck):
        self.deck = deck
        self.config["id"] = self.deck.id()

    def output(self, key_status: dict):
        pass

    def FromOption(opt: dict):
        if opt.get("use_web") is not None:
            return DeckOutputWeb(opt)
        return DeckOutput(opt)

class DeckInput:
    def __init__(self, opt: dict):
        self.key_config = {}
        self.config = opt
        self. deck = None

    def init(self):
        pass

    def set_deck(self, deck):
        self.deck = deck

    def input(self, page: str):
        pass

    def FromOption(opt: dict):
        return DeckInput({})

class DeckOutputWeb(DeckOutput):
    def __init__(self, opt: dict):
        super().__init__(opt)

    def set_deck(self, deck):
        super().set_deck(deck)
        DeckOutputWebGetHandler.idDeckMap[self.deck.id()] = self.deck

    def output(self, key_status: dict):
        id = self.deck.id()
        if id == None:
            return

        _key_status = {}

        for key, v in list(key_status.items()):
            _key_status[key] = v

        for key, v in _key_status.items():
            image_buffer = self.format(key_status[key]["image"])

            b64_image = base64.b64encode(image_buffer.getvalue())

            DeckOutputWebGetHandler.setKeyImage(id, key, b64_image.decode('utf-8'))

    def format(self, image):
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
    def __init__(self, opt: dict):
        super().__init__(opt)

    def init(self):
        pass

    def input(self, input: dict):
        pass

class DeckOutputWebServer:
    def __init__(self):
        pass

    def run(self, port: int):
        with http.server.ThreadingHTTPServer(('', port), DeckOutputWebGetHandler) as httpd:
            print("serving at port", port)
            httpd.serve_forever()
            print("server is started")

class DeckOutputWebGetHandler(http.server.BaseHTTPRequestHandler):
    pathKeyMap = {}
    idDeckMap = {}

    def do_GET(self):
        is404 = True
        if self.path == '/':
            self.send_response(200)
            self.send_header("Content-Type", 'text/html')
            self.end_headers()
            f = open('src/html/index.html', 'r+b')
            self.wfile.write(f.read())
            return
        elif self.path == '/device_info':
            self.send_response(200)
            self.send_header("Content-Type", 'application/json')
            self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin"))
            self.end_headers()
            json_data = {}
            for key in self.idDeckMap.keys():
                deck: VirtualDeck = self.idDeckMap[key]
                json_data[deck.id()] = {
                    "key_count": deck.key_count(),
                    "serial_number": deck.get_serial_number(),
                    "columns": deck.columns(),
                }
            str = json.dumps(json_data)
            self.wfile.write(str.encode('utf-8'))
            return
        else:
            m = re.search('^/([^/]+)(?:/(\d+))?$', self.path)
            id: str = None
            key: int = None
            image_info: dict = None

            if m is not None:
                id = m.group(1)
                key = m.group(2)
                image_info = self.pathKeyMap.get(id)
                if key is not None:
                    key = int(key)

            if key is not None:
                self.call_key_call_back(id, key)
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"Tapped")
                return
            elif image_info is not None:
                self.send_response(200)
                self.send_header("Content-Type", 'application/json')
                self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin"))
                self.end_headers()
                str = json.dumps(image_info)
                self.wfile.write(str.encode('utf-8'))
                return

        self.send_response(404)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"404 not found")

    def setKeyImage(id: str, key: str, image: str):
        self = DeckOutputWebGetHandler
        if self.pathKeyMap.get(id) == None:
            self.pathKeyMap[id] = {}
        if self.pathKeyMap[id].get(key) == None:
            self.pathKeyMap[id][key] = None
        self.pathKeyMap[id][key] = image

    def call_key_call_back(self, id, key):
        deck :VirtualDeck = self.idDeckMap[id]
        deck.key_callback(deck, key, True)
        deck.key_callback(deck, key, False)
