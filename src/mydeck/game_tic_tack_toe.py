import random
import time
import logging
from mydeck import MyDeck, GameAppBase
from typing import List

# 三目並べのビット
# 1   2    4
# 8   16  32
# 64 128 256

# 勝利条件のbit和(勝利列 8パターン)
WIN_CONDITION = {
    84: True,
    7: True,
    56: True,
    448: True,
    273: True,
    73: True,
    146: True,
    292: True,
}

# 次で勝利する条件
#   key 2つ取ったときのbit和
#   value: 3目目で勝利するbit (勝利列 8 x 3 = 24パターン)
PRE_WIN_CONDITION = {
    3: 4,
    6: 1,
    5: 2,
    24: 32,
    48: 8,
    40: 16,
    192: 256,
    384: 64,
    320: 128,
    17: 256,
    272: 1,
    257: 16,
    20: 64,
    80: 4,
    68: 16,
    9: 64,
    72: 1,
    65: 8,
    18: 128,
    134: 2,
    130: 16,
    36: 256,
    288: 4,
    260: 32,
}


class GameTicTackToe(GameAppBase):
    require_key_count: int = 15

    def __init__(self, mydeck: MyDeck, start_key_num: int = 0):
        super().__init__(mydeck)

        if self.enable == False:
            return

        self.addional_key_count = 0
        if mydeck.key_count == 32:
            self.addional_key_count = 3

        mydeck.add_game_key_conf({
            0 + start_key_num: {
                "command": "GameTicTacToe",
                "image": "./src/Assets/tictacktoe.png",
                "label": "TicTacToe",
            },
        })
        mydeck.add_game_command("GameTicTacToe", lambda conf: self.key_setup())

    def key_setup(self):
        mydeck = self.mydeck
        deck = mydeck.deck
        self.data = {}
        mydeck._GAME_KEY_CONFIG = {}

        addional_key_count = self.addional_key_count

        key_conf: dict[int, dict] = {
            0: {
                "name": "frame",
                "value": 1,
            },
            1: {
                "name": "frame",
                "value": 2,
            },
            2: {
                "name": "frame",
                "value": 4,
            },
            5 + addional_key_count: {
                "name": "frame",
                "value": 8,
            },
            6 + addional_key_count: {
                "name": "frame",
                "value": 16,
            },
            7 + addional_key_count: {
                "name": "frame",
                "value": 32,
            },
            10 + addional_key_count * 2: {
                "name": "frame",
                "value": 64,
            },
            11 + addional_key_count * 2: {
                "name": "frame",
                "value": 128,
            },
            12 + addional_key_count * 2: {
                "name": "frame",
                "value": 256,
            },
            9 + addional_key_count * 2: {
                "name": "reverse",
                "image": "./src/Assets/reverse.png",
                "label": "Reverse",
            },
            -2: {
                "name": "restart",
                "image": "./src/Assets/restart.png",
                "label": "Restart",
            },
            -1: {
                "name": "exit",
                "image": "./src/Assets/back.png",
                "label": "exit Game"
            }
        }

        mydeck.set_current_page_without_setup("~GAME_TICK_TACK_TOE")
        mydeck.set_game_status_on()

        deck.reset_keys()

        # Set initial screen brightness to 30%.
        deck.set_brightness(30)

        # Set initial key images.
        deck.set_key_callback(
            lambda deck, key, state: self.key_change_callback(key, state))

        for key in key_conf.keys():
            conf = key_conf[key]
            if conf["name"] == "frame":
                conf["image"] = "./src/Assets/cat.png"
                conf["clicked"] = False
                conf["user"] = None
            mydeck.set_game_key(key, conf)

    def key_change_callback(self, key: int, state: bool):
        mydeck = self.mydeck

        conf = mydeck._GAME_KEY_CONFIG.get(key)
        if state:
            if conf:
                if conf["name"] == "exit":
                    mydeck.exit_game()
                elif conf["name"] == "restart":
                    self.key_setup()
                elif conf["name"] == "frame":
                    if conf["clicked"] == False and mydeck._GAME_KEY_CONFIG.get(4) is None:
                        if self.data.get("reverse") is None:
                            self.data["reverse"] = False
                        if self.data["reverse"]:
                            conf["image"] = "./src/Assets/check.png"
                        else:
                            conf["image"] = "./src/Assets/circle.png"
                        conf["clicked"] = True
                        conf["user"] = 1
                        mydeck.set_game_key(key, conf)
                        self.cpu_turn()
                elif conf["name"] == "reverse":
                    if self.data.get("reverse") is None:
                        self.data["reverse"] = True
                        self.cpu_turn()

    def select_by_cpu(self) -> List:
        # [選択した場所, 勝利者(1: user, 2: cpu, -1: draw)]
        mydeck = self.mydeck
        conf = mydeck._GAME_KEY_CONFIG
        user_val = 0
        cpu_val = 0
        can_select = []
        can_select_value = {}
        for key in conf.keys():
            if conf[key]["name"] == "frame":
                if conf[key]["clicked"]:
                    if conf[key]["user"] == 1:
                        user_val += conf[key]["value"]
                    else:
                        cpu_val += conf[key]["value"]
                else:
                    can_select.append(conf[key]["value"])
                    can_select_value[conf[key]["value"]] = key

        choose_key = None
        winner = None

        # ユーザーがすでに勝利しているかチェック
        for w in WIN_CONDITION.keys():
            if user_val & w == w:
                return [None, 1]

        # 選択するところがない場合は引き分け
        if len(can_select) == 0:
            return [None, -1]

        # CPUが初手の場合はランダム
        if user_val == 0:
            selected = can_select[random.randint(0, len(can_select)-1)]
            choose_key = can_select_value[selected]
        # ユーザーが、真ん中を選んだ場合は端を取る
        elif user_val == 16:
            n = [n for n in [1, 4, 64, 256]
                 if can_select_value.get(n) is not None]
            selected = n[random.randint(0, len(n)-1)]
            choose_key = can_select_value[selected]
        # 真ん中(cpu) x 対角(user)の場合は、辺の中を取る
        elif cpu_val == 16 and user_val in [68, 257]:
            n = [n for n in [2, 8, 128, 32]
                 if can_select_value.get(n) is not None]
            selected = n[random.randint(0, len(n)-1)]
            choose_key = can_select_value[selected]
        # 真ん中があいてるなら真ん中を取る
        elif can_select_value.get(16) is not None:
            choose_key = can_select_value[16]

        if choose_key is None:
            # CPUの勝利条件の場所を探す
            choose_key = can_select_value.get(
                self.search_win_value(cpu_val, can_select, WIN_CONDITION))
            logging.debug("choose_key1: {}".format(choose_key))
        if choose_key is None:
            # ユーザーの勝利条件の場所を探す(ユーザーが勝つ場所に打って妨害する)
            choose_key = can_select_value.get(
                self.search_win_value(user_val, can_select, WIN_CONDITION))
            logging.debug("choose_key2: {}".format(choose_key))
        if choose_key is None:
            # ユーザーの勝てそうな場所を探す(ユーザーの勝てそうな場所は先に抑えて妨害する)
            choose_key = can_select_value.get(self.search_pre_win_value(
                2, user_val, cpu_val, can_select, PRE_WIN_CONDITION))
            logging.debug("choose_key3: {}".format(choose_key))
        if choose_key is None:
            # CPUの勝てそうな場所を探す
            choose_key = can_select_value.get(self.search_pre_win_value(
                1, cpu_val, user_val, can_select, PRE_WIN_CONDITION))
            logging.debug("choose_key4: {}".format(choose_key))
        if choose_key is None:
            # まだ決まっていない場合は、取れるところをrandomで取る
            select = random.randint(0, len(can_select) - 1)
            choose_key = can_select_value[can_select.pop(select)]
            logging.debug("choose_key5: {}".format(choose_key))

        logging.debug("choose_key: {}".format(choose_key))

        # CPUが勝利しているか確認
        for w in WIN_CONDITION.keys():
            if (conf[choose_key]["value"] + cpu_val) & w == w:
                winner = 2
                break

        # 選択するところが1つ以下で、勝者なしの場合は引き分け
        if winner is None:
            if len(can_select) == 1:
                return [choose_key, -1]
            elif len(can_select) == 0:
                return [None, -1]

        return [choose_key, winner]

    # 勝利条件の場所を探す
    def search_win_value(self, val, can_select, win):
        choose_value = None

        for i, v in enumerate(can_select):
            for w in win.keys():
                logging.debug("val: {}, v: {}, w: {}, sum: {}".format(
                    val, v, w, (val + v) & w))
                if (val + v) & w == w:
                    choose_value = v
                    can_select.pop(i)
                    break
            if choose_value is not None:
                break

        return choose_value

    # 勝てそうな条件の場所を探す
    def search_pre_win_value(self, threshold, val, enemy_val, can_select, pre_win):
        can_select_value = {}
        for i, v in enumerate(can_select):
            can_select_value[v] = i

        choose_value = {}
        for i, v in enumerate(can_select):
            for w in pre_win.keys():
                # 相手がすでに置いている場所があるなら、そこは除外
                if w & enemy_val > 0:
                    continue

                next_val = pre_win[w]
                logging.debug("val: {}, v: {}, w: {}, sum: {}, next_val: {}".format(
                    val, v, w, (val + v) & w, next_val))
                if (val + v) & w == w and can_select_value.get(next_val) is not None:
                    logging.debug("choose: {}".format(v))
                    if choose_value.get(v):
                        choose_value[v] += 1
                        break
                    else:
                        choose_value[v] = 1

        logging.debug("selected: {}".format(choose_value))
        if len(choose_value.keys()) == 0:
            return None

        # 真ん中が空いてて危険度が高ければ真ん中を返す
        if choose_value.get(16) and choose_value[16] >= threshold:
            can_select.pop(can_select_value[16])
            return 16

        # 端が空いてて危険度が高ければ端を返す
        corner = [corner for corner in [1, 4, 64, 256] if choose_value.get(
            corner) is not None and choose_value[corner] >= threshold]
        if len(corner) > 0:
            selected = corner[random.randint(0, len(corner)-1)]
            can_select.pop(can_select_value[selected])
            return selected

        # 危険度が高いものを返す
        sort_orders = sorted(choose_value.items(),
                             key=lambda x: x[1], reverse=True)

        if threshold >= sort_orders[0][1]:
            selected = sort_orders[0][0]
            can_select.pop(can_select_value[selected])
            return selected

        return v

    # CPUの順番
    def cpu_turn(self):
        mydeck = self.mydeck
        result = self.select_by_cpu()
        logging.debug("RESULT {}".format(result))
        choose_key = result[0]
        winner = result[1]
        if choose_key is not None and winner != 1:
            choose_conf = mydeck._GAME_KEY_CONFIG.get(choose_key)
            choose_conf["clicked"] = True
            choose_conf["user"] = 2
            if self.data["reverse"]:
                choose_conf["image"] = "./src/Assets/circle.png"
            else:
                choose_conf["image"] = "./src/Assets/check.png"
            time.sleep(0.25)
            mydeck.set_game_key(choose_key, choose_conf)

        if winner is not None:
            conf = {
                "name": "result",
                "image": "./src/Assets/normal.png",
                "label": "Draw!",
            }
            if winner == 1:
                conf["label"] = "WIN!!"
                conf["image"] = "./src/Assets/laugh.png"
            elif winner == 2:
                conf["label"] = "LOOSE!!"
                conf["image"] = "./src/Assets/sad.png"
            # Draw
            mydeck.set_game_key(4 + self.addional_key_count, conf)
