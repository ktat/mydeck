"""Base module to handle STREAM DECK devices"""

import logging
import os
import os.path
import signal
import sys
import threading
from typing import Any, Callable, Dict, List, NoReturn, Optional, TYPE_CHECKING

from PIL import Image

DEFAULT_PORT: int = 3000
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

if TYPE_CHECKING:
    from .my_decks_app_base import App, AppBase, BackgroundAppBase, HookAppBase


class ExceptionInvalidMyDecksConfig(Exception):
    pass


class MyDecks:
    """The class to manage several STREAM DECK like devices.

    This class manages insteaces of MyDeck class.
    """
    mydecks: Dict[str, 'MyDeck'] = {}

    def __init__(self, config: dict):
        """
        config dict takes the following keys:
        - log_level
        - server_port
        - decks and configs or config

        If you have only one STREAM DECK device, use config. If you have several devices, use decks and configs.
        decks is the following structure.
        {
           name1: 'serial number of deck1',
           name2: 'serial number of deck2',
        }

        configs is the following structure.
        {
           name1: {
             alert_func: function_name_for_alert,
             file: '/path/to/config1.yml'
           },
           name2: {
             file: '/path/to/config2.yml'
           },
        }

        config is the following structure.
        {
           alert_func: function_name_for_alert,
           file: '/path/to/config1.yml'
        }

        """
        self.vdeck_config: Any[None, str] = config.get('vdeck_config')
        if self.vdeck_config is not None and type(self.vdeck_config) is not str:
            raise ExceptionInvalidMyDecksConfig()

        self._one_deck_only: bool = False
        self.config: Optional[dict]
        self.decks: Optional[dict] = config.get('decks')
        self.server_port: int = config.get('server_port') or DEFAULT_PORT
        self.configs: Optional[dict] = config.get('configs')
        if self.decks is None and self.configs is None:
            self.config = config.get('config')
            self._one_deck_only = True
        log_level: Optional[str] = config.get('log_level')
        if log_level is not None:
            logging.basicConfig(level=log_level)
        else:
            logging.basicConfig(level=logging.INFO)

    def start_decks(self, no_real_device: bool = False) -> NoReturn:
        """Start and display images to buttons according to configuration."""
        from .my_decks_manager import MyDecksManager
        known_serials: dict = {}
        if self.decks is not None:
            for sn in self.decks.keys():
                known_serials[sn] = {'key_count': 15, 'columns': 5}
        manager = MyDecksManager(
            self.vdeck_config, no_real_device,
            known_serials=known_serials)
        streamdecks = manager.devices
        logging.info("Found {} Stream Deck(s).\n".format(len(streamdecks)))

        for index, deck in enumerate(streamdecks):
            # if not deck.is_visual():
            # continue

            serial_number: str = deck.get_serial_number()
            if self._one_deck_only:
                if self.config is not None:
                    alert_func: Optional[Callable] = self.config.get(
                        'alert_func')
                    config_file: Optional[str] = self.config.get('file')
                    mydeck = MyDeck({
                        'mydecks': self,
                        'myname': 'mydeck',
                        "deck": deck,
                        'alert_func': alert_func,
                        'config': config_file
                    }, self.server_port)
                    self.mydecks[serial_number] = mydeck
                    mydeck.init_deck()
                    break
                else:
                    logging.warning(
                        "config{file: '/path/to/config_file'} is required")
                    raise ExceptionNoConfig()
            elif self.decks is not None:
                sn_alias = self.decks.get(serial_number)
                configs = self.configs
                if sn_alias is not None and configs is not None:
                    sn_config = configs.get(sn_alias)
                    if sn_config is not None:
                        mydeck = MyDeck({
                            'mydecks': self,
                            'myname': sn_alias,
                            "deck": deck,
                            'alert_func': sn_config.get('alert_func'),
                            'config': sn_config.get('file'),
                        }, self.server_port)
                        self.mydecks[sn_alias] = mydeck
                        mydeck.init_deck()
                else:
                    logging.warning(
                        "config is not found for device: {}".format(serial_number))
            else:
                logging.warning("config or (decks and configs) is required")
                raise ExceptionNoConfig()

        # Wire device resilience: each VirtualDeck gets a lifecycle listener
        # that dispatches to the owning MyDeck. A single DeviceSupervisor
        # thread re-enumerates every 3s to detect reconnects.
        from .device_resilience import DeviceSupervisor

        def _dispatch(vdeck, event):
            mydeck = None
            for md in self.mydecks.values():
                if md.deck is vdeck:
                    mydeck = md
                    break
            if mydeck is None:
                return
            if event == 'disconnected':
                mydeck.on_disconnect()
            elif event == 'reconnected':
                mydeck.on_reconnect()

        for md in self.mydecks.values():
            md.deck.set_lifecycle_listener(_dispatch)

        self._device_supervisor = DeviceSupervisor(
            [md.deck for md in self.mydecks.values()])
        self._device_supervisor.start()

        def stop_decks(signal, frame):
            from . import DeckOutputWebServer

            if getattr(self, '_device_supervisor', None) is not None:
                self._device_supervisor.stop()

            DeckOutputWebServer.shutdown()
            for deck in self.mydecks.values():
                deck.stop_working_apps()
                deck._exit = True
                deck.deck.reset()
                deck.deck.close()

            logging.info("mydeck is about to stop. wait a moment.")

            # sys.exit in a signal handler: raises SystemExit on the main
            # thread so finally/atexit hooks (daemon module pidfile cleanup,
            # logging flush) run. Daemon threads get killed by the interpreter
            # on the way out.
            sys.exit()

        signal.signal(signal.SIGINT, stop_decks)
        signal.signal(signal.SIGTERM, stop_decks)
        signal.signal(signal.SIGHUP, stop_decks)

        # Wait until all application threads have terminated (for this example,
        # this is when all deck handles are closed).
        # Skip daemon threads: they should not be joined (they never terminate on their own)
        # and will be killed automatically when the process exits.
        for t in threading.enumerate():
            if t != threading.current_thread() and not t.daemon:
                try:
                    t.join()
                except RuntimeError as e:
                    logging.critical("Error in start_decks {}".format(e))

        logging.info("start_decks end!")
        # os._exit (not sys.exit): by this point all non-daemon worker threads
        # have been joined, but daemon threads (DeviceSupervisor, HID readers)
        # are still alive. os._exit terminates the whole process without
        # waiting for them — the alternative would leave mydeck running
        # silently when the user pressed the Exit key on the deck.
        os._exit(0)

    def list_mydecks(self) -> List['MyDeck']:
        """return list of MyDeck instances"""
        return list(self.mydecks.values())

    def list_other_mydecks(self, mydeck: 'MyDeck') -> List['MyDeck']:
        """return list of MyDeck instances"""
        myname = mydeck.myname
        return list(filter(lambda mydeck: mydeck.myname != myname, self.mydecks.values()))

    def mydeck(self, name: str) -> Optional['MyDeck']:
        """Pass name of the device and return the correspond MyDeck instance."""
        mydeck = self.mydecks.get(name)
        if mydeck is not None:
            return mydeck
        else:
            logging.warning('mydeck is None: {}'.format(name))
        return None


class ExceptionNoConfig(Exception):
    """Exception when no configuration is given"""
    pass


class ExceptionNoDeckGiven(Exception):
    """Exception when no deck is given"""
    pass


class ImageOrFile:
    """Class to represent Image instannce or a file path."""
    is_file = False

    def __init__(self, file_or_image: Any):
        """Constructor. Pass Image.Image instance or file path."""
        self.image: Image.Image
        self.file: str = ''

        if not isinstance(file_or_image, (str, Image.Image)):
            logging.warning(file_or_image)
            raise ExceptionWrongTypeGiven()

        if isinstance(file_or_image, str):
            self.file = file_or_image
            self.is_file = True
        elif isinstance(file_or_image, Image.Image):
            self.image = file_or_image


class ExceptionWrongTypeGiven(Exception):
    """Exception when wrong type is given to ImageOrFile constructor."""
    pass


# Re-export so that existing import paths continue to work:
#   from mydeck.my_decks import MyDeck, Config
#   from mydeck import MyDeck, Config (via __init__.py's `from .my_decks import *`)
# Imports placed at end so module-level ROOT_DIR / ImageOrFile are available
# to my_deck_image (which lazy-imports ROOT_DIR and ImageOrFile from this module).
from .my_deck import MyDeck  # noqa: E402
from .config import Config  # noqa: E402
