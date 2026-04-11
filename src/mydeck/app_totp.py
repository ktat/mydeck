import math
import sys
import time
import logging

import os

from PIL import Image, ImageDraw, ImageFont
from mydeck import MyDeck, ThreadAppBase, ImageOrFile, ROOT_DIR
from .totp_account_manager import TotpAccountManager

X = Y = 100
ACCOUNTS_PAGE = "@TOTP_ACCOUNTS"
DETAIL_PREFIX = "@TOTP_DETAIL_"
BACK_IMAGE = os.path.join(ROOT_DIR, "Assets", "back.png")


class AppTotp(ThreadAppBase):
    use_thread = True

    def __init__(self, mydeck: MyDeck, option: dict = {}):
        super().__init__(mydeck, option)
        self.manager = TotpAccountManager()
        self.time_to_sleep = 1
        self._managed_pages: list[str] = []
        self._last_code: str = ""
        self._last_account_names: list[str] = []
        self._setup_pages()

    def _setup_pages(self) -> None:
        """Register @TOTP_ACCOUNTS and per-account detail pages in key_config."""
        # NOTE: These pages are registered into the live key_config dict.
        # If the config file is hot-reloaded (reflect_config), these entries will be lost.
        # Workaround: restart the daemon after config changes.
        accounts = self.manager.load_accounts()
        key_count = self.mydeck.key_count
        back_key = key_count - 1
        key_config = self.mydeck.key_config()

        # If the app was configured via Web UI on a non-TOTP page (e.g. @HOME: 4),
        # set up that key as a change_page button to @TOTP_ACCOUNTS.
        for page, key in list(self.page_key.items()):
            if page != ACCOUNTS_PAGE:
                if key_config.get(page) is None:
                    key_config[page] = {}
                key_config[page][key] = {
                    "change_page": ACCOUNTS_PAGE,
                    "image": BACK_IMAGE.replace("back", "check"),
                    "label": "2FA",
                    "no_image": True,
                }

        # Accounts list page
        key_config[ACCOUNTS_PAGE] = {}
        for i, acc in enumerate(accounts[:back_key]):
            key_config[ACCOUNTS_PAGE][i] = {
                "change_page": f"{DETAIL_PREFIX}{acc['name']}",
                "no_image": True,
            }
        # Empty keys: open TOTP registration page in browser
        register_url = f"http://127.0.0.1:{self.mydeck.server_port}/totp"
        for i in range(len(accounts), back_key):
            key_config[ACCOUNTS_PAGE][i] = {
                "command": ["xdg-open", register_url],
                "no_image": True,
            }
        key_config[ACCOUNTS_PAGE][back_key] = {
            "change_page": "@previous",
            "image": BACK_IMAGE,
            "label": "Back",
        }

        # Per-account detail pages (back button only; digits drawn by thread)
        for acc in accounts:
            page_name = f"{DETAIL_PREFIX}{acc['name']}"
            key_config[page_name] = {
                back_key: {
                    "change_page": "@previous",
                    "image": BACK_IMAGE,
                    "label": "Back",
                }
            }

        self._managed_pages = [ACCOUNTS_PAGE] + [
            f"{DETAIL_PREFIX}{a['name']}" for a in accounts
        ]

        # Ensure the framework can start our thread when @TOTP_ACCOUNTS is entered
        if ACCOUNTS_PAGE not in self.page_key:
            self.page_key[ACCOUNTS_PAGE] = 0

    def is_in_target_page(self) -> bool:
        return self.mydeck.current_page() in self._managed_pages

    def start(self) -> None:
        last_page: str = ""
        while True:
            if self.mydeck._exit or self._stop:
                break

            current = self.mydeck.current_page()

            if current not in self._managed_pages:
                break  # user navigated away; thread exits

            try:
                if current == ACCOUNTS_PAGE:
                    if last_page != ACCOUNTS_PAGE:
                        self._last_account_names = []  # force re-render on page entry
                    self._render_accounts_page()
                elif current.startswith(DETAIL_PREFIX):
                    name = current[len(DETAIL_PREFIX):]
                    self._render_detail_page(name)
            except Exception as e:
                logging.error("AppTotp render error: %s", e)

            last_page = current
            time.sleep(self.time_to_sleep)

        self.stop_app()
        self.init_app_flag()
        sys.exit()

    def _render_accounts_page(self) -> None:
        accounts = self.manager.load_accounts()
        account_names = [a["name"] for a in accounts]

        # Skip if nothing changed
        if account_names == self._last_account_names:
            return
        self._last_account_names = account_names

        key_count = self.mydeck.key_count
        back_key = key_count - 1
        self._last_code = ""  # reset so detail page re-renders fully on next entry

        # Refresh key_config and managed pages when accounts change
        self._setup_pages()

        for i, acc in enumerate(accounts[:back_key]):
            im = self._make_label_image(acc["name"])
            self.mydeck.update_key_image(
                i, self.mydeck.render_key_image(ImageOrFile(im), acc["name"], "black")
            )

        # Empty keys: show "+" label to indicate registration
        for i in range(len(accounts), back_key):
            im = self._make_label_image("+")
            self.mydeck.update_key_image(
                i, self.mydeck.render_key_image(ImageOrFile(im), "Register", "black")
            )

    def _render_detail_page(self, name: str) -> None:
        code = self.manager.generate_code(name)
        remaining = self.manager.remaining_seconds()
        key_count = self.mydeck.key_count
        back_key = key_count - 1
        available = key_count - 2  # excludes countdown key and back key
        digits_per_key = max(1, math.ceil(6 / available))
        num_digit_keys = math.ceil(6 / digits_per_key)
        countdown_key = num_digit_keys

        code_changed = code != self._last_code
        if code_changed:
            self._last_code = code
            for i in range(num_digit_keys):
                start = i * digits_per_key
                chunk = code[start: start + digits_per_key]
                im = self._make_digit_image(chunk)
                self.mydeck.update_key_image(
                    i, self.mydeck.render_key_image(ImageOrFile(im), chunk, "black")
                )

        countdown_im = self._make_countdown_image(remaining)
        self.mydeck.update_key_image(
            countdown_key,
            self.mydeck.render_key_image(
                ImageOrFile(countdown_im), f"{remaining}s", "black"
            ),
        )

    def _make_label_image(self, text: str) -> Image.Image:
        im = Image.new("RGB", (X, Y), (0, 0, 0))
        draw = ImageDraw.Draw(im)
        font = ImageFont.truetype(self.mydeck.font_path, 20)
        draw.text((5, 35), text=text[:10], font=font, fill="white")
        return im

    def _make_digit_image(self, digits: str) -> Image.Image:
        im = Image.new("RGB", (X, Y), (0, 0, 0))
        draw = ImageDraw.Draw(im)
        font_size = 55 if len(digits) == 1 else 38
        font = ImageFont.truetype(self.mydeck.font_path, font_size)
        bbox = draw.textbbox((0, 0), digits, font=font)
        x = (X - (bbox[2] - bbox[0])) // 2
        y = (Y - (bbox[3] - bbox[1])) // 2
        draw.text((x, y), text=digits, font=font, fill="white")
        return im

    def _make_countdown_image(self, remaining: int) -> Image.Image:
        im = Image.new("RGB", (X, Y), (0, 0, 0))
        draw = ImageDraw.Draw(im)
        elapsed_angle = int(360 * (30 - remaining) / 30)
        color = (255, 60, 60) if remaining <= 5 else (0, 200, 100)
        # Full circle, then carve out elapsed portion clockwise from top
        draw.ellipse([10, 10, 90, 90], fill=color)
        if elapsed_angle > 0:
            draw.pieslice([10, 10, 90, 90], start=-90, end=-90 + elapsed_angle, fill=(0, 0, 0))
        return im
