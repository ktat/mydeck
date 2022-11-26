import subprocess
import logging
from typing import Optional
from mydeck import WindowCheckBase

class AppWindowCheckLinux(WindowCheckBase):
    """Get curent window name for Linux environment using xdotool"""
    def _get_current_window(self) -> Optional[str]:
        try:
            window_ids: list[str] = subprocess.check_output(["xdotool", "getwindowfocus"]).decode().rsplit()
            if window_ids and len(window_ids) > 0:
                window_id: str = window_ids[0]
                result: str = subprocess.check_output(["xdotool", "getwindowname", window_id]).decode()
            return result
        except Exception as e:
            logging.critical(e)
            return None
