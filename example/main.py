from mystreamdeck.configure import MyStreamDeck
from mystreamdeck.alert import MyStreamDeckAlert
from mystreamdeck.random_number import MyStreamDeckGameRandomNumber
from mystreamdeck.memory import MyStreamDeckGameMemory
from mystreamdeck.tictacktoe import MyStreamDeckGameTickTacToe
from mystreamdeck.clock import MyStreamDeckClock
from mystreamdeck.stopwatch import MyStreamDeckStopWatch
from mystreamdeck.calendar import MyStreamDeckCalendar
from mystreamdeck.whacamole import MyStreamDeckGameWhacAMole

import os
import sys
import time
import psutil
import requests
import json
import threading

from StreamDeck.DeviceManager import DeviceManager

ALERT_INTERVAL = 300
CHECK_URL = 'https://www.rwds.net/'
_ALERT_KEY_CONFIG = {
    "command": ["google-chrome", '--profile-directory=Profile 1', 'https://www.rwds.net/'],
    "image": "./src/Assets/cat.png",
    "label": "ALERT",
    "change_page": "@previous"
}

ALERT_KEY_CONFIG = {
    0: _ALERT_KEY_CONFIG,
    1: _ALERT_KEY_CONFIG,
    5: _ALERT_KEY_CONFIG,
    7: _ALERT_KEY_CONFIG,
    10: _ALERT_KEY_CONFIG,
    13: _ALERT_KEY_CONFIG,
    14: _ALERT_KEY_CONFIG,
    9: _ALERT_KEY_CONFIG,
    4: _ALERT_KEY_CONFIG,
}

def check_alert():
    res = requests.get(CHECK_URL)
    if res.status_code != requests.codes.ok:
        return True
    return False


if __name__ == "__main__":
    mydeck = MyStreamDeck({'config': "./example/config/config.yml"})
    mydeck = MyStreamDeck(
        {
            'config': "./example/config/config.yml",
            "apps": [
                lambda mydeck: MyStreamDeckClock(mydeck, {'@HOME': 5, '@JOB': 12}, {}),
                lambda mydeck: MyStreamDeckStopWatch(mydeck, {'@HOME': 6}),
                lambda mydeck: MyStreamDeckCalendar(mydeck, {'@HOME': 7}),
                lambda mydeck: MyStreamDeckAlert(mydeck, check_alert, ALERT_INTERVAL, ALERT_KEY_CONFIG)
            ]
        }
    )
    MyStreamDeckGameRandomNumber(mydeck)
    MyStreamDeckGameMemory(mydeck, "", 3)
    MyStreamDeckGameTickTacToe(mydeck, "", 7)
    MyStreamDeckGameWhacAMole(mydeck, "", 8)

    mydeck.deck_start()

    print("program end")    
    os.exit()
