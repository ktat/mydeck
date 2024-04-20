import re
import http.server
import json
import glob
import psutil
import os
import logging
from StreamDeck.Devices.StreamDeck import TouchscreenEventType, DialEventType
from typing import Union

# 100 x 100 blank image
BLANK_IMAGE = "iVBORw0KGgoAAAANSUhEUgAAAGQAAABkCAQAAADa613fAAAAaUlEQVR42u3PQREAAAgDoC251Y" \
    + "3g34MGNJMXKiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIi" \
    + "IiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiJyWeRuMgFyCP0cAAAAAElFTkSuQmCC"

# 100 x 100 blank image
BLANK_TOUCH_IMAGE = "iVBORw0KGgoAAAANSUhEUgAAAGQAAABkCAQAAADa613fAAAAaUlEQVR42u3PQREAAAgDoC251Y" \
    + "3g34MGNJMXKiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIi" \
    + "IiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiJyWeRuMgFyCP0cAAAAAElFTkSuQmCC"


class DeckOutputWebHandler(http.server.BaseHTTPRequestHandler):
    pathKeyMap: dict = {}
    touchscreenImage: dict = {}
    idDeckMap: dict = {}

    @staticmethod
    def setKeyImage(id: str, key: str, image: str):
        c = DeckOutputWebHandler
        if c.pathKeyMap.get(id) == None:
            c.pathKeyMap[id] = {}
        if c.pathKeyMap[id].get(key) == None:
            c.pathKeyMap[id][key] = None
        c.pathKeyMap[id][key] = image

    @staticmethod
    def setTouchscreenImage(id: str, image: str):
        c = DeckOutputWebHandler
        c.touchscreenImage[id] = image

    @staticmethod
    def reset_keys(id: str, key_count: int):
        c = DeckOutputWebHandler
        c.pathKeyMap[id] = {}
        k: int = 0

        while k < key_count:
            c.pathKeyMap[id][k] = BLANK_IMAGE
            k += 1

    @staticmethod
    def remove_device(id: str):
        c = DeckOutputWebHandler
        c.pathKeyMap.pop(id, None)

    def call_key_call_back(self, id, key):
        from .my_decks_manager import VirtualDeck

        deck: VirtualDeck = self.idDeckMap[id]
        deck.key_callback(deck, key, True)
        deck.key_callback(deck, key, False)

    def call_dial_call_back(self, id, dial_num, event, value):
        from .my_decks_manager import VirtualDeck

        deck: VirtualDeck = self.idDeckMap[id]
        deck.dial_callback(deck, dial_num, event, value)

    def call_touchscreen_call_back(self, id: str, event: int, args: dict):
        from .my_decks_manager import VirtualDeck

        deck: VirtualDeck = self.idDeckMap[id]
        if deck.touchscreen_callback is not None:
            deck.touchscreen_callback(deck, event, args)

    # https://towardsdatascience.com/the-strange-size-of-python-objects-in-memory-ce87bdfbb97f
    def actualsize(self, input_obj):
        import sys
        import gc

        memory_size = 0
        ids = set()
        objects = [input_obj]
        while objects:
            new = []
            for obj in objects:
                if id(obj) not in ids:
                    ids.add(id(obj))
                    memory_size += sys.getsizeof(obj)
                    new.append(obj)
            objects = gc.get_referents(*new)
        return memory_size

    def do_GET(self):
        if self.path == '/':
            return self.res_file_html('src/html/index.html')
        elif (m := re.search("(/(?:js|css)/[^/]+\.(?:js|css))", self.path)) is not None:
            js_or_css_path = m.group(1)
            with open('src/html' + js_or_css_path, mode="rb") as f:
                try:
                    return self.response_js(f)
                except Exception as e:
                    pass
        elif self.path == '/chart/status':
            return self.res_file_html('src/html/chart-status.html')
        elif (m := re.search("(/src/Assets/[^/]+\.(\w+))", self.path)) is not None and m.group(2) is not None:
            image_path = m.group(1)
            ext = m.group(2)
            with open('.' + image_path, mode="rb") as f:
                try:
                    return self.response_image(f, ext)
                except Exception as e:
                    logging.debug(e)
                    pass
        elif (m := re.search("^/api/app/(\w+)/sample_data/$", self.path)) is not None and m.group(1) is not None:
            app_name = m.group(1)
            return self.res_app_sample_data(app_name)
        elif self.path == '/api/status':
            return self.res_status()
        elif self.path == '/api/resource':
            return self.res_resource()
        elif self.path == '/api/device_info':
            return self.res_device_info()
        elif self.path == '/api/images':
            return self.res_images()
        elif self.path == '/api/apps':
            return self.res_apps()
        elif self.path == '/api/device_key_images':
            return self.res_device_key_images()
        elif (m := re.search('^/api/([^/]+)(?:/(\d+|(?:dial|touch)/(\d+)/(\d+)))?$', self.path)) is not None:
            all_zero = True
            c = DeckOutputWebHandler
            for k in c.pathKeyMap.keys():
                if c.pathKeyMap.get(k) is not None and len(c.pathKeyMap[k].keys()) != 0:
                    all_zero = False
                    break

            if all_zero:
                logging.debug("sys.exit!")
                self.server.shutdown()

            id: str = m.group(1)
            # /id/key_num
            if m.group(2) is not None:
                if re.search("dial/(\d+)", m.group(2)):
                    from .my_decks_manager import VirtualDeck
                    dial_num: int = int(m.group(3))
                    value: int = int(m.group(4))
                    vdeck: VirtualDeck = self.idDeckMap[id]
                    vdeck.set_dial_states(dial_num, value)
                    return self.res_dial_changed(id, dial_num, value)
                elif re.search("touch", m.group(2)):
                    args: dict = {}
                    args["x"] = int(m.group(3))
                    args["y"] = int(m.group(4))
                    return self.res_touchscreen_tapped(id, args)
                else:
                    key: int = int(m.group(2))
                    return self.res_key_tapped(id, key)
            # /id
            elif (image_info := self.pathKeyMap.get(id)) is not None:
                res = {
                    "key": image_info,
                    "touch": c.touchscreenImage.get(id),
                    "dial_states": self.idDeckMap[id].dial_states()
                }
                if res["touch"] is None:
                    res["touch"] = BLANK_TOUCH_IMAGE
                return self.res_deck_images(res)

        self.response_404()

    def do_POST(self):
        # /key_setting/: update configuration YAML file
        if self.path == '/api/key_setting/':
            return self.res_key_setting()

        self.response_404()

    def text_headers(self, status: int = 200, type: str = "html; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", 'text/' + type)
        self.end_headers()

    def api_headers(self, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", 'application/json')
        self.send_header("Access-Control-Allow-Origin",
                         self.headers.get("Origin"))
        self.end_headers()

    def api_json_response(self, data: dict):
        self.api_headers()
        str = json.dumps(data)
        self.wfile.write(str.encode('utf-8'))

    def response_404(self):
        self.text_headers(404, 'plain')
        self.wfile.write(bytes("404 not found: {}".format(self.path), 'ascii'))

    def response_js(self, f):
        self.send_response(200)
        self.send_header("Content-Type", 'application/javascript')
        self.end_headers()
        self.wfile.write(f.read())

    def response_image(self, f, ext):
        self.send_response(200)
        self.send_header("Content-Type", 'image/' + ext)
        self.end_headers()
        self.wfile.write(f.read())

    def res_file_html(self, file: str):
        self.text_headers()
        with open(file, 'r+b') as f:
            self.wfile.write(f.read())

    def res_app_sample_data(self, app_name: str):
        from importlib import import_module
        module = import_module(f"mydeck.{app_name}")
        logging.debug(dir(module))
        # Convert the string to camel case
        camel_case_app_name = ''.join(word.title()
                                      for word in app_name.split('_'))
        data = getattr(module, camel_case_app_name).sample_data
        self.api_json_response(data)

    def res_device_info(self):
        from .my_decks_manager import VirtualDeck

        json_data: dict = {}
        for key in self.idDeckMap.keys():
            deck: VirtualDeck = self.idDeckMap[key]
            json_data[deck.id()] = {
                "key_count": deck.key_count(),
                "serial_number": deck.get_serial_number(),
                "columns": deck.columns(),
                "has_touchscreen": deck.is_touch(),
                "touchscreen_size": deck.touchscreen_size,
                "dials": deck.dial_count(),
                "dial_states": deck.dial_states(),
            }
        self.api_json_response(json_data)

    def res_device_key_images(self):
        self.api_json_response(self.pathKeyMap)

    def res_status(self):
        from .my_decks import MyDecks
        json_data: dict[str, dict] = {}
        for sn_alias in MyDecks.mydecks.keys():
            device = MyDecks.mydecks[sn_alias]
            json_data[sn_alias] = {
                "apps": [],
                "current_page": device.current_page()
            }
            for app in device.config.apps:
                json_data[sn_alias]["apps"].append({
                    "name": app.name(),
                    "in_working": app.in_working,
                    "key_config": app.page_key,
                })
        self.api_json_response(json_data)

    def res_resource(self):
        from .my_decks import MyDecks
        json_data: dict[str, int] = {

            "apps": {},
            "memory": 0
        }
        keys = MyDecks.mydecks.keys()
        for sn_alias in keys:
            device = MyDecks.mydecks[sn_alias]
            json_data["memory"] = psutil.Process(os.getpid()).memory_info().rss
            json_data["calc_memory"] = self.actualsize(MyDecks.mydecks)
            json_data["cpu"] = psutil.Process(
                os.getpid()).cpu_percent(interval=1)
            for app in device.config.apps:
                json_data["apps"][sn_alias+"." +
                                  app.name()] = self.actualsize(app)
        self.api_json_response(json_data)

    def res_images(self):
        images: list = glob.glob("./src/Assets/*.png", recursive=False)
        images.sort()
        self.api_json_response(images)

    def res_apps(self):
        from . import my_decks_app_base
        apps: list = list(my_decks_app_base.APP_NAMES.keys())
        apps.sort()
        self.api_json_response(apps)

    def res_key_tapped(self, id: str, key: int):
        self.call_key_call_back(id, key)
        self.text_headers(200, 'plain')
        self.wfile.write(b"Key Tapped")

    def res_dial_changed(self, id: str, dial_num: int, value: int):
        self.call_dial_call_back(id, dial_num, DialEventType.TURN, value)
        self.text_headers(200, 'plain')
        self.wfile.write(b"Dial Changed")

    def res_touchscreen_tapped(self, id: str, args: dict):
        self.call_touchscreen_call_back(
            id, TouchscreenEventType.SHORT, args)
        self.text_headers(200, 'plain')
        self.wfile.write(b"Screen Tapped")

    def res_deck_images(self, image_info: dict):
        self.api_json_response(image_info)

    def res_key_setting(self):
        from .my_decks_manager import MyDecksManager

        self.api_json_response({})

        content_length = int(self.headers['content-length'])
        json_str = self.rfile.read(content_length).decode('utf-8')

        data: dict = json.loads(json_str)
        deck_id: Union[str, None] = data.pop('id', None)

        if deck_id is not None:
            deck = self.idDeckMap[deck_id]
            sn: str = deck.get_serial_number()
            MyDecksManager.ConfigQueue[sn].put(data)
