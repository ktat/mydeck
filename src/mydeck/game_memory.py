import time
import random
import logging
from mydeck import MyDeck, GameAppBase, ExceptionNoDeck

class GameMemory(GameAppBase):
    require_key_count: int = 15

    def __init__ (self, mydeck :MyDeck, start_key_num :int = 0):
        super().__init__(mydeck)

        if self.enable == False:
            return

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
            3 + start_key_num: {
                "command": "GameMemory",
                "image": "./src/Assets/memory-game.png",
                "label": "Memory VS",
                "mode": -1,
            },
        })
        mydeck.add_game_command("GameMemory", lambda conf: self.key_setup(conf["mode"]))

    def key_setup(self, wait_time: int):
        mydeck = self.mydeck
        self.data["num_of_try"] = 0
        self.data["wait_time"] = wait_time
        self.data["opened"] = None
        self.data["vsmode"] = wait_time == -1
        self.data["memory"] = {}
        self.data["turn"] = None
        self.data["score"] = {1: 0, 2: 0} # 1 is user, 2 is cpu
        deck = mydeck.deck

        mydeck.set_current_page_without_setup("~GAME_MEMORY")

        if deck is None:
            raise(ExceptionNoDeck)

        deck.reset()

        # Set initial screen brightness to 30%.
        deck.set_brightness(30)

        # Set initial key images.
        deck.set_key_callback(lambda deck, key, state: self.key_change_callback(key, state))

        empty = {
            "image": "./src/Assets/cat.png",
            "name": "empty"
        }

        mydeck.set_game_status_on()

        for key in range(0, 12):
            mydeck.set_game_key(key, empty)

        pairs = {}
        used: dict = {}
        pos: dict = {}
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

        key_name = 'number'
        if self.data["vsmode"]:
            key_name = 'number_vs'
            mydeck.set_game_key(-2, {
                "name": "reverse",
                "image": "./src/Assets/reverse.png",
                "label": 'reverse'
            })

        for i in range(0, 12):
            n = pos[i]
            img = "./src/Assets/" + str(n) + ".png"
            if wait_time <= 0:
                img = "./src/Assets/cat.png"
            mydeck.set_game_key(i, {
                "image": img,
                "name": "number_prepare",
                "clicked": True,
            })

        if wait_time > 0:
            for i in range(0, wait_time + 1):
                mydeck.set_game_key(-2, {
                    "image": "./src/Assets/" + str(wait_time - i) + ".png",
                    "name": "num_of_wait",
                })
                if i < wait_time:
                    time.sleep(1)

        mydeck.set_game_key(-3, {
            "name": "restart",
            "label": "RESTART",
            "image": "./src/Assets/restart.png",
        })

        mydeck.set_game_key(-1, {
            "name": "exit",
            "image": "./src/Assets/back.png",
            "label": "exit Game"
        })

        for i in range(0, 12):
            n = pos[i]
            mydeck.set_game_key(i, {
                "image": "./src/Assets/cat.png",
                "name": key_name,
                "value": n,
                "clicked": False,
            })

    def key_change_callback(self, key :int, state :bool):
        mydeck = self.mydeck
        deck = mydeck.deck
        # Print new key state
        if deck is not None:
            logging.debug("Deck {} Key {} = {}".format(deck.id(), key, state))

        conf = mydeck._GAME_KEY_CONFIG.get(key)
        wait_time = self.data["wait_time"]
        if state:
            if conf:
                if conf["name"] == "exit":
                    mydeck.exit_game()
                elif conf["name"] == "restart":
                    self.key_setup(wait_time)
                elif conf["name"] == "number":
                    if conf["clicked"] == False and self.data["opened"] != key:
                        self.open_and_check(key, conf)
                    num_of_try = self.data["num_of_try"]
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
                elif conf["name"] == "reverse":
                    turn = self.data["turn"]
                    if turn is None or turn != 1:
                        while True:
                            self.data['turn'] = 2
                            if self.open_by_cpu() is False:
                                break
                        self.data['turn'] = 1
                elif conf["name"] == "number_vs":
                    turn = mydeck._GAME_KEY_CONFIG.get("turn")
                    if conf["clicked"] == False and self.data["opened"] != key and (turn is None or turn == 1):
                        result = self.open_and_check(key, conf)
                        if result >= 0:
                            if result == 1:
                                self.data['score'][1] += 1
                            elif result == 0:
                                self.data['turn'] = 2
                                while True:
                                    if self.open_by_cpu() is False:
                                        break
                                self.data['turn'] = 1

                    score = self.data['score']
                    face = 'normal'
                    label = "{} vs {}".format(score[1], score[2])
                    if score[1] > score[2]:
                        face = 'laugh'
                    elif score[1] < score[2]:
                        face = 'sad'

                    clicked = self.clicked()

                    mydeck.set_key(13, {
                        "name": "num_of_try",
                        "image": "./src/Assets/" + face + ".png",
                        "label": label
                    })



    def clicked(self):
        clicked = 0
        mydeck = self.mydeck
        for i in range(0, 12):
            if mydeck._GAME_KEY_CONFIG[i]["clicked"]:
                clicked += 1
        return clicked

    def evaluate(self, clicked :int, num :int, wait_time :int) -> str:
        mydeck = self.mydeck
        keisu: float = 1
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

    def evaluate2label(self, evaluate :str):
        l = {
            "laugh": "Excelent!",
            "happy": "Good!",
            "normal": "Good job.",
            "unhappy": "Bad!",
            "sad": "Disappointed!",

        }
        return l[evaluate]

    def open_and_check(self, key :int, conf :dict) -> int:
        mydeck = self.mydeck
        self.data['memory'][key] = conf["value"]
        key_name = 'number'
        if self.data["vsmode"]:
            key_name = 'number_vs'
        n = {
            "image": "./src/Assets/" + str(conf["value"]) + ".png",
            "name": key_name,
            "value": conf["value"]
        }
        mydeck.set_key(key, n)
        if self.data["opened"] is None:
            self.data["opened"] = key
        else:
            opened = self.data['opened']
            if mydeck._GAME_KEY_CONFIG[opened]["value"] == mydeck._GAME_KEY_CONFIG[key]["value"]:
                # Right choise
                self.data['opened'] = None
                n["clicked"] = True
                for i in [opened, key]:
                    mydeck.set_game_key(i, n)
                self.data["num_of_try"] += 1
                return 1
            else:
                # Wrong choise
                time.sleep(0.5)
                self.data['opened'] = None
                for i in [opened, key]:
                    empty = {
                        "image": "./src/Assets/cat.png",
                        "name": "number",
                        "value": mydeck._GAME_KEY_CONFIG[i]["value"]
                    }
                    mydeck.set_key(i, empty)
                self.data["num_of_try"] += 1
                return 0
        return -1

    def open_by_cpu(self) -> bool:
        mydeck = self.mydeck
        pairs: dict = {}
        candidate = []
        can_open = []
        can_open_prior = []
        opened = self.data['opened']

        for i in range(0, 12):
            if mydeck._GAME_KEY_CONFIG[i]["clicked"] is False:
                # search the place not opened and let it as candidate
                can_open.append(i)
                if self.data['memory'].get(i) is None:
                    # if the place is not in memory, let is as prior candidate
                    can_open_prior.append(i)

            if (mydeck._GAME_KEY_CONFIG[i]["clicked"] is False or opened == i) and self.data['memory'].get(i):
                # not opend or cpu opened place and when it is in memory
                v = mydeck._GAME_KEY_CONFIG[i]["value"]
                if pairs.get(v) is None:
                    pairs[v] = []
                pairs[v].append(i)
                if len(pairs[v]) > 1:
                    # cpu knows the place of the pair, let it as candidate
                    candidate.append(v)

        # finish when no closed place
        if len(can_open) == 0:
            return False

        # can_open_prior prior to can_open, overrite can_open as can_open_prior
        if len(can_open_prior) > 0:
            can_open = can_open_prior

        random.shuffle(can_open)

        # cpu knows the place of the pair
        if len(candidate) > 0:
            random.shuffle(candidate)
            for i in [0, 1]:
                if pairs[candidate[0]][i] != opened:
                    can_open[0] = pairs[candidate[0]][i]
                    break

        time.sleep(0.5)
        conf = mydeck._GAME_KEY_CONFIG[can_open[0]]
        result = self.open_and_check(can_open[0], mydeck._GAME_KEY_CONFIG[can_open[0]])
        if result == 1:
            self.data['score'][2] += 1
        elif result == 0:
            # if cpu open wrong place, return false
            return False

        # if cpu open right place or cpu open first place, return true
        return True
