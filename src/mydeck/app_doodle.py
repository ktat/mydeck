from mydeck import TriggerAppBase, ImageOrFile, ROOT_DIR
import requests
import webbrowser
import datetime
import re
import os
import time
import glob
from PIL import Image

GOOGLE_LOGO_URL = "https://www.google.com/favicon.ico"


class AppDoodle(TriggerAppBase):
    use_hour_trigger: bool = True
    doodle_name: str = ''

    _key_conf = {
        "app_command": "OpenDoodle",
        "image": ROOT_DIR + "/Assets/gray-box.png",
        "label": "Doodle",
    }
    key_command = {
        "OpenDoodle": lambda app: app.open_browser(),
    }

    # setup key configuration
    def key_setup(self):
        page = self.mydeck.current_page()
        key = self.page_key.get(page)
        if key is not None:
            self.mydeck.set_key_conf(page, key, self._key_conf)

    def set_image_to_key(self, key: int, page: str):
        image_prefix: str = "/tmp/mydeck-doodle."
        self.key_setup()
        d: datetime.datetime = datetime.datetime.now()
        icon_file: str = ''
        icon_files: list[str] = glob.glob(image_prefix + "*")
        if len(icon_files) > 0:
            icon_files = sorted(
                icon_files, key=lambda item: os.stat(item).st_mtime)
            icon_file = icon_files[0]
        if os.path.isfile(icon_file) is False or time.time() - os.stat(icon_file).st_mtime >= 3600:
            try:
                doodles_url = 'https://doodles.google/'
                res = requests.get(doodles_url, timeout=10)
                res.raise_for_status()
                html: str = res.text
                image_url: str = GOOGLE_LOGO_URL
                self.doodle_name: str = "Google"
                ext: str = "ico"
                # Parse first doodle card from homepage HTML
                card_match = re.search(
                    r'class="doodle-card-cta"[^>]*href="/doodle/([^"]+)/"[^>]*>.*?'
                    r'<img[^>]*src="([^"]+)"',
                    html, re.DOTALL)
                if card_match:
                    self.doodle_name = card_match.group(1)
                    image_url = card_match.group(2)
                    if image_url.startswith('//'):
                        image_url = 'https:' + image_url

                m = re.search(r'\.(\w+)$', image_url)
                if m is not None and m.group(1) is not None:
                    ext = m.group(1)

                image_res = requests.get(image_url, timeout=10)
                image_res.raise_for_status()
                icon_file = image_prefix + ext
                with open(icon_file, mode="wb") as f:
                    f.write(image_res.content)
                im = Image.open(icon_file)
                crop_width = int((im.size[0] - im.size[1]) / 3)
                im_cropped = im.crop(
                    (crop_width, 0, im.size[0] - crop_width, im.size[1]))
                percent = 100 / im_cropped.width
                im_resized = im_cropped.resize(
                    (int(im_cropped.width * percent), int(im_cropped.height * percent)))
                im_resized.save(icon_file, format=ext, quality=95)
            except Exception as e:
                self.debug("error: %s" % e)

        if icon_file != "":
            self.update_key_image(
                key,
                self.mydeck.render_key_image(
                    ImageOrFile(icon_file),
                    f"{d.month:02d}/{d.day:02d}",
                    'black',
                    False,
                )
            )

    def open_browser(self):
        webbrowser.open('https://doodles.google/doodle/' + self.doodle_name)
