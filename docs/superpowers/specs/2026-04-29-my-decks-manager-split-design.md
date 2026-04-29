# my_decks_manager.py 分割 リファクタリング設計

Date: 2026-04-29

## Overview

`src/mydeck/my_decks_manager.py` (現在 860 行) が `~/.claude/hooks/check-file-size.sh` の 700 行ブロック上限に抵触している。Config 系クラス群と I/O 系クラス群という独立性が高い 2 クラスタを別ファイルに切り出し、`my_decks_manager.py` を 700 行未満（目標 ~550 行）に縮める。

スコープ:

- 機能変更なし。純粋な構造リファクタ。
- 外部公開シンボル群 (`MyDecksManager`, `VirtualDeck`, `VirtualDeckConfig`, `VirtualDecksConfig`, `ExceptionInvalidVirtualDeckConfig`, `ExceptionVirtualDeckConstructor`, `DeckOutput`, `DeckInput`, `DeckOutputWeb`, `DeckInputWeb`, `DeckOutputWebServer`) の import パスは保持:
  - `from mydeck import DeckInput, DeckOutput, ...` (`__init__.py` 経由) — 動作不変
  - `from mydeck.my_decks_manager import VirtualDeck` — 動作不変
  - `mdm.DeckInput`, `mdm.DeckOutputWeb` のモジュール属性アクセス (テスト依存) — 動作不変

スコープ外:

- `VirtualDeck` 本体 (413 行) の分割 — `MyDecksManager.ConfigQueue` への参照があり循環 import 対策が必要なため別 spec で扱う。
- 700 行を超えている他のファイル (`my_decks.py`, `app_weather_jp.py`, `tests/test_device_resilience.py`) — 別 spec。
- Lazy import スタイルの変更。

---

## Architecture

### ファイル構成

```
src/mydeck/
├── my_decks_manager.py        # MyDecksManager + VirtualDeck + 例外2つ (約 547 行に縮小)
├── virtual_deck_config.py     # VirtualDeckConfig + VirtualDecksConfig + ExceptionInvalidVirtualDeckConfig (新規, 約 153 行)
└── deck_io.py                 # DeckOutput / DeckInput / DeckOutputWeb / DeckInputWeb / DeckOutputWebServer (新規, 約 168 行)
```

### virtual_deck_config.py

移動するクラス (現 my_decks_manager.py の line 131-279):

| クラス | 行数 | 用途 |
|---|---|---|
| `ExceptionInvalidVirtualDeckConfig` | 5 | 不正な設定時の例外 |
| `VirtualDeckConfig` | 103 | 仮想デッキ単一設定 |
| `VirtualDecksConfig` | 41 | YAML から VirtualDeckConfig のリストをパースする |

必要な import (top-level):
- `import logging`
- `import random`
- `import re`
- `import traceback`
- `import yaml`
- `from typing import Optional`
- `from StreamDeck.Devices.StreamDeck import StreamDeck`
- `from StreamDeck.Devices.StreamDeckPlus import StreamDeckPlus`

### deck_io.py

移動するクラス (現 my_decks_manager.py の line 697-860):

| クラス | 行数 | 用途 |
|---|---|---|
| `DeckOutput` | 22 | I/O 基底 (output) |
| `DeckInput` | 26 | I/O 基底 (input) |
| `DeckOutputWeb(DeckOutput)` | 84 | Web UI 用 output |
| `DeckInputWeb(DeckInput)` | 13 | Web UI 用 input (現状未使用) |
| `DeckOutputWebServer` | 19 | ThreadingHTTPServer ラッパ |

必要な import (top-level):
- `import base64`
- `import http.server`
- `import logging`
- `from io import BytesIO`
- `from PIL import Image`
- `from .web_server import DeckOutputWebHandler`

`'VirtualDeck'` への参照は文字列フォワード参照 (`def set_deck(self, deck: 'VirtualDeck')` 等) のみなので `VirtualDeck` の import は **不要**。

### my_decks_manager.py の変更点

1. **import 追加** (top-level):
   ```python
   from .virtual_deck_config import (
       ExceptionInvalidVirtualDeckConfig,
       VirtualDeckConfig,
       VirtualDecksConfig,
   )
   from .deck_io import (
       DeckOutput,
       DeckInput,
       DeckOutputWeb,
       DeckInputWeb,
       DeckOutputWebServer,
   )
   ```

2. **不要になった import を削除** (extracted クラスのみで使われていたもの):
   - `import base64`
   - `import random`
   - `import re`
   - `import traceback`
   - `import yaml`
   - `from io import BytesIO`
   - `from PIL import Image`
   - `from StreamDeck.Devices.StreamDeckPlus import StreamDeckPlus`

   保持する import:
   - `from .web_server import DeckOutputWebHandler` (VirtualDeck から使用)
   - `from .device_resilience import DeckGuard` (VirtualDeck から使用)
   - `import http.server` — ⚠️ DeckOutputWebServer の extraction 後は不要になる可能性。VirtualDeck 内に http.server 参照がないことを確認して削除する。
   - `import logging`, `import threading`, `import queue` — MyDecksManager / VirtualDeck から使用
   - `from .lock import Lock` — VirtualDeck から使用
   - `from StreamDeck.DeviceManager import DeviceManager`, `from StreamDeck.Devices.StreamDeck import StreamDeck` — MyDecksManager から使用
   - `from typing import Optional, Dict, Any, Callable` — VirtualDeck から使用

   実装時は `grep` で各 import の使用箇所を確認した上で安全に削除する。

3. **クラス削除**:
   - line 131-279 (Config クラス群、約 149 行)
   - line 697-860 (I/O クラス群、約 164 行)

### 互換性

- **`from .my_decks_manager import *`** (`__init__.py` 経由): `__all__` 未定義の Python モジュールでは「imported な名前」も `*` の対象になる。新たに import した `DeckOutput`, `DeckInput`, `DeckOutputWeb`, `DeckInputWeb`, `DeckOutputWebServer`, `VirtualDeckConfig` 等もすべて再エクスポートされる。
- **モジュール属性アクセス** (`mdm.DeckInput` 等): top-level の `from .deck_io import DeckOutput, DeckInput, ...` により `my_decks_manager` モジュールの属性として登録される。アクセス可。
- **`from .my_decks_manager import VirtualDeck`** (web_server.py の lazy import 等): VirtualDeck は my_decks_manager.py に残るので動作不変。

### 循環 import 検証

- `deck_io.py` → `web_server.py` (DeckOutputWebHandler の import): 既存と同じ依存方向。問題なし。
- `virtual_deck_config.py` → 外部依存のみ。問題なし。
- `my_decks_manager.py` → `deck_io.py`, `virtual_deck_config.py`: 新規依存。`deck_io` 側から `my_decks_manager` への依存は無いので循環せず。
- `web_server.py` → `my_decks_manager.py` (lazy): 既存通り、影響なし。

---

## Testing

### 自動テスト

`tests/test_device_resilience.py` は `mydeck.my_decks_manager` モジュール属性として `DeckInput`, `DeckOutputWeb`, `VirtualDeck` 等にアクセスする (例: `mdm.DeckInput`)。`mydeck.test_my_decks` (src 配下) は `from mydeck import Config, MyDeck, VirtualDeck, DeckInput, DeckOutput`。両方とも extraction 後も動作する想定。

```
uv run pytest tests/ -x -q
```

ベースライン: 60 passed。リファクタ後も同じく 60 passed であること。

### 手動確認

`mydeck` を起動して以下を確認 (任意):

1. `python -c "from mydeck.my_decks_manager import VirtualDeck, VirtualDeckConfig, VirtualDecksConfig, DeckOutput, DeckInput, DeckOutputWeb, DeckInputWeb, DeckOutputWebServer, MyDecksManager; print('OK')"`
2. `python -c "from mydeck import VirtualDeck, DeckInput, DeckOutput; print('OK')"`
3. `mydeck` を起動してデッキが正常に enumerate される

### 行数確認

- `wc -l src/mydeck/my_decks_manager.py` < 700 (目標 ~550)
- `wc -l src/mydeck/virtual_deck_config.py` < 200
- `wc -l src/mydeck/deck_io.py` < 200

---

## Rollout

1. `virtual_deck_config.py` 新規作成 (Config クラス群移動)。
2. `deck_io.py` 新規作成 (I/O クラス群移動)。
3. `my_decks_manager.py` から該当クラス群を削除し、新ファイルから import。不要になった top-level import を削除。
4. pytest 全パスを確認。
5. import smoke check で全シンボルがアクセス可能なことを確認。
6. 単一コミットでマージ。

ロールバックは `git revert` で 1 コミット戻すだけ。

---

## Risks

- **不要 import の見落とし**: extraction で使われなくなった top-level import を残すと将来の混乱の元。逆に削除しすぎると ImportError。各 import は `grep -nE "<modname>"` で残存使用を確認した上で削除する。
- **`__init__.py` の `from .my_decks_manager import *`**: `__all__` 未定義のため imported names も再エクスポートされる仕様に依存している。Python のこの仕様は安定だが、念のため import smoke check で確認。
- **`http.server` import**: DeckOutputWebServer (extracted) のみで使用される想定だが、見落としがあれば runtime AttributeError。検索で確認。
- **テストの `mdm.DeckInput` モジュール属性アクセス**: top-level import で属性として登録されるので動作するが、`from .deck_io import DeckInput` ではなく `from .deck_io import DeckInput as _` のように私的化したらアクセス不可になるので注意。**publicly な名前のままにする**。
