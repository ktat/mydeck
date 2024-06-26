import time
import random
import threading
import logging
from mydeck import MyDeck, GameAppBase, ROOT_DIR


class GameRandomNumber(GameAppBase):
    require_key_count: int = 6
    require_columns: int = 2
    mode_explanation = "n <= 10: show n numbers."

    def __init__(self, mydeck: MyDeck, conf: dict = {}):
        super().__init__(mydeck)

        self.data: dict = {}

        if mydeck.key_count == 6:
            mydeck.add_game_key_conf([
                {
                    "command": "RandomNumber",
                    "image": ROOT_DIR+"/Assets/3.png",
                    "label": "Random3",
                    "mode": 3,
                },
            ])
        else:
            modes: list = conf.get("modes", [4, 7, 10])
            game_keys: list = []
            for mode in modes:
                if mode > 10:
                    continue
                game_keys.append({
                    "command": "RandomNumber",
                    "image": "%s/Assets/%d.png" % (ROOT_DIR, mode),
                    "label": "Random"+str(mode),
                    "mode": mode,
                })

            mydeck.add_game_key_conf(game_keys)

        mydeck.add_game_command(
            "RandomNumber", lambda conf: self.key_setup(conf.get("mode")))

    def key_setup(self, num):
        mydeck = self.mydeck
        deck = mydeck.deck
        deck.reset_keys()
        mydeck.set_game_status_on()
        mydeck.set_current_page_without_setup("~GAME_RANDOM_NUMBER")
        self.data["mode"] = num

        # Set initial screen brightness to 30%.
        deck.set_brightness(30)

        self.data["correct"] = []

        t = threading.Thread(target=lambda: self.prepare_number(num), args=())
        t.start()

        # Set initial key images.
        deck.set_key_callback(
            lambda deck, key, state: self.key_change_callback(key, state))

        if mydeck.key_count > 6:
            mydeck.set_game_key(-4, {
                "name": "reset",
                "label": "RESET",
                "image": ROOT_DIR+"/Assets/cat.png",
            })

        mydeck.set_game_key(-3, {
            "name": "restart",
            "label": "RESTART",
            "image": ROOT_DIR+"/Assets/restart.png",
        })

        mydeck.set_game_key(-1, {
            "name": "exit",
            "image": ROOT_DIR+"/Assets/back.png",
            "label": "exit Game"
        })

        self.data["answer"] = []

    def prepare_number(self, num):
        mydeck = self.mydeck
        cnt = 0
        r = 0
        used = {}
        prev = 0

        number = {
            "image": "",  # set number image after
            "name": "numberPrepare",
            "click": False,
            "command": "RandomNumber"
        }
        empty = {
            "image": ROOT_DIR+"/Assets/cat.png",
            "name": "empty"
        }

        max = 10
        if mydeck.key_count == 6:
            max = 3

        for key in range(0, max):
            if not mydeck.in_game_status():
                return
            mydeck.set_game_key(key, empty)

        while True:
            if not mydeck.in_game_status():
                return
            time.sleep(0.5)
            cnt += 1
            if cnt > num:
                break
            r = random.randint(0, max - 1)
            while used.get(r) is not None and used.get(r) is True:
                r = random.randint(0, max - 1)
            used[r] = True
            self.data["correct"].append(str(r))
            mydeck.set_game_key(prev, empty)
            number["image"] = ROOT_DIR+"/Assets/" + str(r) + ".png"
            number["value"] = str(r)
            mydeck.set_game_key(r, number)
            prev = r
        mydeck.set_key(r, empty)

        i = 0
        for key in range(0, max):
            if not mydeck.in_game_status():
                return
            mydeck.set_game_key(key, {
                "image": ROOT_DIR+"/Assets/" + str(i) + ".png",
                "name": "number",
                "click": True,
                "value": str(key),
            })
            i = i+1

    def key_change_callback(self, key, state):
        mydeck = self.mydeck
        deck = mydeck.deck

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
                            mydeck.set_key(-2, {
                                "label": "OK",
                                "image": ROOT_DIR+"/Assets/good.png",
                            })
                        else:
                            mydeck.set_key(-2, {
                                "label": "NG",
                                "image": ROOT_DIR+"/Assets/bad.png",
                            })
                            self.data["answer"] = []
