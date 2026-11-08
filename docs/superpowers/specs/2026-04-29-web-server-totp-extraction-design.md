# web_server.py TOTP抽出 リファクタリング設計

Date: 2026-04-29

## Overview

`src/mydeck/web_server.py` (現在 781 行) が `~/.claude/hooks/check-file-size.sh` の 700 行ブロック上限に抵触し、Edit がブロックされる状態にある。`DeckOutputWebHandler` クラスの中で独立性が高い TOTP 系エンドポイント 9 メソッド (GET 1, POST 8) を別ファイルに mixin として切り出し、`web_server.py` を 700 行未満に収める。

スコープ:

- 機能変更なし。純粋な構造リファクタ。
- 外部公開 API (`mydeck.web_server.DeckOutputWebHandler` クラス名・クラス変数・staticmethod) は完全保持。
- ルーティング (`do_GET` / `do_POST` の path 判定) は `web_server.py` に残す。メソッド本体だけを移動。

スコープ外:

- 700 行を超えている他のファイル (`my_decks.py`, `app_weather_jp.py`, `my_decks_manager.py`, `tests/test_device_resilience.py`) — 別 spec で扱う。
- `DeckOutputWebHandler` の責務分割 (デバイス系 / 設定系 / 状態管理系) — TOTP 抽出だけで 700 行制限が解消されるため、ここでは触らない。
- 既存の `from foo import bar` を関数内 import で遅延ロードしているパターン — そのまま維持。

---

## Architecture

### ファイル構成

```
src/mydeck/
├── web_server.py            # DeckOutputWebHandler (約 590 行に縮小)
└── web_server_totp.py       # TotpEndpointsMixin (新規, 約 195 行)
```

### TotpEndpointsMixin

`web_server_totp.py` に `TotpEndpointsMixin` クラスを定義し、以下の 9 メソッドを移動する。

| メソッド | 経路 | HTTPメソッド |
|---|---|---|
| `res_totp_accounts` | `/api/totp/accounts` | GET |
| `res_totp_scan` | `/api/totp/scan` | POST |
| `res_totp_upload` | `/api/totp/upload` | POST |
| `res_totp_register` | `/api/totp/register` | POST |
| `res_totp_set_image` | `/api/totp/set_image` | POST |
| `res_totp_delete` | `/api/totp/delete` | POST |
| `res_totp_reorder` | `/api/totp/reorder` | POST |
| `res_totp_fetch_icon` | `/api/totp/fetch_icon` | POST |
| `res_totp_update` | `/api/totp/update` | POST |

mixin は `BaseHTTPRequestHandler` のインターフェース (`self.headers`, `self.rfile`, `self.api_json_response()`) に依存する設計のままにする。これは継承元クラスにより `MRO` で解決される。

各メソッド内の lazy import (`from .totp_account_manager import TotpAccountManager`, `from PIL import Image as PILImage` など) はそのまま保持。Mixin ファイル先頭での重い import を避けるためで、現状の起動時間特性を保つ。

### web_server.py の変更点

```python
# 追加
from .web_server_totp import TotpEndpointsMixin

# 変更
class DeckOutputWebHandler(TotpEndpointsMixin, http.server.BaseHTTPRequestHandler):
    ...
```

`do_GET` / `do_POST` の TOTP 関連 path 判定 (現在の `if self.path == '/api/totp/...'` の枝) は **無変更で残す**。これらは `self.res_totp_*()` を呼び出すだけで、mixin 経由で解決される。

### 互換性

外部から見た `mydeck.web_server` モジュール表面は変化なし:

- `from mydeck.web_server import DeckOutputWebHandler` — 変更なし
- `DeckOutputWebHandler.path_key_map`, `id_deck_map`, `touchscreen_image`, `id_current_page` (クラス変数) — `web_server.py` 側に残す
- `DeckOutputWebHandler.set_key_image()`, `set_touchscreen_image()`, `reset_keys()`, `remove_device()` (staticmethod) — `web_server.py` 側に残す
- `http.server.ThreadingHTTPServer(('', port), DeckOutputWebHandler)` — 動作変わらず

呼び出し側 (`my_decks_manager.py`, `my_decks.py`, `tests/test_device_resilience.py`) への変更は不要。

---

## Testing

### 自動テスト

`tests/test_device_resilience.py` は `mydeck.web_server` を `MagicMock` で丸ごとスタブ化しているため、内部分割の影響は受けない。既存テスト (pytest) が通り続けることを確認する。

```
uv run pytest tests/ -v
```

### 手動確認

TOTP 機能の自動テストは存在しないため、以下を起動確認する:

1. `python -c "from mydeck.web_server import DeckOutputWebHandler"` — import エラーなし
2. `mydeck` を起動 — Web UI が立ち上がる
3. ブラウザで `/totp` を開く — TOTP UI ページが表示される
4. `/api/totp/accounts` — 既存アカウント一覧が JSON で返る
5. 任意の TOTP アカウントで /totp ページの基本操作 (一覧表示) が動作する

スキャン/登録/削除など書き込み系の手動操作は任意 (リスクは低いが、確認できると望ましい)。

### 行数確認

リファクタ後 `wc -l src/mydeck/web_server.py` が **700 未満** であること。500–700 の警告レンジに収まる想定 (約 590 行)。

---

## Rollout

1. `web_server_totp.py` を新規作成し、mixin を実装。
2. `web_server.py` から TOTP メソッドを削除し、mixin を継承。
3. ローカルで pytest 全パスを確認。
4. `mydeck` を起動して /totp の動作を手動確認。
5. 単一コミットでマージ (機能等価リファクタなのでブランチ分割は不要)。

ロールバックは `git revert` で 1 コミットを戻すだけで完結する。

---

## Risks

- **Method Resolution Order (MRO)**: `class DeckOutputWebHandler(TotpEndpointsMixin, BaseHTTPRequestHandler)` の順序を間違えると `BaseHTTPRequestHandler` のメソッドを mixin が上書きする可能性がある。本件では mixin が `res_totp_*` のみを定義し `BaseHTTPRequestHandler` と名前衝突がないため実害はないが、`mixin → base` の順序を厳守する。
- **lazy import の重複**: 移動した各メソッド内に同じ import (`from .totp_account_manager import TotpAccountManager`) が散在するが、これは元コード由来のスタイル。リファクタの主旨外なので変更しない。
- **テストモック**: `tests/test_device_resilience.py` の `ws_stub.DeckOutputWebHandler = MagicMock()` は属性アクセスが MagicMock の魔法で通るため mixin 化の影響を受けない。
