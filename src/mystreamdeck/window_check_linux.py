import time
import os
import sys
import subprocess
import re

from mystreamdeck import WindowCheckBase

class WindowCheckLinux(WindowCheckBase):
    # get curent window name
    def _get_current_window(self):
        result = None
        try:
            window_ids = subprocess.check_output(["xdotool", "getwindowfocus"]).decode().rsplit()
            if window_ids and len(window_ids) > 0:
                window_id = window_ids[0]
                result = subprocess.check_output(["xdotool", "getwindowname", window_id]).decode()
            return result
        except Exception as e:
            print(e)
            return result
