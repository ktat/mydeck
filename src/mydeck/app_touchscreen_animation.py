from PIL import Image, ImageDraw, ImageFont
from mydeck import MyDeck, TouchAppBase
import logging
import time
import random

# whole image size
X: int = 800
Y: int = 100


class AppTouchscreenAnimation(TouchAppBase):
    class Rect:
        def __init__(self, x: int, y: int, sign_x: int, sign_y: int, speed: int, size: int):
            self.x: int = x
            self.y: int = y
            self.sign_x: int = sign_x
            self.sign_y: int = sign_y
            self.speed: int = speed
            self.size: int = size

    use_thread: bool = True

    def __init__(self, mydeck: MyDeck, option: dict = {}):
        super().__init__(mydeck, option)
        self.rectangles: list[AppTouchscreenAnimation.Rect] = []
        self.time_to_sleep: float = 0.05
        self.wait: int = 0
        self.color: list[str] = ["white", "yellow", "red", "blue", "green", "purple",
                                 "orange", "pink", "cyan", "brown", "gray", "magenta"]
        self.add_object()
        self.add_object()
        self.add_object()

    def key_setup(self):
        pass

    def add_object(self):
        if len(self.rectangles) == len(self.color):
            return

        x: int = random.randint(0, 780)
        y: int = random.randint(0, 80)
        sign_x: int = random.choice([1, -1])
        sign_y: int = random.choice([1, -1])
        speed: int = random.randint(2, 6)
        size: int = random.randint(2, 10)
        self.rectangles.append(AppTouchscreenAnimation.Rect(
            x, y, sign_x, sign_y, speed, size))

    def set_image_to_touchscreen(self):

        for i in range(len(self.rectangles)):
            rectangle = self.rectangles[i]
            size05 = rectangle.size * 0.5
            size20 = rectangle.size * 2

            x, y, sign_x, sign_y, speed = rectangle.x, rectangle.y, rectangle.sign_x, rectangle.sign_y, rectangle.speed
            x += speed * sign_x
            y += speed * sign_y

            if x > 800 - size20:
                x = 800 - size20
                sign_x = -1
            if x < size05:
                x = size05
                sign_x = 1

            if y > 100 - size20:
                y = 100 - size20
                sign_y = -1
            if y < size05:
                y = size05
                sign_y = 1

            self.rectangles[i] = AppTouchscreenAnimation.Rect(
                x, y, sign_x, sign_y, speed, rectangle.size)

            for j in range(len(self.rectangles) - 1):
                for k in range(len(self.rectangles)):
                    if j == k:
                        continue

                    rect1 = self.rectangles[j]
                    rect2 = self.rectangles[k]
                    if (
                        rect1.x - rect1.x % size20 == rect2.x - rect2.x % size20 and
                        rect1.y - rect1.y % size20 == rect2.y - rect2.y % size20
                    ):
                        rect1.x += 5 * rect1.sign_x
                        rect2.x -= 5 * rect2.sign_x
                        rect1.sign_x *= -1
                        rect2.sign_x *= -1
                        if rect1.sign_x == rect2.sign_x:
                            rect1.sign_x *= -1
                        sp1 = rect1.speed
                        sp2 = rect2.speed
                        rect1.speed = sp2
                        rect2.speed = sp1
                        if self.wait < time.time_ns():
                            self.add_object()
                            self.wait = time.time_ns() + 1000000000 * 2

        im = Image.new("RGB", (800, 100), (0, 0, 0))
        draw = ImageDraw.Draw(im)

        for i in range(len(self.rectangles)):
            rectangle = self.rectangles[i]
            selected_color = self.color[i]
            draw.rectangle(
                [rectangle.x, rectangle.y, rectangle.x +
                    rectangle.size * 2, rectangle.y + rectangle.size * 2],
                fill=selected_color,
            )

        self.mydeck.set_touchscreen(
            {"image": im, "x": 0, "y": 0, "width": 800, "height": 100}
        )
