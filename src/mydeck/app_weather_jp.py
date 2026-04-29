from mydeck import MyDeck, TriggerAppBase, ImageOrFile
from typing import Tuple, Optional
from PIL import Image, ImageDraw, ImageFont
import json
import os
import requests
import logging
import re
import datetime

OptStr = Optional[str]


class Area:
    def __init__(self, args: dict):
        self.division: OptStr = args.get('division')  # 東京都
        self.division_code: OptStr = args.get('division_code')  # 130000
        self.area: OptStr = args.get('area')  # 東京地方
        self.area_code: OptStr = args.get('area_code')  # 130000
        self.area_temp: OptStr = args.get('area_temp')  # 東京
        self.area_temp_code: OptStr = args.get('area_temp_code')  # 44132
        self.display_name: OptStr = args.get('display_name')

        if self.division is None and self.division_code is None:
            self.division = '東京都'
            self.division_code = '130000'

        if self.area is None and self.area_code is None:
            self.area = '東京地方'
            self.area_code = '130010'

        if self.area_temp is None and self.area_temp_code is None:
            self.area_temp = '東京'
            self.area_temp_code = '44132'

        result = self.find(division_mapping(),
                           self.division, self.division_code)
        if result is None:
            result = (None, None)
        (self.division, self.division_code) = result

        result = self.find(area_mapping(), self.area, self.area_code)
        if result is None:
            result = (None, None)
        (self.area, self.area_code) = result

    def find(self, mapping: dict, name: str = None, code: str = None) -> Optional[Tuple]:
        if name is not None:
            if mapping.get(name) is not None:
                code = mapping[name]
            if code is not None:
                for item in mapping.items():
                    if item[1] == code:
                        name = item[0]
                        break
            if code is None:
                for key in mapping.keys():
                    if re.match(name, key):
                        code = mapping[key]
                        name = key
                        break
        if name is not None and code is not None:
            return (name, code)

        return None


class JMA:
    def __init__(self, area: Area):
        self.url: str = 'https://www.jma.go.jp/bosai/forecast/data/forecast/{}.json'.format(
            area.division_code)


class JMAResult:
    def __init__(self, weather: OptStr, pop: OptStr, temp: OptStr):
        self.image_url: str
        self.image_name: str
        self.weather: OptStr  # 天気
        self.temp: OptStr  # 気温
        self.pop: OptStr  # 降水量
        now = datetime.datetime.now()
        image = forecast_mapping().get(weather)
        if now.hour <= 18 and now.hour >= 6:
            self.image_url = 'https://www.jma.go.jp/bosai/forecast/img/' + \
                image[0]
            self.image_name = image[0][0:-4]
        else:
            self.image_url = 'https://www.jma.go.jp/bosai/forecast/img/' + \
                image[1]
            self.image_name = image[1][0:-4]

        self.weather = weather
        self.pop = str(pop) + '%'
        self.temp = str(temp) + '℃'


class JMASearch:
    def __init__(self, jma: JMA, area: Area):
        self.jma: JMA = jma
        self.area: Area = area

    def search(self):
        try:
            res = requests.get(self.jma.url, timeout=10)
            res.raise_for_status()
        except (requests.RequestException, ValueError) as e:
            logging.error(f"Failed to fetch weather data: {e}")
            return None
        image_url = ''
        weather: OptStr = None
        temp: OptStr = None
        pop: OptStr = None
        data: dict = res.json()
        for area in data[0]["timeSeries"][0]["areas"]:
            if area["area"]["name"] == self.area.area or area["area"]["code"] == self.area.area_code:
                weather = area["weatherCodes"][0]
                break
        if weather is None:
            logging.warning("No maching weather data found. %s" %
                            data[0]["timeSeries"][0]["areas"])
        for area in data[0]["timeSeries"][1]["areas"]:
            if area["area"]["name"] == self.area.area or area["area"]["code"] == self.area.area_code:
                pop = area["pops"][0]
                break
        if pop is None:
            logging.warning("No maching pop data found. %s" %
                            data[0]["timeSeries"][1]["areas"])
        for area in data[0]["timeSeries"][2]["areas"]:
            if area["area"]["name"] == self.area.area_temp or area["area"]["code"] == self.area.area_temp:
                temp = area["temps"][0]
                break
        if temp is None:
            logging.warning("No maching temp data found. %s" %
                            data[0]["timeSeries"][2]["areas"])
        return JMAResult(weather, pop, temp)


class AppWeatherJp(TriggerAppBase):
    use_hour_trigger: bool = True
    sample_data = {
        "area": "大阪府",
        "area_temp": "大阪",
        "display_name": "Osaka",
        "division": "大阪府",
    }

    def __init__(self, mydeck: MyDeck, option: Optional[dict] = None):
        if option is None:
            option = {}
        super().__init__(mydeck, option)
        self.area: Area = Area(option)
        self.jma: JMA = JMA(self.area)

    def set_image_to_key(self, key: int, page: str):
        result = JMASearch(self.jma, self.area).search()

        if result is not None:
            icon_file = "/tmp/mystreamdeck-app-weather-" + result.image_name + ".png"
            self.mydeck.save_image(result.image_url, icon_file)
            im = Image.open(icon_file)
            im = im.convert("RGB")
            font = ImageFont.truetype(self.mydeck.font_path, 20)
            draw = ImageDraw.Draw(im)
            if result.temp is not None:
                draw.text((28, 1),  font=font, text=result.temp,
                          fill=(200, 200, 200))
                draw.text((27, 0),  font=font,
                          text=result.temp, fill=(255, 0, 0))

            if result.pop is not None:
                draw.text((28, 21),  font=font,
                          text=result.pop, fill=(200, 200, 200))
                draw.text((27, 20),  font=font,
                          text=result.pop, fill=(0, 0, 255))

            l = 20
            if self.area.display_name is not None:
                if len(self.area.display_name) >= 6:
                    l = int(20 / (len(self.area.display_name) / 6))
                    font = ImageFont.truetype(self.mydeck.font_path, l)
                draw.text((11, 44 + (19-l)), font=font,
                          text=self.area.display_name, fill=(0, 0, 0))
                draw.text((10, 43 + (19-l)), font=font,
                          text=self.area.display_name, fill=(255, 255, 255))

            self.update_key_image(
                key,
                self.mydeck.render_key_image(
                    ImageOrFile(im),
                    "",
                    'black',
                    True,
                )
            )


# Module-level cache and JSON loader
_MAPPINGS_CACHE: Optional[dict] = None
_MAPPINGS_PATH = os.path.join(os.path.dirname(__file__), "weather_jp_mappings.json")


def _load_mappings() -> dict:
    global _MAPPINGS_CACHE
    if _MAPPINGS_CACHE is None:
        with open(_MAPPINGS_PATH, encoding="utf-8") as f:
            _MAPPINGS_CACHE = json.load(f)
    return _MAPPINGS_CACHE


def division_mapping():
    return _load_mappings()["division"]


def area_mapping():
    return _load_mappings()["area"]


def forecast_mapping():
    return _load_mappings()["forecast"]
