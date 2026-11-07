"""Image / rendering mixin for MyDeck."""

import hashlib
import os
import re
import requests
import wand.image
from cairosvg import svg2png
from typing import Optional, TYPE_CHECKING
from urllib.parse import urlparse

from PIL import Image, ImageDraw, ImageFont
from StreamDeck.ImageHelpers import PILHelper

from .lock import Lock
from .my_decks_manager import VirtualDeck

if TYPE_CHECKING:
    from .my_decks import ImageOrFile


class MyDeckImageMixin:
    """Image-handling methods for MyDeck.

    Depends on `self.deck`, `self.myname`, `self.font_path`, `self.debug()`,
    and `self.abs_key()` from MyDeck. Also depends on the module-level
    constant `ROOT_DIR` from `my_decks.py`, which is imported lazily inside
    methods that need it to avoid a circular import.
    """

    def determine_image_url(self, image_url: Optional[str], url: Optional[str]) -> Optional[str]:
        """Return url for key image"""
        if image_url is None and url is not None:
            image_url = re.sub(
                r'^(https?://[^/]+).*$', r'\g<1>/favicon.ico', url)

        return image_url

    def image_url_to_file_name(self, image_url: str) -> str:
        """Return file name from url"""
        # Hash the URL so the raw URL (slashes, query strings, ...) never ends up in
        # the path. Keep only a plain terminal extension from the URL path, if any.
        digest = hashlib.sha256(image_url.encode('utf-8')).hexdigest()[:32]
        m = re.search(r'\.(\w{1,5})$', urlparse(image_url).path)
        ext = '.' + m.group(1) if m else ''
        return '/tmp/' + 'mydeck-' + self.myname + '-' + digest + ext

    def image_url_to_image(self, conf: Optional[dict], url: Optional[str] = None):
        """If conf has image_url and get it and then save as the file and set its name as image of conf."""
        from .my_decks import ROOT_DIR  # lazy to avoid circular import
        image_url = None
        icon_file = None
        if conf is not None:
            image_url = self.determine_image_url(conf.get('image_url'), url)
        else:
            conf = {}

        if image_url is not None:
            icon_file_name = self.image_url_to_file_name(image_url)
            icon_file = self.save_image(image_url, icon_file_name)

        if icon_file is not None:
            conf["image"] = icon_file
        else:
            conf["image"] = ROOT_DIR+"/Assets/world.png"

    def save_image(self, icon_url: str, icon_file: str) -> Optional[str]:
        """Get image from icon_url and save it to icon_file"""
        if os.path.exists(icon_file) is False:
            try:
                # bounded wait so setup / config reload cannot hang on a dead endpoint
                res = requests.get(icon_url, timeout=10)
            except requests.RequestException as e:
                self.debug("Error in fetching image {}: {}".format(icon_url, e))
                return None
            if res.status_code == requests.codes.ok:
                icon_data = res.content
                l = Lock(icon_file)
                l.wait()
                try:
                    if icon_url[-3:len(icon_url)] == 'svg':
                        icon_file = icon_file[0:-4] + '.png'
                        svg2png(bytestring=icon_data, write_to=icon_file)
                    else:
                        with open(icon_file, mode="wb") as f:
                            f.write(icon_data)
                finally:
                    # always release the lock, even if conversion or writing raised
                    l.unlock()
                if self.check_icon_file(icon_file):
                    return icon_file
        else:
            return icon_file

        return None

    def check_icon_file(self, file_path: str) -> bool:
        """Check whether file_path is image or not"""
        try:
            with wand.image.Image(filename=file_path):
                return True
        except Exception as e:
            self.debug("Error in check_icon_file: {}".format(e))
            os.rename(file_path, file_path + '.back')
            return False

    # change touchscreen image
    def update_touchscreen_image(self, conf: dict, use_lock: bool = True):
        """Update touchscreen image"""
        from .my_decks import ImageOrFile  # lazy to avoid circular import
        deck: VirtualDeck = self.deck
        x: int = conf.get("x") or 0
        y: int = conf.get("y") or 0
        width: int = conf.get("width") or 800
        height: int = conf.get("height") or 100
        image = self.render_touchscreen_image(ImageOrFile(conf["image"]))
        if deck is not None:
            if use_lock:
                Lock.do_with_lock(deck.get_serial_number(),
                                  lambda: deck.set_touchscreen_image(image, x, y, width, height))
            else:
                deck.set_touchscreen_image(image, x, y, width, height)

    # change key image
    def update_key_image(self, key: int, image: str, use_lock: bool = True):
        """Update image of key"""
        # to prevent corrupt image drawn in key.
        if (deck := self.deck) is not None:
            key = self.abs_key(key)
            if use_lock:
                # logging.debug("update_key_image: %s => %d" % (self.myname, key))
                # Update requested key with the generated image.
                Lock.do_with_lock(self.deck.get_serial_number(),
                                  lambda: deck.set_key_image(key, image))
            else:
                deck.set_key_image(key, image)

    # render touchscreen image
    def render_touchscreen_image(self, image_filename_or_object: 'ImageOrFile'):
        """Render touchscreen image with image."""
        deck = self.deck
        image = PILHelper.create_scaled_touchscreen_image(
            deck, image_filename_or_object.image, margins=[0, 0, 0, 0], background="black")

        if hasattr(self.deck, 'is_virtual'):
            return image
        else:
            return PILHelper.to_native_format(deck, image)

    # render key image and label
    def render_key_image(self, icon_filename_or_object: Optional['ImageOrFile'], label: str = '', bg_color: str = '', no_label: bool = False):
        """Render key image with image, label and background color.

        If ``icon_filename_or_object`` is None, render a label-only key with a
        plain background.
        """
        deck = self.deck
        font_bg_color = "white"
        if bg_color == '' or bg_color == "black":
            bg_color = "black"
        else:
            font_bg_color = "black"
        if label == '':
            label = ""

        if icon_filename_or_object is None:
            image = PILHelper.create_image(deck, background=bg_color)
        else:
            icon: Image.Image = Image.Image()
            if icon_filename_or_object.is_file:
                icon = Image.open(icon_filename_or_object.file)
            else:
                icon = icon_filename_or_object.image

            margins = [0, 0, 20, 0]
            if no_label:
                margins = [0, 0, 0, 0]

            image = PILHelper.create_scaled_image(
                deck, icon, margins=margins, background=bg_color)

        draw = ImageDraw.Draw(image)
        if no_label is False:
            font_size = 14
            if len(label) > 7:
                font_size = int(14 * 7 / len(label) + 0.999)
            font = ImageFont.truetype(self.font_path, font_size)
            draw.text((image.width / 2, image.height - 5), font=font,
                      text=label, anchor="ms", fill=font_bg_color)

        if hasattr(self.deck, 'is_virtual'):
            return image
        else:
            return PILHelper.to_native_format(deck, image)
