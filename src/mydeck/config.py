"""Configuration class extracted from my_decks.py."""

from copy import deepcopy
import importlib
import logging
import os
import os.path
import re
import shutil
import traceback
import yaml
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .my_decks_manager import VirtualDeck

if TYPE_CHECKING:
    from .my_decks_app_base import App, AppBase, BackgroundAppBase, HookAppBase


class Config:
    """STREAM DECK Configuration Class"""

    def __init__(self, mydeck: 'MyDeck', file: str):
        """Pass MyDeck instance as mydeck and configuration file as file"""
        self._file_mtime: float = 0
        self._file: str = ''
        self._config_content_origin: dict = {}
        self._config_content: dict = {}
        self._loaded: dict = {}
        self.conf: dict = {}
        self.apps: List['AppBase'] = []
        self.background_apps: List['BackgroundAppBase'] = []
        self.mydeck: 'MyDeck'
        self.mydeck = mydeck
        self.key_count = mydeck.key_count
        self._file = file

    def save_config(self):
        shutil.copy(self._file, self._file + '.backup')

        with open(self._file, 'w') as f:
            try:
                yaml.safe_dump(self._config_content_origin, f)
                f.close()
            except Exception as e:
                shutil.move(self._file + '.backup', self._file)
                logging.critical("Error in load: %s", e)
                logging.debug(traceback.format_exc())

    def reflect_config(self, force: bool = False):
        """Read configuration file and reset applications and parse content of the configuration file and run apps"""
        loaded = self.load(force)
        if loaded is not None:
            try:
                self.reset_apps()
                self.parse(loaded)
                self.mydeck.threading_apps(self.apps, self.background_apps)
                self.mydeck.key_touchscreen_setup()
            except Exception as e:
                logging.critical("Error in reflect_config: %s", e)
                logging.debug(traceback.format_exc())
                return None

    def load(self, force: bool = False):
        """Load the configuration file, If the file is newer than read before, return the content of the configuration file. Or return None."""
        statinfo = os.stat(self._file)
        if force or self._file_mtime < statinfo.st_mtime:
            self._file_mtime = statinfo.st_mtime
            with open(self._file) as f:
                try:
                    self._config_content_origin = yaml.safe_load(f)
                    self._config_content = deepcopy(
                        self._config_content_origin)
                    return self._config_content
                except Exception as e:
                    logging.critical("Error in load: %s", e)
                    logging.debug(traceback.format_exc())

        return None

    def delete_touchscreen_config(self, page: str) -> bool:
        app_configs: list[dict] = self._config_content_origin.get("apps", [])
        new_app_configs: list[dict] = []
        modified = False
        for app_config in app_configs:
            if app_config.get("option"):
                pages: list = app_config["option"].get("page", [])
                if page in pages:
                    modified = True
                    pages.remove(page)
                if len(pages) > 0:
                    app_config["option"]["page"] = pages
                    new_app_configs.append(app_config)
                else:
                    new_app_configs.append(app_config)
            else:
                modified = True

        if modified:
            self._config_content_origin["apps"] = new_app_configs

        return modified

    def delete_dial_app_config(self, page: str, data: dict) -> bool:
        dial_str: Optional[str] = data.pop('dial', None)

        if dial_str is None or re.match(r'\D', str(dial_str)) is not None:
            return False
        dial: int = int(dial_str)
        return self.delete_key_dial_app_config("page_dial", page, dial)

    def delete_key_app_config(self, page: str, data: dict) -> bool:
        key_str: Optional[str] = data.pop('key', None)

        if key_str is None or re.match(r'\D', str(key_str)) is not None:
            return False
        key: int = int(key_str)
        modified: bool = self.delete_key_dial_app_config("page_key", page, key)

        page_configs: Optional[dict] = self._config_content_origin.get(
            "page_config")
        if page_configs is None:
            page_configs = self._config_content_origin["page_configs"] = {}
            modified = True
        page_config: Optional[dict] = page_configs.get(page)
        if page_config is None:
            page_config = page_configs[page] = {"keys": {}}
            modified = True
        if page_config.get("keys") is None:
            page_config["keys"] = {}
            modified = True

        if page_config["keys"].get(key):
            page_config["keys"].pop(key)
            modified = True
        elif key == self.mydeck.key_count and page_config["keys"].get(-1):
            page_config["keys"].pop(-1)
            modified = True

        return modified

    def delete_key_dial_app_config(self, conf_key: str, page: str, key: int) -> bool:
        modified = False

        app_configs: Optional[list] = self._config_content_origin.get("apps")
        if app_configs is not None:
            new_app_configs: list = []
            for app_config in app_configs:
                if app_config.get("option") and app_config["option"].get(conf_key):
                    if app_config["option"][conf_key].get(page) == key:
                        app_config["option"][conf_key].pop(page)
                        modified = True
                    if len(app_config["option"][conf_key]) == 0:
                        modified = True
                    else:
                        new_app_configs.append(app_config)
                else:
                    new_app_configs.append(app_config)
            self._config_content_origin["apps"] = new_app_configs

        return modified

    def update_page_config_content(self, page: str, data: dict) -> bool:
        key_str: Optional[str] = data.pop('key', None)
        if key_str is None or re.match(r'\D', str(key_str)) is not None:
            return False
        key: int = int(key_str)
        page_config: Optional[dict] = self._config_content_origin.get(
            'page_config')
        if page_config is None or not isinstance(page_config, dict):
            page_config = self._config_content_origin["page_config"] = {}

        current_page_config: Optional[dict] = page_config.get(page)
        if current_page_config is None or not isinstance(current_page_config, dict):
            current_page_config = page_config[page] = {"keys": {}}
        key_config: Optional[dict] = current_page_config.get('keys')
        if key_config is None and not isinstance(key_config, dict):
            key_config = current_page_config['keys'] = {}

        self._config_content_origin['page_config'][page]['keys'][key] = data
        self.check_and_override_app_config(page, key)

        return True

    def check_and_override_app_config(self, page: str, key: int):
        """Check and override app configuration"""
        app_configs: Optional[list] = self._config_content_origin.get("apps")
        if app_configs is not None:
            new_app_configs: list = []
            for config in app_configs:
                if config.get("option") and config["option"].get("page_key"):
                    if config["option"]["page_key"].get(page) == key:
                        config["option"]["page_key"].pop(page)
                    if len(config["option"]["page_key"]) != 0:
                        new_app_configs.append(config)
                else:
                    new_app_configs.append(config)
            self._config_content_origin["apps"] = new_app_configs

    def update_game_config(self, data: dict):
        if not self._config_content_origin.get("games") or self._config_content_origin["games"] != data:
            self._config_content_origin["games"] = data
            return True

        return False

    def update_app_config_content(self, page: str, data: dict) -> bool:
        app_name: Optional[str] = data.pop('app', None)
        if app_name is None:
            return False

        for_touchscreen: bool = data.pop('for_touchscreen', False)
        for_dial: bool = data.pop('for_dial', False)

        app_data: dict = {
            "app": app_name,
            "option": {}
        }
        for config_key in data["config"].keys():
            if config_key != "page_key" and config_key != "page":
                app_data['option'][config_key] = data["config"][config_key]

        if for_touchscreen:
            return self.unify_touchscreen_app_config(page, app_data)
        elif for_dial:
            dial_str: Optional[str] = data.pop('dial', None)
            if dial_str is None or re.match(r'\D', str(dial_str)) is not None:
                return False

            dial: int = int(dial_str)
            return self.unify_dial_app_config(page, dial, app_data)
        else:
            key_str: Optional[str] = data.pop('key', None)
            if key_str is None or re.match(r'\D', str(key_str)) is not None:
                return False

            key: int = int(key_str)
            return self.unify_key_app_config(page, key, app_data)

    def unify_key_app_config(self, page: str, key: int, new_app_config: dict) -> bool:
        modify_status: int = self.unify_app_config(
            "page_key", page, key, new_app_config)

        if modify_status > 0:
            self.check_and_override_page_config(page, key)
            return True

        return False

    def unify_dial_app_config(self, page: str, key: int, new_app_config: dict) -> bool:
        return self.unify_app_config("page_dial", page, key, new_app_config)

    def unify_app_config(self, conf_key: str, page: str, key: int, new_app_config: dict) -> bool:
        MODIFY: int = 1
        ADD: int = 2
        modify_status = ADD

        new_page_key = new_app_config["option"].pop(conf_key, {})

        app_config: Optional[list] = self._config_content_origin.get("apps")
        if app_config is None:
            app_config = []
        self._config_content_origin["apps"] = app_config
        for existing_config in app_config:
            # if same app config exists
            if existing_config["app"] == new_app_config["app"]:
                origin_page_key = existing_config["option"].pop(conf_key, {})
                # if option exists except page_key is same
                if existing_config["option"] == new_app_config["option"]:
                    new_app_config["option"][conf_key] = new_page_key
                    # same setting and same key
                    if origin_page_key.get(page) and origin_page_key[page] == key:
                        # same setting and same key, do nothing
                        logging.debug(
                            "### 1. Same setting and same key, do nothing")
                        return False
                    else:
                        existing_config["option"][conf_key] = origin_page_key
                        # same setting and different page and key, add new_app_config
                        if existing_config["option"][conf_key].get(page):
                            existing_config["option"][conf_key][page] = key
                            modify_status = MODIFY
                            logging.debug(
                                "### 2. Same setting and different page and key, add new_app_config")
                        else:
                            existing_config["option"][conf_key][page] = key
                            modify_status = MODIFY
                            logging.debug(
                                "### 3. Same config, add different page key")

                elif origin_page_key.get(page) and origin_page_key[page] == key:
                    # same app and different config and same key
                    del origin_page_key[page]
                    logging.debug(
                        "### 4. Different config and same key, remove existing config")

                existing_config["option"][conf_key] = origin_page_key
            elif existing_config.get("option") is not None and existing_config["option"].get(conf_key) is not None:
                # different app already exists on the key in the page
                if existing_config["option"][conf_key].get(page) == key:
                    # remove page from page_key
                    existing_config["option"][conf_key].pop(page, None)
                    if len(existing_config["option"][conf_key]) == 0:
                        # if page_key is empty, remove the app and add new app at last
                        app_config.remove(existing_config)
                        logging.debug(
                            "### 5. If page_key is empty, remove the app and add new app at last")

            if modify_status == MODIFY:
                break

        app_config[:] = list(filter(lambda c: c.get("option") and c["option"].get(
            conf_key) and len(c['option'][conf_key].keys()) > 0, app_config))

        if modify_status == ADD:
            new_app_config["option"][conf_key] = {page: key}
            app_config.append(new_app_config)

        return modify_status > 0

    def unify_touchscreen_app_config(self, page: str, new_app_config: dict) -> bool:
        MODIFY: int = 1
        ADD: int = 2
        modify_status = ADD  # 1: modify, 2: add new app

        app_config: Optional[list] = self._config_content_origin.get("apps")
        if app_config is None:
            app_config = []
        self._config_content_origin["apps"] = app_config
        for existing_config in app_config:
            # if same app config exists
            if existing_config["app"] == new_app_config["app"]:
                origin_page: Optional[list] = existing_config["option"].pop(
                    "page", None)
                if origin_page is not None:
                    if page in origin_page:
                        # same setting and same page, do nothing
                        logging.debug(
                            "a. same setting and same page, do nothing")
                        return False
                    else:
                        logging.debug("b. append exsiting config")
                        origin_page.append(page)
                        modify_status = MODIFY
                else:
                    # not touchscreen app
                    pass

                existing_config["option"]["page"] = origin_page
            elif existing_config.get("option") is not None:
                if existing_config["option"].get("page") is not None:
                    # different app already exists in the page
                    if page in existing_config["option"]["page"]:
                        existing_config["option"]["page"].remove(page)
                        logging.debug("c. remove page from existing config")

            if modify_status == MODIFY:
                break

        app_config[:] = list(filter(lambda c: c.get("option") and c["option"].get(
            "page") and len(c['option']["page"]) > 0, app_config))

        if modify_status == ADD:
            new_app_config["option"]["page"] = [page]
            app_config.append(new_app_config)

        return modify_status > 0

    def check_and_override_page_config(self, page: str, key: int):
        """Check and override key configuration"""
        page_config: Optional[dict] = self._config_content_origin.get(
            "page_config")
        if page_config is not None and page_config.get(page) is not None and page_config[page].get("keys") is not None:
            # remove the key from the page
            if page_config[page]["keys"].get(key) is not None:
                page_config[page]["keys"].pop(key)
            if key == self.mydeck.key_count and page_config[page]["keys"].get(-1):
                page_config[page]["keys"].pop(-1)

    def parse(self, conf: dict):
        """Parse configuration file."""
        if self.mydeck is not None:
            page_config: Optional[dict[str, dict]] = conf.get('page_config')
            if page_config is not None:
                for page in page_config.keys():
                    key_config = page_config[page].get('keys')
                    if key_config is not None:
                        self.mydeck.set_key_config(
                            self.modify_key_config_with_page(page, key_config))
                    touch_config = page_config[page].get('touch')
                    if touch_config is not None:
                        self.mydeck.set_touchscreen_config(
                            self.modify_touchscreen_config_with_page(page, touch_config))
                    dial_config = page_config[page].get('dials')
                    if dial_config is not None:
                        self.mydeck.set_dial_config(
                            self.modify_dial_config_with_page(page, dial_config))
                    command_config = page_config[page].get('commands')
                    if command_config is not None:
                        self.mydeck.set_command_config(page, command_config)

        apps_conf = conf.get('apps')
        if apps_conf is not None:
            self.parse_apps(apps_conf)
        games_conf = conf.get('games')
        if games_conf is not None:
            self.parse_games(games_conf)

    def parse_games(self, games_conf: list):
        """Apply the configuration of games"""

        key_config = self.mydeck.key_config()
        for page_name in list(key_config.keys()):
            if page_name.startswith("@GAME"):
                del key_config[page_name]

        for game_conf in games_conf:
            self.parse_game(game_conf["game"], game_conf)

    def parse_game(self, game: str, game_conf: Optional[dict] = None):
        """Apply the configuration of a game.

        `game` may be a short name (``RandomNumber`` → ``mydeck.game_random_number.GameRandomNumber``)
        or a fully-qualified path (``my_pkg.games.MyGame``) for third-party plugins.
        """
        if game_conf is None:
            game_conf = {}
        module_path, class_name = self._resolve_app_target(game, prefix='Game')
        m = self._load_module(module_path)
        getattr(m, class_name)(self.mydeck, game_conf)

    def reset_apps(self):
        """Reset apps"""
        for app in self.apps:
            app._stop = True
            if app.use_trigger:
                app.trigger.set()

        # destloy apps
        for app in self.apps:
            del app
        for app in self.background_apps:
            del app

        self.apps = []
        self.background_apps = []
        self.hook_apps: Dict[str, List['HookAppBase']] = {}
        self.is_background_thread_started = False

    def parse_apps(self, apps_conf: List[dict]):
        """Apply the configuration of apss"""
        if apps_conf is None:
            return False

        for app_conf in apps_conf:
            self.parse_app(app_conf)

        self.parse_app({"app": "Trigger"})

        # Auto-register AppTotp so @TOTP_ACCOUNTS page always has a key_config,
        # even when the user hasn't explicitly added a Totp entry to apps:.
        # Without this, assigning change_page: @TOTP_ACCOUNTS from the Web UI
        # would lead to an empty page when the button is pressed.
        has_totp = any(c.get("app") == "Totp" for c in apps_conf)
        if not has_totp:
            self.parse_app({"app": "Totp", "option": {}})

    def append_hook_app(self, app: 'HookAppBase'):
        """Append hook apps"""
        on = app.on
        on_apps = self.hook_apps.get(on)
        if on_apps is None:
            self.hook_apps[on] = []
        self.hook_apps[on].append(app)

    def parse_app(self, app_conf: dict):
        """Apply the configuration of an aps"""
        if app_conf is None:
            return False

        app = app_conf.get('app')
        if app is not None:
            module_path, class_name = self._resolve_app_target(app, prefix='App')
            m = self._load_module(module_path)
            o = getattr(m, class_name)(self.mydeck, app_conf.get('option'))
            if o.is_background_app:
                self.background_apps.append(o)
                if app_conf['app'] == 'Alert' and self.mydeck is not None:
                    o.set_check_func(self.mydeck._alert_func)
                    self.mydeck.set_alert_key_conf(
                        self.modify_key_config(app_conf['option']["key_config"]))
            elif o.is_hook_app:
                self.append_hook_app(o)
            elif o.is_dial_app():
                self.apps.append(o)
                o.dial_setup()
            else:
                self.apps.append(o)
                o.key_setup()

        return o

    def _resolve_app_target(self, name: str, prefix: str) -> tuple:
        """Resolve an ``app:``/``game:`` value to a (module_path, class_name).

        - If ``name`` contains a dot it is treated as a fully-qualified path:
          ``my_plugin.apps.Weather`` → module ``my_plugin.apps``,
          class ``Weather``. This is how third-party plugin packages are loaded.
        - Otherwise the built-in convention applies:
          ``Clock`` with ``prefix='App'`` →
          module ``mydeck.app_clock``, class ``AppClock``.
        """
        if '.' in name:
            module_path, _, class_name = name.rpartition('.')
            return module_path, class_name
        class_name = prefix + name
        module_name = re.sub('([A-Z])', r'_\1', class_name)[1:].lower()
        return 'mydeck.' + module_name, class_name

    def _load_module(self, module_path: str):
        if self._loaded.get(module_path) is None:
            self._loaded[module_path] = importlib.import_module(module_path)
        return self._loaded[module_path]

    def not_working_apps(self) -> List['AppBase']:
        """Return the list of the apps not working"""
        return list(filter(lambda app: app.use_thread and app.is_in_target_page() and not app.in_working, self.apps))

    def modify_key_config_with_page(self, page: str, conf: dict):
        """Modify key configuration according to conf whose key is page name and value is configuration dict."""

        if self.mydeck._PAGE_CONFIG['keys'].get(page) is None:
            self.mydeck._PAGE_CONFIG['keys'][page] = {}

        self.mydeck._PAGE_CONFIG['keys'][page] = self.modify_key_config(conf)

        return self.mydeck._PAGE_CONFIG['keys']

    def modify_dial_config_with_page(self, page: str, conf: dict):
        """Modify dial configuration according to conf whose key is page name and value is configuration dict."""

        if self.mydeck._PAGE_CONFIG['dials'].get(page) is None:
            self.mydeck._PAGE_CONFIG['dials'][page] = {}

        self.mydeck._PAGE_CONFIG['dials'][page] = conf

        return self.mydeck._PAGE_CONFIG['dials']

    def modify_key_config(self, conf: dict):
        """Modify key configuration with conf whose key is number of key and value is configuration dict."""
        key_count = self.key_count
        new_config = {}
        for _key in conf.keys():
            key = _key
            if _key < 0:
                key = key_count + _key
            new_config[key] = conf[_key]
        return new_config

    def modify_touchscreen_config_with_page(self, page: str, conf: dict):
        """Modify touchscreen configuration according to conf whose key is page name and value is configuration dict."""

        if self.mydeck._PAGE_CONFIG['touch'].get(page) is None:
            self.mydeck._PAGE_CONFIG['touch'][page] = {}

        self.mydeck._PAGE_CONFIG['touch'][page] = conf

        return self.mydeck._PAGE_CONFIG['touch']
