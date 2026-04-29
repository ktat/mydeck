# app_weather_jp.py 静的データ JSON 抽出 リファクタリング設計

Date: 2026-04-30

## Overview

`src/mydeck/app_weather_jp.py` (現在 1244 行) が `~/.claude/hooks/check-file-size.sh` の 700 行ブロック上限に抵触している。ファイルの **約 84% (1049 行)** は 3 つの mapping 関数 (`division_mapping` / `area_mapping` / `forecast_mapping`) が静的辞書を return しているだけで、コードロジックは含まない純粋なデータ。これを JSON ファイルに抽出する。

特筆: `forecast_mapping` 単独で 829 行あり、Python ファイルに切り出しても再度 700 行超になる。`.json` は当該 hook の対象外 (`*.md|*.json|*.yaml|*.yml|*.toml|*.lock|*.svg|*.css` をスキップ) なので JSON 抽出が唯一のクリーンな解。

スコープ:

- 機能変更なし。3 関数の **戻り値の形と内容** はバイト単位で同一。
- 外部公開 API (`AppWeatherJp` クラス、3 mapping 関数の名前と振る舞い) を保持。
- パッケージインストール時に JSON ファイルが配布されるよう `pyproject.toml` の `package-data` を更新。

スコープ外:

- 700 行を超えている他のファイル (`my_decks.py`, `tests/test_device_resilience.py`) — 別 spec。
- mapping 関数のキャッシュ最適化以上の機能改善。
- 他の app_*.py ファイルへの同様処理。

---

## Architecture

### ファイル構成

```
src/mydeck/
├── app_weather_jp.py                # 1244 -> 約 200 行に縮小
└── weather_jp_mappings.json         # 新規、約 1050 行 (静的データ)
```

### weather_jp_mappings.json

ルートはオブジェクトで 3 キーを持つ:

```json
{
  "division": { "宗谷地方": "011000", "...": "..." },
  "area":     { "宗谷": "011000", "...": "..." },
  "forecast": {
    "100": ["100.svg", "500.svg", "100", "晴", "CLEAR"],
    "...": ["..."]
  }
}
```

各サブツリーは現在の `division_mapping()` / `area_mapping()` / `forecast_mapping()` の戻り値と完全一致。

### app_weather_jp.py 変更点

1. **import 追加**: `import os` (既存の `import json` は流用)。

2. **モジュールレベルのキャッシュとローダ追加**:

   ```python
   _MAPPINGS_CACHE: Optional[dict] = None
   _MAPPINGS_PATH = os.path.join(os.path.dirname(__file__), "weather_jp_mappings.json")

   def _load_mappings() -> dict:
       global _MAPPINGS_CACHE
       if _MAPPINGS_CACHE is None:
           with open(_MAPPINGS_PATH, encoding="utf-8") as f:
               _MAPPINGS_CACHE = json.load(f)
       return _MAPPINGS_CACHE
   ```

3. **3 mapping 関数の本体置換**:

   ```python
   def division_mapping():
       return _load_mappings()["division"]

   def area_mapping():
       return _load_mappings()["area"]

   def forecast_mapping():
       return _load_mappings()["forecast"]
   ```

4. **削除**: 現 line 196-265 (`division_mapping` 本体)、266-415 (`area_mapping`)、416-1244 (`forecast_mapping`)。

### pyproject.toml 変更

現状:
```
[tool.setuptools.package-data]
mydeck = ["Assets/**/*", "html/**/*"]
```

変更後:
```
[tool.setuptools.package-data]
mydeck = ["Assets/**/*", "html/**/*", "*.json"]
```

`*.json` を package-data に追加する。これにより `pip install` / `uv pip install` 時に `weather_jp_mappings.json` が `mydeck/` パッケージディレクトリに配置される。

### MANIFEST.in

ソース配布 (`sdist`) には `*.py` と前述の `Assets`/`html` のみを含める設定。`weather_jp_mappings.json` も sdist に含めるよう以下を追加:

```
include src/mydeck/*.json
```

(現状は `recursive-include src/mydeck/Assets *` 等しか書かれておらず、JSON は sdist から漏れる可能性があるため)

### 互換性

- **`from mydeck.app_weather_jp import division_mapping, area_mapping, forecast_mapping`**: 関数名・シグニチャ・戻り値は不変。
- **`from .app_weather_jp import *`** (`__init__.py`): 関数 + クラスの公開シンボルは変わらない。
- **キャッシュの副作用**: `_MAPPINGS_CACHE` はモジュール初回参照時にだけロード。プロセス内で複数回 `division_mapping()` を呼んでも JSON ファイルは 1 度しか読まない。元コード (毎回新しい dict を return) と異なり同じ dict 参照を返す点だけ差分があるが、現行コードでは戻り値を変更している箇所はないため実害なし。

---

## Testing

### 自動テスト

`tests/test_plugin_resolution.py` が `mydeck.app_weather_jp.AppWeatherJp` を文字列参照で検証している。リファクタ後も同じく動作する想定。

```
uv run pytest tests/ -x -q
```

ベースライン: 60 passed。リファクタ後も 60 passed であること。

### 手動確認

```bash
uv run python -c "
from mydeck.app_weather_jp import division_mapping, area_mapping, forecast_mapping
d = division_mapping(); a = area_mapping(); f = forecast_mapping()
print('division entries:', len(d), 'sample:', next(iter(d.items())))
print('area entries:', len(a), 'sample:', next(iter(a.items())))
print('forecast entries:', len(f), 'sample:', next(iter(f.items())))
"
```

期待: 元コードと同じ件数・同じ最初のエントリが返る。

### 行数確認

- `wc -l src/mydeck/app_weather_jp.py` < 700 (目標 ~200)
- `wc -l src/mydeck/weather_jp_mappings.json` は制約なし (.json は hook 対象外)

### データ等価性確認 (重要)

リファクタ前後で 3 つの dict が完全一致することを以下で確認:

```bash
# Before refactor (run on main branch or via git stash):
git show main:src/mydeck/app_weather_jp.py > /tmp/orig_weather.py
uv run python -c "
import sys; sys.path.insert(0, '/tmp')
import importlib.util
spec = importlib.util.spec_from_file_location('orig_weather', '/tmp/orig_weather.py')
# ... but mydeck.app_weather_jp imports from mydeck which makes this awkward.
"
```

実装の簡便のため、以下の手順で代替する:

1. `main` ブランチで `python -c "from mydeck.app_weather_jp import division_mapping, area_mapping, forecast_mapping; import json; print(json.dumps({'division': division_mapping(), 'area': area_mapping(), 'forecast': forecast_mapping()}, ensure_ascii=False, indent=2))" > /tmp/orig_mappings.json` を取得。
2. これをそのまま `src/mydeck/weather_jp_mappings.json` として配置。
3. リファクタ後、同じコマンドを refactor ブランチで実行し、`/tmp/refactor_mappings.json` に保存。
4. `diff /tmp/orig_mappings.json /tmp/refactor_mappings.json` が空であることを確認。

---

## Rollout

1. `main` ブランチから 3 mapping 関数の戻り値をダンプして JSON 化、`src/mydeck/weather_jp_mappings.json` を生成。
2. `app_weather_jp.py` の 3 関数を JSON ロード版に書き換え、データ部 (line 196-1244) を削除、`os` import 追加。
3. `pyproject.toml` の `package-data` に `*.json` を追加。
4. `MANIFEST.in` に `include src/mydeck/*.json` を追加。
5. データ等価性確認 (上記)。
6. pytest 全パスを確認。
7. 単一コミット。

---

## Risks

- **データ抽出の正確性**: 1049 行の Python dict を JSON 化する際、文字エンコーディング (日本語) や型 (キーは全部 string) が崩れる可能性。`ensure_ascii=False` で UTF-8 のまま JSON 化し、`diff` で完全一致を検証する。
- **package-data の漏れ**: pip install 後に JSON が見つからない事態を避けるため、`pyproject.toml` の `package-data` と `MANIFEST.in` の両方を更新する。インストール後の動作確認 (`uv pip install -e .` のうえ import smoke check) は推奨。
- **キャッシュの初期化順**: `_MAPPINGS_CACHE = None` はモジュール import 時に評価される。テストで `app_weather_jp` を import した直後に `division_mapping()` を呼んだとき、JSON ファイルへのパス解決が正しいか確認。
- **JSON ファイル不在時の挙動**: `_load_mappings` は FileNotFoundError を伝播する (catch しない)。これは元コード (mapping 関数が常に dict を返す) と挙動が異なるが、実運用上 JSON ファイルが欠ける = パッケージインストール不全であり、明示的にエラーとなる方が望ましい。
