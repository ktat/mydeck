from mydeck import MyDeck, TriggerAppBase, ImageOrFile
import requests
import json
import subprocess
import datetime
import re
import os
import time
import glob
from PIL import Image

BING_URL = 'https://www.bing.com/HPImageArchive.aspx?format=js&idx=0&n=1&mkt='


class AppBingPhoto(TriggerAppBase):
    use_day_trigger: bool = True
    _key_conf = {
        "app_command": "OpenBing",
        "image": "./src/Assets/gray-box.png",
        "label": "Bing Photo",
    }
    key_command = {
        "OpenBing": lambda app: app.open_browser(),
    }

    def __init__(self, mydeck: MyDeck, config: dict = {}):
        super().__init__(mydeck, config)
        self.lang = 'en-US'
        self.now = datetime.datetime.now()
        if (lang := config.get("lang")) is not None:
            self.lang = lang

    # setup key configuration
    def key_setup(self):
        page = self.mydeck.current_page()
        key = self.page_key.get(page)
        if key is not None:
            self.mydeck.set_key_conf(page, key, self._key_conf)

    def set_image_to_key(self, key: int, page: str):
        if not self.is_in_target_page():
            return

        image_prefix: str = "/tmp/mydeck-bing_photo."
        self.key_setup()
        d: datetime.datetime = datetime.datetime.now()
        icon_file: str = ''
        icon_files: list[str] = glob.glob(image_prefix + '*')
        if len(icon_files) > 0:
            icon_files = sorted(
                icon_files, key=lambda item: os.stat(item).st_mtime)
            icon_file = icon_files[0]
        if os.path.isfile(icon_file) is False or time.time() - os.stat(icon_file).st_mtime >= 3600:
            res = requests.get(BING_URL + self.lang)
            if res.status_code == requests.codes.ok:
                data: dict = json.loads(res.text)
                if data.get('images') is not None and len(data['images']) > 0 and (url := data['images'][0].get('url')):
                    image_url: str = 'https://bing.com' + url
                    ext: str = "jpg"
                    m = re.search('\.(jpg|png|gif)', image_url)
                    if m is not None and m.group(1) is not None:
                        ext = m.group(1)
                    image_res = requests.get(image_url)
                    if image_res.status_code == requests.codes.ok:
                        icon_file = image_prefix + ext

                        with open(icon_file, mode="wb") as f:
                            f.write(image_res.content)
                        im = Image.open(icon_file)
                        percent = 100 / im.width
                        im_resized = im.resize(
                            (int(im.width * percent), int(im.height * percent)))
                        im_resized.save(icon_file, format=ext, quality=95)
        self.mydeck.update_key_image(
            key,
            self.mydeck.render_key_image(
                ImageOrFile(icon_file),
                "",
                'black',
                True,
            )
        )

    def open_browser(self):
        command = ['google-chrome', '--profile-directory=Default',
                   'https://www.bing.com/']
        subprocess.Popen(command)
