# web_server.py TOTP抽出 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `src/mydeck/web_server.py` (現 781 行) を 700 行未満に縮め、`~/.claude/hooks/check-file-size.sh` の Edit ブロックを解消する。TOTP 関連 9 メソッド (GET 1, POST 8) を `web_server_totp.py` に mixin として切り出す。

**Architecture:** `TotpEndpointsMixin` を新規ファイルに作成し、`DeckOutputWebHandler` が継承する。HTTPリクエストハンドラとしてのインターフェース (`self.headers`, `self.rfile`, `self.api_json_response`) は `BaseHTTPRequestHandler` から MRO で解決される。`do_GET` / `do_POST` のルーティングは web_server.py に残し、メソッド本体だけ移す。

**Tech Stack:** Python 3, `http.server.BaseHTTPRequestHandler`, pytest, uv.

**Spec:** `docs/superpowers/specs/2026-04-29-web-server-totp-extraction-design.md`

---

### Task 1: 現状ベースラインの記録

**Files:**
- 既存ファイル参照のみ

- [ ] **Step 1: 現在の行数を記録**

Run:
```bash
wc -l src/mydeck/web_server.py
```
Expected: `781 src/mydeck/web_server.py`

- [ ] **Step 2: 既存テストが通る状態を確認**

Run:
```bash
uv run pytest tests/ -x -q
```
Expected: 全テスト PASS。失敗するテストがある場合は、リファクタの前に既存の状態を記録（このリファクタが原因ではないことを後で示すため）。

- [ ] **Step 3: 関連 import の現状確認**

Run:
```bash
grep -n "DeckOutputWebHandler\|web_server" src/mydeck/my_decks_manager.py src/mydeck/my_decks.py
```
Expected: 既存の import / 使用箇所がリストされる。これらは Task 全体で**変更されない**ことを後で確認する。

---

### Task 2: web_server_totp.py を新規作成し、TotpEndpointsMixin を実装

**Files:**
- Create: `src/mydeck/web_server_totp.py`

- [ ] **Step 1: 新規ファイルを作成**

Create `src/mydeck/web_server_totp.py`:

```python
import json
import logging


class TotpEndpointsMixin:
    """TOTP-related endpoint handlers for DeckOutputWebHandler.

    Provides the `res_totp_*` methods. Designed to be mixed into a class
    that also inherits from `http.server.BaseHTTPRequestHandler`, since
    these methods rely on `self.headers`, `self.rfile`, and the
    `self.api_json_response()` helper defined on the handler.
    """

    def res_totp_accounts(self):
        from .totp_account_manager import TotpAccountManager
        manager = TotpAccountManager()
        return self.api_json_response(manager.load_accounts())

    def res_totp_scan(self):
        """Decode QR code from base64 image and return the raw URI (no registration)."""
        import base64
        from io import BytesIO
        from PIL import Image as PILImage
        from pyzbar.pyzbar import decode as pyzbar_decode

        try:
            content_length = int(self.headers['content-length'])
            if content_length > 10 * 1024 * 1024:
                return self.api_json_response({"error": "image too large"})
            body = json.loads(self.rfile.read(content_length).decode('utf-8'))
            image_data = base64.b64decode(body['image_b64'])
            im = PILImage.open(BytesIO(image_data)).convert('L')  # grayscale for better detection
            logging.debug("TOTP scan: image size=%s, mode=%s", im.size, im.mode)
            decoded = pyzbar_decode(im)
            logging.debug("TOTP scan: pyzbar found %d codes", len(decoded))
            if not decoded:
                return self.api_json_response({})
            uri = decoded[0].data.decode('utf-8')
            logging.debug("TOTP scan: decoded URI=%s", uri[:50])
            return self.api_json_response({"uri": uri})
        except Exception as e:
            logging.error("TOTP scan error: %s", e)
            return self.api_json_response({"error": str(e)})

    def res_totp_upload(self):
        import base64
        from io import BytesIO
        from PIL import Image as PILImage
        from pyzbar.pyzbar import decode as pyzbar_decode
        from .totp_account_manager import TotpAccountManager

        try:
            content_length = int(self.headers['content-length'])
            if content_length > 10 * 1024 * 1024:
                return self.api_json_response({"error": "image too large (max 10 MB)"})
            body = json.loads(self.rfile.read(content_length).decode('utf-8'))
            image_data = base64.b64decode(body['image_b64'])
            im = PILImage.open(BytesIO(image_data))
            decoded = pyzbar_decode(im)
            if not decoded:
                return self.api_json_response({"error": "QR code not found in image"})
            uri = decoded[0].data.decode('utf-8')
            manager = TotpAccountManager()
            parsed = manager.parse_otpauth_uri(uri)
            name = body.get('name') or parsed['name']
            manager.save_account(name, parsed['issuer'], parsed['secret'])
            return self.api_json_response({"ok": True, "name": name})
        except Exception as e:
            logging.error("TOTP upload error: %s", e)
            return self.api_json_response({"error": str(e)})

    def res_totp_register(self):
        import base64 as _base64
        from .totp_account_manager import TotpAccountManager

        try:
            content_length = int(self.headers['content-length'])
            body = json.loads(self.rfile.read(content_length).decode('utf-8'))
            manager = TotpAccountManager()
            uri = body.get('uri', '')
            if uri.startswith('otpauth-migration://'):
                entries = manager.parse_migration_uri(uri)
                if not entries:
                    return self.api_json_response({"error": "No TOTP accounts found in migration data"})
                names = []
                for entry in entries:
                    manager.save_account(entry['name'], entry['issuer'], entry['secret'])
                    names.append(entry['name'])
                return self.api_json_response({"ok": True, "name": ", ".join(names), "count": len(names)})
            elif uri:
                parsed = manager.parse_otpauth_uri(uri)
                name = body.get('name') or parsed['name']
                manager.save_account(name, parsed['issuer'], parsed['secret'])
            else:
                name = body['name']
                issuer = body.get('issuer', name)
                secret = body['secret'].upper().replace(' ', '')
                try:
                    _base64.b32decode(secret, casefold=True)
                except Exception:
                    return self.api_json_response({"error": "invalid Base32 secret"})
                manager.save_account(name, issuer, secret)
            return self.api_json_response({"ok": True, "name": name})
        except Exception as e:
            logging.error("TOTP register error: %s", e)
            return self.api_json_response({"error": str(e)})

    def res_totp_set_image(self):
        import base64
        import requests as req
        from .totp_account_manager import TotpAccountManager

        try:
            content_length = int(self.headers['content-length'])
            if content_length > 10 * 1024 * 1024:
                return self.api_json_response({"error": "image too large (max 10 MB)"})
            body = json.loads(self.rfile.read(content_length).decode('utf-8'))
            name = body['name']
            manager = TotpAccountManager()
            if 'image_url' in body:
                resp = req.get(body['image_url'], timeout=10)
                if resp.status_code != 200:
                    return self.api_json_response({"error": f"画像の取得に失敗: HTTP {resp.status_code}"})
                image_data = resp.content
            else:
                image_data = base64.b64decode(body['image_b64'])
            path = manager.set_account_image(name, image_data)
            return self.api_json_response({"ok": True, "path": path})
        except Exception as e:
            logging.error("TOTP set_image error: %s", e)
            return self.api_json_response({"error": str(e)})

    def res_totp_delete(self):
        from .totp_account_manager import TotpAccountManager

        try:
            content_length = int(self.headers['content-length'])
            body = json.loads(self.rfile.read(content_length).decode('utf-8'))
            name = body['name']
            manager = TotpAccountManager()
            ok = manager.delete_account(name)
            return self.api_json_response({"ok": ok})
        except Exception as e:
            logging.error("TOTP delete error: %s", e)
            return self.api_json_response({"error": str(e)})

    def res_totp_reorder(self):
        from .totp_account_manager import TotpAccountManager

        try:
            content_length = int(self.headers['content-length'])
            body = json.loads(self.rfile.read(content_length).decode('utf-8'))
            names = body['names']
            manager = TotpAccountManager()
            ok = manager.reorder_accounts(names)
            return self.api_json_response({"ok": ok})
        except Exception as e:
            logging.error("TOTP reorder error: %s", e)
            return self.api_json_response({"error": str(e)})

    def res_totp_fetch_icon(self):
        from .totp_account_manager import TotpAccountManager

        try:
            content_length = int(self.headers['content-length'])
            body = json.loads(self.rfile.read(content_length).decode('utf-8'))
            name = body['name']
            manager = TotpAccountManager()
            accounts = manager.load_accounts()
            issuer = name
            for acc in accounts:
                if acc["name"] == name:
                    issuer = acc.get("issuer", name)
                    # Clear existing image so _auto_fetch_icon will run
                    if acc.get("image"):
                        acc.pop("image")
                        with open(manager.accounts_file, "w") as f:
                            json.dump(accounts, f, indent=2)
                    break
            manager._auto_fetch_icon(name, issuer)
            # Check if it worked
            path = manager._image_path(name)
            if path:
                return self.api_json_response({"ok": True, "path": path})
            else:
                return self.api_json_response({"error": "アイコンが見つかりませんでした"})
        except Exception as e:
            logging.error("TOTP fetch_icon error: %s", e)
            return self.api_json_response({"error": str(e)})

    def res_totp_update(self):
        from .totp_account_manager import TotpAccountManager

        try:
            content_length = int(self.headers['content-length'])
            body = json.loads(self.rfile.read(content_length).decode('utf-8'))
            name = body['name']
            new_name = body.get('new_name')
            new_issuer = body.get('new_issuer')
            manager = TotpAccountManager()
            ok = manager.update_account(name, new_name=new_name, new_issuer=new_issuer)
            return self.api_json_response({"ok": ok})
        except Exception as e:
            logging.error("TOTP update error: %s", e)
            return self.api_json_response({"error": str(e)})
```

- [ ] **Step 2: import 構文チェック**

Run:
```bash
uv run python -c "from mydeck.web_server_totp import TotpEndpointsMixin; print(TotpEndpointsMixin.__name__)"
```
Expected: `TotpEndpointsMixin`

注意: この時点では mixin は単体では機能しない（`self.api_json_response` 等が未解決）。動作確認は Task 4 で行う。

- [ ] **Step 3: コミット (中間状態)**

ここではまだコミットしない — Task 3 と一緒の状態でコミットする。重複を避けるため。

---

### Task 3: web_server.py から TOTP メソッド本体を削除し、mixin を継承

**Files:**
- Modify: `src/mydeck/web_server.py` (line 1-10 あたりに import 追加、25 行目のクラス宣言、583-774 行目の TOTP メソッドを削除)

- [ ] **Step 1: import 追加**

`src/mydeck/web_server.py` の先頭 import 群 (line 1-10) の最後に以下を追加:

変更前:
```python
import re
import http.server
import json
import glob
import psutil
import os
import logging
from StreamDeck.Devices.StreamDeck import TouchscreenEventType, DialEventType
from typing import Optional, Any
from typing import Union
```

変更後:
```python
import re
import http.server
import json
import glob
import psutil
import os
import logging
from StreamDeck.Devices.StreamDeck import TouchscreenEventType, DialEventType
from typing import Optional, Any
from typing import Union

from .web_server_totp import TotpEndpointsMixin
```

- [ ] **Step 2: クラス宣言を変更**

`src/mydeck/web_server.py` line 25:

変更前:
```python
class DeckOutputWebHandler(http.server.BaseHTTPRequestHandler):
```

変更後:
```python
class DeckOutputWebHandler(TotpEndpointsMixin, http.server.BaseHTTPRequestHandler):
```

注意: Mixin → Base の順序を厳守。逆にすると `BaseHTTPRequestHandler` のメソッドが mixin で上書きされる可能性が出る。

- [ ] **Step 3: TOTP メソッド本体を削除**

`src/mydeck/web_server.py` から、line 583-774 の **9 メソッド全体** を削除する。

削除対象（メソッド名で示す。各メソッドの `def` 行から次のメソッドの直前の空行までを含めて削除）:
1. `res_totp_accounts` (line 583-586)
2. `res_totp_scan` (line 588-612)
3. `res_totp_upload` (line 614-639)
4. `res_totp_register` (line 641-675)
5. `res_totp_set_image` (line 677-700)
6. `res_totp_delete` (line 702-714)
7. `res_totp_reorder` (line 716-728)
8. `res_totp_fetch_icon` (line 730-758)
9. `res_totp_update` (line 760-774)

`res_totp_accounts` の前にあるメソッド (`res_key_setting`, line 567-) と、`res_totp_update` の後にあるメソッド (`log_message`, line 776-) の間にあった TOTP 群がすべて消える。クラス末尾の `log_message` メソッドが `res_key_setting` の直後（1 行空行を挟んで）に来る形になる。

具体的な削除方法（Edit ツールで一括）: `res_totp_accounts` の `def` 行から `res_totp_update` メソッドの最後の行 (`return self.api_json_response({"error": str(e)})`) までを 1 つの `old_string` として指定し、`new_string` を空文字または改行 1 つにする。

削除後、`def log_message` の直前に空行が 1 つだけ残る形にする。

- [ ] **Step 4: import 構文チェック**

Run:
```bash
uv run python -c "from mydeck.web_server import DeckOutputWebHandler; print(DeckOutputWebHandler.__mro__)"
```
Expected: 出力に `TotpEndpointsMixin` と `BaseHTTPRequestHandler` の両方が `DeckOutputWebHandler` の MRO に含まれる。例:
```
(<class 'mydeck.web_server.DeckOutputWebHandler'>, <class 'mydeck.web_server_totp.TotpEndpointsMixin'>, <class 'http.server.BaseHTTPRequestHandler'>, ...)
```

- [ ] **Step 5: TOTP メソッドが mixin 経由でアクセス可能なことを確認**

Run:
```bash
uv run python -c "from mydeck.web_server import DeckOutputWebHandler; assert hasattr(DeckOutputWebHandler, 'res_totp_accounts'); assert hasattr(DeckOutputWebHandler, 'res_totp_update'); print('OK')"
```
Expected: `OK`

- [ ] **Step 6: 行数確認**

Run:
```bash
wc -l src/mydeck/web_server.py src/mydeck/web_server_totp.py
```
Expected:
- `web_server.py` < 700（約 590 行想定）
- `web_server_totp.py` < 700（約 195 行想定）

`web_server.py` が 700 行以上残っている場合、削除し漏れがある。`grep -n "res_totp_" src/mydeck/web_server.py` で残存メソッドを探す（Mixin 化後はここに何もマッチしないはず）。

```bash
grep -n "def res_totp_" src/mydeck/web_server.py
```
Expected: 出力なし（または exit code 1）。

---

### Task 4: テスト・動作確認

**Files:**
- 既存ファイル参照のみ

- [ ] **Step 1: pytest 全パスを確認**

Run:
```bash
uv run pytest tests/ -x -q
```
Expected: Task 1 で記録したベースラインと同じ結果（全 PASS、または同じ既知の失敗）。本リファクタが原因の **新規** 失敗がないこと。

`tests/test_device_resilience.py` は `mydeck.web_server` を `MagicMock` で stub しているため内部分割の影響は受けない想定。

- [ ] **Step 2: mydeck CLI が起動エラーなくロードできるか**

Run:
```bash
uv run python -c "import mydeck.web_server; import mydeck.my_decks_manager; import mydeck.my_decks; print('imports OK')"
```
Expected: `imports OK`

- [ ] **Step 3: 手動: TOTP UI 動作確認 (任意だが推奨)**

`mydeck` を起動し、ブラウザで以下を確認:
1. `http://localhost:<port>/totp` にアクセス → TOTP 画面が表示される
2. `http://localhost:<port>/api/totp/accounts` → 既存アカウント一覧 JSON が返る (アカウント未登録なら `[]`)
3. ブラウザの DevTools で 500 エラーが出ていないこと

確認できない環境（デバイス未接続等）の場合はスキップ可。

---

### Task 5: コミット

**Files:**
- すべて

- [ ] **Step 1: 変更内容を確認**

Run:
```bash
git status
git diff --stat
```
Expected:
```
 src/mydeck/web_server.py       | (-XXX 行)
 src/mydeck/web_server_totp.py  | (+XXX 行) NEW
```
new file が `web_server_totp.py`、modified が `web_server.py` のみ。

- [ ] **Step 2: コミット**

```bash
git add src/mydeck/web_server.py src/mydeck/web_server_totp.py
git commit -m "$(cat <<'EOF'
refactor: extract TOTP endpoints to web_server_totp.py mixin

Move 9 res_totp_* methods from DeckOutputWebHandler to TotpEndpointsMixin
to bring web_server.py below the 700-line edit-block limit.

Functionally equivalent: routing, class-level state, and external imports
are unchanged. DeckOutputWebHandler now inherits from TotpEndpointsMixin
first, then BaseHTTPRequestHandler.

Spec: docs/superpowers/specs/2026-04-29-web-server-totp-extraction-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 3: コミットの確認**

Run:
```bash
git log --stat -1
```
Expected: 1 ファイル新規 (`web_server_totp.py`)、1 ファイル変更 (`web_server.py`)、テストは未変更。

---

## Self-Review Notes

- ✅ Spec 全要件カバー: TOTP 9 メソッド抽出 (Task 2, 3)、行数チェック (Task 3 Step 6)、テスト確認 (Task 4)、外部 API 不変 (Task 3 Step 4-5)
- ✅ プレースホルダなし: 全 import / クラス定義 / 削除対象行は具体的に指定
- ✅ 名前一貫性: `TotpEndpointsMixin` / `web_server_totp.py` / `res_totp_*` がすべての Task で同一表記
- ✅ メソッド数: spec / plan ともに 9 メソッド (GET 1 + POST 8) で統一済み。
