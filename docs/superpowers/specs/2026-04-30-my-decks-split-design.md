# my_decks.py 分割 リファクタリング設計

Date: 2026-04-30

## Overview

`src/mydeck/my_decks.py` (現在 1763 行) が `~/.claude/hooks/check-file-size.sh` の 700 行ブロック上限に大きく抵触している。`MyDeck` クラス (935 行) と `Config` クラス (551 行) のいずれも単独で 500 行超のため、ファイル全体を**論理的な責務単位で 5 ファイルに分割**する。

スコープ:

- 機能変更なし。純粋な構造リファクタ。
- 外部公開シンボル (`MyDecks`, `MyDeck`, `Config`, `ImageOrFile`, `ExceptionInvalidMyDecksConfig`, `ExceptionNoConfig`, `ExceptionNoDeckGiven`, `ExceptionWrongTypeGiven`, `ROOT_DIR`, `DEFAULT_PORT`) の import パスは保持:
  - `from mydeck import MyDecks, MyDeck, ImageOrFile, ROOT_DIR` (`__init__.py` 経由) — 動作不変
  - `from mydeck.my_decks import MyDecks` — 動作不変
  - 型注釈で使われる文字列フォワード参照 (`'MyDeck'`, `'Config'`, `'AppBase'`, etc.) — 動作不変

スコープ外:

- 残り 1 ファイル (`tests/test_device_resilience.py`、790 行) — 別 spec。
- `MyDecks` クラスや `Config` クラス自体の責務分割。
- App / Game の plugin 解決ロジックなどの構造改善。

---

## Architecture

### ファイル構成

```
src/mydeck/
├── my_decks.py            # MyDecks + 4例外 + ImageOrFile + ROOT_DIR/DEFAULT_PORT (約 280 行)
├── config.py              # Config (新規, 約 555 行)
├── my_deck.py             # MyDeck コア (新規, 約 440 行)
├── my_deck_image.py       # MyDeckImageMixin (新規, 約 160 行)
└── my_deck_handlers.py    # MyDeckHandlersMixin (新規, 約 360 行)
```

### my_decks.py (modified)

残るもの:
- 行頭のモジュール docstring と全 import (一部 import は不要になり整理)
- 定数 `DEFAULT_PORT`, `ROOT_DIR`
- `class ExceptionInvalidMyDecksConfig`
- `class MyDecks` (現 line 41-244)
- `class ExceptionNoConfig`
- `class ExceptionNoDeckGiven`
- `class ImageOrFile` (現 line 1741-1760)
- `class ExceptionWrongTypeGiven`

追加 import (`__init__.py` の `from .my_decks import *` で再エクスポートされるよう top-level に置く):
```python
from .my_deck import MyDeck
from .config import Config
```

`MyDeck` と `Config` のインポートは循環参照対策で **ファイルの末尾**に置く可能性あり (詳細は Risks を参照)。

### config.py (NEW)

`class Config` (現 line 1190-1740) を移動。

必要 import:
- `import importlib` (line 1701 周辺)
- `import logging`, `import os.path`, `import re`, `import yaml`
- `from copy import deepcopy`
- `from typing import Any, List, Optional, Dict, Tuple` 等
- `from .my_decks_manager import VirtualDeck` (使用されている場合)
- 文字列フォワード参照: `'MyDeck'`, `'AppBase'`, `'BackgroundAppBase'`, `'HookAppBase'` — import 不要

### my_deck.py (NEW)

`class MyDeck` の **コア**メソッド。inherits from 2 mixins。

```python
from .my_deck_image import MyDeckImageMixin
from .my_deck_handlers import MyDeckHandlersMixin

class MyDeck(MyDeckImageMixin, MyDeckHandlersMixin):
    ...
```

含まれるメソッド (現 line 255-1189 のうち以下):
- `_find_font` (260)
- `__init__` (270)
- `debug` (325), `init_deck` (330)
- ステータス系: `in_game_status`, `in_alert`, `key_config`, `dial_config`, `touchscreen_config`, `run_page_command`, `set_alert_on/off`, `set_game_status_on/off` (337-389)
- ページ管理: `previous_page`, `pop_last_previous_page`, `set_previous_page`, `current_page`, `_set_current_page`, `set_current_page_without_setup`, `set_current_page` (391-451)
- 接続管理: `on_disconnect`, `_ensure_disconnected_page_config`, `on_reconnect`, `set_previouse_page_if_current_page_is_empty` (452-557)
- アラート/状態: `stop_working_apps`, `handler_alert`, `handler_alert_stop` (953-970)
- スレッド/ライフサイクル: `threading_apps` (1085), `abs_key` (1131), `run_hook_apps` (1137), `update_config` (1145-1189)

### my_deck_image.py (NEW)

`class MyDeckImageMixin` を定義 (mixin)。`BaseHTTPRequestHandler` 継承前提なし、純粋な mixin。

含まれるメソッド (現 line 656-809):
- `determine_image_url` (656)
- `image_url_to_file_name` (664)
- `image_url_to_image` (671)
- `save_image` (689)
- `check_icon_file` (712)
- `update_touchscreen_image` (723)
- `update_key_image` (739)
- `render_touchscreen_image` (753)
- `render_key_image` (765-809)

mixin が依存する **`self` の属性**:
- `self.deck`, `self.myname`, `self.font_path` (`__init__` で設定)

mixin が依存する **`self` のメソッド**:
- `self.debug`, `self.abs_key` (MyDeck コアに残る)

mixin が依存する **モジュール定数**:
- `ROOT_DIR` — `from .my_decks import ROOT_DIR` で import

必要 import:
- `import os`, `import re`, `import requests`
- `import wand.image`
- `from cairosvg import svg2png`
- `from typing import Optional`
- `from PIL import Image, ImageDraw, ImageFont`
- `from StreamDeck.ImageHelpers import PILHelper`
- `from .lock import Lock`
- `from .my_decks_manager import VirtualDeck`
- `from .my_decks import ROOT_DIR, ImageOrFile` (循環の可能性があるので `TYPE_CHECKING`/lazy import の選択)

### my_deck_handlers.py (NEW)

`class MyDeckHandlersMixin` を定義 (mixin)。

含まれるメソッド:
- セットアップ系 (現 line 558-655): `has_page_key_config`, `key_touchscreen_setup`, `touchscreen_setup`, `set_touchscreen`, `dial_setup`, `set_dial`, `set_key`
- コールバック系 (現 line 810-952): `touchscreen_change_callback`, `dial_change_callback`, `key_change_callback`
- Config-write 系 (現 line 971-1084): `set_key_config`, `set_dial_config`, `set_touchscreen_config`, `set_command_config`, `set_game_key`, `add_game_key_conf`, `add_game_command`, `set_alert_key_conf`, `exit_game`, `set_key_conf`, `set_touchscreen_conf`, `set_dial_conf`

mixin が依存する `self` の属性とメソッド:
- `self.deck`, `self.config`, `self.previous_page_name`, `self._current_page` などの instance 属性
- `self.current_page()`, `self.set_current_page()`, `self.update_key_image()` など other-mixin メソッド

必要 import:
- `import re`, `import time`, `import threading`, `import logging`, `import traceback`, `import datetime`, `import subprocess`, `import signal`, `import os`
- `from typing import Any, NoReturn, List, Optional, Callable, Dict, Union`
- `from PIL import Image`
- `from .lock import Lock`
- `from .my_decks_manager import VirtualDeck, DeckOutputWebHandler`

### MRO

```
MyDeck → MyDeckImageMixin → MyDeckHandlersMixin → object
```

順序: Image を先、Handlers を後にすると MRO は上記。Handlers の `self.update_key_image` は Image にあるので、`MyDeck.update_key_image` を呼ぶと MRO で解決される。逆順でもよいが、Image cluster は基礎的なメソッド (描画) を提供するため先に置くのが自然。

`object` に同名メソッドはないので衝突なし。

### 互換性

**外部 API**:
- `from mydeck.my_decks import MyDeck`: my_decks.py に top-level `from .my_deck import MyDeck` を置けば動作。
- `from mydeck import MyDeck, Config, ImageOrFile, ROOT_DIR`: `__init__.py` の `from .my_decks import *` 経由で再エクスポート (no `__all__` 想定)。
- `mydeck.my_decks.X` モジュール属性アクセス: top-level import で属性として登録される。

**内部参照**:
- `MyDeck.__init__` 内で `self.config: Optional['Config'] = None` の文字列フォワード参照は my_deck.py に残してもエラーにならない。実体の `Config` は `from .config import Config` で取得。
- `web_server.py` の lazy import (`from .my_decks import MyDecks, MyDeck`) は my_decks.py の re-export を経由して動作。
- `app_web_server.py` の `from mydeck import MyDeck, BackgroundAppBase, DeckOutputWebServer` も同様。

### 循環 import 検証

依存関係:
```
my_decks.py (modified) ─→ my_deck.py ─→ my_deck_image.py ──→ my_decks.py (ROOT_DIR, ImageOrFile) ⚠️
                                       └→ my_deck_handlers.py
                       └→ config.py
```

`my_deck_image.py` が `my_decks.py` の `ROOT_DIR` / `ImageOrFile` を必要とする場合、循環参照になる:
1. `my_decks.py` import 開始
2. → `from .my_deck import MyDeck` を実行
3. → `my_deck.py` import 開始 → `from .my_deck_image import MyDeckImageMixin`
4. → `my_deck_image.py` import 開始 → `from .my_decks import ROOT_DIR` (まだ初期化途中)
5. → `ImportError` ないし `AttributeError` の可能性

**回避策**:
- (a) my_decks.py の `from .my_deck import MyDeck` は **ファイル末尾**で行う (`ROOT_DIR` 等が定義済みになってから)
- (b) `my_deck_image.py` でも遅延 import (`def render_key_image(...): from .my_decks import ROOT_DIR; ...`) を採用

(a) の方が明示的でテスタビリティも保てる。spec ではこちらを採用。

### my_decks.py のレイアウト変更

```python
"""Base module..."""

# import 群 (整理後)

DEFAULT_PORT: int = 3000
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

if TYPE_CHECKING:
    from .my_decks_app_base import App, AppBase, BackgroundAppBase, HookAppBase


class ExceptionInvalidMyDecksConfig(Exception): ...
class MyDecks: ...
class ExceptionNoConfig(Exception): ...
class ExceptionNoDeckGiven(Exception): ...
class ImageOrFile: ...
class ExceptionWrongTypeGiven(Exception): ...


# ── Re-export to preserve `from mydeck.my_decks import MyDeck, Config` ──
# Imports placed at end so module-level `ROOT_DIR` / `ImageOrFile` are available
# to the imported submodules.
from .my_deck import MyDeck  # noqa: E402
from .config import Config  # noqa: E402
```

---

## Testing

### 自動テスト

```
uv run pytest tests/ -x -q
```

ベースライン: 60 passed。リファクタ後も 60 passed 維持。

`tests/test_device_resilience.py` は `mydeck.my_decks_manager` を MagicMock でスタブしているため、`my_decks.py` 内部分割の影響は無い想定。`tests/test_plugin_resolution.py` は `mydeck.app_*` の import 経路を検証するが、`MyDeck` / `Config` の入れ子が変わらない限り影響なし。

### 手動 import smoke check

```bash
uv run python -c "
from mydeck.my_decks import (
    MyDecks, MyDeck, Config, ImageOrFile,
    ExceptionInvalidMyDecksConfig, ExceptionNoConfig,
    ExceptionNoDeckGiven, ExceptionWrongTypeGiven,
    ROOT_DIR, DEFAULT_PORT,
)
print('all symbols OK')
"

uv run python -c "
from mydeck import MyDeck, Config, ImageOrFile, ROOT_DIR, MyDecks
print('package re-exports OK')
"

uv run python -c "
from mydeck.my_deck import MyDeck
from mydeck.config import Config
from mydeck.my_deck_image import MyDeckImageMixin
from mydeck.my_deck_handlers import MyDeckHandlersMixin
assert MyDeckImageMixin in MyDeck.__mro__
assert MyDeckHandlersMixin in MyDeck.__mro__
print('MRO OK')
"
```

### 行数確認

各ファイル < 700:
- `my_decks.py` < 350
- `config.py` < 600
- `my_deck.py` < 500
- `my_deck_image.py` < 200
- `my_deck_handlers.py` < 400

---

## Rollout

1. `config.py` 新規作成 (Config class 移動)。
2. `my_deck_image.py` 新規作成 (Image cluster mixin)。
3. `my_deck_handlers.py` 新規作成 (Handlers cluster mixin)。
4. `my_deck.py` 新規作成 (MyDeck core + mixin inheritance)。
5. `my_decks.py` を縮小 (MyDecks + 例外群 + ImageOrFile のみ + 末尾 re-export)。
6. import 整理 (各ファイルで使われない import を削除)。
7. pytest 全パスを確認。
8. import smoke check で全シンボルがアクセス可能なことを確認。
9. 単一コミット。

---

## Risks

- **循環 import**: `my_decks.py` ⇄ `my_deck.py` ⇄ `my_deck_image.py` の間に依存ループが生じる可能性。`from .my_deck import MyDeck` を `my_decks.py` の **末尾**に置くこと、および mixin 側で必要な ROOT_DIR / ImageOrFile を **遅延 import** にすることで回避。実装時は `python -c "import mydeck.my_decks"` の smoke check で都度検証する。
- **MRO 衝突**: `MyDeckImageMixin`, `MyDeckHandlersMixin`, `object` に同名メソッドがあると意図しない解決順になる。本件では mixin 同士に同名メソッドはなく、`object` にもないので問題なし。
- **`self` の属性参照**: 各 mixin が `self.deck` 等の属性に依存しているが、これらは `MyDeck.__init__` で設定される。Mixin 単体でインスタンス化しない限り問題なし (mixin は MyDeck の継承を通じてのみ使用される)。
- **テストの import パス**: `tests/` で `mydeck.my_decks.MyDeck` への直接アクセスがある場合、my_decks.py の末尾 re-export で動作する。mock 化が必要ならパッチ対象パスも変える必要があり要確認 (今回 grep の結果、テストは `mydeck.my_decks_manager` 経由なので影響なし)。
- **TYPE_CHECKING block**: `my_decks.py` の `if TYPE_CHECKING: from .my_decks_app_base import ...` は、`MyDeck` を抽出した my_deck.py でも必要。`TYPE_CHECKING` ガードのもとで重複 import は安全。
- **MyDecks クラスの `mydecks: Dict[str, 'MyDeck']` のような型注釈**: 文字列 forward ref のため import 不要。
