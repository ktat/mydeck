from PIL import Image, ImageDraw, ImageFont
import time
import random
import threading

class GameWhacAMole:
    data = {
        "score": 0,
    }
    exit = False
    def __init__ (self, mydeck, start_key_num=0):
        self.mydeck = mydeck
        mydeck.add_game_key_conf({
            0 + start_key_num: {
                "command": "WhacAMole",
                "image": "./src/Assets/cat.png",
                "label": "Whac-A-Mole",
                "mode": 10,
            },
        })
        mydeck.add_game_command("WhacAMole", lambda conf: self.key_setup(conf.get("mode")))
        
    def key_setup(self, num):
        mydeck = self.mydeck
        deck = mydeck.deck
        self.exit = False
        deck.reset()
        mydeck.set_current_page_without_setup("~GAME_WHAC_A_MOLE")
        self.data["mode"] = num
        self.data["score"] = 0
        self.data["count"] = 0
        print("Opened '{}' device (serial number: '{}', fw: '{}')".format(
            deck.deck_type(), deck.get_serial_number(), deck.get_firmware_version()
        ))

        # Set initial screen brightness to 30%.
        deck.set_brightness(30)

        prev = 0

        mydeck.set_game_status(1)

        # Set initial key images.
        deck.set_key_callback(lambda deck, key, state: self.key_change_callback(key, state))

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

        t = threading.Thread(target=lambda : self.appear_mole(), args=())
        t.start()

    def appear_mole(self):
        mydeck = self.mydeck
        prev = None
        empty = {
            "image": "./src/Assets/empty.png",
            "name": "empty"
        }
        mole = {
            "image": "./src/Assets/cat.png",
            "name": "mole",
            "click": False,
        }
        left_second_key = {
            "image": "",
            "name": "left_second",
            "click": False,
        }
        game_time = self.data['mode']
        t = time.time()
        while True:
            if not mydeck.in_game_status():
                break
            if self.exit:
                break

            self.data["count"] += 1
            time.sleep(random.uniform(0.2, 0.7))
            r = random.randint(0,9)
            if prev is not None:
                mydeck.set_game_key(prev, empty)
            mydeck.set_game_key(r, mole)
            prev = r
            self.data["left_second"] = game_time - int(time.time() - t)
            if self.data["left_second"] <= 0:
                self.data["left_second"] = 0

            left_second_key["image"] =  "./src/Assets/" + str(self.data["left_second"]) + ".png"
            mydeck.set_game_key(10, left_second_key)

            self.show_score()
            if self.data["left_second"] == 0:
                
                break

    def show_score(self):
        mydeck = self.mydeck
        im = Image.new('RGB', (100, 100), (0, 0, 0))
        font = ImageFont.truetype(mydeck.font_path, 40)
        draw = ImageDraw.Draw(im)
        draw.text((0, 0), font=font, text=str(self.data["score"]), fill="white")
        draw.text((30,30), font=font, text="/", fill="white")
        draw.text((40, 60), font=font, text=str(self.data["count"]), fill="white")        
        self.mydeck.update_key_image(
            13,
            self.mydeck.render_key_image(
                im,
                "",
                'black',
            )
        )

        
    def key_change_callback(self, key, state):
        mydeck = self.mydeck
        deck = mydeck.deck
        # Print new key state
        print("Deck {} Key {} = {}".format(deck.id(), key, state), flush=True)

        conf = mydeck._GAME_KEY_CONFIG.get(key)
        if state:
            if conf:
                if conf["name"] == "exit":
                    self.exit = True
                    if self.data["left_second"] > 0:
                        time.sleep(1)
                    mydeck.exit_game()
                if conf["name"] == "reset":
                    mydeck._GAME_KEY_CONFIG["answer"] = []
                if conf["name"] == "restart":
                    self.key_setup(self.data["mode"])
                if conf["name"] == "mole":
                    if self.data["left_second"] > 0:
                        self.data["score"] += 1
                        self.show_score()
