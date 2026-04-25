import re
import http.server
import json
import glob
import psutil
import os
import logging
from StreamDeck.Devices.StreamDeck import TouchscreenEventType, DialEventType
from typing import Optional, Any
from typing import Union

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

# 100 x 100 blank image
BLANK_IMAGE = "iVBORw0KGgoAAAANSUhEUgAAAGQAAABkCAQAAADa613fAAAAaUlEQVR42u3PQREAAAgDoC251Y" \
    + "3g34MGNJMXKiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIi" \
    + "IiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiJyWeRuMgFyCP0cAAAAAElFTkSuQmCC"

# 100 x 100 blank image
BLANK_TOUCH_IMAGE = "iVBORw0KGgoAAAANSUhEUgAAAGQAAABkCAQAAADa613fAAAAaUlEQVR42u3PQREAAAgDoC251Y" \
    + "3g34MGNJMXKiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIi" \
    + "IiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiJyWeRuMgFyCP0cAAAAAElFTkSuQmCC"


class DeckOutputWebHandler(http.server.BaseHTTPRequestHandler):
    # Intentional class-level mutable state: `http.server.BaseHTTPRequestHandler`
    # instantiates a fresh handler per request, so per-instance dicts would be
    # useless for cross-request state. These maps are shared across all handler
    # instances (keyed by deck id) and serve as the process-wide bridge between
    # the StreamDeck devices and the Web UI.
    path_key_map: dict = {}
    touchscreen_image: dict = {}
    id_deck_map: dict = {}
    id_current_page: dict = {}

    @staticmethod
    def set_key_image(id: str, key: str, image: str):
        c = DeckOutputWebHandler
        if c.path_key_map.get(id) == None:
            c.path_key_map[id] = {}
        if c.path_key_map[id].get(key) == None:
            c.path_key_map[id][key] = None
        c.path_key_map[id][key] = image

    @staticmethod
    def set_touchscreen_image(id: str, image: str):
        c = DeckOutputWebHandler
        c.touchscreen_image[id] = image

    @staticmethod
    def reset_keys(id: str, key_count: int):
        c = DeckOutputWebHandler
        c.path_key_map[id] = {}
        k: int = 0

        while k < key_count:
            c.path_key_map[id][k] = BLANK_IMAGE
            k += 1

    @staticmethod
    def remove_device(id: str):
        c = DeckOutputWebHandler
        c.path_key_map.pop(id, None)

    def call_key_call_back(self, id, key):
        from .my_decks_manager import VirtualDeck

        deck: VirtualDeck = self.id_deck_map[id]
        deck.key_callback(deck, key, True)
        deck.key_callback(deck, key, False)

    def call_dial_call_back(self, id, dial_num, event, value):
        from .my_decks_manager import VirtualDeck

        deck: VirtualDeck = self.id_deck_map[id]
        deck.dial_callback(deck, dial_num, event, value)

    def call_touchscreen_call_back(self, id: str, event: int, args: dict):
        from .my_decks_manager import VirtualDeck

        deck: VirtualDeck = self.id_deck_map[id]
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
            return self.res_file_html(ROOT_DIR+'/html/index.html')
        elif self.path == '/api/openaction/info':
            return self.res_openaction_info()
        elif self.path == '/api/openaction/plugins':
            return self.res_openaction_plugins()
        elif (m := re.search(r"^/pi/([a-zA-Z0-9._-]+\.sdPlugin)/(.+)$", self.path)) is not None:
            return self.res_pi_file(m.group(1), m.group(2))
        elif (m := re.search(r"(/(?:js|css)/[^/]+\.(?:js|css))", self.path)) is not None:
            js_or_css_path = m.group(1)
            with open(ROOT_DIR+'/html' + js_or_css_path, mode="rb") as f:
                try:
                    return self.response_js(f)
                except Exception as e:
                    pass
        elif self.path == '/chart/status':
            return self.res_file_html(ROOT_DIR+'/html/chart-status.html')
        elif self.path == '/totp':
            return self.res_file_html(ROOT_DIR + '/html/totp.html')
        elif self.path == '/api/totp/accounts':
            return self.res_totp_accounts()
        elif (m := re.search(r"^(.+/Assets/[^/]+\.(\w+))", self.path)) is not None and m.group(2) is not None:
            image_path = m.group(1)
            ext = m.group(2)
            abs_image_path = os.path.realpath(image_path)
            allowed_roots = [os.path.realpath(ROOT_DIR + '/Assets')]
            try:
                from .my_decks_starter import MyDecksStarter
                if MyDecksStarter.config_path:
                    allowed_roots.append(os.path.realpath(MyDecksStarter.config_path + '/Assets'))
            except Exception:
                pass
            if not any(os.path.commonpath([abs_image_path, root]) == root for root in allowed_roots):
                return self.response_404()
            with open(abs_image_path, mode="rb") as f:
                try:
                    return self.response_image(f, ext)
                except Exception as e:
                    logging.debug(e)
                    pass
        elif (m := re.search(r"^/api/app/(\w+)/sample_data/$", self.path)) is not None and m.group(1) is not None:
            app_name = m.group(1)
            return self.res_app_sample_data(app_name)
        elif (m := re.search(r"^/api/device/(\w+)/key_config/([^/]+)/(\d+)/$", self.path)) is not None:
            id = m.group(1)
            current_page = m.group(2)
            key_index = int(m.group(3))
            return self.res_current_key_config(id, current_page, key_index)
        elif (m := re.search(r"^/api/device/(\w+)/dial_config/([^/]+)/(\d+)/$", self.path)) is not None:
            id = m.group(1)
            current_page = m.group(2)
            key_index = int(m.group(3))
            return self.res_current_dial_config(id, current_page, key_index)
        elif (m := re.search(r"^/api/device/(\w+)/touchscreen_config/([^/]+)/$", self.path)) is not None:
            id = m.group(1)
            current_page = m.group(2)
            return self.res_current_touchscreen_config(id, current_page)
        elif (m := re.search(r"^/api/device/(\w+)/game_config/$", self.path)) is not None:
            id = m.group(1)
            return self.res_game_config(id)
        elif self.path == '/api/status':
            return self.res_status()
        elif self.path == '/api/resource':
            return self.res_resource()
        elif self.path == '/api/device_info':
            return self.res_device_info()
        elif self.path == '/api/images':
            return self.res_images()
        elif self.path == '/favicon.ico':
            image_path = ROOT_DIR + '/html/favicon.ico'
            with open(image_path, mode="rb") as f:
                try:
                    return self.response_image(f, "ico")
                except Exception as e:
                    logging.debug(e)
                    pass
        elif self.path == '/api/apps':
            return self.res_apps()
        elif self.path == '/api/games':
            return self.res_games()
        elif self.path == '/api/device_key_images':
            return self.res_device_key_images()
        elif (m := re.search(r'^/api/([^/]+)(?:/(\d+|(?:dial|touch)/(\d+)/(\d+)))?$', self.path)) is not None:
            all_zero = True
            c = DeckOutputWebHandler
            for k in c.path_key_map.keys():
                if c.path_key_map.get(k) is not None and len(c.path_key_map[k].keys()) != 0:
                    all_zero = False
                    break

            if all_zero:
                logging.debug("sys.exit!")
                self.server.shutdown()

            id: str = m.group(1)
            # /id/key_num
            if m.group(2) is not None:
                if re.search(r"dial/(\d+)", m.group(2)):
                    from .my_decks_manager import VirtualDeck
                    dial_num: int = int(m.group(3))
                    value: int = int(m.group(4))
                    vdeck: VirtualDeck = self.id_deck_map[id]
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
            elif (image_info := self.path_key_map.get(id)) is not None:
                res = {
                    "root_dir": ROOT_DIR,
                    "current_page": self.id_current_page.get(id, "@HOME"),
                    "key": image_info,
                    "touch": c.touchscreen_image.get(id),
                    "dial_states": self.id_deck_map[id].dial_states()
                }
                if res["touch"] is None:
                    res["touch"] = BLANK_TOUCH_IMAGE
                return self.res_deck_images(res)

        self.response_404()

    def do_POST(self):
        # /key_setting/: update configuration YAML file
        if self.path == '/api/key_setting/':
            return self.res_key_setting()

        if self.path == '/api/game_config/':
            return self.res_game_setting()

        if self.path == '/api/totp/upload':
            return self.res_totp_upload()

        if self.path == '/api/openaction/upload':
            return self.res_openaction_upload()

        if self.path == '/api/openaction/uninstall':
            return self.res_openaction_uninstall()

        if self.path == '/api/totp/scan':
            return self.res_totp_scan()

        if self.path == '/api/totp/register':
            return self.res_totp_register()

        if self.path == '/api/totp/delete':
            return self.res_totp_delete()

        if self.path == '/api/totp/set_image':
            return self.res_totp_set_image()

        if self.path == '/api/totp/reorder':
            return self.res_totp_reorder()

        if self.path == '/api/totp/fetch_icon':
            return self.res_totp_fetch_icon()

        if self.path == '/api/totp/update':
            return self.res_totp_update()

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

    def api_json_response(self, data: Any):
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
        # Convert the string to camel case
        camel_case_app_name = ''.join(word.title()
                                      for word in app_name.split('_'))
        data = getattr(module, camel_case_app_name).sample_data
        self.api_json_response(data)

    def res_game_config(self, id: str):
        from .my_decks_manager import VirtualDeck
        from .my_decks import MyDecks

        deck: VirtualDeck = self.id_deck_map[id]

        games_config: list = []
        for mydeck in MyDecks.mydecks.values():
            if mydeck.deck.get_serial_number() == deck.get_serial_number():
                sn_alias = mydeck.myname
                if MyDecks.mydecks[sn_alias] is None:
                    continue
                conf = MyDecks.mydecks[sn_alias].config
                if conf is None:
                    continue
                if conf._config_content_origin is None:
                    continue

                games_config = conf._config_content_origin.get("games", [])
                break

        return self.api_json_response(games_config)

    def res_current_key_config(self, id: str, current_page: str, key_index: int):
        from .my_decks_manager import VirtualDeck
        from .my_decks import MyDecks

        deck: VirtualDeck = self.id_deck_map[id]

        page_config_config: Optional[dict] = {}
        apps_config: Optional[list[dict]] = []
        for mydeck in MyDecks.mydecks.values():
            if mydeck.deck.get_serial_number() == deck.get_serial_number():
                sn_alias = mydeck.myname
                if MyDecks.mydecks[sn_alias] is None:
                    continue
                conf = MyDecks.mydecks[sn_alias].config
                if conf is None:
                    continue
                if conf._config_content_origin is None:
                    continue

                apps_config = conf._config_content_origin.get("apps")
                page_config_config = conf._config_content_origin.get(
                    "page_config")
                break

        from .my_decks import MyDecks, MyDeck
        page_name: str = current_page

        if page_name == "":
            return self.response_404()

        target_key_config: Optional[dict] = None
        if page_config_config is not None:
            page_config = page_config_config.get(page_name)
            if page_config is not None:
                keys_config = page_config.get("keys")
                if keys_config is not None:
                    target_key_config = keys_config.get(key_index)

        target_app_config: Optional[dict] = None
        if apps_config is not None:
            for app_config in apps_config:
                if app_config.get("option") is not None:
                    if page_key := app_config["option"].get("page_key"):
                        for page in page_key.keys():
                            if page == page_name and page_key[page] == key_index:
                                target_app_config = app_config
                                break

        return self.api_json_response({
            "key_config": target_key_config,
            "app_config": target_app_config
        })

    def res_current_dial_config(self, id: str, current_page: str, dial_index: int):
        from .my_decks_manager import VirtualDeck
        from .my_decks import MyDecks

        deck: VirtualDeck = self.id_deck_map[id]

        apps_config: Optional[list[dict]] = []
        for mydeck in MyDecks.mydecks.values():
            if mydeck.deck.get_serial_number() == deck.get_serial_number():
                sn_alias = mydeck.myname
                if MyDecks.mydecks[sn_alias] is None:
                    continue
                conf = MyDecks.mydecks[sn_alias].config
                if conf is None:
                    continue
                if conf._config_content_origin is None:
                    continue

                apps_config = conf._config_content_origin.get("apps")
                break

        from .my_decks import MyDecks, MyDeck
        page_name: str = current_page

        if page_name == "":
            return self.response_404()

        target_app_config: Optional[dict] = None
        if apps_config is not None:
            for app_config in apps_config:
                if app_config.get("option") is not None:
                    if page_key := app_config["option"].get("page_dial"):
                        for page in page_key.keys():
                            if page == page_name and page_key[page] == dial_index:
                                target_app_config = app_config
                                break

        return self.api_json_response({
            "app_config": target_app_config
        })

    def res_current_touchscreen_config(self, id: str, current_page: str):
        from .my_decks_manager import VirtualDeck
        from .my_decks import MyDecks

        deck: VirtualDeck = self.id_deck_map[id]

        apps_config: Optional[list] = []
        for mydeck in MyDecks.mydecks.values():
            if mydeck.deck.get_serial_number() == deck.get_serial_number():
                sn_alias = mydeck.myname
                if MyDecks.mydecks[sn_alias] is None:
                    continue
                conf = MyDecks.mydecks[sn_alias].config
                if conf is None:
                    continue
                if conf._config_content_origin is None:
                    continue

                apps_config = conf._config_content_origin.get("apps")
                break

        from .my_decks import MyDecks, MyDeck
        page_name: str = current_page

        if page_name == "":
            return self.response_404()

        target_app_config: Optional[dict] = None
        if apps_config is not None:
            for app_config in apps_config:
                pages = app_config.get("option", {}).get("page", [])
                for page in pages:
                    if page == page_name:
                        target_app_config = app_config["option"]
                        if target_app_config is not None and target_app_config["page"] is not None:
                            del target_app_config["page"]
                        break

        return self.api_json_response({
            "app_config": target_app_config
        })

    def res_device_info(self):
        from .my_decks_manager import VirtualDeck

        json_data: dict = {}
        for key in self.id_deck_map.keys():
            deck: VirtualDeck = self.id_deck_map[key]
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
        self.api_json_response(self.path_key_map)

    def res_status(self):
        from .my_decks import MyDecks, MyDeck
        json_data: dict[str, dict] = {}
        for sn_alias in MyDecks.mydecks.keys():
            device: MyDeck = MyDecks.mydecks[sn_alias]
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
        from mydeck.my_decks_starter import MyDecksStarter
        images: list = glob.glob(ROOT_DIR+"/Assets/*.png", recursive=False)
        if MyDecksStarter.config_path != "":
            images2: list = glob.glob(
                MyDecksStarter.config_path+"/Assets/*.png", recursive=False)
            images.extend(images2)

        images.sort()
        self.api_json_response(images)

    def res_apps(self):
        from . import my_decks_app_base
        apps: list = list(my_decks_app_base.APP_NAMES.keys())
        apps.sort()
        self.api_json_response(apps)

    def res_games(self):
        from . import my_decks_app_base
        games_with_explanation: list = []
        games: list = list(my_decks_app_base.GAME_NAMES.keys())
        games.sort()
        for game in games:
            games_with_explanation.append(
                {"name": game, "mode_explanation": my_decks_app_base.GAME_NAMES[game]})
        self.api_json_response(games_with_explanation)

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

        content_length = int(self.headers['content-length'])
        json_str = self.rfile.read(content_length).decode('utf-8')

        data: dict = json.loads(json_str)
        deck_id: Union[str, None] = data.pop('id', None)

        if deck_id is not None:
            deck = self.id_deck_map[deck_id]
            sn: str = deck.get_serial_number()
            MyDecksManager.ConfigQueue[sn].put(data)

        self.api_json_response({})

    def res_openaction_upload(self):
        """Receive a .streamDeckPlugin (zip) file as base64-encoded JSON,
        extract it under the bridge's plugins_dir, and synthesize a minimal
        manifest.json when the bundled one is encrypted (Elgato Marketplace
        plugins ship a binary "ELGATO"-prefixed manifest the desktop app
        decrypts at runtime; we cannot, so we extract action UUIDs from the
        plugin code instead).

        Body: {"filename": "...", "file_b64": "..."}
        Returns: {"ok": True, "plugin_uuid": "...", "actions": [...] } | {"error": "..."}

        After upload, mydeck must be restarted to spawn the new plugin —
        the bridge spawns plugins once at startup and does not hot-reload.
        """
        import base64 as _base64
        import io as _io
        import os as _os
        import zipfile as _zipfile
        import re as _re
        from pathlib import Path as _Path
        try:
            from .my_decks import MyDecks
            plugins_root = None
            registry = None
            for md in MyDecks.mydecks.values():
                bridge = getattr(md, '_openaction_bridge', None)
                if bridge is not None:
                    plugins_root = bridge.plugins_dir
                    registry = bridge._registry
                    break
            if plugins_root is None:
                return self.api_json_response({"error": "OpenAction bridge not running"})

            content_length = int(self.headers.get('content-length', 0))
            if content_length > 50 * 1024 * 1024:
                return self.api_json_response({"error": "file too large (max 50 MB)"})
            body = json.loads(self.rfile.read(content_length).decode('utf-8'))
            data = _base64.b64decode(body.get('file_b64', ''))
            if not data:
                return self.api_json_response({"error": "empty file"})

            # Confirm it's a zip; .streamDeckPlugin is a zip archive.
            try:
                zf = _zipfile.ZipFile(_io.BytesIO(data))
            except _zipfile.BadZipFile:
                return self.api_json_response({"error": "not a valid .streamDeckPlugin (zip) file"})

            # Find the .sdPlugin top-level directory inside the zip.
            sd_dir = None
            for name in zf.namelist():
                first = name.split('/', 1)[0]
                if first.endswith('.sdPlugin'):
                    sd_dir = first
                    break
            if sd_dir is None:
                return self.api_json_response({"error": "no .sdPlugin folder inside archive"})

            target_dir = plugins_root / sd_dir
            if target_dir.exists():
                # Refuse to overwrite existing plugin to avoid clobbering
                # user-edited manifests (e.g. the synthetic one for Timebox).
                return self.api_json_response({
                    "error": "plugin already installed: {}; uninstall it first".format(sd_dir)
                })

            # Path-traversal guard.
            plugins_root_real = _os.path.realpath(str(plugins_root))
            for name in zf.namelist():
                dest = _os.path.realpath(str(plugins_root / name))
                if _os.path.commonpath([dest, plugins_root_real]) != plugins_root_real:
                    return self.api_json_response({"error": "archive contains unsafe paths"})

            zf.extractall(str(plugins_root))

            # Inspect manifest. If it begins with the "ELGATO" magic bytes the
            # plugin was packaged by Elgato Marketplace and the manifest is
            # encrypted. Synthesize a minimal one so our registry can load it.
            manifest_path = target_dir / "manifest.json"
            synthesized = False
            plugin_uuid = sd_dir[: -len(".sdPlugin")]
            actions_found: list = []
            if not manifest_path.is_file():
                synthesized = True
            else:
                head = manifest_path.read_bytes()[:6]
                if head.startswith(b"ELGATO"):
                    synthesized = True
            if synthesized:
                actions_found = self._synthesize_openaction_manifest(target_dir, plugin_uuid)

            # Verify the plugin is actually loadable on this platform — Stocks
            # and similar Mac/Windows-only plugins ship native binaries and
            # have no Linux CodePath; they unzip fine but the registry skips
            # them silently, so the user would never see them in the list.
            try:
                from .openaction.manifest import load_manifest
                load_manifest(target_dir)
                load_error = None
            except Exception as e:
                load_error = str(e)

            if load_error is not None:
                # Roll back the extracted files so the user can retry without
                # hitting "plugin already installed".
                import shutil as _shutil
                try:
                    _shutil.rmtree(str(target_dir))
                except Exception:
                    pass
                return self.api_json_response({
                    "error": (
                        "Plugin extracted but cannot run on this platform: "
                        + load_error
                        + ". Most likely it ships only Mac/Windows binaries "
                          "or uses a CodePath we do not support."
                    ),
                })

            # Trigger a registry rescan so future lookups (and the next bridge
            # restart) see the new plugin. We do not spawn the plugin here —
            # bridge.launch_plugin runs only at startup; daemon restart is
            # required for the new plugin to actually run.
            try:
                if registry is not None:
                    from .openaction.registry import ActionRegistry
                    new_reg = ActionRegistry.from_directory(plugins_root)
                    registry._plugins = new_reg._plugins
                    registry._by_action_uuid = new_reg._by_action_uuid
            except Exception as e:
                logging.warning("openaction registry rescan failed: %s", e)

            return self.api_json_response({
                "ok": True,
                "plugin_uuid": plugin_uuid,
                "synthesized_manifest": synthesized,
                "actions": actions_found,
                "restart_required": True,
            })
        except Exception as e:
            logging.error("openaction upload error: %s", e)
            return self.api_json_response({"error": str(e)})

    def _synthesize_openaction_manifest(self, target_dir, plugin_uuid: str) -> list:
        """Generate a minimal manifest.json for an Elgato-encrypted plugin.

        Strategy: scan plugin bundles (.js / native) for occurrences of
        "<plugin_uuid>.<something>" — those are the action UUIDs. Pick the
        most likely CodePath from common SDK layouts.
        """
        import json as _json
        import re as _re
        from pathlib import Path as _Path

        # Collect strings matching "<plugin_uuid>.<id>" from common code files.
        action_pattern = _re.compile(_re.escape(plugin_uuid) + r"\.[a-zA-Z0-9._-]+")
        seen = set()
        for f in target_dir.rglob("*"):
            if not f.is_file():
                continue
            if f.suffix.lower() not in (".js", ".mjs", ".cjs", ".ts"):
                continue
            try:
                text = f.read_text(errors="ignore")
            except Exception:
                continue
            for m in action_pattern.findall(text):
                # Filter out things like the plugin uuid itself or paths.
                tail = m[len(plugin_uuid) + 1:]
                if "." in tail or "/" in tail:
                    continue
                seen.add(m)

        # Pick a CodePath from common locations.
        candidates = ["bin/plugin.js", "bin/plugin.mjs", "plugin/index.html",
                      "index.html", "plugin.js", "main.js"]
        code_path = None
        for c in candidates:
            if (target_dir / c).is_file():
                code_path = c
                break

        actions = []
        for uuid in sorted(seen):
            short = uuid[len(plugin_uuid) + 1:]
            actions.append({
                "UUID": uuid,
                "Name": short.replace("-", " ").replace("_", " ").title(),
                "Tooltip": short,
                "States": [{"Image": "imgs/plugin/marketplace", "Name": short}],
            })

        manifest = {
            "Name": plugin_uuid.split(".")[-1].title(),
            "Version": "1.0",
            "Author": "unknown",
            "OS": [{"Platform": "linux", "MinimumVersion": "1.0"}],
            "SDKVersion": 2,
            "Software": {"MinimumVersion": "6.0"},
            "Icon": "imgs/plugin/marketplace",
            "Category": plugin_uuid.split(".")[-1].title(),
            "UUID": plugin_uuid,
            "Actions": actions,
        }
        if code_path is not None:
            manifest["CodePath"] = code_path

        manifest_path = target_dir / "manifest.json"
        # If an encrypted manifest is in the way, keep a backup before
        # overwriting so the user can compare or restore later.
        if manifest_path.is_file():
            backup = manifest_path.with_suffix(".json.elgato-encrypted")
            if not backup.is_file():
                manifest_path.rename(backup)
        with manifest_path.open("w") as f:
            _json.dump(manifest, f, indent=2)
        return [a["UUID"] for a in actions]

    def res_openaction_uninstall(self):
        """Remove an installed OpenAction plugin directory.
        Body: {"plugin_uuid": "..."}"""
        import os as _os
        import shutil as _shutil
        try:
            from .my_decks import MyDecks
            plugins_root = None
            registry = None
            for md in MyDecks.mydecks.values():
                bridge = getattr(md, '_openaction_bridge', None)
                if bridge is not None:
                    plugins_root = bridge.plugins_dir
                    registry = bridge._registry
                    break
            if plugins_root is None:
                return self.api_json_response({"error": "OpenAction bridge not running"})

            content_length = int(self.headers.get('content-length', 0))
            body = json.loads(self.rfile.read(content_length).decode('utf-8'))
            plugin_uuid = body.get('plugin_uuid', '')
            if not plugin_uuid or '/' in plugin_uuid or '..' in plugin_uuid:
                return self.api_json_response({"error": "invalid plugin_uuid"})
            target = plugins_root / (plugin_uuid + ".sdPlugin")
            real_target = _os.path.realpath(str(target))
            real_root = _os.path.realpath(str(plugins_root))
            if _os.path.commonpath([real_target, real_root]) != real_root:
                return self.api_json_response({"error": "path outside plugins_dir"})
            if not target.exists():
                return self.api_json_response({"error": "plugin not installed"})
            _shutil.rmtree(str(target))

            try:
                if registry is not None:
                    from .openaction.registry import ActionRegistry
                    new_reg = ActionRegistry.from_directory(plugins_root)
                    registry._plugins = new_reg._plugins
                    registry._by_action_uuid = new_reg._by_action_uuid
            except Exception as e:
                logging.warning("openaction registry rescan failed: %s", e)

            return self.api_json_response({"ok": True, "restart_required": True})
        except Exception as e:
            logging.error("openaction uninstall error: %s", e)
            return self.api_json_response({"error": str(e)})

    def res_openaction_info(self):
        """Expose the OpenAction bridge WebSocket port to the Web UI so
        Property Inspector iframes can connect with connectElgatoStreamDeckSocket."""
        try:
            from .my_decks import MyDecks
            for md in MyDecks.mydecks.values():
                bridge = getattr(md, '_openaction_bridge', None)
                if bridge is None or bridge._server is None:
                    continue
                return self.api_json_response({"port": bridge._server.port})
        except Exception as e:
            logging.debug("openaction info lookup failed: %s", e)
        return self.api_json_response({"port": None})

    def res_openaction_plugins(self):
        """List installed OpenAction plugins and their actions for the Web UI's action-picker."""
        try:
            from .my_decks import MyDecks
            for md in MyDecks.mydecks.values():
                bridge = getattr(md, '_openaction_bridge', None)
                if bridge is None or bridge._registry is None:
                    continue
                plugins = []
                for manifest in bridge._registry.all_plugins():
                    plugins.append({
                        "uuid": manifest.plugin_uuid,
                        "name": manifest.name,
                        "actions": [
                            {
                                "uuid": a.action_uuid,
                                "name": a.name,
                                "property_inspector": self._pi_path_for(manifest, a.action_uuid),
                            }
                            for a in manifest.actions
                        ],
                    })
                return self.api_json_response({"plugins": plugins})
        except Exception as e:
            logging.debug("openaction plugins lookup failed: %s", e)
        return self.api_json_response({"plugins": []})

    def _pi_path_for(self, manifest, action_uuid):
        """Return a relative URL for the PI HTML if the plugin ships one."""
        plugin_dir = manifest.plugin_dir
        short = action_uuid
        if manifest.plugin_uuid and action_uuid.startswith(manifest.plugin_uuid + "."):
            short = action_uuid[len(manifest.plugin_uuid) + 1:]
        candidates = []
        for base in ("ui", "propertyinspector", "pi", "action/js"):
            for name in (short, short.replace("_", "-"), short.replace("-", "_"),
                         "inspector", "index", "index_pi"):
                for ext in (".html", "/index.html"):
                    candidates.append("{}/{}{}".format(base, name, ext))
            candidates.extend([
                "{}/index.html".format(base),
                "{}/inspector.html".format(base),
            ])
        candidates.extend(["inspector.html", "index.html"])
        for c in candidates:
            if (plugin_dir / c).is_file():
                return "/pi/{}/{}".format(plugin_dir.name, c)
        return None

    def res_pi_file(self, plugin_sd_dir: str, rest: str):
        """Serve files from a plugin directory for Property Inspector iframes,
        confined to the plugins root."""
        import os as _os
        # rest may include a query string (self.path is the full request path);
        # strip it before resolving on disk. The query is still available via
        # self.path for _inject_pi_bootstrap to parse.
        if '?' in rest:
            rest = rest.split('?', 1)[0]
        try:
            from .my_decks import MyDecks
            plugins_root = None
            for md in MyDecks.mydecks.values():
                bridge = getattr(md, '_openaction_bridge', None)
                if bridge is not None:
                    plugins_root = bridge.plugins_dir
                    break
            if plugins_root is None:
                return self.response_404()
            target = (plugins_root / plugin_sd_dir / rest).resolve()
            root = _os.path.realpath(str(plugins_root))
            if _os.path.commonpath([str(target), root]) != root:
                return self.response_404()
            if not target.is_file():
                return self.response_404()
            ext = target.suffix.lstrip('.').lower()
            mime = {
                'html': 'text/html; charset=utf-8',
                'htm': 'text/html; charset=utf-8',
                'js': 'application/javascript; charset=utf-8',
                'mjs': 'application/javascript; charset=utf-8',
                'css': 'text/css; charset=utf-8',
                'png': 'image/png',
                'jpg': 'image/jpeg',
                'jpeg': 'image/jpeg',
                'gif': 'image/gif',
                'svg': 'image/svg+xml',
                'json': 'application/json; charset=utf-8',
                'woff': 'font/woff',
                'woff2': 'font/woff2',
                'ttf': 'font/ttf',
                'wav': 'audio/wav',
                'mp3': 'audio/mpeg',
            }.get(ext, 'application/octet-stream')
            data = target.read_bytes()
            if ext in ('html', 'htm'):
                from urllib.parse import urlparse, parse_qs
                try:
                    q = parse_qs(urlparse(self.path).query)
                    ctx = (q.get('ctx') or [''])[0]
                    action = (q.get('action') or [''])[0]
                except Exception:
                    ctx, action = '', ''
                data = self._inject_pi_bootstrap(data, ctx, action)
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        except Exception as e:
            logging.debug("PI file serve failed: %s", e)
            return self.response_404()

    def _inject_pi_bootstrap(self, html_bytes: bytes, ctx: str, action_uuid: str) -> bytes:
        """Inject a bootstrap script so the PI iframe connects to the bridge.
        The PI's own scripts define connectElgatoStreamDeckSocket; we wait for
        it to appear, fetch the bridge port from the Web UI, and invoke it with
        the context token and action UUID supplied via query string."""
        import json as _json
        ctx_js = _json.dumps(ctx)
        action_js = _json.dumps(action_uuid)
        bootstrap = (
            "<script>\n"
            "(function() {\n"
            "  var CTX = " + ctx_js + ";\n"
            "  var ACTION = " + action_js + ";\n"
            "  function waitFor(pred, cb, max) {\n"
            "    var tries = 0;\n"
            "    var id = setInterval(function() {\n"
            "      if (pred()) { clearInterval(id); cb(); }\n"
            "      else if (++tries > (max || 100)) { clearInterval(id); }\n"
            "    }, 50);\n"
            "  }\n"
            "  window.addEventListener('DOMContentLoaded', function() {\n"
            "    fetch('/api/openaction/info').then(function(r) { return r.json(); }).then(function(info) {\n"
            "      if (!info || !info.port) return;\n"
            "      var appInfo = {\n"
            "        application: { font: '', language: 'en', platform: 'linux', platformVersion: '', version: '6.0.0' },\n"
            "        plugin: { uuid: '', version: '1.0.0' },\n"
            "        devicePixelRatio: 1, devices: [], colors: {}\n"
            "      };\n"
            "      var actionInfo = { action: ACTION, context: CTX, device: '', payload: { settings: {}, coordinates: {row:0, column:0} } };\n"
            "      waitFor(\n"
            "        function() { return typeof connectElgatoStreamDeckSocket === 'function' || typeof connectSocket === 'function'; },\n"
            "        function() {\n"
            "          var fn = window.connectElgatoStreamDeckSocket || window.connectSocket;\n"
            "          fn(info.port, CTX, 'registerPropertyInspector', JSON.stringify(appInfo), JSON.stringify(actionInfo));\n"
            "        }\n"
            "      );\n"
            "    });\n"
            "  });\n"
            "})();\n"
            "</script>\n"
        ).encode('utf-8')
        lower = html_bytes.lower()
        idx = lower.rfind(b"</head>")
        if idx < 0:
            idx = lower.rfind(b"</body>")
        if idx < 0:
            return html_bytes + bootstrap
        return html_bytes[:idx] + bootstrap + html_bytes[idx:]

    def res_totp_accounts(self):
        from .totp_account_manager import TotpAccountManager
        manager = TotpAccountManager()
        return self.api_json_response(manager.load_accounts())

    def res_totp_scan(self):
        """Decode QR code from base64 image and return the raw URI (no registration)."""
        import base64
        from io import BytesIO
        from PIL import Image as PILImage
        from pyzbar.pyzbar import decode as pyzbar_decode

        try:
            content_length = int(self.headers['content-length'])
            if content_length > 10 * 1024 * 1024:
                return self.api_json_response({"error": "image too large"})
            body = json.loads(self.rfile.read(content_length).decode('utf-8'))
            image_data = base64.b64decode(body['image_b64'])
            im = PILImage.open(BytesIO(image_data)).convert('L')  # grayscale for better detection
            logging.debug("TOTP scan: image size=%s, mode=%s", im.size, im.mode)
            decoded = pyzbar_decode(im)
            logging.debug("TOTP scan: pyzbar found %d codes", len(decoded))
            if not decoded:
                return self.api_json_response({})
            uri = decoded[0].data.decode('utf-8')
            logging.debug("TOTP scan: decoded URI=%s", uri[:50])
            return self.api_json_response({"uri": uri})
        except Exception as e:
            logging.error("TOTP scan error: %s", e)
            return self.api_json_response({"error": str(e)})

    def res_totp_upload(self):
        import base64
        from io import BytesIO
        from PIL import Image as PILImage
        from pyzbar.pyzbar import decode as pyzbar_decode
        from .totp_account_manager import TotpAccountManager

        try:
            content_length = int(self.headers['content-length'])
            if content_length > 10 * 1024 * 1024:
                return self.api_json_response({"error": "image too large (max 10 MB)"})
            body = json.loads(self.rfile.read(content_length).decode('utf-8'))
            image_data = base64.b64decode(body['image_b64'])
            im = PILImage.open(BytesIO(image_data))
            decoded = pyzbar_decode(im)
            if not decoded:
                return self.api_json_response({"error": "QR code not found in image"})
            uri = decoded[0].data.decode('utf-8')
            manager = TotpAccountManager()
            parsed = manager.parse_otpauth_uri(uri)
            name = body.get('name') or parsed['name']
            manager.save_account(name, parsed['issuer'], parsed['secret'])
            return self.api_json_response({"ok": True, "name": name})
        except Exception as e:
            logging.error("TOTP upload error: %s", e)
            return self.api_json_response({"error": str(e)})

    def res_totp_register(self):
        import base64 as _base64
        from .totp_account_manager import TotpAccountManager

        try:
            content_length = int(self.headers['content-length'])
            body = json.loads(self.rfile.read(content_length).decode('utf-8'))
            manager = TotpAccountManager()
            uri = body.get('uri', '')
            if uri.startswith('otpauth-migration://'):
                entries = manager.parse_migration_uri(uri)
                if not entries:
                    return self.api_json_response({"error": "No TOTP accounts found in migration data"})
                names = []
                for entry in entries:
                    manager.save_account(entry['name'], entry['issuer'], entry['secret'])
                    names.append(entry['name'])
                return self.api_json_response({"ok": True, "name": ", ".join(names), "count": len(names)})
            elif uri:
                parsed = manager.parse_otpauth_uri(uri)
                name = body.get('name') or parsed['name']
                manager.save_account(name, parsed['issuer'], parsed['secret'])
            else:
                name = body['name']
                issuer = body.get('issuer', name)
                secret = body['secret'].upper().replace(' ', '')
                try:
                    _base64.b32decode(secret, casefold=True)
                except Exception:
                    return self.api_json_response({"error": "invalid Base32 secret"})
                manager.save_account(name, issuer, secret)
            return self.api_json_response({"ok": True, "name": name})
        except Exception as e:
            logging.error("TOTP register error: %s", e)
            return self.api_json_response({"error": str(e)})

    def res_totp_set_image(self):
        import base64
        import requests as req
        from .totp_account_manager import TotpAccountManager

        try:
            content_length = int(self.headers['content-length'])
            if content_length > 10 * 1024 * 1024:
                return self.api_json_response({"error": "image too large (max 10 MB)"})
            body = json.loads(self.rfile.read(content_length).decode('utf-8'))
            name = body['name']
            manager = TotpAccountManager()
            if 'image_url' in body:
                resp = req.get(body['image_url'], timeout=10)
                if resp.status_code != 200:
                    return self.api_json_response({"error": f"画像の取得に失敗: HTTP {resp.status_code}"})
                image_data = resp.content
            else:
                image_data = base64.b64decode(body['image_b64'])
            path = manager.set_account_image(name, image_data)
            return self.api_json_response({"ok": True, "path": path})
        except Exception as e:
            logging.error("TOTP set_image error: %s", e)
            return self.api_json_response({"error": str(e)})

    def res_totp_delete(self):
        from .totp_account_manager import TotpAccountManager

        try:
            content_length = int(self.headers['content-length'])
            body = json.loads(self.rfile.read(content_length).decode('utf-8'))
            name = body['name']
            manager = TotpAccountManager()
            ok = manager.delete_account(name)
            return self.api_json_response({"ok": ok})
        except Exception as e:
            logging.error("TOTP delete error: %s", e)
            return self.api_json_response({"error": str(e)})

    def res_totp_reorder(self):
        from .totp_account_manager import TotpAccountManager

        try:
            content_length = int(self.headers['content-length'])
            body = json.loads(self.rfile.read(content_length).decode('utf-8'))
            names = body['names']
            manager = TotpAccountManager()
            ok = manager.reorder_accounts(names)
            return self.api_json_response({"ok": ok})
        except Exception as e:
            logging.error("TOTP reorder error: %s", e)
            return self.api_json_response({"error": str(e)})

    def res_totp_fetch_icon(self):
        from .totp_account_manager import TotpAccountManager

        try:
            content_length = int(self.headers['content-length'])
            body = json.loads(self.rfile.read(content_length).decode('utf-8'))
            name = body['name']
            manager = TotpAccountManager()
            accounts = manager.load_accounts()
            issuer = name
            for acc in accounts:
                if acc["name"] == name:
                    issuer = acc.get("issuer", name)
                    # Clear existing image so _auto_fetch_icon will run
                    if acc.get("image"):
                        acc.pop("image")
                        with open(manager.accounts_file, "w") as f:
                            json.dump(accounts, f, indent=2)
                    break
            manager._auto_fetch_icon(name, issuer)
            # Check if it worked
            path = manager._image_path(name)
            if path:
                return self.api_json_response({"ok": True, "path": path})
            else:
                return self.api_json_response({"error": "アイコンが見つかりませんでした"})
        except Exception as e:
            logging.error("TOTP fetch_icon error: %s", e)
            return self.api_json_response({"error": str(e)})

    def res_totp_update(self):
        from .totp_account_manager import TotpAccountManager

        try:
            content_length = int(self.headers['content-length'])
            body = json.loads(self.rfile.read(content_length).decode('utf-8'))
            name = body['name']
            new_name = body.get('new_name')
            new_issuer = body.get('new_issuer')
            manager = TotpAccountManager()
            ok = manager.update_account(name, new_name=new_name, new_issuer=new_issuer)
            return self.api_json_response({"ok": ok})
        except Exception as e:
            logging.error("TOTP update error: %s", e)
            return self.api_json_response({"error": str(e)})

    def log_message(self, format, *args):
        message = format % args
        logging.debug("%s - - [%s] %s" %
                      (self.address_string(),
                          self.log_date_time_string(),
                          message.translate(self._control_char_table)))
