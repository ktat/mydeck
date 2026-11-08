import logging
import random
import re
import traceback
import yaml
from typing import Optional
from StreamDeck.Devices.StreamDeck import StreamDeck
from StreamDeck.Devices.StreamDeckPlus import StreamDeckPlus


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
        self._touchscreen_size: tuple[int, int] = (0, 0)

        real_deck: StreamDeck = opt.get("real_deck")
        if real_deck is not None:
            self._id = id
            self._key_count = real_deck.KEY_COUNT
            self._columns = real_deck.KEY_COLS
            logging.info(real_deck.get_serial_number())
            self._serial_number = real_deck.get_serial_number()
        else:
            key_count = opt.get('key_count')
            if key_count is None or re.match(r'\D', str(key_count)) is not None:
                raise ExceptionInvalidVirtualDeckConfig()
            self._key_count = key_count
            columns = opt.get('columns')
            if columns is None or re.match(r'\D', str(columns)) is not None:
                raise ExceptionInvalidVirtualDeckConfig()
            self._columns = columns
            serial_number = opt.get('serial_number')
            if serial_number is None:
                raise ExceptionInvalidVirtualDeckConfig()
            self._serial_number = str(serial_number)
            has_touchscreen: Optional[bool] = opt.get('has_touchscreen')
            if has_touchscreen is not None and has_touchscreen:
                self._has_touch_interface = has_touchscreen
                size: Optional[tuple[int, int]] = opt.get("touchscreen_size")
                if size is not None:
                    self._touchscreen_size = (size[0], size[1])
                else:
                    plus = StreamDeckPlus
                    self._touchscreen_size = (
                        plus.TOUCHSCREEN_PIXEL_WIDTH, plus.TOUCHSCREEN_PIXEL_HEIGHT
                    )

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
        if not isinstance(i, dict):
            return {}
        return i

    def output_option(self) -> dict:
        o = self.opt.get('output')
        if not isinstance(o, dict):
            return {}
        return o

    def dials(self) -> int:
        return self._dials

    def has_touchscreen(self) -> bool:
        return self._has_touch_interface

    def touchscreen_size(self) -> tuple[int, int]:
        return self._touchscreen_size

    def config(self) -> dict:
        return {
            'id': self.id(),
            'key_count': self.key_count(),
            'columns': self.columns(),
            'serial_number': self.serial_number(),
            "dial_count": self.dials(),
            "has_touchscreen": self.has_touchscreen(),
            "touchscreen_size": self.touchscreen_size(),
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
          touchscreen_size: [400, 100]
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
