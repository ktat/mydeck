from PIL import Image, ImageDraw, ImageFont
import datetime
import time
import sys

# whole image size
X = 100
Y = 100

class Calendar:
    # if app reuquire thread, true
    use_thread = True
    # dict: key is page name and value is key number.
    page_key = {}
    # need to stop thread
    stop = False

    previous_page = ''
    previous_date = ''

    option = {}
    key_command = {}

    def __init__(self, mydeck, option={}):
        self.mydeck = mydeck
        if option.get('page_key') is not None:
            self.page_key = option['page_key']

    def set_image_to_key(self, key, page):
        now = datetime.datetime.now()
        date_text = "{0:02d}/{1:02d}".format(now.month, now.day)

        # quit when page and date is not changed
        if page != self.previous_date or date_text != self.previous_page:
            self.previous_page = page
            self.previous_date = date_text
        else:
            return False

        im = Image.new('RGB', (X, Y), (0, 0, 0))
        font = ImageFont.truetype(self.mydeck.font_path, 34)
        draw = ImageDraw.Draw(im)
        wday = now.strftime('%a')
        color = "white"
        if wday in 'Sun':
            color="red"
        draw.text((12, 0), font=font, text=wday,fill=color)
        draw.text((0, 33), font=font, text=date_text, fill="white")
        font = ImageFont.truetype(self.mydeck.font_path, 30)
        draw.text((10, 73), font=font, text=str(now.year), fill="white")

        self.mydeck.update_key_image(
            key,
            self.mydeck.render_key_image(
                im,
                "",
                'black',
            )
        )

    # if use_thread is true, this method is call in thread
    def start(self):
        t = datetime.datetime.now()
        while True:
            try:
                page = self.mydeck.current_page()
                key  = self.page_key.get(page)
                if key is not None:
                    self.set_image_to_key(key, page)
            except Exception as e:
                print(e)
                pass
            # exit when main process is finished
            if self.mydeck._exit:
                break
            time.sleep(1)
        sys.exit()

    # No need to setup key, do notiong and return anything.
    def key_setup(self):
        return True
