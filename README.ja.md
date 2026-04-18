# MyDeck

[English](README.md) | 日本語

MyDeck は実機の STREAM DECK を設定するためのツールです。
また、実機 STREAM DECK の状態をブラウザから確認・操作することもできます。
STREAM DECK 実機が無くても、ブラウザ上で仮想外付けキーボードとして使えます。

[![MyDeck Demo](youtube-thumbnail.png)](https://www.youtube.com/watch?v=PqSREyznhI4)

- [STREAM DECK](https://www.elgato.com/ja/stream-deck) を手軽に設定するため
- STREAM DECK 互換の仮想デバイスを使うため
- 仮想デバイス・実機デバイス両対応の Web インターフェース

STREAM DECK のセットアップ自体は [こちらの手順](https://onlinux.systems/guides/20220520_how-to-set-up-elgatos-stream-deck-on-ubuntu-linux-2204) を参照してください。

このパッケージは主に Linux 環境を想定していますが、`app_window_check_linux` 以外は Linux 依存はありません。テスト済みなのは Ubuntu 22.04 のみですが、他の環境でも動作するはずです。

## 依存パッケージ

システムパッケージ:

- [xdotool](https://manpages.ubuntu.com/manpages/trusty/man1/xdotool.1.html) — アクティブウィンドウ検知(`app_window_check_linux`)で使用
- ImageMagick のライブラリ(`python3-wand` 用)
- `cairo` / `libzbar0` (TOTP 登録時の QR スキャン)
- GNOME Keyring (または `secretstorage` 互換のバックエンド) — TOTP シークレット保存先

Ubuntu の場合:

```
apt install xdotool libmagickwand-dev libcairo2-dev libzbar0 gnome-keyring
```

Python 依存 (`pip install .` で自動インストール):

- `streamdeck`, `Pillow`, `wand`, `cairosvg`
- `pyyaml`, `requests`, `qrcode`, `netifaces`
- `python-daemon`, `pidfile`, `psutil`
- `pyotp`, `pyzbar`, `keyring` (TOTP 2FA アプリ用)

## 注意

まだ alpha 品質のソフトウェアです。

- Python 流儀に沿っていないコードが残っている可能性があります
- `MyDeck` / `MyDecksManager` 周りの API は変わる可能性があります

## 使い方

STREAM DECK 実機が無くても動きます。

1. コードを clone
2. `pip install .` で `mydeck` コマンドがインストールされる
3. `mydeck` を実行
4. ブラウザで `http://127.0.0.1:3000` を開いて deck を設定

### `mydeck` の CLI オプション

| オプション | デフォルト | 説明 |
|---|---|---|
| `--port` | `3000` | Web サーバのポート |
| `--config-path` | `~/.config/mydeck` | デバイス毎の YAML 設定を置くディレクトリ |
| `--log-level` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL` のいずれか |
| `--vdeck` | off | 物理デバイスが無くても仮想 deck で起動する |
| `--no-qr` | off | 起動時の Web UI URL の QR コード表示を省略 |
| `-d` | off | デーモンとして起動 (PID ファイルは `--config-path` 配下) |
| `--stop` | — | 稼働中のデーモンを停止 |
| `--restart` | — | 稼働中のデーモンを停止して、新しく起動し直す |

### デバイスの切断耐性

STREAM DECK の USB を抜いたり、ノート PC がサスペンド/レジュームしても `mydeck` プロセスは落ちません。バックグラウンドの supervisor が 3 秒毎に再列挙し、デバイスが戻ってきたら自動で再接続して、切断前に表示していたページとアプリを復元します。過去に起動したことのある serial のデバイスなら、起動時に接続されていなくても OK です — 後から差し込めば自動でアタッチされます。

### TOTP 2FA アプリ (`AppTotp`)

Web UI から TOTP アカウントを登録(シークレット手入力、`otpauth://` URI、QR画像アップロード、カメラスキャン)すると、6桁の現在コードとカウントダウンリングを STREAM DECK のキー上にリアルタイム表示します。シークレットは GNOME Keyring に、アカウントのメタ情報は `~/.config/mydeck/totp_accounts.json` に保存されます。専用ページ `@TOTP_ACCOUNTS` は自動生成されるので、任意のキーに `change_page: '@TOTP_ACCOUNTS'` を指定してリンクできます。

### 外部プラグイン (サードパーティアプリ)

YAML の `app:` / `game:` には、組み込みの短名 (`Clock` → `mydeck.app_clock.AppClock`) だけでなく、ドット付きのフル修飾パスを書けます。これにより外部パッケージとして配布されたプラグインを読み込めます:

```yaml
apps:
  - app: my_plugin.apps.Weather      # my_plugin.apps.Weather を import
    option:
      page_key:
        '@HOME': 3
games:
  - game: my_plugin.games.MyGame     # my_plugin.games.MyGame を import
```

プラグインを独立パッケージとして配布する場合は、`mydeck` と同じ Python 環境にインストール(例: `pip install my_plugin`)し、YAML ではその import path をそのまま書きます。プラグインクラスは `mydeck.my_decks_app_base` 配下の基底クラス (`ThreadAppBase`, `BackgroundAppBase`, `HookAppBase`, `TouchAppBase`, `GameAppBase`) を継承してください — 契約とライフサイクルの詳細は `docs/make_your_app.md` にあります。

## `mydeck` をインストールせずに example を動かす場合

### STREAM DECK 実機を持っている場合

```
PYTHONPATH=src python3 example/main.py
```

### STREAM DECK 実機を持っていない場合

```
PYTHONPATH=src python3 example/main_virtual.py
```

その後、ブラウザで以下の URL を開いてください。

http://localhost:3000/

ポートをデフォルト 3000 から変えたい場合は第 1 引数でポート番号を渡します。

```
PYTHONPATH=src python3 example/main_virtual.py 3001
```

## 設定

### 仮想 Deck の設定

仮想 deck を使うときは `mydeck` コマンドが初回に自動で作ってくれるので、手動で編集する必要はありません。

```yaml
1: # ID
  key_count: 4
  columns: 2
  serial_number: 'dummy1'
2: # ID
  key_count: 6
  columns: 3
  serial_number: 'dummy2'
```

### ページ設定のルール

設定ファイルは Web インターフェースから編集できます。

```yaml
page_config:
  PAGE_LABEL:
    keys:
      KEY_NUMBER:
        "command": ["command", "options"]
        "chrome": ["profile name", "url"]
        "image_url": "https://example.com/path/to/image"
        "change_page: "ANOTHER_PAGE_NAME"
        "image": "image to display"
        "label": "label to display"
        "background_color": "white"
        "exit": 1
```

- PAGE\_LABEL ... ページ名、またはアクティブウィンドウ名
- KEY\_NUMBER ... キー番号(0 始まり)
- command ... OS 側のコマンド
- chrome ... 指定プロファイルで Chrome を起動。`image` / `image_url` が無い場合は url のルート + `/favicon.ico` を画像として使う
- image\_url ... 画像ファイルパスの代わりに URL を指定
- change\_page ... ボタンを押したらページ遷移
- image ... ボタン上に表示する画像
- label ... 画像の下に表示するラベル
- background\_color ... キーの背景色
- exit ... `1` のみ有効。押すとアプリを終了する

`command` と `change_page` は併用可能です。併用時はコマンドを実行してからページを切り替えます。

#### YAML 設定のライブリロード

設定ファイルは mtime が変わると自動で再読込されますが、実際に反映されるのは `key_touchscreen_setup()` が走るタイミング — つまり **ページ切り替え時** です。inotify 的なファイル監視はしていません。

- 既にインストール済みアプリへの編集(キーの追加・削除・位置変更、オプション変更): そのデッキでページ遷移した次のタイミングで反映
- **新しい** Python パッケージ(新しいドットパスで指定するプラグイン等)のインストール: `mydeck` の **再起動が必要** (`mydeck --restart -d`)。Python はインタプリタ起動時にしか `site-packages` / `.pth` を見ないため、稼働中のプロセスでは `pip install` したプラグインが見えません
- 既にロード済みのアプリのコード変更(組み込みの `app_*.py` を書き換えた場合など): こちらも再起動が必要 — `importlib` がモジュールをキャッシュするため

#### PAGE\_LABEL

- `@HOME` は特別なラベル。最初のページとして使われる
- `@GAME` はゲームを集めたページ用の予約ラベル
- `@previous` も特別なラベル。`change_page` の値に指定でき、押すと(`~` で始まらない)直前のページに戻る

ウィンドウタイトルを PAGE\_LABEL にすると、アクティブウィンドウに応じてページが切り替わります。

#### 例

##### 設定

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
  - game: RandomNumber
  - game: Memory
  - game: TicTackToe
  - game: WhacAMole
"page_config":
  "@HOME":
    keys:
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
    keys:
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
    keys:
      0:
        "command": ["google-chrome", '--profile-directory=Profile 1']
        "image": "/usr/share/icons/hicolor/256x256/apps/google-chrome.png"
        "label": "Chrome(JOB)"
  "@CONFIG":
    keys:
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
    keys:
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
    kyes:
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

### メインスクリプト

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
    mydecks = MyStreamDecks(
        {
            'server_port': 3001, # default is 3000
            'config': {
               'file': "./example/config/config.yml",
               'alert_func': check_alert,
            },
      	}
    )

    mydecks.start_decks()

    os.exit()
```

複数デバイスを持っている場合:

```python
if __name__ == "__main__":
    mydecks = MyStreamDecks({
        'server_port': 3001, # default is 3000
        'decks': {
            'SERIAL_KEY_1': 'name1',
            'SERIAL_KEY_2': 'name2',
        },
        'configs': {
            'name1': {
                'file': "/path/to/config1.yml",
                'alert_func': check_alert,
            },
            'name2': {
                'file': "/path/to/config2.yml",
            },
        }
    })

    mydecks.start_decks()
```

実機デバイスを持っていない場合:

```yaml
if __name__ == "__main__":
    mydecks = MyStreamDecks({
        'vdeck_config': "example/config/vdeck.yml",
        'decks': {
            'dummy1': '4key-dummy',
            'dummy2': '6key-dummy',
            'dummy3': '15key-dummy',
        },
        'configs': {
            '6key': {
                'file': "example/config/config2.yml",
            },
            '4key-dummy': {
                'file': "example/config/config-d1.yml",
            },
            '6key-dummy': {
                'file': "example/config/config-d2.yml",
            },
            '15key-dummy': {
                'file': "example/config/config.yml",
                'alert_func': check_alert,
            },
        }

    })

    mydecks.start_decks(True)
```

## LICENSE

MIT: https://ktat.mit-license.org/2016

## 関連情報

### python-elgato-streamdeck リポジトリ

https://github.com/abcminiuser/python-elgato-streamdeck

### アイコン

一部のアイコンは以下から取得しています:
https://remixicon.com/
