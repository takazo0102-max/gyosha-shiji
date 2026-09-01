# ashiba — Archicad 仮設足場計画ツール（くさび緊結式）

Archicadの躯体モデルから、くさび緊結式足場の**割付・法規チェック・数量拾い・帳票生成**までを
一気通貫で行うツール。コアバリューは「Archicadから出ない。線を引けば割付が解けて、法規チェックまで付く」。

## アーキテクチャ

```
躯体外形（Tapir経由 or JSON） → 割付エンジン(純Python) → 足場ラインGDL配置 + 帳票出力
```

- **割付エンジンはArchicad非依存**（`src/ashiba/`）。Tapir接続は `tapir_adapter.py` に隔離
- **足場ライン方式**（最重要決定）: 部材1本ごとにオブジェクトを置かず、
  1つの辺＝1つのGDLオブジェクト（`gdl/ashiba_line.gdl`）が内部で
  支柱・布材・踏板・手すり・幅木・ブレスをパラメトリック生成する
- 部材マスタは外部CSV（`data/part_master.csv`）。**系列ロック**でインチ/センチ混在を機械的にブロック
- 呼び寸法(nominal)と実寸法(actual)を厳密分離: 割付計算は呼び寸法、描画は実寸法

## ディレクトリ

| パス | 内容 |
|---|---|
| `src/ashiba/master.py` | 部材マスタ読込・系列ロック |
| `src/ashiba/geometry.py` | 直交ポリゴン検証・出隅/入隅分類・足場中心線ループ |
| `src/ashiba/plan_solver.py` | 平面割付（コーナー固定点＋スパンDP＋離れ最適化＋全体シフト） |
| `src/ashiba/elevation_solver.py` | 立面割付（コマピッチDP・ジャッキ端数吸収・千鳥） |
| `src/ashiba/model.py` | 足場モデル・壁つなぎ自動配置 |
| `src/ashiba/law_check.py` | 法規チェック9項目（安衛則 根拠条文付き） |
| `src/ashiba/quantity.py` | 数量拾い（従属部材ルール・重量・トラック概算・架け面積） |
| `src/ashiba/report.py` | 数量表CSV・割付レポートMD・plan.json |
| `src/ashiba/cli.py` | ワンクリック実行CLI |
| `src/ashiba/tapir_adapter.py` | Archicad/Tapir接続（AC28+Tapir1.5.8 実機E2E検証済み） |
| `gdl/ashiba_line.gsm` | **足場ラインオブジェクト（コンパイル済み・そのままライブラリ読込可）** |
| `gdl/hsf/ashiba_line/` | 同GDLソース（HSF形式: paramlist + 1d/2d/3dスクリプト） |
| `gdl/ashiba_line.gdl` | 同スクリプトの単一ファイル参照版 |
| `gdl/kyakubu_detail_2d.gdl` | 脚部詳細図2Dシンボル（参照実装） |
| `scripts/run_from_archicad.py` | ツールバー割当用エントリ |
| `scripts/e2e_archicad_test.py` | 実機E2Eテスト（スラブ→割付→4辺配置→検証） |
| `scripts/dev_gsm_iterate.py` | GDL開発イテレーション（コンパイル→注入→配置→プレビュー） |

## 使い方

### スタンドアロン（Archicad不要）

```bash
cd ashiba
PYTHONPATH=src python3 -m ashiba.cli examples/rect_30x20.json --out out/
```

出力: `数量表.csv`（型番ベース・発注書兼用）/ `割付レポート.md`（平面割付・法規チェック・数量サマリ）/
`plan.json`（GDL配置・再編集用の機械可読データ）

### Archicadから（要 Tapir アドオン。AC28+Tapir1.5.8で実機検証済み）

1. `gdl/ashiba_line.gsm` をライブラリマネージャで読込（または埋め込みライブラリへ追加）
2. `scripts/run_from_archicad.py` の条件入力（系列・軒高・期間）を編集
3. Tapirのスクリプト割当でツールバーボタン化 → 躯体スラブを選択して実行

E2E確認は `python3 scripts/e2e_archicad_test.py`（テスト用スラブ作成→割付→
4辺配置→角度・パラメータ検証→3D/2Dプレビュー保存まで自動実行）。

### GDLの編集とコンパイル

ソースは `gdl/hsf/ashiba_line/`（HSF形式）。LP_XMLConverter（GRAPHISOFT LibDev Toolkit）で
`LP_XMLConverter hsf2libpart gdl/hsf/ashiba_line gdl/ashiba_line.gsm` としてGSM化する。
開発イテレーションは `scripts/dev_gsm_iterate.py <版番号>` で
コンパイル→埋め込みライブラリ注入→テスト配置→プレビュー画像化まで自動化済み
（埋め込みライブラリは同名上書き不可のため版名を変えて追加する方式）。

## 割付エンジンの要点（開発指示書 §4 準拠）

- **平面**: コーナー頂点は固定点（端数を受けない）。各辺は両端固定で
  真物 {1800,1500,1200,900,600} のみのDPスパン割（切断調整は存在しない）。
  端数は壁離れ250〜350で吸収し、全体XYシフトで対面バランスを最適化。
  離れ350超の面には対処案（落下防止材／内ブラケット）を自動提示
- **出隅は回し**（コーナー支柱1本を両面共有）、**入隅**は符号反転で処理。
  支柱帰属は「各辺は始点支柱を所有し終点支柱は所有しない」→ 二重計上ゼロ
- **立面**: 固定点は最上層作業床（軒高＋手すり分）、端数吸収は最下部（ジャッキ≤270＋短支柱）。
  コマピッチ刻みDPで本数最小・長尺優先。実例 G(270)+3800×4+900=16370 を再現（テスト済み）。
  隣接支柱のジョイント千鳥用の代替構成も出力

## 数量拾いの前提ルール（`QuantityRules` で調整可能）

- 本足場＝内外2列建地、支柱構成は内外同一とみなす
- 布材: 根がらみ内外2本＋作業層ごとに床レベル内外2本＋外側手すり・中桟2本
- 腕木＝布材600を支柱位置×(作業層＋根がらみ)
- ブレスは構面数（1800スパン×層）から自動算出。1800以外のスパンは注記で明示
- アンダーベース数＝ジャッキ数＝支柱位置×列数
- 架け面積＝(建物外周+4m)×(建物高さ+0.5m)

## テスト

```bash
cd ashiba
/usr/local/bin/python3.13 -m unittest discover -s tests
```

受け入れ基準（指示書§10）はすべてテスト化済み:
矩形ワンクリック生成 / 実例値16370の再現 / L型の出隅・入隅と二重計上なし /
違反モデルでの法規9項目全検出 / 離れ250〜350または対処案提示。

## 制約・免責（指示書§9）

- **MVP範囲**: 信和A系列・矩形/L型（直交90度コーナーのみ）。非直交は明示的に拒否
- 部材の**単位重量はカタログ近似の概算値**。数量（本数）は割付から厳密だが、
  重量・トラック台数は概算。実運用前にマスタCSVの重量を自社データで差し替えること
- Tapir接続・GDL 3D/2D生成は Archicad 28 (Mac, Intel) + Tapir 1.5.8 でE2E検証済み。
  他バージョンではTapirコマンドの応答形式差分に注意（実機の落とし穴メモは
  `tapir_adapter.py` 冒頭のdocstringに集約）
- 本ツールの出力は計画作成参画者（有資格者）が確認する前提の下書き

## ロードマップ

- **Phase 1（本実装）**: 平面/立面割付・法規チェック9項目・数量CSV・架け面積・足場ラインGDL
- Phase 2: 詳細図5枚・構造計算書Excel転記・様式20号下書き
- Phase 3: B系列/インチ/枠組/次世代、ブラケット区間、朝顔、階段自動配置
- Phase 4: 敷地メッシュ連動ジャッキ表、GL高低差、壁つなぎ風荷重
