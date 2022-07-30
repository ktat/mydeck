from mystreamdeck import *

import os
import sys
import time
import psutil
import requests
import json
import threading

from StreamDeck.DeviceManager import DeviceManager

CHECK_URL = 'https://www.rwds.net/xx'

def check_alert():
    res = requests.get(CHECK_URL)
    if res.status_code != requests.codes.ok:
        return True
    return False


if __name__ == "__main__":
    mydeck = MyStreamDeck({
        'config': "./example/config/config.yml",
        'alert_func': check_alert,
    })

    mydeck.deck_start()

    os.exit()
