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
ACCOUNTS_PAGE_PREFIX = "@TOTP_ACCOUNTS"  # pages: @TOTP_ACCOUNTS, @TOTP_ACCOUNTS_2, ...
DETAIL_PREFIX = "@TOTP_DETAIL_"
BACK_IMAGE = os.path.join(ROOT_DIR, "Assets", "back.png")
FORWARD_IMAGE = os.path.join(ROOT_DIR, "Assets", "forward.png")


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

    def _accounts_page_name(self, page_index: int) -> str:
        if page_index == 0:
            return ACCOUNTS_PAGE
        return f"{ACCOUNTS_PAGE}_{page_index + 1}"

    def _accounts_per_page(self) -> int:
        """Number of account slots per page (excluding +, →, Back keys)."""
        # Reserve: back_key for Back, back_key-1 for →
        return self.mydeck.key_count - 2

    def _setup_pages(self) -> None:
        """Register account list pages (with pagination) and detail pages."""
        # NOTE: These pages are registered into the live key_config dict.
        # If the config file is hot-reloaded (reflect_config), these entries will be lost.
        accounts = self.manager.load_accounts()
        key_count = self.mydeck.key_count
        back_key = key_count - 1
        next_key = back_key - 1
        per_page = self._accounts_per_page()
        key_config = self.mydeck.key_config()
        register_url = f"http://127.0.0.1:{self.mydeck.server_port}/totp"

        # Set up change_page for keys on non-TOTP pages (Web UI config)
        for page, key in list(self.page_key.items()):
            if not page.startswith(ACCOUNTS_PAGE_PREFIX):
                if key_config.get(page) is None:
                    key_config[page] = {}
                key_config[page][key] = {
                    "change_page": ACCOUNTS_PAGE,
                    "image": BACK_IMAGE.replace("back", "check"),
                    "label": "2FA",
                    "no_image": True,
                }

        # Calculate pages
        # Each page shows up to per_page accounts, plus one "+" button after the last account
        total_items = len(accounts) + 1  # accounts + one "+" button
        num_pages = max(1, math.ceil(total_items / per_page))

        account_pages: list[str] = []
        for p in range(num_pages):
            page_name = self._accounts_page_name(p)
            account_pages.append(page_name)
            key_config[page_name] = {}

            start_idx = p * per_page
            end_idx = min(start_idx + per_page, len(accounts))
            page_accounts = accounts[start_idx:end_idx]

            # Account buttons
            for i, acc in enumerate(page_accounts):
                key_config[page_name][i] = {
                    "change_page": f"{DETAIL_PREFIX}{acc['name']}",
                    "no_image": True,
                }

            # "+" button: one, right after last account on this page
            plus_idx = len(page_accounts)
            if plus_idx < per_page and start_idx + plus_idx >= len(accounts):
                key_config[page_name][plus_idx] = {
                    "command": ["xdg-open", register_url],
                    "no_image": True,
                }

            # "→" next page button
            if p < num_pages - 1:
                next_page = self._accounts_page_name(p + 1)
                key_config[page_name][next_key] = {
                    "change_page": next_page,
                    "image": FORWARD_IMAGE if os.path.exists(FORWARD_IMAGE) else BACK_IMAGE,
                    "label": "Next",
                    "no_image": True,
                }

            # "Back" button
            key_config[page_name][back_key] = {
                "change_page": "@previous",
                "image": BACK_IMAGE,
                "label": "Back",
            }

        # Detail pages
        for acc in accounts:
            page_name = f"{DETAIL_PREFIX}{acc['name']}"
            key_config[page_name] = {
                back_key: {
                    "change_page": "@previous",
                    "image": BACK_IMAGE,
                    "label": "Back",
                }
            }

        self._managed_pages = account_pages + [
            f"{DETAIL_PREFIX}{a['name']}" for a in accounts
        ]

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
                break

            try:
                if current.startswith(ACCOUNTS_PAGE_PREFIX) and not current.startswith(DETAIL_PREFIX):
                    if last_page != current:
                        self._last_account_names = []  # force re-render on page entry
                    self._render_accounts_page(current)
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

    def _render_accounts_page(self, current_page: str) -> None:
        accounts = self.manager.load_accounts()
        account_names = [a["name"] for a in accounts]

        if account_names == self._last_account_names:
            return
        self._last_account_names = account_names

        key_count = self.mydeck.key_count
        back_key = key_count - 1
        next_key = back_key - 1
        per_page = self._accounts_per_page()
        self._last_code = ""

        self._setup_pages()

        # Determine page index
        page_index = 0
        for i in range(100):
            if self._accounts_page_name(i) == current_page:
                page_index = i
                break

        start_idx = page_index * per_page
        end_idx = min(start_idx + per_page, len(accounts))
        page_accounts = accounts[start_idx:end_idx]

        # Render account buttons
        for i, acc in enumerate(page_accounts):
            im = self._make_account_image(acc)
            self.mydeck.update_key_image(
                i, self.mydeck.render_key_image(ImageOrFile(im), "", "black")
            )

        # "+" button right after accounts
        plus_idx = len(page_accounts)
        if plus_idx < per_page and start_idx + plus_idx >= len(accounts):
            im = self._make_centered_text_image("+", 50)
            self.mydeck.update_key_image(
                plus_idx, self.mydeck.render_key_image(ImageOrFile(im), "", "black")
            )
            plus_idx += 1

        # Clear remaining keys between content and nav buttons
        for i in range(plus_idx, next_key):
            self.mydeck.update_key_image(
                i, self.mydeck.render_key_image(
                    ImageOrFile(Image.new("RGB", (X, Y), (0, 0, 0))), "", "black")
            )

        # "→" next page indicator (rendered by app for visual, click handled by key_config)
        num_pages = max(1, math.ceil((len(accounts) + 1) / per_page))
        if page_index < num_pages - 1:
            im = self._make_centered_text_image("→", 40)
            self.mydeck.update_key_image(
                next_key, self.mydeck.render_key_image(ImageOrFile(im), "", "black")
            )
        else:
            self.mydeck.update_key_image(
                next_key, self.mydeck.render_key_image(
                    ImageOrFile(Image.new("RGB", (X, Y), (0, 0, 0))), "", "black")
            )

    def _render_detail_page(self, name: str) -> None:
        code = self.manager.generate_code(name)
        remaining = self.manager.remaining_seconds()
        key_count = self.mydeck.key_count
        back_key = key_count - 1
        available = key_count - 2
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
                    i, self.mydeck.render_key_image(ImageOrFile(im), "", "black")
                )

        countdown_im = self._make_countdown_image(remaining)
        self.mydeck.update_key_image(
            countdown_key,
            self.mydeck.render_key_image(
                ImageOrFile(countdown_im), f"{remaining}s", "black"
            ),
        )

    def _make_account_image(self, acc: dict) -> Image.Image:
        """Render account button: background image (if set) + name + issuer at bottom."""
        image_path = acc.get("image")
        has_image = image_path and os.path.exists(image_path)
        if has_image:
            im = Image.open(image_path).convert("RGBA").resize((X, Y))
        else:
            im = Image.new("RGBA", (X, Y), (0, 0, 0, 255))
        overlay = Image.new("RGBA", (X, Y), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        name = acc.get("name", "")[:12]
        issuer = acc.get("issuer", "")[:12]
        font = ImageFont.truetype(self.mydeck.font_path, 16)
        # Draw name with background band
        bbox_n = draw.textbbox((0, 0), name, font=font)
        text_w = bbox_n[2] - bbox_n[0]
        text_h = bbox_n[3] - bbox_n[1]
        x_n = (X - text_w) // 2
        y_n = (Y - text_h) // 2 - 8
        if has_image:
            draw.rectangle([0, y_n - 2, X, y_n + text_h + 4], fill=(0, 0, 0, 160))
        draw.text((x_n, y_n), text=name, font=font, fill="white")
        # Draw issuer at bottom with background band
        if issuer and issuer != name:
            bbox_i = draw.textbbox((0, 0), issuer, font=font)
            i_w = bbox_i[2] - bbox_i[0]
            i_h = bbox_i[3] - bbox_i[1]
            x_i = (X - i_w) // 2
            y_i = Y - 22
            if has_image:
                draw.rectangle([0, y_i - 2, X, y_i + i_h + 4], fill=(0, 0, 0, 160))
            draw.text((x_i, y_i), text=issuer, font=font, fill=(200, 200, 200))
        im = Image.alpha_composite(im, overlay)
        return im.convert("RGB")

    def _make_centered_text_image(self, text: str, font_size: int) -> Image.Image:
        im = Image.new("RGB", (X, Y), (0, 0, 0))
        draw = ImageDraw.Draw(im)
        font = ImageFont.truetype(self.mydeck.font_path, font_size)
        bbox = draw.textbbox((0, 0), text, font=font)
        x = (X - (bbox[2] - bbox[0])) // 2
        y = (Y - (bbox[3] - bbox[1])) // 2
        draw.text((x, y), text=text, font=font, fill="white")
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
        draw.ellipse([10, 10, 90, 90], fill=color)
        if elapsed_angle > 0:
            draw.pieslice([10, 10, 90, 90], start=-90, end=-90 + elapsed_angle, fill=(0, 0, 0))
        return im
