"""Archicadツールバー割当用スクリプト（Tapirのスクリプト割当機能でボタン化する）.

操作モデル（GLOOBE踏襲）:
  躯体スラブを選択 → このスクリプトを実行 → 足場ライン一括生成＋帳票一式出力

CLI（python3 -m ashiba.cli）と同じ solve_all/write_outputs を通すので、
ボタンから出る成果物もCLIと同じ（壁つなぎ最適化・階段・敷地・構造計算・
総合判定・設置届まで）。以前はこのスクリプトだけ手順を書き下しており、
構造計算も総合判定も無い薄いレポートしか出ていなかった。

条件（系列・軒高・開口部など）はデスクトップの ashiba_spec.json（入力JSONと同じキー）で
上書きできる。無ければ下の SPEC の既定値。系列だけなら --series=nikken_nd1800 でも指定できる。

部品（gdl/ashiba_line.gsm・ashiba_detail.gsm）は無ければ自動で埋め込みライブラリへ入れる
（配置パイプライン自体は Archicad 28 + Tapir 1.5.8 でE2E検証済み:
 scripts/e2e_archicad_test.py）。
"""

import json
import os
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from ashiba.cli import result_dict, solve_all, write_outputs  # noqa: E402
from ashiba.tapir_adapter import (  # noqa: E402
    MESH_MARGIN_MM,
    ArchicadClient,
    get_selected_outline_mm,
    slab_outline_mm_by_guid,
    place_details,
    place_elevations,
    place_scaffold_lines,
    read_ground_model,
)
from ashiba.elevation_sections import load_record, place_section_elevations, save_record  # noqa: E402

# ---- 条件入力（Phase 2でUIダイアログ化。当面はここを編集する） ----
# キー名と既定値は入力JSONと同じ（ashiba/cli.py のスキーマ参照）
SPEC = {
    "project_name": "足場計画",
    "series_id": "shinwa_A",
    "eaves_height_mm": 15400,      # 軒高
    "guard_extra_mm": 900,         # 最上層作業床固定点 = 軒高 + 手すり分
    "period_days": 90,
    "site": {"region": "関東(内陸)", "sheet_type": "メッシュシート"},
}
LINE_OBJECT = "ashiba_line"
DETAIL_OBJECT = "ashiba_detail"
MVO_OBJECT = "ashiba_mvo"           # モデル表示オプション（ライブラリグローバル）
GDL_DIR = Path(__file__).resolve().parents[1] / "gdl"


def versioned_part_name(base: str, gdl_dir: Path = GDL_DIR) -> str:
    """配布GSMの部品名（基本名_版）。版は build_dist_gsm.py が書く .gsm.hash（HSFのハッシュ8桁）.

    ハッシュが無ければ基本名のまま（手で読み込んだ部品を使う）。
    """
    stamp = gdl_dir / f"{base}.gsm.hash"
    if not stamp.exists():
        return base
    h = stamp.read_text(encoding="utf-8").strip()
    return f"{base}_{h}" if h.isalnum() and len(h) == 8 else base
PLACE_DETAILS = True               # 詳細図も並べるか
PLACE_ELEVATIONS = True            # 各面の立面図も並べるか
# 立面図の作り方。section=断面図ビューポイント（立面ツール相当）で3Dから投影しレイアウトへ／
# object=平面図の下に2Dオブジェクトで並べる（従来）／none=作らない。入力の elevation_mode で上書き
ELEVATION_MODE = "section"
FLOOR_LEVELS_MM: list[float] = []  # 立面に描く各階レベル（空なら描かない）
# 図面の並べ先。躯体外形の左下から下方向へ、立面→詳細図の順に置く
ELEVATION_OFFSET_MM = -45000.0
DETAIL_OFFSET_MM = -20000.0
OUT_DIR = Path.home() / "Desktop" / "ashiba_out"
# 条件をスクリプトを編集せずに変えるための上書きファイル（存在すれば SPEC に重ねる）。
# 中身は入力JSONと同じキー（series_id・eaves_height_mm・site・openings 等。outline_mm は
# 選択したスラブから取るので無視）。環境変数 ASHIBA_SPEC でパスを差し替えられる
SPEC_OVERRIDE = Path(os.environ.get("ASHIBA_SPEC", str(Path.home() / "Desktop" / "ashiba_spec.json")))


# 出力先に毎回書く上書き条件の雛形。"_" で始まるキーはコメント（検証で無視される）。
# 利用者が README を探さなくても、高さ・スパン・面名指定の書き方が手元に残る
SAMPLE_SPEC = {
    "_説明": "このファイルを ~/Desktop/ashiba_spec.json にコピーして値を変えると、ツールバー実行の条件になります。"
             "\"_\" で始まるキーはコメントなので残して構いません。外形（outline_mm）は選択したスラブから取ります",
    "project_name": "足場計画",
    "series_id": "shinwa_A",
    "_series_id": "shinwa_A / shinwa_B / nikken_nd1800 / nikken_nd1900 / waku（枠組）",
    "eaves_height_mm": 15400,
    "guard_extra_mm": 900,
    "_scaffold_height_mm": "足場高さを直接決めるときは scaffold_height_mm を書く（軒高＋手すり分より優先）。例: 15000",
    "building_height_mm": 16000,
    "period_days": 90,
    "guard_rail_type": "布材",
    "_guard_rail_type": "布材（手すり＋中桟＋幅木）／先行手すり（手すり＋X斜材一体・幅木なし）",
    "inner_guard_rail": True,
    "line_mode_3d": False,
    "elevation_mode": "section",
    "scaffold_form": "本足場",
    "_scaffold_form": "本足場／一側足場",
    "_span_overrides": "面ごとにスパン列を固定する例（面名は割付レポートの平面割付表と同じ。\"1800x5\" は1800を5本）",
    "_span_overrides_example": [{"face": "南面", "spans_mm": ["1800x5", 900, 900, "1800x11"]}],
    "_stairs": "階段の位置を決める例（省くと自動配置）",
    "_stairs_example": {"positions": [{"face": "南面", "start_mm": 1800}, {"face": "北面", "start_mm": 1800}]},
    "_openings_example": [{"face": "南面", "start_mm": 3600, "beam_span_mm": 3600, "level": 2}],
    "_loading_stages_example": [{"face": "南面", "start_mm": 12600, "span_count": 2, "projection_mm": 1500,
                                  "load_kn": 9.8, "levels": [3]}],
    "_hoists_example": [{"face": "北面", "position_mm": 9000, "landing_levels": [2, 5],
                         "cage_width_mm": 2400, "cage_depth_mm": 1800, "load_kn": 9.8}],
    "_hoists_note": "ロングスパンエレベーターの詳細図は昇降機1基に1枚。搬器寸法（cage_width_mm/cage_depth_mm）と"
                    "積載荷重（load_kn。9.8以上＝1t以上は設置届、2.45以上は設置報告）を書くと図と届出区分に反映",
    "_bracket_sections_example": [{"face": "東面", "start_mm": 0, "end_mm": 7200, "width": 400,
                                    "direction": "内", "levels": [1, 2]}],
    "site": {"region": "関東(内陸)", "sheet_type": "メッシュシート"},
    "notification": {"site_name": "現場名"},
}
SAMPLE_NAME = "ashiba_spec.sample.json"


def write_sample_spec(out_dir: Path) -> Path:
    """上書き条件の雛形を出力先に書く（毎回上書き。利用者の ashiba_spec.json には触らない）."""
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / SAMPLE_NAME
    p.write_text(json.dumps(SAMPLE_SPEC, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def elevation_face_titles(face_names: list, project_name) -> list:
    """立面図の表題に入れる面名。案件名があれば添える（複数棟を同じ図面に置くと、
    「立面図 南面」だけではどの棟か分からない）."""
    name = str(project_name or "").strip()
    if not name:
        return list(face_names)
    return [f"{n}　{name}" for n in face_names]


def load_spec_override() -> dict:
    """条件の上書きファイルを読む（無ければ空、壊れていれば止める）.

    以前は読めないと「既定の条件で続けます」と印字して進んでいたが、ツールバーからの
    実行では印字が見えず、waku を指定したつもりで信和Aの足場が置かれる。
    ファイルがあるのに読めない・オブジェクトでない場合は入力エラーで止める。
    """
    from ashiba.cli import InputError

    if not SPEC_OVERRIDE.exists():
        print(f"条件の上書きファイルは無し（既定条件）。条件を変えるには {SPEC_OVERRIDE} を置く"
              f"（雛形: {OUT_DIR / SAMPLE_NAME}）")
        return {}
    try:
        data = json.loads(SPEC_OVERRIDE.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        raise InputError(
            f"条件の上書きファイル {SPEC_OVERRIDE} を読めません（{e}）。"
            "JSON の綴り（末尾のカンマ・コメント不可）を直すか、ファイルを外してから実行してください"
        ) from None
    if not isinstance(data, dict):
        raise InputError(
            f"条件の上書きファイル {SPEC_OVERRIDE} はオブジェクト（{{ ... }}）で書いてください"
        )
    data.pop("outline_mm", None)    # 外形は選択したスラブから取る（ファイルの外形は無視）
    print(f"条件の上書き: {SPEC_OVERRIDE}（{', '.join(sorted(data))}）")
    return data


def main() -> None:
    client = ArchicadClient()
    spec = dict(SPEC)
    spec.update(load_spec_override())
    for a in sys.argv[1:]:
        if a.startswith("--series="):
            spec["series_id"] = a.split("=", 1)[1]
    # 外形: 通常は選択中のスラブ。環境変数 ASHIBA_SLAB=<GUID先頭> があればそのスラブ
    # （スクリプトからの検証用。表示中のフロアに無い要素は選択しても拾えないため）
    slab_guid = os.environ.get("ASHIBA_SLAB", "").strip()
    if slab_guid:
        spec["outline_mm"] = [list(p) for p in slab_outline_mm_by_guid(client, slab_guid)]
    else:
        spec["outline_mm"] = [list(p) for p in get_selected_outline_mm(client)]
    # 同梱の配布GSM（足場ライン・詳細図）を埋め込みライブラリに入れる。手で読み込んで
    # いなくても止まらないように（既に入っていれば何もしない）
    # 埋め込んだ部品は Tapir から上書きできないので、GSM の版（HSFのハッシュ）を
    # 名前に付けて埋め込む。GSM を更新すれば新しい名前で入り、古い部品は置き換え時に消える
    line_part = versioned_part_name(LINE_OBJECT)
    detail_part = versioned_part_name(DETAIL_OBJECT)
    # MVO部品は置かないが、ライブラリに入っていればモデル表示オプションに「仮設足場の表示設定」が出る
    added = client.ensure_embedded_parts([
        (GDL_DIR / f"{LINE_OBJECT}.gsm", line_part), (GDL_DIR / f"{DETAIL_OBJECT}.gsm", detail_part),
        (GDL_DIR / f"{MVO_OBJECT}.gsm", versioned_part_name(MVO_OBJECT)),
    ])
    if added:
        print(f"配布GSMを埋め込みライブラリへ追加: {', '.join(added)}")
    # 敷地メッシュがあれば高低差を拾う（無ければ平坦として解く）
    ground = read_ground_model(client, outline_mm=spec["outline_mm"])
    if ground.ignored_meshes:
        print(f"敷地メッシュ{ground.ignored_meshes}個は建物の範囲外（{MESH_MARGIN_MM / 1000:.0f}m以上離れている）"
              "なので、この棟の地盤には使いません")
    if not ground.is_flat:
        spec["ground_points_mm"] = [list(p) for p in ground.points]

    r = solve_all(spec)
    write_outputs(r, OUT_DIR)
    write_sample_spec(OUT_DIR)
    result = result_dict(r, OUT_DIR)

    lines = place_scaffold_lines(
        r.model, line_part, client, stair_plan=r.stair_plan,
        openings=r.openings, platforms=r.platforms, bracket_sections=r.brackets,
        terrain=r.terrain,
    )
    x0 = min(v[0] for v in r.model.plan.outline.vertices)
    y0 = min(v[1] for v in r.model.plan.outline.vertices)
    elevs = []
    elevation_mode = str(spec.get("elevation_mode") or ELEVATION_MODE)
    sections = []
    if elevation_mode == "section":
        # 立面は断面図ビューポイント（立面ツール相当）で作り、サブセット「仮設足場」のレイアウトに図面として置く
        prev = load_record(OUT_DIR)
        sections = place_section_elevations(r.model, client, prefix=str(spec.get("project_name") or "足場"), previous=prev)
        save_record(OUT_DIR, sections, prev)
        for pl in sections:
            for n in pl.notes:
                print(f"  立面（{pl.face_name}）: {n}")
    if PLACE_ELEVATIONS and elevation_mode == "object":
        # 面名は指定しなければ方位（南面・東面…）が入る
        elevs = place_elevations(
            r.model, line_part, stair_plan=r.stair_plan, openings=r.openings,
            platforms=r.platforms, bracket_sections=r.brackets, terrain=r.terrain,
            origin_mm=(x0, y0 + ELEVATION_OFFSET_MM),
            floor_levels_mm=FLOOR_LEVELS_MM or None, client=client,
            face_names=elevation_face_titles(r.model.plan.face_names(), spec.get("project_name")),
        )
    details = []
    if PLACE_DETAILS:
        details = place_details(
            r.model, r.detail_sheets, detail_part,
            origin_mm=(x0, y0 + DETAIL_OFFSET_MM), client=client,
        )

    # 同じスラブでの再実行は前回の配置を置き換える。外形や離れ・系列が変わると位置が
    # ずれるので「同じ位置」ではなく「このスラブに対して置いたもの」（外形の範囲と
    # 立面図・詳細図の行）で拾い、今回置いた分だけ残す（枠組→くさびの切替で7個残った）
    placed_now = {e["elementId"]["guid"] for e in lines + elevs + details}
    stale = [
        e for e in client.objects_for_slab(
            r.model.plan.outline.vertices, (LINE_OBJECT, DETAIL_OBJECT),
            elevation_offset_mm=ELEVATION_OFFSET_MM, detail_offset_mm=DETAIL_OFFSET_MM,
        ) if e["elementId"]["guid"] not in placed_now
    ]
    if stale:
        client.delete_elements(stale)
    replaced = len(stale)
    v = result["verdict"]
    n_sec = sum(1 for pl in sections if pl.drawing_guid)
    sec_txt = (f"立面図 {n_sec}面（断面図ビューポイント→レイアウト「仮設足場」、1/{sections[0].scale}）・"
               if sections else f"立面図 {len(elevs)}面・")
    print(f"足場ライン {len(lines)}本・" + sec_txt
          + f"詳細図 {len(details)}枚を配置しました"
          + (f"（前回の配置{replaced}個を置き換え）" if replaced else ""))
    print("総合判定: " + ("成立" if v["ok"] else "是正が必要"))
    for b in v["blockers"]:
        print(f"  是正: {b}")
    for kind, sev, text in r.warnings:
        if sev == "NG":
            print(f"    {kind}: {text}")
    if v["warn"]:
        print(f"  要確認 {v['warn']}件: " + "／".join(v["warn_breakdown"])
              + "（割付レポートの要確認一覧を参照）")
    print(f"帳票出力先: {OUT_DIR}")


if __name__ == "__main__":
    # CLI と同じく、入力・マスタ・耐力値・Archicad接続の失敗はトレースバックではなく
    # 原因と直し方を出して終了コード2で止める（上書きファイルの綴り違いもここに来る）
    from ashiba.cli import InputError
    from ashiba.geometry import ValidationError
    from ashiba.master import MasterDataError, SeriesLockError
    from ashiba.structural import CapacityError
    from ashiba.tapir_adapter import TapirError

    try:
        main()
    except (InputError, ValidationError, MasterDataError, SeriesLockError,
            CapacityError, TapirError) as e:
        print(f"[ashiba] {type(e).__name__}: {e}")
        raise SystemExit(2)
