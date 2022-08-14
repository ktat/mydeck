import re
from mystreamdeck import BackgroundAppBase, MyStreamDeck
from typing import Optional

class WindowCheckBase(BackgroundAppBase):
    window_title_regexps = [
        [r'^Meet.+Google Chrome$', 'Meet - Google Chrome'],
        [r'^(Slack \|.+?\|.+?\|).+', '\g<1>'],
    ]

    def __init__ (self, mydeck: MyStreamDeck, config: dict = {}):
        super().__init__(mydeck)

        if config is not None and config.get('window_title_regexps'):
            self.window_title_regexps = config['window_title_regexps']

    def execute_in_thread(self):
        mydeck = self.mydeck
        if not mydeck.in_alert():
            new_result: str = self.get_current_window()

            if new_result is not None and new_result != mydeck._previous_window:
                mydeck._previous_window = new_result
                self.switch_page(new_result)

    def switch_page(self, page: str):
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
    def _get_current_window(self):
        print("implment it subclass")

    # replace specified strings from curent window name
    def get_current_window(self) -> Optional[str]:
        result: Optional[str] = self._get_current_window()
        if result is not None:
            for reg in self.window_title_regexps:
                r1 = reg[0]
                r2 = reg[1]
                result = re.sub(r1, eval('"' + r2 + '"'), str(result))
                result = re.sub(r"\n", "", str(result))
        return result
