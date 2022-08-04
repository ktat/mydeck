# MySteamDeck

To use [STREAM DECK](https://www.elgato.com/ja/stream-deck) on Linux enviroment easily.

Check the following instruction at first when you haven't setup STREAM DECK.
https://onlinux.systems/guides/20220520_how-to-set-up-elgatos-stream-deck-on-ubuntu-linux-2204

## Dependency

[xdotool](https://manpages.ubuntu.com/manpages/trusty/man1/xdotool.1.html), python3-wand and python3-cairosvg are required.

Ubuntu:
```
apt install xdotool
apt install python3-wand
apt install python3-cairosvg
```

## CAUTION

This is an alpha version software and I don't know much about Python.

- Some code may be wrong for Python way
- Exception handlings are not yet coded at all
- I don't assume multiple STREAM DECK
- Currently, I only assume 15 key STREAM DECK

## How to run example

```
PYTHONPATH=src python3 example/main.py
```

## configuration rule

```yaml
PAGE_LABEL:
  key_number:
    "command": ["command", "options"]
    "chrome": ["profile name", "url"]
    "image_url": "https://example.com/path/to/image"
    "change_page: "ANOTHER_PAGE_NAME"
    "image": "image to display"
    "label": "label to display"
    "background_color": "white"
    "exit": 1
```

- PAGE_LABEL ... Name of the page or name of active window
- key_number ... It should be number, start from 0
- command ... OS command
- chrome ... launch chrome with profile. if image & image_url is not set, check url root path + /faviocn.ico and use it as image if it exists.
- image_url ... use url instead of image file path
- change_page ... change page when the button is pushed
- image ... an image shown on button
- label ... a label shown on button below the image
- background_color ... background color of the key
- exit ... can set 1 only. Exit app when the button is pushed

`command` and `change_page` can be used in same time.
In the case, command is executed and then page is changed.

configuration is live reload,
when you change yaml file, it is loaded when page is changed.

### PAGE_LABEL

- `@HOME` is special label. This configuration is used for first page.
- `@GAME` is reserved label for the page to collect games.
- `@previous` is also special label. It can be used for the value of `change_page`. When the button is pushed, go back to the previous page whose name isn't started with `~`.

If you set window title as PAGE_LABEL, page is changed according to active window.

## example

### configuration

```yaml
---
"apps":
  - app: Clock
    option:
      page_key:
        '@HOME': 5
        '@JOB': 12
  - app: StopWatch
    option:
      page_key:
        '@HOME': 6
  - app: Calendar
    option:
      page_key:
        '@home': 7
"alert":
   retry_interval: 60
   check_interval: 180
   key_config:
      7:
        command: ["google-chrome", '--profile-directory=Profile 1', 'https://example.com/nagios/cgi-bin/status.cgi?host=all&servicestatustypes=16&hoststatustypes=15']
        image: "./src/Assets/nagios.ico"
        change_page: '@previous'
"games":
  RandomNumber: 0
  Memory: 3
  TicTackToe: 7
  WhacAMole: 8
"key_config":
  "@HOME":
    0:
      "change_page": "@PRIVATE"
      "label": "Private"
      "image": "./src/Assets/ktat.png"
    1:
      "change_page": "@JOB"
      "label": "Job"
      "image": "./src/Assets/job.png"
    2:
      "change_page": "@GAME"
      "label": "Game"
      "image": "./src/Assets/game.png"
    10:
      "label": "Config"
      "image": "./src/Assets/settings.png"
      "change_page": "@CONFIG"
    14:
      "exit": 1
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
      "change_page": "@CONFIG"
    14:
      "change_page": "@HOME"
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
      "change_page": "@previous"
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
      "change_page": "@JOB"
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
      "change_page": "@JOB"
      "label": "Back"
      "image": "./src/Assets/back.png"
```

### main script

```python
from mystreamdeck import *

import os

CHECK_URL = 'https://example.com/'

def check_alert():
    res = requests.get(CHECK_URL)
    if res.status_code != requests.codes.ok:
        return True
    return False

if __name__ == "__main__":
    mydeck = MyStreamDeck(
        {
            'config': "./example/config/config.yml",
            'alert_func': check_alert,
	}
    )

    mydeck.deck_start()

    os.exit()
```

## LICENSE

MIT: https://ktat.mit-license.org/2016

## SEE ALSO

### python-elgato-streamdeck repository

https://github.com/abcminiuser/python-elgato-streamdeck

### icons

Some of icon are from the fowlloing:
https://remixicon.com/
