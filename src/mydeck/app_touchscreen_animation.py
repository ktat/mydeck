from PIL import Image, ImageDraw, ImageFont
from mydeck import MyDeck, TouchAppBase
import logging
import time
import random

# whole image size
X: int = 800
Y: int = 100


class AppTouchscreenAnimation(TouchAppBase):
    use_thread = True

    def __init__(self, mydeck: MyDeck, option: dict = {}):
        super().__init__(mydeck, option)
        self.size = 10
        self.x: list = [self.size, 800 - self.size]
        self.y: list = [self.size, 90 - self.size]
        self.sign_x: list = [1, -1]
        self.sign_y: list = [1, -1]
        self.time_to_sleep = 0.05
        self.speed = [
            3,
            5,
        ]

    def key_setup(self):
        pass

    def set_image_to_touchscreen(self):

        size05 = self.size * 0.5
        size20 = self.size * 2

        for i in range(2):
            self.x[i] += self.speed[i] * self.sign_x[i]
            self.y[i] += self.speed[i] * self.sign_y[i]

            if self.x[i] > 800 - size20:
                self.x[i] = 800 - size20
                self.sign_x[i] = -1
            if self.x[i] < size05:
                self.x[i] = size05
                self.sign_x[i] = 1

            if self.y[i] > 100 - size20:
                self.y[i] = 100 - size20
                self.sign_y[i] = -1
            if self.y[i] < size05:
                self.y[i] = size05
                self.sign_y[i] = 1

            if self.x[0] - self.x[0] % size20 == self.x[1] - self.x[1] % size20 and self.y[0] - self.y[0] % size20 == self.y[1] - self.y[1] % size20:
                self.x[0] += 5 * self.sign_x[0]
                self.x[1] -= 5 * self.sign_x[1]
                self.sign_x[0] *= -1
                self.sign_x[1] *= -1
                if self.sign_x[0] == self.sign_x[1]:
                    self.sign_x[0] *= -1
                self.speed = [self.speed[1], self.speed[0]]

        im = Image.new('RGB', (800, 100), (0, 0, 0))
        draw = ImageDraw.Draw(im)

        color = ["white", "yellow"]
        for i in range(2):
            draw.rectangle([self.x[i], self.y[i], self.x[i] + size20,
                            self.y[i] + size20], fill=color[i])

        self.mydeck.set_touchscreen(
            {"image": im, "x": 0, "y": 0, "width": 800, "height": 100})
