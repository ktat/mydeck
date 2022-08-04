import time
import random

class GameRandomNumber:
    data = {}
    def __init__ (self, mydeck, start_key_num=0):
        self.mydeck = mydeck
        mydeck.add_game_key_conf({
            0 + start_key_num: {
                "command": "RandomNumber",
                "image": "./src/Assets/5.png",
                "label": "Random5",
                "mode": 5,
            },
            1 + start_key_num: {
                "command": "RandomNumber",
                "image": "./src/Assets/7.png",
                "label": "Random7",
                "mode": 7,
            },
            2 + start_key_num: {
                "command": "RandomNumber",
                "image": "./src/Assets/10.png",
                "label": "Random10",
                "mode": 10,
            }
        })
        mydeck.add_game_command("RandomNumber", lambda conf: self.key_setup(conf.get("mode")))
        
    def key_setup(self, num):
        mydeck = self.mydeck
        deck = mydeck.deck
        deck.reset()
        mydeck.set_current_page_without_setup("~GAME_RANDOM_NUMBER")
        self.data["mode"] = num
        print("Opened '{}' device (serial number: '{}', fw: '{}')".format(
            deck.deck_type(), deck.get_serial_number(), deck.get_firmware_version()
        ))

        # Set initial screen brightness to 30%.
        deck.set_brightness(30)

        number = {
            "image": "", # set number image after
            "name": "number",
            "click": False,
        }
        empty = {
            "image": "./src/Assets/cat.png",
            "name": "empty"
        }

        prev = 0

        mydeck.set_game_status(1)

        for key in range(0, 10):
            mydeck.set_game_key(key, empty)

        # Set initial key images.
        deck.set_key_callback(lambda deck, key, state: self.key_change_callback(key, state))

        cnt = 0
        r = 0
        used = {}
        self.data["correct"] = [];
        while True:
            if not mydeck.in_game_status():
                break

            time.sleep(0.5)
            cnt += 1
            if cnt > num:
                mydeck.set_game_status(0)
                break

            r = random.randint(0,9)
            while used.get(r) is not None and used.get(r) is True:
                r = random.randint(0,9)
            used[r] = True
            self.data["correct"].append(str(r))
            mydeck.set_game_key(prev, empty)
            number["image"] = "./src/Assets/" + str(r) + ".png"
            number["value"] = str(r)
            mydeck.set_game_key(r, number)
            prev = r
        mydeck.set_key(r, empty)

        i = 0
        for key in range(0, 10):
            mydeck.set_game_key(key, {
                "image": "./src/Assets/" + str(i) + ".png",
                "name": "number",
                "click": True,
                "value": str(key),
            })
            i = i+1

        mydeck.set_game_key(10, {
            "name": "reset",
            "label": "RESET",
            "image": "./src/Assets/cat.png",
        })

        mydeck.set_game_key(11, {
            "name": "restart",
            "label": "RESTART",
            "image": "./src/Assets/restart.png",
        })

        mydeck.set_game_key(14, {
            "name": "exit",
            "image": "./src/Assets/back.png",
            "label": "exit Game"
        })

        self.data["answer"] = []

    def key_change_callback(self, key, state):
        mydeck = self.mydeck
        deck = mydeck.deck
        # Print new key state
        print("Deck {} Key {} = {}".format(deck.id(), key, state), flush=True)

        conf = mydeck._GAME_KEY_CONFIG.get(key)
        if state:
            if conf:
                if conf["name"] == "exit":
                    mydeck.exit_game()
                if conf["name"] == "reset":
                    mydeck._GAME_KEY_CONFIG["answer"] = []
                if conf["name"] == "restart":
                    self.key_setup(self.data["mode"])
                if conf["name"] == "number":
                    if conf["click"]:
                        self.data["answer"].append(conf["value"])
                    if len(self.data["answer"]) == self.data["mode"]:
                        if "-".join(self.data["answer"]) == "-".join(self.data["correct"]):
                            mydeck.set_key(13, {
                                "label": "OK",
                                "image": "./src/Assets/good.png",
                            })
                        else:
                            mydeck.set_key(13, {
                                "label": "NG",
                                "image": "./src/Assets/bad.png",
                            })
                            self.data["answer"] = [];
