# MySteamDeck

To use [STREAM DECK](https://www.elgato.com/ja/stream-deck) on Linux enviroment easily.

### Dependency

[xdotool](https://manpages.ubuntu.com/manpages/trusty/man1/xdotool.1.html) is required.

Ubuntu:
```
apt install xdotool
```

### CAUTION

This is alpha version software and I don't know much about Python.

- Some code may be wrong for Python way.
- Exception handlings are not yet coded at all.

## configuration rule

```yaml
`PANEL_LABEL`:
  key_number:
    "command": ["command", "options"]
    "change_panel: "ANOTHER_PANEL_NAME"
    "image": "image to display"
    "label": "label to display"
```

- PANEL_LABEL ... Name of panel
- key_number ... It should be number, start from 0.
- command ... OS command
- change_panel ... change panel when the button is pushed.
- image ... an image shown on button
- label ... a label shown on button below the image

`command` and `change_panel` can be used in same time.
In the case, command is executed and then panel is changed.

configuration is live reload, 
when you change yaml file, it is loaded when panel is changed.

### PANEL_LABEL

`@HOME` is special label. This configuration is used for first panel.
`@previous` is also special label. It can be used for the value of `change_panel`. 
When the button is pushed, go back to the previous panel whose name isn't started with `~`.

## example

### configuration

```yaml
---
"@HOME":
  0: 
    "change_panel": "@PRIVATE"
    "label": "Private"
    "image": "./src/Assets/ktat.png"
  1: 
    "change_panel": "@JOB"
    "label": "Job"
    "image": "./src/Assets/job.png"
  2: 
    "change_panel": "@GAME"
    "label": "Game"
    "image": "./src/Assets/game.png"
  10: 
    "label": "Config"
    "image": "./src/Assets/settings.png"
    "change_panel": "@CONFIG"
  14: 
    "name": "exit"
    "image": "./src/Assets/exit.png"
    "label": "Exit"
"@PRIVATE": 
  0: 
    "command": ["google-chrome", "--profile-directory=Default"]
    "image": "/usr/share/icons/hicolor/256x256/apps/google-chrome.png"
    "label": "Chrome(PRIVATE)"
  10: 
    "label": "Config"
    "image": "./src/Assets/settings.png"
    "change_panel": "@CONFIG"
  14: 
    "change_panel": "@HOME"
    "image": "./src/Assets/home.png"
"@JOB": 
  0: 
    "command": ["google-chrome", '--profile-directory=Profile 1']
    "image": "/usr/share/icons/hicolor/256x256/apps/google-chrome.png"
    "label": "Chrome(JOB)"
"@CONFIG": 
  0: 
    "label": "Audio"
    "command": ["pavucontrol", "--tab=4"]
    "image": "./src/Assets/audio.png"
  1: 
    "label": "Sound"
    "command": ["gnome-control-center", "sound"]
    "image": "./src/Assets/sound.png"
  2: 
    "label": "Display"
    "command": ["gnome-control-center", "display"]
    "image": "./src/Assets/display.png"
  14: 
    "change_panel": "@previous"
    "image": "./src/Assets/back.png"
    "label": "Back"
"Meet - Google Chrome": 
  0: 
    "command": ["echo", "meet"]
    "image": "./src/Assets/meet.png"
    "label": "Google Meet"
  1: 
    "command": ["xdotool", "key", "ctrl+d"]
    "image": "./src/Assets/mute.png"
    "label": "mute"
  2: 
    "command": ["xdotool", "key", "ctrl+e"]
    "image": "./src/Assets/video.png"
    "label": "camera"
  10: 
    "label": "Audio"
    "command": ["pavucontrol", "--tab=4"]
    "image": "./src/Assets/audio.png"
  11: 
    "label": "Sound"
    "command": ["gnome-control-center", "sound"]
    "image": "./src/Assets/sound.png"
  14: 
    "change_panel": "@JOB"
    "label": "Back"
    "image": "./src/Assets/back.png"
"Zoom Meeting": 
  0: 
    "command": ["echo", "zoom"]
    "image": "./src/Assets/zoom.png"
    "label": "Zoom"
  1: 
    "command": ["xdotool", "key", "alt+a"]
    "image": "./src/Assets/mute.png"
    "label": "mute"
  2: 
    "command": ["xdotool", "key", "alt+v"]
    "image": "./src/Assets/video.png"
    "label": "camera"
  10: 
    "label": "Audio"
    "command": ["pavucontrol", "--tab=4"]
    "image": "./src/Assets/audio.png"
  11: 
    "label": "Sound"
    "command": ["gnome-control-center", "sound"]
    "image": "./src/Assets/sound.png"
  14: 
    "change_panel": "@JOB"
    "label": "Back"
    "image": "./src/Assets/back.png"
```

### main script

```python
from mystreamdeck.configure import MyStreamDeck
from mystreamdeck.alert import MyStreamDeckAlert
from mystreamdeck.random_number import MyStreamDeckGameRandomNumber
from mystreamdeck.memory import MyStreamDeckGameMemory
from mystreamdeck.tictacktoe import MyStreamDeckGameTickTacToe

import os
import signal
import time
import psutil
import requests
import json
import threading

from StreamDeck.DeviceManager import DeviceManager

# NAGIOS JSON URL
NAGIOS_URL = 'https://example.com/nagios/cgi-bin/nagios2json.cgi?hostprops=2&serviceprops=2&servicestatustypes=24'
ALERT_CHECK_INTERVAL = 60
_ALERT_KEY_CONFIG = {
    "command": ["google-chrome", '--profile-directory=Profile 1', 'https://exapmle.com/nagios/cgi-bin/status.cgi?host=all&servicestatustypes=16&hoststatustypes=15'],
    "image": "./src/Assets/nagios.ico",
    "label": "nagios",
    "change_panel": "@previous"
}

ALERT_KEY_CONFIG = {
    0: _ALERT_KEY_CONFIG,
    1: _ALERT_KEY_CONFIG,
    5: _ALERT_KEY_CONFIG,
    7: _ALERT_KEY_CONFIG,
    10: _ALERT_KEY_CONFIG,
    13: _ALERT_KEY_CONFIG,
    14: _ALERT_KEY_CONFIG,
    9: _ALERT_KEY_CONFIG,
    4: _ALERT_KEY_CONFIG,
}

# function to check alert
def check_alert():
    res = requests.get(NAGIOS_URL)
    if res.status_code == requests.codes.ok:
        data = json.loads(res.text)
        alerts = data.get("data")

        if alerts and len(alerts) > 0:
	   print(alerts_for_check)
           return True

    return False


if __name__ == "__main__":
    mydeck = MyStreamDeck({'config': "/path/to/config.yml"})
    MyStreamDeckGameRandomNumber(mydeck)
    MyStreamDeckGameMemory(mydeck, "", 3)
    MyStreamDeckGameTickTacToe(mydeck, "", 6)  
    mydeck_alert = MyStreamDeckAlert(mydeck, ALERT_CHECK_INTERVAL, ALERT_KEY_CONFIG)
    
    current_pid = os.getpid()
    child_pid = os.fork()

    if child_pid == 0:
        # child process
        mydeck.register_singal_handler()

        streamdecks = DeviceManager().enumerate()
        print("Found {} Stream Deck(s).\n".format(len(streamdecks)))

        for index, deck in enumerate(streamdecks):
            # This example only works with devices that have screens.
            if not deck.is_visual():
                continue

            mydeck.deck = deck
            deck.open()
            mydeck.key_setup()

            # Wait until all application threads have terminated (for this example,
            # this is when all deck handles are closed).
            for t in threading.enumerate():
                try:
                    t.join()
                except RuntimeError:
                    pass

        os._exit(0)
    else:
        # parent process
        mydeck.child_pid = child_pid
        mydeck.register_singal_handler_for_parent()
        mydeck_alert.register_check_function(check_alert)
        while True:
            time.sleep(1)
            
            if psutil.pid_exists(child_pid):
                mydeck_alert.check_alert()
                mydeck.check_window_switch()
            else:
                break
```

## SEE ALSO

### python-elgato-streamdeck repository

https://github.com/abcminiuser/python-elgato-streamdeck

### icons

Some of icon are from the fowlloing:
https://remixicon.com/
