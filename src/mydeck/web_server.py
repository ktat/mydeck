import re
import http
import json
import glob
from typing import Union

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
        from .my_decks_manager import VirtualDeck

        deck :VirtualDeck = self.idDeckMap[id]
        deck.key_callback(deck, key, True)
        deck.key_callback(deck, key, False)

    def do_GET(self):
        if self.path == '/':
            return self.res_vdeck_html()
        elif self.path == '/status':
            return self.res_status()
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
        from .my_decks_manager import VirtualDeck

        json_data: dict = {}
        for key in self.idDeckMap.keys():
            deck: VirtualDeck = self.idDeckMap[key]
            json_data[deck.id()] = {
                "key_count": deck.key_count(),
                "serial_number": deck.get_serial_number(),
                "columns": deck.columns(),
            }
        self.api_json_response(json_data)

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
        from .my_decks_manager import MyDecksManager

        self.api_json_response({})

        content_length = int(self.headers['content-length'])
        json_str = self.rfile.read(content_length).decode('utf-8')

        data: dict = json.loads(json_str)
        deck_id :Union[str,None] = data.pop('id', None)
        if deck_id is not None:
            deck = self.idDeckMap[deck_id]
            sn: str = deck.get_serial_number()
            MyDecksManager.ConfigQueue[sn].put(data)