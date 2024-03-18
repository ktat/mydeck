from mydeck import MyDecks
import os
import sys
import requests

#CHECK_URL = 'https://www.rwds.net/xx'
#
#def check_alert():
#    res = requests.get(CHECK_URL)
#    if res.status_code != requests.codes.ok:
#        return True
#    return False


if __name__ == "__main__":
    port: int = 3000  # 3000 is default port, change this if required
    if len(sys.argv) > 1:
        port = int(sys.argv[1])

    mydecks = MyDecks({
        'server_port': port,
        'vdeck_config': "example/config/vdeck.yml",
        'decks': {
            'dummy1': '4key-dummy',
            'dummy2': '6key-dummy',
            'dummy3': '15key-dummy',
        },
        'configs': {
            '6key': {
                'file': "example/config/config2.yml",
            },
            '4key-dummy': {
                'file': "example/config/config-d1.yml",
            },
            '6key-dummy': {
                'file': "example/config/config-d2.yml",
            },
            '15key-dummy': {
                'file': "example/config/config.yml",
#                'alert_func': check_alert,
            },
        }

    })

    mydecks.start_decks(True)

    os._exit(0)
