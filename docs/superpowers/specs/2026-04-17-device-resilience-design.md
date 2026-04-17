# デバイス切断耐性設計

Date: 2026-04-17

## Overview

ノートPCのスリープ、USBケーブル抜去、デバイス電源断などでSTREAM DECKが切断された際に、`mydeck` プロセスをクラッシュさせず、再接続時に自動復帰させる。

具体的な要件:

1. 切断時にプロセスが落ちない（`TransportError` 等がトップレベルまで伝播しない）
2. スリープ復帰後、自動で元のページ・アプリ状態に戻る
3. 起動時に未接続でも、configsに登録済みのserialのデバイスが後から挿されれば認識・起動する
4. 未知 serial のデバイスは今回のスコープ外（自動config生成は将来課題）
5. 仮想デバイス（Web UIのみの`VirtualDeck`）は対象外（物理的に切断されないため）

---

## Architecture

### 責務の分割

`MyDecksManager` を「デバイスのライフサイクル管理者」に格上げする。3つの責務を持つ:

```
MyDecksManager
├── 初期 enumerate & MyDeck 生成（既存）
├── DeviceSupervisor（新規）: 3秒周期で enumerate、state更新・通知
└── 各 VirtualDeck が「接続状態」を保持、real I/O は DeckGuard 経由
```

### 新規コンポーネント

- **`DeckGuard`**: `real_deck` への全呼び出しを仲介する薄いラッパ。切断中は書き込み系をno-op、読取系はNone返却。`TransportError`/`OSError` を捕捉したら対応する`VirtualDeck`を切断状態に遷移させる。
- **`DeviceSupervisor`**: デーモンスレッド。3秒毎に `DeviceManager().enumerate()` を実行し、管理下のserialの生存を確認。新規出現・消失を検知して `MyDecksManager` に通知。
- **`~DISCONNECTED` ページ**: 予約ページ名。keys/apps/dials/touchなし。切断中の一時遷移先として使う。

### 変更コンポーネント

- **`VirtualDeck`**: `connected: bool` プロパティ追加。`mark_disconnected()` / `reattach(new_real_deck)` メソッド追加。
- **`MyDeck`**: `_pre_disconnect_page: str` プロパティ追加。`on_disconnect()` / `on_reconnect()` コールバック追加。
- **`MyDecksManager`**: supervisor起動、切断/再接続イベントのディスパッチ。

---

## State Model

`VirtualDeck.connected` を唯一の真実（single source of truth）とする。

```
 [CONNECTED] --TransportError or enumerate欠落--> [DISCONNECTED]
      ^                                                  |
      |                                                  |
      +-- enumerate一致 & real_deck再open成功 <----------+
```

- 仮想デバイス（`real_deck is None`）は常に `connected=True`（状態遷移対象外）。
- serial が一致した物理デバイス再検出時のみ再接続。別serialは無視。

---

## Data Flow

### 切断時

1. アプリスレッド（例: `AppClock`）または python-elgato-streamdeck の HID reader thread が `real_deck.set_key_image` 等を呼ぶ
2. `DeckGuard.__getattr__` でラップされた呼び出しが `TransportError` を発生
3. `DeckGuard` が例外を捕捉、該当 `VirtualDeck.mark_disconnected()` を呼ぶ
4. `VirtualDeck` が `MyDecksManager` へ通知（callback or event queue）
5. `MyDecksManager` が対応する `MyDeck.on_disconnect()` を呼ぶ
6. `MyDeck.on_disconnect()`:
   - 現ページを `_pre_disconnect_page` に保存
   - `set_current_page("~DISCONNECTED", add_previous=False)` を実行
7. 既存の `threading_apps()` が呼ばれ、`~DISCONNECTED` にはアプリ設定がないため、稼働中のフォアグラウンドアプリは `check_to_stop()` により全員自然終了
8. background_apps（例: `AppAlert`）はそのまま稼働するが、`real_deck.*` 呼び出しはすべて `DeckGuard` が no-op するので無害
9. Supervisor は次のtickで enumerate の欠落を確認し状態整合（既にDISCONNECTEDなら何もしない）

### 再接続時

1. Supervisor が3秒tickで `DeviceManager().enumerate()` 実行
2. 切断中 `VirtualDeck` の serial と一致するデバイスを発見
3. 新しい `real_deck.open()` を試行（失敗時は次tickで再試行）
4. 成功したら `VirtualDeck.reattach(new_real_deck)` を呼ぶ
5. `VirtualDeck`:
   - `real_deck` を差し替え
   - `connected=True`
   - `set_key_callback` / `set_dial_callback` / `set_touchscreen_callback` を再登録（新しい real_deck に bind し直す必要がある）
6. `MyDecksManager` が対応する `MyDeck.on_reconnect()` を呼ぶ
7. `MyDeck.on_reconnect()`:
   - `deck.reset()` で物理画面をクリア
   - `deck.set_brightness(30)` 等の初期化
   - `set_current_page(_pre_disconnect_page, add_previous=False)` で元ページへ復帰
8. 既存の `threading_apps()` でアプリ再起動、`key_touchscreen_setup()` で画像再描画される

### 起動時未接続デバイスの後挿し

1. `MyDecksStarter.check_configs` が既存通り `DeviceManager().enumerate()` を実行
2. 起動時に見つかった物理デバイス + configs に記載があるが未検出のserialも、空の `real_deck=None` 状態で `VirtualDeck` を作成（`connected=False` で開始）
3. `MyDeck` インスタンスは通常通り生成（ただし `on_disconnect` 相当の初期状態）
4. Supervisor が3秒tickで enumerate し、該当serialが見つかれば再接続フローと同じ処理で起動

※ `MyDecksStarter.check_configs` の対話処理（仮想デバイスを作るか等）は既存動作を変えない。起動時に既知・未知いずれの物理デバイスも無い場合の挙動（プロンプト）も維持する。

---

## Error Handling

- `DeckGuard` は `TransportError`（`StreamDeck.Transport.Transport.TransportError`）と `OSError` を捕捉。それ以外は rethrow。
- `real_deck.set_key_callback` は切断中に渡された callback を `VirtualDeck` 側でバッファ、再接続時に新 real_deck へ再登録する。
- Supervisor スレッドは最上位 `try/except Exception` でループを継続（supervisor自身が死なない）。想定外例外は `logging.error` + stack trace。
- `real_deck.open()` 失敗時は次のpollingで再試行。連続N回失敗時の特別処理は今回スコープ外。
- ログレベル:
  - 切断検知・再接続検知: `INFO`
  - 切断中に黙殺したI/O: `DEBUG`
  - supervisor の想定外例外: `ERROR`

---

## Concurrency & Locking

- `VirtualDeck.connected` の読み書きは `update_lock`（既存の `RLock`）で保護。
- `reattach` 中に別スレッドが I/O を呼ばないよう、`DeckGuard` も同じ `update_lock` を取る。
- Supervisor thread と I/O 呼び出しスレッド間のレースは `update_lock` で直列化。
- `MyDeck.on_disconnect/on_reconnect` は MyDecksManager のディスパッチャスレッドで同期実行（別スレッド化しない）。

---

## Configuration

ユーザー向け設定追加は最小限:

- `supervisor_interval`（秒、デフォルト `3`）: 将来的な拡張点。今回はハードコード定数で十分だが、定数として一箇所に定義し後から config 化できるようにしておく。

既存の `vdeck.yml` / `configs` 形式は変更なし。

---

## Testing Strategy

### Unit tests

- `DeckGuard`:
  - 接続中は real_deck を素通し
  - 切断中は書き込み系 no-op、読み取り系 None
  - `TransportError` 発生時に `mark_disconnected` が呼ばれる
- `VirtualDeck`:
  - `mark_disconnected` / `reattach` の状態遷移
  - `reattach` でcallback再登録
- `MyDeck`:
  - `on_disconnect` で現ページ保存 & `~DISCONNECTED` 遷移
  - `on_reconnect` で保存ページへ復帰
- `DeviceSupervisor`:
  - 新規・消失の検知、モック DeviceManager で制御

### Integration tests

- `MyDecksManager` レベル: 偽の DeviceManager 注入、切断→再接続シナリオで `~DISCONNECTED` 遷移と復帰を検証。
- 切断中にフォアグラウンドアプリが停止し、再接続後に再起動することを確認。
- 切断中に background_app が `set_key_image` を呼んでも例外が伝播しないことを確認。

### Manual verification

- 実機でUSB抜き挿し × 連続数回
- ノートPCスリープ→復帰
- 起動時デバイス未接続→後から挿す
- 別serial のデバイスを挿しても無視されることを確認

---

## Out of Scope

- 未知serialデバイスの自動config生成（plug-and-play フル対応）
- 接続状態の Web UI 可視化（将来課題）
- supervisor_interval のconfigファイル化
- 連続reconnect失敗時の exponential backoff
- HID レベルの低電力・省電力モード対応

---

## Migration / Compatibility

- 既存の設定ファイル（`vdeck.yml`, configs）は変更なし
- 既存API（`MyDecksManager.__init__`, `MyDeck` パブリックメソッド）にbreaking changeなし
- `VirtualDeck` に新プロパティ/メソッドが追加されるが、既存の使用箇所は互換
- 仮想デバイスのみの環境では実質的に何も変わらない（supervisor は物理デバイスの serial のみ監視）
