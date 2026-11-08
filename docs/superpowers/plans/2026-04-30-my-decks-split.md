# my_decks.py 分割 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `src/mydeck/my_decks.py` (現 1763 行) を 5 ファイルに分割。`my_decks.py` 自体は ~280 行に縮小し、新規 4 ファイルもすべて 700 行未満に収める。`MyDeck` クラスは 2 mixin を継承する形で再構成する。

**Architecture:** Config と MyDeck を別ファイルに、MyDeck はさらに ImageMixin と HandlersMixin に分割。`my_decks.py` 末尾で re-import して既存の `from mydeck.my_decks import ...` 経路を維持。

**Tech Stack:** Python 3, pytest, uv.

**Spec:** `docs/superpowers/specs/2026-04-30-my-decks-split-design.md`

---

### Task 1: ベースライン記録

- [ ] **Step 1: 行数記録**

```bash
wc -l src/mydeck/my_decks.py
```
Expected: `1763 src/mydeck/my_decks.py`

- [ ] **Step 2: pytest baseline**

```bash
uv run pytest tests/ -x -q
```
Expected: `60 passed`

- [ ] **Step 3: 主要 import smoke check**

```bash
uv run python -c "
from mydeck.my_decks import (
    MyDecks, MyDeck, Config, ImageOrFile,
    ExceptionInvalidMyDecksConfig, ExceptionNoConfig,
    ExceptionNoDeckGiven, ExceptionWrongTypeGiven,
    ROOT_DIR, DEFAULT_PORT,
)
import mydeck.my_decks as m
names = sorted(n for n in dir(m) if not n.startswith('_'))
print('\n'.join(names))
" > /tmp/my_decks_before.txt
wc -l /tmp/my_decks_before.txt
```
Expected: 多数のシンボル (`Config`, `MyDeck`, `MyDecks`, `ImageOrFile`, `ROOT_DIR` 等を含む)。Task 5 の verify 用。

---

### Task 2: config.py を新規作成

**Files:**
- Create: `src/mydeck/config.py`

- [ ] **Step 1: 必要な範囲を抽出**

`main` の `src/mydeck/my_decks.py` 行 **1190-1740** が `class Config` の本体。これを byte-for-byte 移植。

- [ ] **Step 2: ファイルを書く**

`src/mydeck/config.py` を新規作成。先頭 import 群:

```python
"""Configuration class extracted from my_decks.py."""

from copy import deepcopy
import importlib
import logging
import os
import os.path
import re
import shutil
import sys
import traceback
import yaml
from typing import Any, Dict, List, Optional, Tuple, Union, TYPE_CHECKING

from .my_decks_manager import VirtualDeck

if TYPE_CHECKING:
    from .my_decks_app_base import App, AppBase, BackgroundAppBase, HookAppBase
```

その下に `class Config:` 以降の現 line 1190-1740 をそのまま貼り付ける。

実装メモ:
- 文字列フォワード参照 (`'MyDeck'`, `'AppBase'`, etc.) のため、これらの実体 import は不要 (TYPE_CHECKING ブロック内で参照可能にする)。
- 未使用の import は実装時に grep で確認しながら削除する。例えば `import sys` は Config 内で使われていなければ落として OK。

- [ ] **Step 3: import 確認**

```bash
uv run python -c "from mydeck.config import Config; print('Config OK')"
```
Expected: `Config OK`

- [ ] **Step 4: 行数確認**

```bash
wc -l src/mydeck/config.py
```
Expected: 700 未満 (~555 行)。

---

### Task 3: my_deck_image.py を新規作成

**Files:**
- Create: `src/mydeck/my_deck_image.py`

- [ ] **Step 1: 必要な範囲を抽出**

`main` の `my_decks.py` 行 **656-809** が image cluster の 9 メソッド (`determine_image_url` から `render_key_image` まで)。

- [ ] **Step 2: ファイルを書く**

`src/mydeck/my_deck_image.py`:

```python
"""Image / rendering mixin for MyDeck."""

import os
import re
import requests
import wand.image
from cairosvg import svg2png
from typing import Optional, TYPE_CHECKING

from PIL import Image, ImageDraw, ImageFont
from StreamDeck.ImageHelpers import PILHelper

from .lock import Lock
from .my_decks_manager import VirtualDeck

if TYPE_CHECKING:
    from .my_decks import ImageOrFile


class MyDeckImageMixin:
    """Image-handling methods for MyDeck.

    Depends on `self.deck`, `self.myname`, `self.font_path`, `self.debug()`,
    and `self.abs_key()` from MyDeck. Also depends on the module-level
    constant `ROOT_DIR` from `my_decks.py`, which is imported lazily inside
    methods that need it to avoid a circular import.
    """
```

そのクラス本体に、現 line 656-809 の 9 メソッドを byte-for-byte 移植する (4-space indent はそのまま)。

ただし、`ROOT_DIR` を参照するメソッド (`image_url_to_image` line 687 で使用) には**メソッド内で遅延 import**する:

```python
def image_url_to_image(self, conf: Optional[dict], url: Optional[str] = None):
    from .my_decks import ROOT_DIR  # lazy to avoid circular import
    """If conf has image_url ..."""
    image_url = None
    icon_file = None
    ...
```

`ImageOrFile` も `update_touchscreen_image` で使う:

```python
def update_touchscreen_image(self, conf: dict, use_lock: bool = True):
    from .my_decks import ImageOrFile  # lazy to avoid circular import
    ...
```

実装者注意:
- 既存メソッドが `Image.open(...)` のように `Image` (PIL) を使う箇所はそのまま動く。
- `from .my_decks_manager import VirtualDeck` は `update_touchscreen_image` の `deck: VirtualDeck = self.deck` で必要。

- [ ] **Step 3: import 確認**

```bash
uv run python -c "from mydeck.my_deck_image import MyDeckImageMixin; print('image mixin OK')"
```
Expected: `image mixin OK`

- [ ] **Step 4: 行数確認**

```bash
wc -l src/mydeck/my_deck_image.py
```
Expected: 700 未満 (~165 行)。

---

### Task 4: my_deck_handlers.py を新規作成

**Files:**
- Create: `src/mydeck/my_deck_handlers.py`

- [ ] **Step 1: 必要な範囲を抽出**

`main` の `my_decks.py` から **3 つの非連続レンジ**:
- **Setup cluster**: 行 558-655 (`has_page_key_config` 〜 `set_key`)
- **Callbacks cluster**: 行 810-952 (`touchscreen_change_callback` 〜 `key_change_callback`)
- **Config-write cluster**: 行 971-1084 (`set_key_config` 〜 `set_dial_conf`)

- [ ] **Step 2: ファイルを書く**

`src/mydeck/my_deck_handlers.py`:

```python
"""Handlers / setup / config-writers mixin for MyDeck."""

import datetime
import logging
import os
import re
import signal
import subprocess
import threading
import time
import traceback
from typing import Any, Callable, Dict, List, NoReturn, Optional, Union, TYPE_CHECKING

from PIL import Image

from .lock import Lock
from .my_decks_manager import VirtualDeck, DeckOutputWebHandler

if TYPE_CHECKING:
    from .my_decks_app_base import AppBase, BackgroundAppBase


class MyDeckHandlersMixin:
    """Setup, callback, and config-write methods for MyDeck.

    Depends on attributes (`self.deck`, `self.config`, `self._current_page`,
    etc.) and methods (`self.current_page()`, `self.update_key_image()`, ...)
    on MyDeck and MyDeckImageMixin.
    """
```

その下に、3 つの非連続レンジを以下の順で並べる:
1. Setup cluster (現 line 558-655)
2. Callbacks cluster (現 line 810-952)
3. Config-write cluster (現 line 971-1084)

各メソッドは **4-space indent のまま** を維持し、メソッド本体は **byte-for-byte 移植**する。

実装者注意:
- `set_current_page` (line 428) や `update_key_image` (line 739) を呼び出す箇所はそのまま `self.set_current_page(...)` / `self.update_key_image(...)` で OK (MyDeck の MRO で解決)。
- `set_command_config` (line 989) で `subprocess.run` を呼ぶ箇所がある場合は `import subprocess` が必要。grep で確認。

- [ ] **Step 3: import 確認**

```bash
uv run python -c "from mydeck.my_deck_handlers import MyDeckHandlersMixin; print('handlers mixin OK')"
```
Expected: `handlers mixin OK`

- [ ] **Step 4: 行数確認**

```bash
wc -l src/mydeck/my_deck_handlers.py
```
Expected: 700 未満 (~370 行)。

---

### Task 5: my_deck.py を新規作成

**Files:**
- Create: `src/mydeck/my_deck.py`

- [ ] **Step 1: 必要な範囲を抽出**

`main` の `my_decks.py` から `MyDeck` の **コア**メソッドのみ抽出:
- 行 255-557 (init + status + page management + connection management)
- 行 953-970 (alert/handler stops)
- 行 1085-1189 (threading_apps, abs_key, run_hook_apps, update_config)

抽出 **しない**: 行 558-655 (setup, → handlers mixin), 656-809 (image, → image mixin), 810-952 (callbacks, → handlers mixin), 971-1084 (config writers, → handlers mixin)

- [ ] **Step 2: ファイルを書く**

`src/mydeck/my_deck.py`:

```python
"""MyDeck core class. Methods are split across mixins:
- MyDeckImageMixin (image / rendering)
- MyDeckHandlersMixin (setup / callbacks / config writers)
"""

import logging
import os
import sys
import threading
import time
import traceback
from typing import Any, Callable, Dict, List, NoReturn, Optional, TYPE_CHECKING, Union

from PIL import Image, ImageDraw, ImageFont
from StreamDeck.Devices import StreamDeckOriginalV2

from .lock import Lock
from .my_deck_handlers import MyDeckHandlersMixin
from .my_deck_image import MyDeckImageMixin
from .my_decks_manager import VirtualDeck, DeckOutputWebHandler

if TYPE_CHECKING:
    from .my_decks_app_base import App, AppBase, BackgroundAppBase, HookAppBase
    from .my_decks import Config, ImageOrFile


class MyDeck(MyDeckImageMixin, MyDeckHandlersMixin):
    """Class to handle a single STREAM DECK device."""
```

その下に、上記抽出範囲の MyDeck メソッドを順序通りに貼り付ける。`_find_font` (260) は staticmethod なのでそのまま。

実装者注意:
- `from .app_web_server import AppWebServer` のような lazy import (現 line 1087) はそのままメソッド内に残す。
- MRO 順序: `(MyDeckImageMixin, MyDeckHandlersMixin)` — Image を先。これで MyDeck → ImageMixin → HandlersMixin → object の順。
- 文字列フォワード参照 (`'Config'`, `'AppBase'`, etc.) はそのまま使える。

- [ ] **Step 3: import 確認**

```bash
uv run python -c "
from mydeck.my_deck import MyDeck
from mydeck.my_deck_image import MyDeckImageMixin
from mydeck.my_deck_handlers import MyDeckHandlersMixin
assert MyDeckImageMixin in MyDeck.__mro__
assert MyDeckHandlersMixin in MyDeck.__mro__
assert hasattr(MyDeck, 'render_key_image'), 'image mixin missing'
assert hasattr(MyDeck, 'set_key_conf'), 'handlers mixin missing'
assert hasattr(MyDeck, '__init__'), 'core missing'
print('MRO + methods OK:', [c.__name__ for c in MyDeck.__mro__])
"
```
Expected: 全 assertion パス、MRO に MyDeckImageMixin と MyDeckHandlersMixin が含まれる。

- [ ] **Step 4: 行数確認**

```bash
wc -l src/mydeck/my_deck.py
```
Expected: 700 未満 (~440 行)。

---

### Task 6: my_decks.py を縮小

**Files:**
- Modify: `src/mydeck/my_decks.py`

このファイルは現状 1763 行で `Edit` フックがブロックする。`Write` ツールで全体を上書きする。

- [ ] **Step 1: 残すクラスのみで新内容を生成**

新 `my_decks.py` の構造:

```python
"""Base module to handle STREAM DECK devices"""

# import 群 (削減後、実装時に grep で要否確認)
import os
import os.path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

DEFAULT_PORT: int = 3000
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

if TYPE_CHECKING:
    from .my_decks_app_base import App, AppBase, BackgroundAppBase, HookAppBase


class ExceptionInvalidMyDecksConfig(Exception):
    pass


class MyDecks:
    """..."""
    # 現 line 41-244 を byte-for-byte 移植


class ExceptionNoConfig(Exception):
    pass


class ExceptionNoDeckGiven(Exception):
    pass


class ImageOrFile:
    """..."""
    # 現 line 1741-1760 を byte-for-byte 移植


class ExceptionWrongTypeGiven(Exception):
    pass


# Re-export so that existing import paths continue to work:
#   from mydeck.my_decks import MyDeck, Config
#   from mydeck import MyDeck, Config (via __init__.py's `from .my_decks import *`)
# Imports placed at end so module-level ROOT_DIR / ImageOrFile are available
# to my_deck_image (which lazy-imports ROOT_DIR and ImageOrFile from this module).
from .my_deck import MyDeck  # noqa: E402
from .config import Config  # noqa: E402
```

実装者注意:
- `MyDecks` クラスが使う import (`from .my_decks_manager import VirtualDeck, DeckOutputWebHandler`、`signal`、`time`、`logging`、`yaml` 等) は MyDecks 本体の参照を grep で確認した上で残す。
- `ImageOrFile` クラスが使う import (`from PIL import Image` 等) も必要なら残す。
- `from .my_decks_manager import VirtualDeck, DeckOutputWebHandler` は MyDecks 本体で使われている可能性が高いので残す。

- [ ] **Step 2: Write で書き換え**

現状 1763 行のファイルは Edit ブロック。`Write` ツールで全体置換する。

- [ ] **Step 3: 行数確認**

```bash
wc -l src/mydeck/my_decks.py
```
Expected: 700 未満 (~280 行 想定)。

```bash
grep -nE "^class (MyDecks|ExceptionInvalidMyDecksConfig|ExceptionNoConfig|ExceptionNoDeckGiven|ImageOrFile|ExceptionWrongTypeGiven)\b" src/mydeck/my_decks.py
```
Expected: 6 マッチ。

```bash
grep -nE "^class (MyDeck|Config)\b" src/mydeck/my_decks.py
```
Expected: 出力なし (extracted)。

- [ ] **Step 4: import smoke check**

```bash
uv run python -c "
from mydeck.my_decks import (
    MyDecks, MyDeck, Config, ImageOrFile,
    ExceptionInvalidMyDecksConfig, ExceptionNoConfig,
    ExceptionNoDeckGiven, ExceptionWrongTypeGiven,
    ROOT_DIR, DEFAULT_PORT,
)
print('all 10 symbols importable from mydeck.my_decks')
"
```
Expected: `all 10 symbols importable from mydeck.my_decks`

```bash
uv run python -c "
from mydeck import MyDeck, Config, ImageOrFile, ROOT_DIR, MyDecks
print('package re-exports OK')
"
```
Expected: `package re-exports OK`

- [ ] **Step 5: シンボル一覧 diff**

```bash
uv run python -c "
import mydeck.my_decks as m
names = sorted(n for n in dir(m) if not n.startswith('_'))
print('\n'.join(names))
" > /tmp/my_decks_after.txt
diff /tmp/my_decks_before.txt /tmp/my_decks_after.txt
echo "diff exit: $?"
```
Expected: 主要シンボル (Config, MyDeck, MyDecks, ImageOrFile, ROOT_DIR, DEFAULT_PORT, 例外群) が差分なし。差分があるとすれば、削除した import (例: `wand`, `cairosvg`, `requests`) のモジュール属性経由のリーケージのみ。これらが消えるのは想定内なので問題なし。

---

### Task 7: テスト実行

- [ ] **Step 1: pytest 全パス**

```bash
uv run pytest tests/ -x -q
```
Expected: `60 passed` (ベースラインと同じ)。

- [ ] **Step 2: import 健全性総合チェック**

```bash
uv run python -c "
import mydeck
import mydeck.web_server, mydeck.my_decks_manager, mydeck.my_decks
import mydeck.my_deck, mydeck.my_deck_image, mydeck.my_deck_handlers
import mydeck.config, mydeck.app_weather_jp
print('all imports OK')
"
```
Expected: `all imports OK`

- [ ] **Step 3: 主要 app_*.py の import チェック (ext-internal 経由の確認)**

```bash
uv run python -c "
import mydeck.app_alert, mydeck.app_clock, mydeck.app_bing_photo
import mydeck.app_weather_jp, mydeck.app_trigger
import mydeck.game_random_number
print('app modules import OK')
"
```
Expected: `app modules import OK`

これは `from mydeck import MyDeck, ROOT_DIR` 等が動くことの確認。

---

### Task 8: コミット

- [ ] **Step 1: 変更内容を確認**

```bash
git status
git diff --stat
```
Expected:
- `src/mydeck/my_decks.py` (modified, 大幅減)
- `src/mydeck/config.py` (new)
- `src/mydeck/my_deck.py` (new)
- `src/mydeck/my_deck_image.py` (new)
- `src/mydeck/my_deck_handlers.py` (new)

- [ ] **Step 2: コミット**

```bash
git add src/mydeck/my_decks.py src/mydeck/config.py src/mydeck/my_deck.py src/mydeck/my_deck_image.py src/mydeck/my_deck_handlers.py
git commit -m "$(cat <<'EOF'
refactor: split my_decks.py into config and MyDeck modules

Extract Config class to config.py. Split MyDeck across 3 files:
- my_deck.py: core (init, lifecycle, page management, threading)
- my_deck_image.py: MyDeckImageMixin (image / icon URL / rendering)
- my_deck_handlers.py: MyDeckHandlersMixin (setup, callbacks, config writers)

MyDeck inherits from (MyDeckImageMixin, MyDeckHandlersMixin) so all method
calls resolve via MRO. my_decks.py keeps MyDecks, exceptions, ImageOrFile,
ROOT_DIR, DEFAULT_PORT, and re-exports MyDeck and Config at the end so
existing import paths (from mydeck.my_decks import MyDeck, Config; from
mydeck import MyDeck, Config) continue to work via the package's
`from .my_decks import *` pattern.

Brings my_decks.py from 1763 lines to ~280, comfortably below the 700-line
edit-block limit. All new files are also < 700 lines.

Spec: docs/superpowers/specs/2026-04-30-my-decks-split-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 3: コミット確認**

```bash
git log --stat -1
```
Expected: 5 ファイル変更 (1 modified, 4 new)。

---

## Self-Review Notes

- ✅ Spec 全要件カバー: Config 抽出 (Task 2)、Image mixin (Task 3)、Handlers mixin (Task 4)、MyDeck core (Task 5)、my_decks.py 縮小 (Task 6)、シンボル互換性確認 (Task 6 Step 4-5)、pytest (Task 7)、app modules チェック (Task 7 Step 3)
- ✅ プレースホルダなし: 全レンジを行番号で指定、import 群を明示
- ✅ 名前一貫性: `MyDeckImageMixin`, `MyDeckHandlersMixin`, `my_deck_image.py`, `my_deck_handlers.py`, `config.py`, `my_deck.py` がすべての Task で一貫
- ✅ 循環参照対策: my_decks.py 末尾 re-import + mixin 内の lazy import (`from .my_decks import ROOT_DIR, ImageOrFile`)
