# my_decks_manager.py 分割 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `src/mydeck/my_decks_manager.py` (現 860 行) を 700 行未満 (目標 ~550 行) に縮め、Edit ブロックを解消する。Config 系クラス群を `virtual_deck_config.py` に、I/O 系クラス群を `deck_io.py` に切り出す。

**Architecture:** 2 つの新規モジュールを作成し、`my_decks_manager.py` は top-level import で各シンボルを再公開することで `__init__.py` の `from .my_decks_manager import *` 経由のアクセス互換性を維持する。

**Tech Stack:** Python 3, pytest, uv.

**Spec:** `docs/superpowers/specs/2026-04-29-my-decks-manager-split-design.md`

---

### Task 1: ベースライン記録

**Files:**
- 既存ファイル参照のみ

- [ ] **Step 1: 行数記録**

```bash
wc -l src/mydeck/my_decks_manager.py
```
Expected: `860 src/mydeck/my_decks_manager.py`

- [ ] **Step 2: pytest baseline**

```bash
uv run pytest tests/ -x -q
```
Expected: `60 passed`

- [ ] **Step 3: 主要 import 一覧の保存 (後で再エクスポート確認用)**

```bash
uv run python -c "import mydeck.my_decks_manager as m; names = sorted(n for n in dir(m) if not n.startswith('_')); print('\n'.join(names))" > /tmp/mdm_before.txt
wc -l /tmp/mdm_before.txt
```
Expected: 多数のシンボル名がリストアップされる。後の Task 4 で diff 確認に使う。

---

### Task 2: virtual_deck_config.py を新規作成

**Files:**
- Create: `src/mydeck/virtual_deck_config.py`

- [ ] **Step 1: 新規ファイルを作成**

`src/mydeck/virtual_deck_config.py` を作成し、以下の内容を書く:

```python
import logging
import random
import re
import traceback
import yaml
from typing import Optional
from StreamDeck.Devices.StreamDeck import StreamDeck
from StreamDeck.Devices.StreamDeckPlus import StreamDeckPlus


class ExceptionInvalidVirtualDeckConfig(Exception):
    """Exception class when invalid virtual deck configuration is given"""
    pass


class VirtualDeckConfig:
    """Virtual Deck Configuration class"""

    def __init__(self, id: str, opt: dict):
        self.opt = opt
        self._id: str
        self._key_count: int
        self._columns: int
        self._dials: int = 0
        self._has_touch_interface: bool = False
        self._serial_number: str
        self._touchscreen_size: tuple[int, int] = (0, 0)

        real_deck: StreamDeck = opt.get("real_deck")
        if real_deck is not None:
            self._id = id
            self._key_count = real_deck.KEY_COUNT
            self._columns = real_deck.KEY_COLS
            logging.info(real_deck.get_serial_number())
            self._serial_number = real_deck.get_serial_number()
        else:
            key_count = opt.get('key_count')
            if key_count is None or re.match(r'\D', str(key_count)) is not None:
                raise ExceptionInvalidVirtualDeckConfig()
            self._key_count = key_count
            columns = opt.get('columns')
            if columns is None or re.match(r'\D', str(columns)) is not None:
                raise ExceptionInvalidVirtualDeckConfig()
            self._columns = columns
            serial_number = opt.get('serial_number')
            if serial_number is None:
                raise ExceptionInvalidVirtualDeckConfig()
            self._serial_number = str(serial_number)
            has_touchscreen: Optional[bool] = opt.get('has_touchscreen')
            if has_touchscreen is not None and has_touchscreen:
                self._has_touch_interface = has_touchscreen
                size: Optional[tuple[int, int]] = opt.get("touchscreen_size")
                if size is not None:
                    self._touchscreen_size = (size[0], size[1])
                else:
                    plus = StreamDeckPlus
                    self._touchscreen_size = (
                        plus.TOUCHSCREEN_PIXEL_WIDTH, plus.TOUCHSCREEN_PIXEL_HEIGHT
                    )

            num_of_dials: Optional[int] = opt.get('dial_count')
            if num_of_dials is not None and num_of_dials is not None and num_of_dials > 0:
                self._dials = num_of_dials

            self._id = id

    def id(self) -> str:
        return self._id

    def key_count(self) -> int:
        return self._key_count

    def columns(self) -> int:
        return self._columns

    def serial_number(self) -> str:
        sn = self._serial_number
        if sn is None:
            logging.critical("serial_nubmer is required")
            exit
        return sn

    def get_random_serial_number(self) -> str:
        return str(random.random())

    def input_option(self) -> dict:
        i = self.opt.get('input')
        if not isinstance(i, dict):
            return {}
        return i

    def output_option(self) -> dict:
        o = self.opt.get('output')
        if not isinstance(o, dict):
            return {}
        return o

    def dials(self) -> int:
        return self._dials

    def has_touchscreen(self) -> bool:
        return self._has_touch_interface

    def touchscreen_size(self) -> tuple[int, int]:
        return self._touchscreen_size

    def config(self) -> dict:
        return {
            'id': self.id(),
            'key_count': self.key_count(),
            'columns': self.columns(),
            'serial_number': self.serial_number(),
            "dial_count": self.dials(),
            "has_touchscreen": self.has_touchscreen(),
            "touchscreen_size": self.touchscreen_size(),
        }


class VirtualDecksConfig:
    """Multiple Virutal Decks Configuration Class"""

    def __init__(self, file: str):
        """Pass file name of yaml file. liek the foolowing:

        example:
        ---
        1:
          key_count: 4
          columns: 2
          serial_number: 'dummy1'
          has_touchscreen: true
          dial_count: 2
          touchscreen_size: [400, 100]
        2:
          key_count: 6
          columns: 3
          serial_number: 'dummy2'
          has_touchscreen: true
          dial_count: 4
        """
        self.file = file
        self.config: dict = {}

    def parse(self) -> list[VirtualDeckConfig]:
        """Parse virutal deck configuration and return list of VirtualDeckConfig instances."""
        configs: list[VirtualDeckConfig] = []
        with open(self.file) as f:
            try:
                config: dict = yaml.safe_load(f)
                for id in config.keys():
                    opt: dict = config[id]
                    configs.append(VirtualDeckConfig(str(id), opt))
            except Exception as e:
                logging.critical("Error in load: %s", e)
                logging.debug(traceback.format_exc())

        return configs
```

これは現 `my_decks_manager.py` の line 131-279 を byte-for-byte 移動したもの。

- [ ] **Step 2: import チェック**

```bash
uv run python -c "from mydeck.virtual_deck_config import ExceptionInvalidVirtualDeckConfig, VirtualDeckConfig, VirtualDecksConfig; print('OK')"
```
Expected: `OK`

---

### Task 3: deck_io.py を新規作成

**Files:**
- Create: `src/mydeck/deck_io.py`

- [ ] **Step 1: 新規ファイルを作成**

`src/mydeck/deck_io.py` を作成し、以下の内容を書く:

```python
import base64
import http.server
import logging
from io import BytesIO
from PIL import Image
from .web_server import DeckOutputWebHandler


class DeckOutput:
    """Deck output base Class. This should not be used directly.
    """

    def __init__(self, opt: dict):
        self.key_config: dict = {}
        self.config: dict = opt
        self.deck: 'VirtualDeck'

    def init(self):
        """Implement it in subclass."""
        pass

    def set_deck(self, deck: 'VirtualDeck'):
        """Set virtual deck instance"""
        self.deck = deck
        self.config["id"] = self.deck.id()

    def output(self, key_status: dict, touchscreen_image):
        pass


class DeckInput:
    """Deck input base Class. This should not be used directly.
    use FromOption method and get the intance of the subclass.

    But, currently it does nothing.
    """

    def __init__(self, opt: dict):
        self.key_config: dict = {}
        self.config = opt
        self. deck = None

    def init(self):
        pass

    def set_deck(self, deck):
        self.deck = deck

    def input(self, page: str):
        pass

    @staticmethod
    def FromOption(opt: dict):
        return DeckInput({})


class DeckOutputWeb(DeckOutput):
    id_deck_map: dict[int, 'VirtualDeck']
    """Subclass of DeckOutput for Web."""

    def __init__(self, opt: dict):
        super().__init__(opt)

    def set_deck(self, deck: 'VirtualDeck'):
        """Set deck ID and deck instance to Globl Variable DeckOutputWebHandlerid_deck_map dict."""
        super().set_deck(deck)
        DeckOutputWebHandler.id_deck_map[self.deck.id()] = self.deck

    def output(self, key_status: dict, touchscreen_image):
        """pass key and its image to DeckOutputWebHandler.set_key_image"""
        id = self.deck.id()
        if id == None:
            return

        _key_status = {}

        for key, v in list(key_status.items()):
            _key_status[key] = v

        for key, v in _key_status.items():
            if key_status[key]["image"] is None:
                key_status[key]["image"] = Image.new(
                    'RGBA', (100, 100), (0, 0, 0, 127))

            image_buffer = self.key_image_format(key_status[key]["image"])
            b64_image = base64.b64encode(image_buffer.getvalue())

            DeckOutputWebHandler.set_key_image(
                id, key, b64_image.decode('utf-8'))

        if touchscreen_image:
            image_buffer = self.touchscreen_image_format(touchscreen_image)
            b64_image = base64.b64encode(image_buffer.getvalue())

            DeckOutputWebHandler.set_touchscreen_image(
                id, b64_image.decode('utf-8'))

    def key_image_format(self, image):
        """return image as BytesIO binary stream"""
        image_format = self.deck.key_image_format()

        if image_format['rotation']:
            image = image.rotate(image_format['rotation'])

        if image_format['flip'][0]:
            image = image.transpose(Image.FLIP_LEFT_RIGHT)

        if image_format['flip'][1]:
            image = image.transpose(Image.FLIP_TOP_BOTTOM)

        if image.size != image_format['size']:
            image.thumbnail(image_format['size'])

        buffered = BytesIO()
        image.save(buffered, image_format["format"], quality=100)

        return buffered

    def touchscreen_image_format(self, image):
        """return image as BytesIO binary stream"""
        image_format = self.deck.touchscreen_image_format()

        if image_format['rotation']:
            image = image.rotate(image_format['rotation'])

        if image_format['flip'][0]:
            image = image.transpose(Image.FLIP_LEFT_RIGHT)

        if image_format['flip'][1]:
            image = image.transpose(Image.FLIP_TOP_BOTTOM)

        if image.size != image_format['size']:
            image.thumbnail(image_format['size'])

        buffered = BytesIO()
        image.save(buffered, image_format["format"], quality=100)

        return buffered


class DeckInputWeb(DeckInput):
    """Currently no use"""

    def __init__(self, opt: dict):
        super().__init__(opt)

    def init(self):
        pass

    def input(self, page: str):
        pass


class DeckOutputWebServer:
    """virtual deck server"""
    httpd = None

    def __init__(self):
        pass

    @staticmethod
    def shutdown():
        if DeckOutputWebServer.httpd is not None:
            DeckOutputWebServer.httpd.shutdown()

    def run(self, port: int):
        with http.server.ThreadingHTTPServer(('', port), DeckOutputWebHandler) as httpd:
            DeckOutputWebServer.httpd = httpd
            logging.info("serving at port %d", port)
            logging.info("server is started")
            httpd.serve_forever()
            logging.info("server is exited")
```

これは現 `my_decks_manager.py` の line 697-860 を byte-for-byte 移動したもの。`'VirtualDeck'` は文字列フォワード参照のままなので VirtualDeck の import は不要。

- [ ] **Step 2: import チェック**

```bash
uv run python -c "from mydeck.deck_io import DeckOutput, DeckInput, DeckOutputWeb, DeckInputWeb, DeckOutputWebServer; print('OK')"
```
Expected: `OK`

---

### Task 4: my_decks_manager.py から該当クラス群を削除し、新ファイルから import

**Files:**
- Modify: `src/mydeck/my_decks_manager.py`

このファイルは現在 860 行で Edit ツールがブロックされている。`Read` で全体を取得した上で `Write` ツールで一括書き換えする。

- [ ] **Step 1: 全体を読み込む**

```python
# pseudocode for the implementer
content = Read(src/mydeck/my_decks_manager.py)
```

- [ ] **Step 2: 削除と import 追加を反映した新内容を生成**

新内容の構造 (約 547 行想定):

```
[line 1-21 相当] 既存 import (ただし不要 import を削除し、新 import を追加)
  - 削除: import base64, import random, import re, import traceback, import yaml
  - 削除: from io import BytesIO, from PIL import Image
  - 削除: from StreamDeck.Devices.StreamDeckPlus import StreamDeckPlus
  - 削除: import http.server  (DeckOutputWebServer 抜けで使用箇所がなくなるため。但し VirtualDeck 等で使われていないことを grep で確認してから削除)
  - 保持: from .web_server import DeckOutputWebHandler
  - 保持: from .device_resilience import DeckGuard
  - 保持: import logging, import queue, import threading
  - 保持: from .lock import Lock
  - 保持: from StreamDeck.DeviceManager import DeviceManager
  - 保持: from StreamDeck.Devices.StreamDeck import StreamDeck
  - 保持: from typing import Optional, Dict, Any, Callable
  - 追加: from .virtual_deck_config import (
            ExceptionInvalidVirtualDeckConfig,
            VirtualDeckConfig,
            VirtualDecksConfig,
        )
  - 追加: from .deck_io import (
            DeckOutput,
            DeckInput,
            DeckOutputWeb,
            DeckInputWeb,
            DeckOutputWebServer,
        )

[元 line 22-130 相当] class MyDecksManager: (無変更)

[元 line 280-283 相当] class ExceptionVirtualDeckConstructor(Exception): (無変更)
  - 注: 元 line 131-135 の ExceptionInvalidVirtualDeckConfig は削除 (extracted)
  - 注: 元 line 136-238 の VirtualDeckConfig は削除 (extracted)
  - 注: 元 line 239-279 の VirtualDecksConfig は削除 (extracted)

[元 line 284-696 相当] class VirtualDeck: (無変更)

[元 line 697-860 相当のクラス群] 削除 (extracted)
```

不要 import の削除に際しては、各 import 名を `grep -n "<import name>"` で検索し、残るコード (MyDecksManager / ExceptionVirtualDeckConstructor / VirtualDeck) で **使用されていない** ことを確認する。例:

```bash
grep -nE "\bbase64\b|\brandom\b|\btraceback\b|\byaml\b|BytesIO|StreamDeckPlus|\bImage\b" src/mydeck/my_decks_manager.py
```

(extraction 前の状態で `\bre\b` を検索すると `class` 等の re-で始まる単語も拾うので注意。実装時は `import re` 自体の使用箇所を `\bre\.` パターンで確認するのがよい)

- [ ] **Step 3: Write で書き換え**

実装者注: `my_decks_manager.py` は現状 860 行で `Edit` フックがブロックする。`Write` ツールで全体置換する。書き換え後は < 700 行になり、以降の `Edit` は通る。

新内容 (上記構造) を `Write` で `src/mydeck/my_decks_manager.py` に書き込む。

- [ ] **Step 4: 行数確認**

```bash
wc -l src/mydeck/my_decks_manager.py src/mydeck/virtual_deck_config.py src/mydeck/deck_io.py
```
Expected:
- `my_decks_manager.py`: 700 未満 (目標 ~547 ± 数行)
- `virtual_deck_config.py`: 約 153 行
- `deck_io.py`: 約 168 行

`my_decks_manager.py` が 700 行以上なら削除し漏れがある。

```bash
grep -nE "^class (DeckOutput|DeckInput|DeckOutputWeb|DeckInputWeb|DeckOutputWebServer|VirtualDeckConfig|VirtualDecksConfig|ExceptionInvalidVirtualDeckConfig)\b" src/mydeck/my_decks_manager.py
```
Expected: 出力なし。

- [ ] **Step 5: import smoke check**

```bash
uv run python -c "
from mydeck.my_decks_manager import (
    MyDecksManager,
    VirtualDeck,
    VirtualDeckConfig,
    VirtualDecksConfig,
    ExceptionInvalidVirtualDeckConfig,
    ExceptionVirtualDeckConstructor,
    DeckOutput,
    DeckInput,
    DeckOutputWeb,
    DeckInputWeb,
    DeckOutputWebServer,
)
print('all imports OK')
"
```
Expected: `all imports OK`

```bash
uv run python -c "from mydeck import VirtualDeck, DeckInput, DeckOutput, DeckOutputWeb, DeckInputWeb, DeckOutputWebServer; print('package re-exports OK')"
```
Expected: `package re-exports OK`

```bash
uv run python -c "import mydeck.my_decks_manager as m; print('DeckInput attr:', hasattr(m, 'DeckInput'), 'VirtualDeck attr:', hasattr(m, 'VirtualDeck'), 'DeckOutputWeb attr:', hasattr(m, 'DeckOutputWeb'))"
```
Expected: 全部 True

- [ ] **Step 6: シンボル一覧 diff**

```bash
uv run python -c "import mydeck.my_decks_manager as m; names = sorted(n for n in dir(m) if not n.startswith('_')); print('\n'.join(names))" > /tmp/mdm_after.txt
diff /tmp/mdm_before.txt /tmp/mdm_after.txt
```
Expected: 差分なし、または増減があってもそれが望ましいか吟味。

期待: ベースラインで存在していた public シンボルがすべて残る。新たに増えた名前があるとすれば、それは新規 import 由来 (例: 削除した import の元シンボルがない場合のみ。通常は変化なし)。

---

### Task 5: テスト実行

**Files:**
- 既存ファイル参照のみ

- [ ] **Step 1: pytest 全パス**

```bash
uv run pytest tests/ -x -q
```
Expected: 60 passed (ベースラインと一致)。

- [ ] **Step 2: import 健全性総合チェック**

```bash
uv run python -c "import mydeck.web_server, mydeck.my_decks_manager, mydeck.my_decks, mydeck.virtual_deck_config, mydeck.deck_io; print('all module imports OK')"
```
Expected: `all module imports OK`

---

### Task 6: コミット

**Files:**
- すべて

- [ ] **Step 1: 変更内容を確認**

```bash
git status
git diff --stat
```
Expected:
- `src/mydeck/my_decks_manager.py` (modified)
- `src/mydeck/virtual_deck_config.py` (new)
- `src/mydeck/deck_io.py` (new)

- [ ] **Step 2: コミット**

```bash
git add src/mydeck/my_decks_manager.py src/mydeck/virtual_deck_config.py src/mydeck/deck_io.py
git commit -m "$(cat <<'EOF'
refactor: split my_decks_manager.py into config and IO modules

Extract VirtualDeckConfig cluster (ExceptionInvalidVirtualDeckConfig,
VirtualDeckConfig, VirtualDecksConfig) to virtual_deck_config.py.
Extract IO cluster (DeckOutput, DeckInput, DeckOutputWeb, DeckInputWeb,
DeckOutputWebServer) to deck_io.py.

Brings my_decks_manager.py from 860 lines to ~550, comfortably below
the 700-line edit-block limit. Re-imports preserve all external symbols
via top-level imports, so `from mydeck import ...` and module-attribute
access patterns continue to work.

Spec: docs/superpowers/specs/2026-04-29-my-decks-manager-split-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 3: コミット確認**

```bash
git log --stat -1
```
Expected: 3 ファイル変更 (1 modified, 2 new)。

---

## Self-Review Notes

- ✅ Spec 全要件カバー: 2 ファイル抽出 (Task 2, 3)、my_decks_manager 縮小 (Task 4)、不要 import 削除指示、シンボル互換性確認 (Task 4 Step 5-6)、pytest (Task 5)
- ✅ プレースホルダなし: 全コードを完全記述、削除する import 一覧と保持する import 一覧を明示
- ✅ 名前一貫性: `virtual_deck_config.py` / `deck_io.py` / 各クラス名がすべての Task で一貫
