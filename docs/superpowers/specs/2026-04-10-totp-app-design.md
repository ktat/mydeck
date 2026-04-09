# TOTP 2FA App Design

Date: 2026-04-10

## Overview

StreamDeck上でTOTP（Time-based One-Time Password）認証コードを表示するアプリ。
複数アカウントを管理し、選択したアカウントのコードをリアルタイムに表示する。

---

## Architecture

### New file
- `src/mydeck/app_totp.py` — `AppTOTP` クラス（ThreadAppBase サブクラス）

### Modified file
- `src/mydeck/web_server.py` — QR登録用エンドポイントを追加

### Dependencies (new)
- `pyotp` — TOTP コード生成
- `pyzbar` — QR画像からotpauth URIをデコード
- `keyring` — GNOME Keyringとの連携（シークレット保存）

---

## Page Flow

```
メインページ
  └─[2FAボタン]─→ アカウント一覧ページ
                    ├─[GitHub]─→ 詳細ページ(GitHub)
                    ├─[Google]─→ 詳細ページ(Google)
                    ├─[AWS]─→   詳細ページ(AWS)
                    └─[戻る(右下)]─→ メインページ

詳細ページ(各アカウント)
  ├─ 数字キー（左上から順に6桁を配置）
  ├─ カウントダウン円キー（独立したキー1つ）
  └─[戻る(右下)]─→ アカウント一覧ページ
```

---

## Key Layouts

### アカウント一覧ページ（15キー: 3行×5列の例）

```
行1: [GitHub][Google][AWS][ ][ ]
行2: [ ][ ][ ][ ][ ]
行3: [ ][ ][ ][ ][戻る]
```

### 詳細ページ（15キー: 3行×5列の例）

```
行1: [1][2][3][4][5]
行2: [6][⏱][ ][ ][ ]
行3: [ ][ ][ ][ ][戻る]
```

### 詳細ページ（6キー: 2行×3列の例）

```
行1: [12][34][56]
行2: [⏱][ ][戻る]
```

### キー数に応じた桁数の自動計算

利用可能キー数 = 総キー数 - 2（カウントダウン1 + 戻る1）
1キーあたりの桁数 = ceil(6 / 利用可能キー数)

---

## Data Storage

### アカウント一覧
`~/.config/mystreamdeck/totp_accounts.json`（機密情報なし）:

```json
[
  {"name": "GitHub", "issuer": "GitHub"},
  {"name": "Google", "issuer": "Google"}
]
```

### シークレットキー
GNOME Keyring（libsecret）経由で保存・取得:

```python
import keyring

# 保存
keyring.set_password("mystreamdeck-totp", "GitHub", "JBSWY3DPEHPK3PXP")

# 取得
secret = keyring.get_password("mystreamdeck-totp", "GitHub")
```

---

## Web UI (QR Registration)

既存の `web_server.py` に以下のエンドポイントを追加:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/totp` | 登録フォームUI（HTML） |
| POST | `/totp/upload` | QR画像アップロード → pyzbarでデコード → keyringに保存 |
| POST | `/totp/register` | `otpauth://totp/...` URI またはシークレット文字列を直接入力 |
| DELETE | `/totp/delete/<name>` | アカウント削除 |

### 登録フロー（QR画像）
1. ユーザーがQR画像をアップロード
2. `pyzbar.decode()` でQRコードをデコード
3. `otpauth://totp/<name>?secret=<BASE32>&issuer=<issuer>` をパース
4. `totp_accounts.json` にアカウント情報を追記
5. `keyring.set_password()` でシークレットを保存

### 登録フロー（テキスト入力）
1. ユーザーが `otpauth://` URI またはシークレット文字列を貼り付け
2. URIの場合はパース、文字列の場合はnameと合わせて登録
3. 上記4-5と同様

---

## Visual Rendering

### 数字キー
- PILで黒背景に白文字
- 1桁の場合: 大フォント（例: 60px）
- 2桁の場合: 中フォント（例: 40px）
- コードが切り替わる瞬間（30秒ごと）に全数字キーを一斉更新

### カウントダウン円キー
- `ImageDraw.pieslice()` でパックマン型の円グラフを描画
- 毎秒更新: `angle = 360 * (remaining_seconds / 30)`
- 残り時間が少ないほど欠けていく（視覚的に残り時間を表現）
- 残り5秒以下で色を赤に変更（警告表示）

### アカウント一覧キー
- アカウント名を中央に表示
- 長い場合は2行に折り返し
- アイコン画像があれば上部に表示（オプション、将来拡張）

---

## AppTOTP Class Structure

```python
class AppTOTP(ThreadAppBase):
    use_thread = True

    def __init__(self, mydeck, config={}):
        # config: accounts_file path, etc.

    def start(self):
        # メインループ: 毎秒コードとカウントダウンを更新

    def on_key_press(self, key):
        # キー押下ハンドラ: ページ遷移 or 戻る

    def render_accounts_page(self):
        # アカウント一覧キーを描画

    def render_detail_page(self, account_name):
        # 数字キーとカウントダウンキーを描画

    def _render_digit_keys(self, code, available_keys):
        # 6桁コードをキー数に応じて分配して描画

    def _render_countdown_key(self, key_index):
        # 残り時間の円グラフを描画
```
