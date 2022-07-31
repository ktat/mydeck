from mystreamdeck import AppBase
from PIL import Image, ImageDraw, ImageFont
import datetime
import time
import sys
import json
import requests

class WeatherJp(AppBase):
    # if app reuquire thread, true
    use_thread = True

    previous_page = ''
    previous_date = ''
    url = None

    def __init__(self, mydeck, option={}):
        super().__init__(mydeck, option)
        if option.get('jma_url'):
            self.url = option["jma_url"]
        else:
            self.url = 'https://www.jma.go.jp/bosai/forecast/data/forecast/130000.json'
        if option.get('place'):
            self.place = option["place"]
            self.place_tmp = option["place_tmp"]            
        else:
            self.place = '東京地方'
            self.place_tmp = '東京'

    def set_image_to_key(self, key, page):
        now = datetime.datetime.now()
        date_text = "{0:02d}/{1:02d}/{2:02d}".format(now.month, now.day, now.hour)
        # quit when page and date is not changed
        if self.in_other_page or page != self.previous_page or date_text != self.previous_date:
            self.previous_page = page
            self.previous_date = date_text
        else:
            return False

        res = requests.get(self.url)
        if res.status_code == requests.codes.ok:
            data = json.loads(res.text)
            image_url = None
            tmp_min = None
            tmp_max = None
            for d in data[0]["timeSeries"]:
                for area in d["areas"]:
                    if area["area"]["name"] == self.place or area["area"]["code"] == self.place:
                        wheather = area["weatherCodes"][0]
                        image_url = 'https://www.jma.go.jp/bosai/forecast/img/' + wheather + '.svg'
                        self.mydeck.save_image(image_url, "/tmp/mystreamdeck-app-weather.png")
                        break
                else:
                    continue
                break
            for area in data[1]["tempAverage"]["areas"]:
                if area["area"]["name"] == self.place_tmp or area["area"]["code"] == self.place_tmp:
                    tmp_min = area["min"]
                    tmp_max = area["max"]
                    break

        im = Image.open("/tmp/mystreamdeck-app-weather.png")
        im = im.convert("RGB")
        font = ImageFont.truetype(self.mydeck.font_path, 20)
        draw = ImageDraw.Draw(im)
        draw.text((20, 23), font=font, text=tmp_max, fill="red" , width=3)
        draw.text((20, 43), font=font, text=tmp_min, fill="blue", width=3)
        self.mydeck.update_key_image(
            key,
            self.mydeck.render_key_image(
                im,
                "",
                'black',
                True,
            )
        )
