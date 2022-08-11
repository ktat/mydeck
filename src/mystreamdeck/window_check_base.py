import time
import os
import sys
from mystreamdeck import BackgroundAppBase

class WindowCheckBase(BackgroundAppBase):
    # if app reuquire thread, true
    use_thread = True
    # need to stop thread
    stop = False

    in_working = False
    is_background_app = True

    _window_title_regexps = [
        [r'^Meet.+Google Chrome$', 'Meet - Google Chrome'],
        [r'^(Slack \|.+?\|.+?\|).+', '\\1'],
    ]

    def execute_in_thread(self):
        mydeck = self.mydeck
        if not mydeck.in_alert():
            new_result = self.get_current_window()

            if new_result is not None and new_result != mydeck._previous_window:
                mydeck._previous_window = new_result
                self.switch_page(new_result)

    def switch_page(self, page):
        mydeck = self.mydeck
        # enabled when alert is off and not playing game
        if not mydeck.in_alert() and not mydeck.in_game_status():
            current_page = mydeck.current_page()
            previous_page = mydeck.previous_page()

            if mydeck.key_config().get(page):
                mydeck.set_current_page(page)
                # when no configuration for window and current_page is not started with '@', set previous_page
            elif current_page[0:1] != '@':
                mydeck.set_current_page(mydeck.pop_last_previous_page())

    # get curent window name
    def get_current_window(self):
        print("implment it subclass")
