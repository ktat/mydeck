import logging
from mydeck import MyDecks
from StreamDeck.DeviceManager import DeviceManager
from StreamDeck.Devices.StreamDeck import StreamDeck
import os
import yaml
import sys
from typing import Dict, Any
import argparse
import netifaces
import qrcode


class MyDecksStarter:
    configPath: str = ""
    config: dict = {}

    def __init__(self, config: dict, use_vdeck: bool = False):
        self.config = config
        config_path: str = self.config["config_path"]

        MyDecksStarter.configPath = config_path

        if not os.path.exists(config_path):
            os.makedirs(config_path)
        if not self.check_configs(use_vdeck):
            logging.warn("config check failed. exit.")
            sys.exit(1)

    def run(self):
        mydecks = MyDecks(self.config)
        mydecks.start_decks()

    def load_vdeck_config(self, vdeck_config_path: str) -> bool:
        if not os.path.exists(vdeck_config_path) or os.path.getsize(vdeck_config_path) == 0:
            return False

        with open(vdeck_config_path, 'r') as file:
            data = yaml.load(file, Loader=yaml.FullLoader)
            for index in data.keys():
                self.check_deck_config_and_create_if_required(
                    data[index]["serial_number"])
        return True

    def check_deck_config_and_create_if_required(self, sn: str):
        file_path = self.config['config_path'] + '/' + sn + '.yml'
        self.config['decks'][sn] = sn
        self.config['configs'][sn] = {
            'file': file_path,
        }
        data = {
            "apps": [],
            "page_config": {
                "@HOME": {
                    "keys": {
                    }
                }
            },
        }
        if not os.path.exists(file_path):
            with open(file_path, 'w') as file:
                yaml.dump(data, file)
                logging.info(file_path + " is created.")

    def check_configs(self, use_vdeck: bool) -> bool:
        config_path: str = self.config["config_path"]
        configure_vdeck: bool = use_vdeck

        if not self.config.get("decks"):
            self.config["decks"] = {}

        vdeck_config_path = config_path + "/vdeck.yml"
        self.config["configs"] = {}

        if use_vdeck:
            # if use_vdeck, load vdeck config. if not exists, need to configure vdeck.
            self.config['vdeck_config'] = vdeck_config_path
            configure_vdeck = not self.load_vdeck_config(vdeck_config_path)

        real_decks: list[StreamDeck] = DeviceManager().enumerate()
        if len(real_decks) > 0:
            for deck in real_decks:
                deck.open()
                deck.reset()

                sn = deck.get_serial_number()
                deck.close()
                self.check_deck_config_and_create_if_required(sn)
        elif not use_vdeck:
            # if no real decks and not use virtual deck, confirm to create virtual decks
            while True:
                print(
                    "StreamDeck devices are not found and no --use-vdeck flag. Do you use vdeck? (y/n)")
                answer = input()
                if answer.lower() == "n":
                    return False
                elif answer.lower() == "y":
                    self.config['vdeck_config'] = vdeck_config_path
                    configure_vdeck = not self.load_vdeck_config(
                        vdeck_config_path)

        if configure_vdeck:
            if not os.path.exists(vdeck_config_path):
                with open(vdeck_config_path, 'w') as file:
                    yaml.dump({}, file)

            if len(real_decks) > 0:
                while True:
                    print("Do you want additional virtual decks? (y/n)")

                    answer = input()
                    if answer != "":
                        break

                if answer != "y":
                    configure_vdeck = False

            if configure_vdeck:
                data = {}
                i = 0
                while True:
                    i += 1
                    deck_data: Dict[str, Any] = {
                        "serial_number": "vdeck" + str(i)
                    }
                    while True:
                        print("Num of keys?(default 15)")
                        key_count = input()
                        if key_count == "":
                            deck_data["key_count"] = 15
                        elif not key_count.isdigit():
                            print("! Invalid input. Please enter a valid number.")
                            continue
                        else:
                            deck_data["key_count"] = int(key_count)
                        break

                    while True:
                        print("Num of columns?(default 5)")
                        columns = input()
                        if columns == "":
                            deck_data["columns"] = 5
                        elif not columns.isdigit():
                            print("! Invalid input. Please enter a valid number.")
                            continue
                        else:
                            deck_data["columns"] = int(columns)
                        break

                    print("Has touchscreen? (y/n)")
                    has_touchscreen = input()
                    if has_touchscreen is not None and has_touchscreen.lower() == "y":
                        deck_data["has_touchscreen"] = True
                    else:
                        deck_data["has_touchscreen"] = False

                    print("Num of dials? (0 if none)")
                    while True:
                        dial_count = input()
                        if dial_count != "" and dial_count != "0":
                            if not dial_count.isdigit():
                                print(
                                    "! Invalid input. Please enter a valid number.")
                                continue
                        elif dial_count.isdigit():
                            deck_data["dial_count"] = int(dial_count)
                        break

                    data[i] = deck_data

                    print("Do you want to add another virtual deck? (y/n)")
                    answer = input()
                    if answer == "" or answer.lower() == "n":
                        break

                with open(vdeck_config_path, 'w') as file:
                    yaml.dump(data, file)
                    for index in data.keys():
                        self.check_deck_config_and_create_if_required(
                            data[index]["serial_number"])

                    logging.info("vdeck.yml created. Please edit it.")
            elif len(real_decks) == 0:
                logging.warn(
                    "This program requires, at least, one of StreamDeck device or virtual devcie.")
                return False

        return True


def get_private_ips() -> list[str]:
    ips: list[str] = ["127.0.0.1"]
    for interface in netifaces.interfaces():
        try:
            for link in netifaces.ifaddresses(interface)[netifaces.AF_INET]:
                ip_address = link['addr']
                if ip_address.startswith('192.168') or ip_address.startswith('10.'):
                    ips.append(ip_address)
        except KeyError:
            pass

    return ips


def print_qr_code(data: str):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    qr.print_ascii()


def main():
    log_levels: list[str] = list(logging._levelToName.values(
    )) + [x.lower() for x in logging._levelToName.values()]

    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=3000, help='Server port')
    parser.add_argument(
        '--log-level', default='INFO', choices=log_levels, help='Log level')
    parser.add_argument(
        '--config-path', default=os.path.expanduser('~/.config/mydeck'), help='Config directory')
    parser.add_argument('--vdeck', action='store_true',
                        default=False, help='Use virutal devices')
    parser.add_argument('--no-qr', action='store_true',
                        default=False, help='Do not print QR code')
    args = parser.parse_args()

    config: dict = {}

    if args.log_level is not None:
        config["log_level"] = args.log_level.upper()
    if args.port is not None:
        config["server_port"] = args.port
    if args.config_path is not None:
        config["config_path"] = args.config_path
    if config.get("config_path") is None:
        print("config_path is required")
        sys.exit(1)

    logging.basicConfig(level=config.get("log_level", "INFO"))

    ips = get_private_ips()
    print("MyDeck Server is running. Access to the following URL.\n")
    index = 0
    for ip in ips:
        url = "http://" + ip + ":" + str(config["server_port"])
        if index > 0:
            print("%d: %s" % (index, url))
        else:
            print("-: %s" % url)
        index += 1

    if not args.no_qr:
        strdin = input(
            "\nSelect the IP address to print as QR code(Enter to skip): ")
        if strdin.isdigit():
            url = "http://" + ips[int(strdin)] + ":" + \
                str(config["server_port"])
            print_qr_code(url)
    else:
        print("\nSkip QR code printing.\n")

    mydecks_starter = MyDecksStarter(config, args.vdeck)
    mydecks_starter.run()

    os._exit(0)
