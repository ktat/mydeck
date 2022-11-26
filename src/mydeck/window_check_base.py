import re
import logging

from mydeck import BackgroundAppBase, MyDeck
from typing import Optional

class WindowCheckBase(BackgroundAppBase):
    """A base class to check active window. Don't use this class directly."""
    window_title_regexps = [
        [r'^Meet.+Google Chrome$', 'Meet'],
        [r'^(Slack \|.+?\|.+?\|).+', '\g<1>'],
        [r'^.+  YouTube.+Google Chrome$', 'YouTube'],
    ]

    def __init__ (self, mydeck: MyDeck, config: dict = {}):
        """'window_title_regexps' is a dict whose key is regexp and value is a replacement like the following
        {
          [r'^Meet.+Google Chrome$', 'Meet'],
          [r'^(Slack \|.+?\|.+?\|).+', '\g<1>'],
          [r'^.+  YouTube.+Google Chrome$', 'YouTube'],
        }
        Normaly, they are given from configuration file like the following.

        - app: 'WindowCheckLinux'
          option:
            window_title_regexps:
              - ['^Meet.+Google Chrome$', 'Meet - Google Chrome']
              - ['^(Slack \|.+?\|).+$', '\g<1>']
              - ['^.+ YouTube.+Google Chrome$', 'YouTube']
              - ['^Amazon.co.jp:.+ Prime Video.+Google Chrome$', 'Prime Video']
        """
        super().__init__(mydeck)

        if config is not None and config.get('window_title_regexps'):
            self.window_title_regexps = config['window_title_regexps']

    def execute_in_thread(self):
        """The method it is called in application thread."""
        mydeck = self.mydeck
        if not mydeck.in_alert():
            new_result: str = self.get_current_window()

            if new_result is not None and new_result != mydeck._previous_window:
                logging.debug(new_result)
                mydeck._previous_window = new_result
                self.switch_page(new_result)

    def switch_page(self, page: str):
        """If the page exists for current active window, change current page."""
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

    def _get_current_window(self) -> Optional[str]:
        """Get curent window name. It should be implmented in subclass."""
        logging.critical("implment it subclass")
        return None

    def get_current_window(self) -> Optional[str]:
        """replace specified strings from curent window name"""
        result: Optional[str] = self._get_current_window()
        if result is not None:
            for reg in self.window_title_regexps:
                r1 = reg[0]
                r2 = reg[1]
                result = re.sub(r1, eval('"' + r2 + '"'), str(result))
                result = re.sub(r"\n", "", str(result))
        return result

