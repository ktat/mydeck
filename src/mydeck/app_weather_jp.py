from mydeck import MyDeck, TriggerAppBase, ImageOrFile
from typing import Tuple, Optional
from PIL import Image, ImageDraw, ImageFont
import json
import requests
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
        res = requests.get(self.jma.url)
        if res.status_code == requests.codes.ok:
            image_url = ''
            weather: OptStr = None
            temp: OptStr = None
            pop: OptStr = None
            data: dict = json.loads(res.text)
            for area in data[0]["timeSeries"][0]["areas"]:
                if area["area"]["name"] == self.area.area or area["area"]["code"] == self.area.area_code:
                    weather = area["weatherCodes"][0]
                    break
            for area in data[0]["timeSeries"][1]["areas"]:
                if area["area"]["name"] == self.area.area or area["area"]["code"] == self.area.area_code:
                    pop = area["pops"][0]
                    break
            for area in data[0]["timeSeries"][2]["areas"]:
                if area["area"]["name"] == self.area.area_temp or area["area"]["code"] == self.area.area_temp:
                    temp = area["temps"][0]
                    break
            return JMAResult(weather, pop, temp)
        return None


class AppWeatherJp(TriggerAppBase):
    use_hour_trigger: bool = True

    def __init__(self, mydeck: MyDeck, option: dict = {}):
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

            self.mydeck.update_key_image(
                key,
                self.mydeck.render_key_image(
                    ImageOrFile(im),
                    "",
                    'black',
                    True,
                )
            )


def division_mapping():
    return {
        '宗谷地方': '011000',
        '上川地方': '012010',
        '留萌地方': '012020',
        '網走地方': '013000',
        '北見地方': '013000',
        '紋別地方': '013000',
        '根室地方': '014010',
        '釧路地方': '014020',
        '十勝地方': '014030',
        '胆振地方': '015010',
        '日高地方': '015020',
        '石狩地方': '016010',
        '空知地方': '016020',
        '後志地方': '016030',
        '渡島地方': '017010',
        '檜山地方': '017020',
        '青森県': '020000',
        '岩手県': '030000',
        '宮城県': '040000',
        '秋田県': '050000',
        '山形県': '060000',
        '福島県': '070000',
        '茨城県': '080000',
        '栃木県': '090000',
        '群馬県': '100000',
        '埼玉県': '110000',
        '千葉県': '120000',
        '東京都': '130000',
        '神奈川県': '140000',
        '新潟県': '150000',
        '富山県': '160000',
        '石川県': '170000',
        '福井県': '180000',
        '山梨県': '190000',
        '長野県': '200000',
        '岐阜県': '210000',
        '静岡県': '220000',
        '愛知県': '230000',
        '三重県': '240000',
        '滋賀県': '250000',
        '京都府': '260000',
        '大阪府': '270000',
        '兵庫県': '280000',
        '奈良県': '290000',
        '和歌山県': '300000',
        '鳥取県': '310000',
        '島根県': '320000',
        '岡山県': '330000',
        '広島県': '340000',
        '山口県': '350000',
        '徳島県': '360000',
        '香川県': '370000',
        '愛媛県': '380000',
        '高知県': '390000',
        '福岡県': '400000',
        '佐賀県': '410000',
        '長崎県': '420000',
        '熊本県': '430000',
        '大分県': '440000',
        '宮崎県': '450000',
        '鹿児島県': '460100',
        '沖縄本島地方': '471000',
        '大東島地方': '472000',
        '宮古島地方': '473000',
        '八重山地方': '474000,',
    }


def area_mapping():
    return {
        '宗谷地方': '011000',
        '上川地方': '012010',
        '留萌地方': '012020',
        '網走地方': '013010',
        '北見地方': '013020',
        '紋別地方': '013030',
        '根室地方': '014010',
        '釧路地方': '014020',
        '十勝地方': '014030',
        '胆振地方': '015010',
        '日高地方': '015020',
        '石狩地方': '016010',
        '空知地方': '016020',
        '後志地方': '016030',
        '渡島地方': '017010',
        '檜山地方': '017020',
        '津軽': '020010',
        '下北': '020020',
        '三八上北': '020030',
        '内陸': '030010',
        '沿岸北部': '030020',
        '沿岸南部': '030030',
        '東部': '040010',
        '西部': '040020',
        '沿岸': '050010',
        '内陸': '050020',
        '村山': '060010',
        '置賜': '060020',
        '庄内': '060030',
        '最上': '060040',
        '中通り': '070010',
        '浜通り': '070020',
        '会津': '070030',
        '北部': '080010',
        '南部': '080020',
        '南部': '090010',
        '北部': '090020',
        '南部': '100010',
        '北部': '100020',
        '南部': '110010',
        '北部': '110020',
        '秩父地方': '110030',
        '北西部': '120010',
        '北東部': '120020',
        '南部': '120030',
        '東京地方': '130010',
        '伊豆諸島北部': '130020',
        '伊豆諸島南部': '130030',
        '小笠原諸島': '130040',
        '東部': '140010',
        '西部': '140020',
        '下越': '150010',
        '中越': '150020',
        '上越': '150030',
        '佐渡': '150040',
        '東部': '160010',
        '西部': '160020',
        '加賀': '170010',
        '能登': '170020',
        '嶺北': '180010',
        '嶺南': '180020',
        '中・西部': '190010',
        '東部・富士五湖': '190020',
        '北部': '200010',
        '中部': '200020',
        '南部': '200030',
        '美濃地方': '210010',
        '飛騨地方': '210020',
        '中部': '220010',
        '伊豆': '220020',
        '東部': '220030',
        '西部': '220040',
        '西部': '230010',
        '東部': '230020',
        '北中部': '240010',
        '南部': '240020',
        '南部': '250010',
        '北部': '250020',
        '南部': '260010',
        '北部': '260020',
        '大阪府': '270000',
        '南部': '280010',
        '北部': '280020',
        '北部': '290010',
        '南部': '290020',
        '北部': '300010',
        '南部': '300020',
        '東部': '310010',
        '中・西部': '310020',
        '東部': '320010',
        '西部': '320020',
        '隠岐': '320030',
        '南部': '330010',
        '北部': '330020',
        '南部': '340010',
        '北部': '340020',
        '西部': '350010',
        '中部': '350020',
        '東部': '350030',
        '北部': '350040',
        '北部': '360010',
        '南部': '360020',
        '香川県': '370000',
        '中予': '380010',
        '東予': '380020',
        '南予': '380030',
        '中部': '390010',
        '東部': '390020',
        '西部': '390030',
        '福岡地方': '400010',
        '北九州地方': '400020',
        '筑豊地方': '400030',
        '筑後地方': '400040',
        '南部': '410010',
        '北部': '410020',
        '南部': '420010',
        '北部': '420020',
        '壱岐・対馬': '420030',
        '五島': '420040',
        '熊本地方': '430010',
        '阿蘇地方': '430020',
        '天草・芦北地方': '430030',
        '球磨地方': '430040',
        '中部': '440010',
        '北部': '440020',
        '西部': '440030',
        '南部': '440040',
        '南部平野部': '450010',
        '北部平野部': '450020',
        '南部山沿い': '450030',
        '北部山沿い': '450040',
        '薩摩地方': '460010',
        '大隅地方': '460020',
        '種子島・屋久島地方': '460030',
        '奄美地方': '460040',
        '本島中南部': '471010',
        '本島北部': '471020',
        '久米島': '471030',
        '大東島地方': '472000',
        '宮古島地方': '473000',
        '石垣島地方': '474010',
        '与那国島地方': '474020',
    }

# https://www.jma.go.jp/bosai/forecast/
# Forecast.Const.TELOPS in console of developer tool


def forecast_mapping():
    return {
        "100": [
            "100.svg",
            "500.svg",
            "100",
            "晴",
            "CLEAR"
        ],
        "101": [
            "101.svg",
            "501.svg",
            "100",
            "晴時々曇",
            "PARTLY CLOUDY"
        ],
        "102": [
            "102.svg",
            "502.svg",
            "300",
            "晴一時雨",
            "CLEAR, OCCASIONAL SCATTERED SHOWERS"
        ],
        "103": [
            "102.svg",
            "502.svg",
            "300",
            "晴時々雨",
            "CLEAR, FREQUENT SCATTERED SHOWERS"
        ],
        "104": [
            "104.svg",
            "504.svg",
            "400",
            "晴一時雪",
            "CLEAR, SNOW FLURRIES"
        ],
        "105": [
            "104.svg",
            "504.svg",
            "400",
            "晴時々雪",
            "CLEAR, FREQUENT SNOW FLURRIES"
        ],
        "106": [
            "102.svg",
            "502.svg",
            "300",
            "晴一時雨か雪",
            "CLEAR, OCCASIONAL SCATTERED SHOWERS OR SNOW FLURRIES"
        ],
        "107": [
            "102.svg",
            "502.svg",
            "300",
            "晴時々雨か雪",
            "CLEAR, FREQUENT SCATTERED SHOWERS OR SNOW FLURRIES"
        ],
        "108": [
            "102.svg",
            "502.svg",
            "300",
            "晴一時雨か雷雨",
            "CLEAR, OCCASIONAL SCATTERED SHOWERS AND/OR THUNDER"
        ],
        "110": [
            "110.svg",
            "510.svg",
            "100",
            "晴後時々曇",
            "CLEAR, PARTLY CLOUDY LATER"
        ],
        "111": [
            "110.svg",
            "510.svg",
            "100",
            "晴後曇",
            "CLEAR, CLOUDY LATER"
        ],
        "112": [
            "112.svg",
            "512.svg",
            "300",
            "晴後一時雨",
            "CLEAR, OCCASIONAL SCATTERED SHOWERS LATER"
        ],
        "113": [
            "112.svg",
            "512.svg",
            "300",
            "晴後時々雨",
            "CLEAR, FREQUENT SCATTERED SHOWERS LATER"
        ],
        "114": [
            "112.svg",
            "512.svg",
            "300",
            "晴後雨",
            "CLEAR,RAIN LATER"
        ],
        "115": [
            "115.svg",
            "515.svg",
            "400",
            "晴後一時雪",
            "CLEAR, OCCASIONAL SNOW FLURRIES LATER"
        ],
        "116": [
            "115.svg",
            "515.svg",
            "400",
            "晴後時々雪",
            "CLEAR, FREQUENT SNOW FLURRIES LATER"
        ],
        "117": [
            "115.svg",
            "515.svg",
            "400",
            "晴後雪",
            "CLEAR,SNOW LATER"
        ],
        "118": [
            "112.svg",
            "512.svg",
            "300",
            "晴後雨か雪",
            "CLEAR, RAIN OR SNOW LATER"
        ],
        "119": [
            "112.svg",
            "512.svg",
            "300",
            "晴後雨か雷雨",
            "CLEAR, RAIN AND/OR THUNDER LATER"
        ],
        "120": [
            "102.svg",
            "502.svg",
            "300",
            "晴朝夕一時雨",
            "OCCASIONAL SCATTERED SHOWERS IN THE MORNING AND EVENING, CLEAR DURING THE DAY"
        ],
        "121": [
            "102.svg",
            "502.svg",
            "300",
            "晴朝の内一時雨",
            "OCCASIONAL SCATTERED SHOWERS IN THE MORNING, CLEAR DURING THE DAY"
        ],
        "122": [
            "112.svg",
            "512.svg",
            "300",
            "晴夕方一時雨",
            "CLEAR, OCCASIONAL SCATTERED SHOWERS IN THE EVENING"
        ],
        "123": [
            "100.svg",
            "500.svg",
            "100",
            "晴山沿い雷雨",
            "CLEAR IN THE PLAINS, RAIN AND THUNDER NEAR MOUTAINOUS AREAS"
        ],
        "124": [
            "100.svg",
            "500.svg",
            "100",
            "晴山沿い雪",
            "CLEAR IN THE PLAINS, SNOW NEAR MOUTAINOUS AREAS"
        ],
        "125": [
            "112.svg",
            "512.svg",
            "300",
            "晴午後は雷雨",
            "CLEAR, RAIN AND THUNDER IN THE AFTERNOON"
        ],
        "126": [
            "112.svg",
            "512.svg",
            "300",
            "晴昼頃から雨",
            "CLEAR, RAIN IN THE AFTERNOON"
        ],
        "127": [
            "112.svg",
            "512.svg",
            "300",
            "晴夕方から雨",
            "CLEAR, RAIN IN THE EVENING"
        ],
        "128": [
            "112.svg",
            "512.svg",
            "300",
            "晴夜は雨",
            "CLEAR, RAIN IN THE NIGHT"
        ],
        "130": [
            "100.svg",
            "500.svg",
            "100",
            "朝の内霧後晴",
            "FOG IN THE MORNING, CLEAR LATER"
        ],
        "131": [
            "100.svg",
            "500.svg",
            "100",
            "晴明け方霧",
            "FOG AROUND DAWN, CLEAR LATER"
        ],
        "132": [
            "101.svg",
            "501.svg",
            "100",
            "晴朝夕曇",
            "CLOUDY IN THE MORNING AND EVENING, CLEAR DURING THE DAY"
        ],
        "140": [
            "102.svg",
            "502.svg",
            "300",
            "晴時々雨で雷を伴う",
            "CLEAR, FREQUENT SCATTERED SHOWERS AND THUNDER"
        ],
        "160": [
            "104.svg",
            "504.svg",
            "400",
            "晴一時雪か雨",
            "CLEAR, SNOW FLURRIES OR OCCASIONAL SCATTERED SHOWERS"
        ],
        "170": [
            "104.svg",
            "504.svg",
            "400",
            "晴時々雪か雨",
            "CLEAR, FREQUENT SNOW FLURRIES OR SCATTERED SHOWERS"
        ],
        "181": [
            "115.svg",
            "515.svg",
            "400",
            "晴後雪か雨",
            "CLEAR, SNOW OR RAIN LATER"
        ],
        "200": [
            "200.svg",
            "200.svg",
            "200",
            "曇",
            "CLOUDY"
        ],
        "201": [
            "201.svg",
            "601.svg",
            "200",
            "曇時々晴",
            "MOSTLY CLOUDY"
        ],
        "202": [
            "202.svg",
            "202.svg",
            "300",
            "曇一時雨",
            "CLOUDY, OCCASIONAL SCATTERED SHOWERS"
        ],
        "203": [
            "202.svg",
            "202.svg",
            "300",
            "曇時々雨",
            "CLOUDY, FREQUENT SCATTERED SHOWERS"
        ],
        "204": [
            "204.svg",
            "204.svg",
            "400",
            "曇一時雪",
            "CLOUDY, OCCASIONAL SNOW FLURRIES"
        ],
        "205": [
            "204.svg",
            "204.svg",
            "400",
            "曇時々雪",
            "CLOUDY FREQUENT SNOW FLURRIES"
        ],
        "206": [
            "202.svg",
            "202.svg",
            "300",
            "曇一時雨か雪",
            "CLOUDY, OCCASIONAL SCATTERED SHOWERS OR SNOW FLURRIES"
        ],
        "207": [
            "202.svg",
            "202.svg",
            "300",
            "曇時々雨か雪",
            "CLOUDY, FREQUENT SCCATERED SHOWERS OR SNOW FLURRIES"
        ],
        "208": [
            "202.svg",
            "202.svg",
            "300",
            "曇一時雨か雷雨",
            "CLOUDY, OCCASIONAL SCATTERED SHOWERS AND/OR THUNDER"
        ],
        "209": [
            "200.svg",
            "200.svg",
            "200",
            "霧",
            "FOG"
        ],
        "210": [
            "210.svg",
            "610.svg",
            "200",
            "曇後時々晴",
            "CLOUDY, PARTLY CLOUDY LATER"
        ],
        "211": [
            "210.svg",
            "610.svg",
            "200",
            "曇後晴",
            "CLOUDY, CLEAR LATER"
        ],
        "212": [
            "212.svg",
            "212.svg",
            "300",
            "曇後一時雨",
            "CLOUDY, OCCASIONAL SCATTERED SHOWERS LATER"
        ],
        "213": [
            "212.svg",
            "212.svg",
            "300",
            "曇後時々雨",
            "CLOUDY, FREQUENT SCATTERED SHOWERS LATER"
        ],
        "214": [
            "212.svg",
            "212.svg",
            "300",
            "曇後雨",
            "CLOUDY, RAIN LATER"
        ],
        "215": [
            "215.svg",
            "215.svg",
            "400",
            "曇後一時雪",
            "CLOUDY, SNOW FLURRIES LATER"
        ],
        "216": [
            "215.svg",
            "215.svg",
            "400",
            "曇後時々雪",
            "CLOUDY, FREQUENT SNOW FLURRIES LATER"
        ],
        "217": [
            "215.svg",
            "215.svg",
            "400",
            "曇後雪",
            "CLOUDY, SNOW LATER"
        ],
        "218": [
            "212.svg",
            "212.svg",
            "300",
            "曇後雨か雪",
            "CLOUDY, RAIN OR SNOW LATER"
        ],
        "219": [
            "212.svg",
            "212.svg",
            "300",
            "曇後雨か雷雨",
            "CLOUDY, RAIN AND/OR THUNDER LATER"
        ],
        "220": [
            "202.svg",
            "202.svg",
            "300",
            "曇朝夕一時雨",
            "OCCASIONAL SCCATERED SHOWERS IN THE MORNING AND EVENING, CLOUDY DURING THE DAY"
        ],
        "221": [
            "202.svg",
            "202.svg",
            "300",
            "曇朝の内一時雨",
            "CLOUDY OCCASIONAL SCCATERED SHOWERS IN THE MORNING"
        ],
        "222": [
            "212.svg",
            "212.svg",
            "300",
            "曇夕方一時雨",
            "CLOUDY, OCCASIONAL SCCATERED SHOWERS IN THE EVENING"
        ],
        "223": [
            "201.svg",
            "601.svg",
            "200",
            "曇日中時々晴",
            "CLOUDY IN THE MORNING AND EVENING, PARTLY CLOUDY DURING THE DAY,"
        ],
        "224": [
            "212.svg",
            "212.svg",
            "300",
            "曇昼頃から雨",
            "CLOUDY, RAIN IN THE AFTERNOON"
        ],
        "225": [
            "212.svg",
            "212.svg",
            "300",
            "曇夕方から雨",
            "CLOUDY, RAIN IN THE EVENING"
        ],
        "226": [
            "212.svg",
            "212.svg",
            "300",
            "曇夜は雨",
            "CLOUDY, RAIN IN THE NIGHT"
        ],
        "228": [
            "215.svg",
            "215.svg",
            "400",
            "曇昼頃から雪",
            "CLOUDY, SNOW IN THE AFTERNOON"
        ],
        "229": [
            "215.svg",
            "215.svg",
            "400",
            "曇夕方から雪",
            "CLOUDY, SNOW IN THE EVENING"
        ],
        "230": [
            "215.svg",
            "215.svg",
            "400",
            "曇夜は雪",
            "CLOUDY, SNOW IN THE NIGHT"
        ],
        "231": [
            "200.svg",
            "200.svg",
            "200",
            "曇海上海岸は霧か霧雨",
            "CLOUDY, FOG OR DRIZZLING ON THE SEA AND NEAR SEASHORE"
        ],
        "240": [
            "202.svg",
            "202.svg",
            "300",
            "曇時々雨で雷を伴う",
            "CLOUDY, FREQUENT SCCATERED SHOWERS AND THUNDER"
        ],
        "250": [
            "204.svg",
            "204.svg",
            "400",
            "曇時々雪で雷を伴う",
            "CLOUDY, FREQUENT SNOW AND THUNDER"
        ],
        "260": [
            "204.svg",
            "204.svg",
            "400",
            "曇一時雪か雨",
            "CLOUDY, SNOW FLURRIES OR OCCASIONAL SCATTERED SHOWERS"
        ],
        "270": [
            "204.svg",
            "204.svg",
            "400",
            "曇時々雪か雨",
            "CLOUDY, FREQUENT SNOW FLURRIES OR SCATTERED SHOWERS"
        ],
        "281": [
            "215.svg",
            "215.svg",
            "400",
            "曇後雪か雨",
            "CLOUDY, SNOW OR RAIN LATER"
        ],
        "300": [
            "300.svg",
            "300.svg",
            "300",
            "雨",
            "RAIN"
        ],
        "301": [
            "301.svg",
            "701.svg",
            "300",
            "雨時々晴",
            "RAIN, PARTLY CLOUDY"
        ],
        "302": [
            "302.svg",
            "302.svg",
            "300",
            "雨時々止む",
            "SHOWERS THROUGHOUT THE DAY"
        ],
        "303": [
            "303.svg",
            "303.svg",
            "400",
            "雨時々雪",
            "RAIN,FREQUENT SNOW FLURRIES"
        ],
        "304": [
            "300.svg",
            "300.svg",
            "300",
            "雨か雪",
            "RAINORSNOW"
        ],
        "306": [
            "300.svg",
            "300.svg",
            "300",
            "大雨",
            "HEAVYRAIN"
        ],
        "308": [
            "308.svg",
            "308.svg",
            "300",
            "雨で暴風を伴う",
            "RAINSTORM"
        ],
        "309": [
            "303.svg",
            "303.svg",
            "400",
            "雨一時雪",
            "RAIN,OCCASIONAL SNOW"
        ],
        "311": [
            "311.svg",
            "711.svg",
            "300",
            "雨後晴",
            "RAIN,CLEAR LATER"
        ],
        "313": [
            "313.svg",
            "313.svg",
            "300",
            "雨後曇",
            "RAIN,CLOUDY LATER"
        ],
        "314": [
            "314.svg",
            "314.svg",
            "400",
            "雨後時々雪",
            "RAIN, FREQUENT SNOW FLURRIES LATER"
        ],
        "315": [
            "314.svg",
            "314.svg",
            "400",
            "雨後雪",
            "RAIN,SNOW LATER"
        ],
        "316": [
            "311.svg",
            "711.svg",
            "300",
            "雨か雪後晴",
            "RAIN OR SNOW, CLEAR LATER"
        ],
        "317": [
            "313.svg",
            "313.svg",
            "300",
            "雨か雪後曇",
            "RAIN OR SNOW, CLOUDY LATER"
        ],
        "320": [
            "311.svg",
            "711.svg",
            "300",
            "朝の内雨後晴",
            "RAIN IN THE MORNING, CLEAR LATER"
        ],
        "321": [
            "313.svg",
            "313.svg",
            "300",
            "朝の内雨後曇",
            "RAIN IN THE MORNING, CLOUDY LATER"
        ],
        "322": [
            "303.svg",
            "303.svg",
            "400",
            "雨朝晩一時雪",
            "OCCASIONAL SNOW IN THE MORNING AND EVENING, RAIN DURING THE DAY"
        ],
        "323": [
            "311.svg",
            "711.svg",
            "300",
            "雨昼頃から晴",
            "RAIN, CLEAR IN THE AFTERNOON"
        ],
        "324": [
            "311.svg",
            "711.svg",
            "300",
            "雨夕方から晴",
            "RAIN, CLEAR IN THE EVENING"
        ],
        "325": [
            "311.svg",
            "711.svg",
            "300",
            "雨夜は晴",
            "RAIN, CLEAR IN THE NIGHT"
        ],
        "326": [
            "314.svg",
            "314.svg",
            "400",
            "雨夕方から雪",
            "RAIN, SNOW IN THE EVENING"
        ],
        "327": [
            "314.svg",
            "314.svg",
            "400",
            "雨夜は雪",
            "RAIN,SNOW IN THE NIGHT"
        ],
        "328": [
            "300.svg",
            "300.svg",
            "300",
            "雨一時強く降る",
            "RAIN, EXPECT OCCASIONAL HEAVY RAINFALL"
        ],
        "329": [
            "300.svg",
            "300.svg",
            "300",
            "雨一時みぞれ",
            "RAIN, OCCASIONAL SLEET"
        ],
        "340": [
            "400.svg",
            "400.svg",
            "400",
            "雪か雨",
            "SNOWORRAIN"
        ],
        "350": [
            "300.svg",
            "300.svg",
            "300",
            "雨で雷を伴う",
            "RAIN AND THUNDER"
        ],
        "361": [
            "411.svg",
            "811.svg",
            "400",
            "雪か雨後晴",
            "SNOW OR RAIN, CLEAR LATER"
        ],
        "371": [
            "413.svg",
            "413.svg",
            "400",
            "雪か雨後曇",
            "SNOW OR RAIN, CLOUDY LATER"
        ],
        "400": [
            "400.svg",
            "400.svg",
            "400",
            "雪",
            "SNOW"
        ],
        "401": [
            "401.svg",
            "801.svg",
            "400",
            "雪時々晴",
            "SNOW, FREQUENT CLEAR"
        ],
        "402": [
            "402.svg",
            "402.svg",
            "400",
            "雪時々止む",
            "SNOWTHROUGHOUT THE DAY"
        ],
        "403": [
            "403.svg",
            "403.svg",
            "400",
            "雪時々雨",
            "SNOW,FREQUENT SCCATERED SHOWERS"
        ],
        "405": [
            "400.svg",
            "400.svg",
            "400",
            "大雪",
            "HEAVYSNOW"
        ],
        "406": [
            "406.svg",
            "406.svg",
            "400",
            "風雪強い",
            "SNOWSTORM"
        ],
        "407": [
            "406.svg",
            "406.svg",
            "400",
            "暴風雪",
            "HEAVYSNOWSTORM"
        ],
        "409": [
            "403.svg",
            "403.svg",
            "400",
            "雪一時雨",
            "SNOW, OCCASIONAL SCCATERED SHOWERS"
        ],
        "411": [
            "411.svg",
            "811.svg",
            "400",
            "雪後晴",
            "SNOW,CLEAR LATER"
        ],
        "413": [
            "413.svg",
            "413.svg",
            "400",
            "雪後曇",
            "SNOW,CLOUDY LATER"
        ],
        "414": [
            "414.svg",
            "414.svg",
            "400",
            "雪後雨",
            "SNOW,RAIN LATER"
        ],
        "420": [
            "411.svg",
            "811.svg",
            "400",
            "朝の内雪後晴",
            "SNOW IN THE MORNING, CLEAR LATER"
        ],
        "421": [
            "413.svg",
            "413.svg",
            "400",
            "朝の内雪後曇",
            "SNOW IN THE MORNING, CLOUDY LATER"
        ],
        "422": [
            "414.svg",
            "414.svg",
            "400",
            "雪昼頃から雨",
            "SNOW, RAIN IN THE AFTERNOON"
        ],
        "423": [
            "414.svg",
            "414.svg",
            "400",
            "雪夕方から雨",
            "SNOW, RAIN IN THE EVENING"
        ],
        "425": [
            "400.svg",
            "400.svg",
            "400",
            "雪一時強く降る",
            "SNOW, EXPECT OCCASIONAL HEAVY SNOWFALL"
        ],
        "426": [
            "400.svg",
            "400.svg",
            "400",
            "雪後みぞれ",
            "SNOW, SLEET LATER"
        ],
        "427": [
            "400.svg",
            "400.svg",
            "400",
            "雪一時みぞれ",
            "SNOW, OCCASIONAL SLEET"
        ],
        "450": [
            "400.svg",
            "400.svg",
            "400",
            "雪で雷を伴う",
            "SNOW AND THUNDER"
        ]
    }
