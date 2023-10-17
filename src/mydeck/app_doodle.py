from mydeck import TriggerAppBase, ImageOrFile
import requests
import json
import subprocess
import datetime
import re
import os
import time
import glob
from PIL import Image


class AppDoodle(TriggerAppBase):
    use_hour_trigger: bool = True
    doodle_name: str = ''

    _key_conf = {
        "app_command": "OpenDoodle",
        "image": "./src/Assets/gray-box.png",
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
            doodles_api_url = 'https://www.google.com/doodles/json/{0:04d}/{1:02d}'.format(
                d.year, d.month)
            res = requests.get(doodles_api_url)
            if res.status_code == requests.codes.ok:
                data: list = json.loads(res.text)
                image_url: str = 'https:' + data[0]["high_res_url"]
                date: list = data[0]['run_date_array']
                ext: str = ""
                m = re.search('\.(\w+)$', image_url)
                if m is not None and m.group(1) is not None:
                    ext = m.group(1)

                self.doodle_name: str = data[0]['name']

                image_res = requests.get(image_url)
                if image_res.status_code == requests.codes.ok:
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
        self.mydeck.update_key_image(
            key,
            self.mydeck.render_key_image(
                ImageOrFile(icon_file),
                "{0:02d}/{1:02d}".format(d.year, d.month),
                'black',
                False,
            )
        )

    def open_browser(self):
        command = ['google-chrome', '--profile-directory=Default',
                   'https://www.google.com/doodles/' + self.doodle_name]
        subprocess.Popen(command)
