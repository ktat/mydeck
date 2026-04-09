import subprocess
import logging
from typing import Optional
from mydeck import WindowCheckBase

class AppWindowCheckLinux(WindowCheckBase):
    """Get current window name for Linux environment using xdotool"""
    def _get_current_window(self) -> Optional[str]:
        try:
            window_id: str = subprocess.check_output(
                ["xdotool", "getwindowfocus"], stderr=subprocess.DEVNULL
            ).decode().strip()
            if not window_id:
                return None
            return subprocess.check_output(
                ["xdotool", "getwindowname", window_id], stderr=subprocess.DEVNULL
            ).decode().strip()
        except FileNotFoundError:
            logging.error("Dependency missing: 'xdotool' is not installed on this system.")
        except subprocess.CalledProcessError as e:
            logging.error(f"xdotool command failed: {e}")
        except Exception as e:
            logging.error(f"Unexpected error retrieving window name: {e}")
        return None
