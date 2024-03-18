from mydeck import *

import os
import requests

from StreamDeck.DeviceManager import DeviceManager

CHECK_URL = 'https://www.rwds.net/xx'

def check_alert():
    res = requests.get(CHECK_URL)
    if res.status_code != requests.codes.ok:
        return True
    return False


if __name__ == "__main__":
    mydecks = MyDecks({
        "server_port": 3000, # 3000 is default port, change this if required
        'config': {
            'file': "./example/config/config.yml",
            'alert_func': check_alert,
        }
    })

    mydecks.start_decks()

    os.exit()
