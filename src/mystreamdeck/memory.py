import time
import random

class MyStreamDeckGameMemory:
    def __init__ (self, mydeck, command_prefix="", start_key_num=0):
        self.mydeck = mydeck
        mydeck.add_game_key_conf({
            0 + start_key_num: {
                "command": "GameMemory",
                "image": "./src/Assets/memory-game.png",
                "label": "Memory 8",
                "mode": 8,
            },
            1 + start_key_num: {
                "command": "GameMemory",
                "image": "./src/Assets/memory-game.png",
                "label": "Memory 4",
                "mode": 4,
            },
            2 + start_key_num: {
                "command": "GameMemory",
                "image": "./src/Assets/memory-game.png",
                "label": "Memory 0",
                "mode": 0,
            },
        })
        mydeck.add_game_command(command_prefix + "GameMemory", lambda conf: self.key_setup(conf["mode"]))

    def key_setup(self, wait_time):
        mydeck = self.mydeck
        mydeck._GAME_KEY_CONFIG["num_of_try"] = 0
        mydeck._GAME_KEY_CONFIG["wait_time"] = wait_time
        mydeck._GAME_KEY_CONFIG["opened"] = None
        deck = mydeck.deck
        deck.reset()
        mydeck.set_current_page_without_setup("~GAME_MEMORY")

        # Set initial screen brightness to 30%.
        deck.set_brightness(30)

        empty = {
            "image": "./src/Assets/cat.png",
            "name": "empty"
        }

        mydeck.set_game_status(1)

        for key in range(0, 12):
            mydeck.set_game_key(key, empty)

        # Set initial key images.
        deck.set_key_callback(lambda deck, key, state: self.key_change_callback(key, state))

        pairs = {}
        used = {}
        pos = {}
        for i in range(1, 7):
            n = random.randint(0, 11)
            while used.get(n):
                n = random.randint(0, 11)

            used[n] = True

            n2 = random.randint(0, 11)
            while used.get(n2):
                n2 = random.randint(0, 11)

            used[n2] = True
            pairs[i] = [n, n2]
            pos[n] = pos[n2] = i
            print(n)
            print(n2)

        for i in range(0, 12):
            n = pos[i]
            img = "./src/Assets/" + str(n) + ".png"
            if wait_time == 0:
                img = "./src/Assets/cat.png"
            mydeck.set_game_key(i, {
                "image": img,
                "name": "number",
                "click": True,
            })

        if wait_time > 0:
            for i in range(0, wait_time + 1):
                mydeck.set_game_key(13, {
                    "image": "./src/Assets/" + str(wait_time - i) + ".png",
                    "name": "num_of_wait",
                    "click": True,
                })
                if i < wait_time:
                    time.sleep(1)

        for i in range(0, 12):
            n = pos[i]
            mydeck.set_game_key(i, {
                "image": "./src/Assets/cat.png",
                "name": "number",
                "value": n,
                "clicked": False,
            })

        mydeck.set_game_key(12, {
            "name": "restart",
            "label": "RESTART",
            "image": "./src/Assets/restart.png",
        })

        mydeck.set_game_key(14, {
            "name": "exit",
            "image": "./src/Assets/back.png",
            "label": "exit Game"
        })

    def key_change_callback(self, key, state):
        mydeck = self.mydeck
        deck = mydeck.deck
        # Print new key state
        print("Deck {} Key {} = {}".format(deck.id(), key, state), flush=True)

        conf = mydeck._GAME_KEY_CONFIG.get(key)
        wait_time = mydeck._GAME_KEY_CONFIG["wait_time"]
        if state:
            if conf:
                print(conf)
                if conf["name"] == "exit":
                    mydeck.exit_game()
                elif conf["name"] == "restart":
                    self.key_setup(wait_time)
                elif conf["name"] == "number":
                    if conf["clicked"] == False and mydeck._GAME_KEY_CONFIG["opened"] != key:
                        self.open_and_check(key, conf)
                    num_of_try = mydeck._GAME_KEY_CONFIG["num_of_try"]
                    clicked = self.clicked()
                    evaluate = self.evaluate(clicked, num_of_try, wait_time)
                    label = ''
                    if clicked == 12:
                        label = self.evaluate2label(evaluate)
                    else:
                        label = str(num_of_try)

                    mydeck.set_key(13, {
                        "name": "num_of_try",
                        "image": "./src/Assets/" + evaluate + ".png",
                        "label": label
                    })

    def clicked(self):
        clicked = 0
        mydeck = self.mydeck
        for i in range(0, 12):
            if mydeck._GAME_KEY_CONFIG[i]["clicked"]:
                clicked += 1
        return clicked

    def evaluate(self, clicked, num, wait_time):
        mydeck = self.mydeck
        keisu = 1
        if wait_time == 0:
            keisu = 0.8

        evaluate = "normal"

        if num == 0:
            return evaluate

        rate = clicked / (num * 2)
        if rate >= 1 * keisu:
            evaluate = "laugh"
        elif rate > 0.67 * keisu:
            evaluate = "happy"
        elif rate > 0.55 * keisu:
            evaluate = "normal"
        elif rate > 0.46 * keisu:
            evaluate = "unhappy"
        else:
            evaluate = "sad"

        return evaluate

    def evaluate2label(self, evaluate):
        l = {
            "laugh": "Excelent!",
            "happy": "Good!",
            "normal": "Good job.",
            "unhappy": "Bad!",
            "sad": "Disappointed!",

        }
        return l[evaluate]

    def open_and_check(self, key, conf):
        mydeck = self.mydeck
        n = {
            "image": "./src/Assets/" + str(conf["value"]) + ".png",
            "name": "number",
            "value": conf["value"]
        }
        mydeck.set_key(key, n)
        if mydeck._GAME_KEY_CONFIG["opened"] is None:
            mydeck._GAME_KEY_CONFIG["opened"] = key
        else:
            opened = mydeck._GAME_KEY_CONFIG["opened"]
            if mydeck._GAME_KEY_CONFIG[opened]["value"] == mydeck._GAME_KEY_CONFIG[key]["value"]:
                # Right choise
                mydeck._GAME_KEY_CONFIG["opened"] = None
                n["clicked"] = True
                for i in [opened, key]:
                    mydeck.set_game_key(i, n)
                mydeck._GAME_KEY_CONFIG["num_of_try"] += 1
                return 1
            else:
                # Wrong choise
                time.sleep(0.5)
                mydeck._GAME_KEY_CONFIG["opened"] = None
                for i in [opened, key]:
                    empty = {
                        "image": "./src/Assets/cat.png",
                        "name": "number",
                        "value": mydeck._GAME_KEY_CONFIG[i]["value"]
                    }
                    mydeck.set_key(i, empty)
                mydeck._GAME_KEY_CONFIG["num_of_try"] += 1
                return 0
        return -1
