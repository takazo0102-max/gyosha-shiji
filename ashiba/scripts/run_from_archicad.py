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
 scripts/e2e_archicad_test.py。断面図方式の立面・平面図レイアウトは Archicad 30 + Tapir 1.7.0。
 Tapir が 1.7.0 より古ければ立面は部品方式に自動で戻す: ashiba/tapir_features.py）。
"""

import json
import os
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from ashiba.cli import result_dict, solve_all, write_outputs  # noqa: E402
from ashiba.detail_sheet import place_detail_sheet  # noqa: E402
from ashiba.pdf_publish import DEFAULT_PUBLISHER_SET, publish_scaffold_pdf  # noqa: E402
from ashiba.project_info import fill_title_block  # noqa: E402
from ashiba.tapir_features import choose_elevation_mode, environment_notes  # noqa: E402
from ashiba.tapir_adapter import (  # noqa: E402
    is_ashiba_part,
    TapirError,
    MESH_MARGIN_MM,
    ArchicadClient,
    get_selected_outline_mm,
    slab_outline_mm_by_guid,
    place_details,
    place_elevations,
    place_scaffold_lines,
    read_ground_model,
)
from ashiba.elevation_sections import (  # noqa: E402
    activate_floor_plan,
    building_key,
    load_record,
    load_record_meta,
    remove_stale_prefixes,
    place_plan_sheet,
    place_section_elevations,
    save_record,
)

# ---- 条件入力（Phase 2でUIダイアログ化。当面はここを編集する） ----
# キー名と既定値は入力JSONと同じ（ashiba/cli.py のスキーマ参照）
SPEC = {
    "project_name": "足場計画",
    "series_id": "shinwa_A",
    "module": "",                  # "inch" でインチ（1829/1524/1219/914/610）。series_id を空にすれば既定の日建ND1800
    "eaves_height_mm": 15400,      # 軒高
    "guard_extra_mm": 900,         # 最上層作業床固定点 = 軒高 + 手すり分
    "period_days": 90,
    "site": {"region": "関東(内陸)", "sheet_type": "メッシュシート"},
}
LINE_OBJECT = "ashiba_line"
DETAIL_OBJECT = "ashiba_detail"
MVO_OBJECT = "ashiba_mvo"           # モデル表示オプション（ライブラリグローバル）
SPEC_OBJECT = "ashiba_spec"         # 足場条件（ツールバーが読む入力条件の部品）
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
    "module": "",
    "_module": "\"inch\"（インチ: 1829/1524/1219/914/610）か \"metric\"（メートル: 1800/1500/1200/900/600）。series_id を空にすれば既定の系列（インチ=nikken_nd1800、メートル=shinwa_A）。両方書いて食い違うと止まる",
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


def read_spec_objects(client) -> list:
    """プロジェクトの足場条件部品を (要素, 原点mm, パラメータ) の一覧で返す."""
    objs = client.tapir("GetElementsByType", {"elementType": "Object"}).get("elements", [])
    found = []
    for e, d in zip(objs, client.get_details(objs) if objs else []):
        dd = d.get("details", {})
        lp = dd.get("libPart") or {}
        if not is_ashiba_part(lp.get("name", "") if isinstance(lp, dict) else "", (SPEC_OBJECT,)):
            continue
        o = dd.get("origin") or {}
        resp = client.tapir("GetGDLParametersOfElements", {"elements": [e]})
        item = (resp.get("gdlParametersOfElements") or [{}])[0]
        params = {p.get("name"): p.get("value") for p in item.get("gdlParameters", item.get("parameters", []))}
        found.append((e, (float(o.get("x", 0)) * 1000.0, float(o.get("y", 0)) * 1000.0), params))
    return found


def apply_spec_object(client, spec: dict) -> dict:
    """この建物の足場条件部品を読んで条件に重ねる。無ければ今の条件で部品を置く."""
    from ashiba.spec_object import merge_object_into_spec, params_from_spec, pick_spec_object, spec_from_params, spec_object_position

    hit = pick_spec_object(read_spec_objects(client), spec["outline_mm"])
    if hit is not None and not hit[1]:
        # 部品が埋め込みライブラリから消えると、置いた条件部品のパラメータは1つも読めなくなる
        # （2026-10-18 実機: 古い版を整理したときに置いてある版まで消えた）。空の条件として読まず、置き直す
        print("足場条件の部品の値を読めません（部品がライブラリから消えた可能性）。消して今の条件で置き直します"
              "（前の条件は戻らないので、設定ダイアログで入れ直してください）")
        try:
            client.delete_elements([hit[0]])
        except TapirError:
            pass
        hit = None
    if hit is not None:
        _el, params = hit
        obj = spec_from_params(params)
        print(f"条件: 足場条件の部品から（{', '.join(sorted(obj))}）。JSON より優先します")
        return merge_object_into_spec(spec, obj)
    name = versioned_part_name(SPEC_OBJECT)
    x, y = spec_object_position(spec["outline_mm"])
    try:
        el = client.create_object(name, x, y)
        client.set_gdl_parameters(el, params_from_spec(spec), name)
        print("足場条件の部品を建物の左下に置きました。次からは、その部品の設定ダイアログで条件を変えて"
              "ツールバーを実行してください（JSON より優先）")
    except TapirError as e:
        print(f"足場条件の部品を置けませんでした（{e}）。JSON の条件で続けます")
    return spec


def line_floor(client, lines: list[dict]):
    """足場ラインを置いたフロアの番号（読めなければ None＝現在のフロア）."""
    if not lines:
        return None
    try:
        det = client.tapir("GetDetailsOfElements", {"elements": lines[:1]}).get("detailsOfElements", [])
        return int(det[0]["floorIndex"]) if det and "floorIndex" in det[0] else None
    except (TapirError, KeyError, TypeError, ValueError):
        return None


def place_plan_annotations(client, r, out_dir, lines: list[dict]) -> tuple[int, int]:
    """平面図に寸法（寸法ツール）と部材名のラベルを置き、GUID を建物ごとに控える。(寸法数, ラベル数) を返す.

    前回この建物に置いた分は控えの GUID で消してから置く。寸法が置けた足場ラインは dimTool=True にして、
    部品が描くスパン寸法と二重にしない（置けなければ部品の寸法のまま）。失敗しても配置は止めない。
    """
    from ashiba.elevation_sections import building_key, create_labels, fit_scale, plan_region_mm
    from ashiba.plan_labels import plan_dimension_data, plan_labels, remove_plan_labels, save_label_record

    bkey = building_key(r.model.plan.outline.vertices)
    guids: list[str] = []
    n_dim = n_lab = 0
    try:
        activate_floor_plan(client)
        remove_plan_labels(client, out_dir, bkey)
    except TapirError:
        pass
    try:
        res = client.tapir("CreateAssociativeDimensions",
                           {"dimensionsData": plan_dimension_data(r.model, lines, r.platforms)})
        made = [el for el in res.get("elements", [])]
        ok = [el["elementId"]["guid"] for el in made if "elementId" in el]
        guids += ok
        n_dim = len(ok)
        # 面ごとに2本（スパン・全長）。両方置けた面だけ部品の寸法を消す
        for k, line in enumerate(lines):
            pair = made[2 * k:2 * k + 2]
            if len(pair) == 2 and all("elementId" in el for el in pair):
                client.set_gdl_parameters(line, {"dimTool": True})
        errs = [el.get("error", {}).get("message", "") for el in made if "elementId" not in el]
        if errs:
            print(f"  平面図: 寸法ツールで置けなかった寸法 {len(errs)}本（部品の寸法のまま）: {errs[0]}")
    except TapirError as e:
        print(f"  平面図: 寸法ツールの寸法を置けませんでした（部品の寸法のまま）: {e}")
    try:
        region = plan_region_mm(r.model)
        scale = fit_scale((region[2] - region[0], region[3] - region[1]), (841.0, 594.0)) or 200
        labels = plan_labels(r.model, r.stair_plan, text_scale=float(scale), platforms=r.platforms)
        lab = create_labels(client, labels, floor_index=line_floor(client, lines))
        guids += lab
        n_lab = len(lab)
    except TapirError as e:
        print(f"  平面図: 部材名のラベルを置けませんでした（{e}）")
    save_label_record(out_dir, bkey, guids)
    return n_dim, n_lab


def main(outline_mm=None, spec_override=None, out_dir=None, use_spec_object=True, fill_title=True) -> dict:
    """ツールバーの本体。置いたものと結果を dict で返す（実機スモーク scripts/smoke_archicad.py が照合に使う）.

    spec_override を渡すと、デスクトップの条件ファイルとコマンド引数の代わりにそれを使う。
    out_dir を渡すと帳票と立面の控えをそこへ書く（利用者の ashiba_out を汚さない）。
    use_spec_object=False なら足場条件の部品を読まず、置きもしない。
    fill_title=False ならプロジェクト情報（表題欄）に触らない（スモークは利用者のプロジェクト情報を変えない）。
    """
    OUT_DIR = Path(out_dir) if out_dir else globals()["OUT_DIR"]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    client = ArchicadClient()
    if not client.wait_ready():
        raise TapirError("Archicad が2分以上応答しません。ダイアログを閉じるか操作を止めてから、もう一度実行してください")
    # 版を見て、使える機能を決める（古い Tapir で断面方式を試して途中で止まらないように）
    tapir_v, archicad_v = client.versions()
    for n in environment_notes(tapir_v, archicad_v):
        print(f"注意: {n}")
    # スラブ・足場部品は平面図のデータベースにある。レイアウトや断面が前面だと見つからない
    activate_floor_plan(client)
    spec = dict(SPEC)
    override = load_spec_override() if spec_override is None else dict(spec_override)
    spec.update(override)
    # 条件ファイルが module（インチ／メートル）だけを書いて series_id を書かないときは、
    # ここの既定の series_id（信和A）に引きずられずにそのモジュールの既定系列を使う
    if override.get("module") and not override.get("series_id"):
        spec.pop("series_id", None)
    if not spec.get("module"):
        spec.pop("module", None)
    for a in (sys.argv[1:] if spec_override is None else []):
        if a.startswith("--series="):
            spec["series_id"] = a.split("=", 1)[1]
        if a.startswith("--module="):
            # --module=inch: インチの既定系列（日建ND1800）。series_id を一緒に指定して食い違えば止まる
            spec["module"] = a.split("=", 1)[1]
            if "--series=" not in " ".join(sys.argv[1:]):
                spec.pop("series_id", None)
    # 外形: 通常は選択中のスラブ。環境変数 ASHIBA_SLAB=<GUID先頭> があればそのスラブ
    # （スクリプトからの検証用。表示中のフロアに無い要素は選択しても拾えないため）
    slab_guid = os.environ.get("ASHIBA_SLAB", "").strip()
    if outline_mm:
        spec["outline_mm"] = [list(p) for p in outline_mm]        # 読み戻し→解き直し（plan.json の外形）
    elif slab_guid:
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
        (GDL_DIR / f"{SPEC_OBJECT}.gsm", versioned_part_name(SPEC_OBJECT)),
    ])
    if added:
        print(f"配布GSMを埋め込みライブラリへ追加: {', '.join(added)}")
    # 足場条件の部品: あればその条件を JSON より優先して使う。無ければいまの条件で置く
    if use_spec_object:
        spec = apply_spec_object(client, spec)
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
    # 平面の部材名ラベル（引出線つき）。前回この建物に置いたラベルは控えの GUID で消してから置く
    plan_dim_n, plan_label_n = place_plan_annotations(client, r, OUT_DIR, lines)
    x0 = min(v[0] for v in r.model.plan.outline.vertices)
    y0 = min(v[1] for v in r.model.plan.outline.vertices)
    elevs = []
    elevation_mode, mode_notes = choose_elevation_mode(str(spec.get("elevation_mode") or ELEVATION_MODE), tapir_v)
    for n in mode_notes:
        print(f"  立面: {n}")
    sections = []
    plan_sheet = None
    if elevation_mode == "section":
        # 立面は断面図ビューポイント（立面ツール相当）で作り、サブセット「仮設足場」のレイアウトに図面として置く
        prefix = str(spec.get("project_name") or "足場")
        bkey = building_key(r.model.plan.outline.vertices)
        prev = load_record(OUT_DIR)
        # 同じ建物で工事名を変えたときは、古い名前の断面・レイアウトを先に片付ける
        prev, gone = remove_stale_prefixes(client, prev, load_record_meta(OUT_DIR), bkey, prefix)
        if gone:
            print(f"  立面: 工事名を変えたので、前の名前（{'・'.join(gone)}）の断面とレイアウトを片付けました")
        sections = place_section_elevations(r.model, client, prefix=prefix, previous=prev, terrain=r.terrain,
                                            stair_plan=r.stair_plan,
                                            on_sections=lambda res: save_record(OUT_DIR, res, prev, bkey, prefix))
        save_record(OUT_DIR, sections, prev, bkey, prefix)
        # 足場平面図も同じサブセットのレイアウトへ（配置フロアの平面を足場の範囲で切り抜く）
        plan_sheet = place_plan_sheet(r.model, client, prefix=str(spec.get("project_name") or "足場"),
                                      floor_index=line_floor(client, lines))
        for n in plan_sheet.notes:
            print(f"  平面図: {n}")
        if plan_sheet.drawing_guid:
            print(f"  平面図: レイアウト「{plan_sheet.layout_name}」に 1/{plan_sheet.scale}")
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
    detail_sheet = None
    if PLACE_DETAILS:
        details = place_details(
            r.model, r.detail_sheets, detail_part,
            origin_mm=(x0, y0 + DETAIL_OFFSET_MM), client=client,
        )
        if elevation_mode == "section" and details:
            # 詳細図もサブセット「仮設足場」のレイアウトへ（部品を 1/20 の文字で描かせ、詰め直して切り抜く）
            detail_sheet = place_detail_sheet(client, details, [s.title for s in r.detail_sheets],
                                              prefix=str(spec.get("project_name") or "足場"))
            for n in detail_sheet.notes:
                print(f"  詳細図: {n}")
            if detail_sheet.drawing_guids:
                print(f"  詳細図: レイアウト「{detail_sheet.layout_name}」に {len(detail_sheet.drawing_guids)}枚、1/{detail_sheet.scale}")

    # レイアウトの表題欄: 工事名・敷地住所・施工者・計画作成者をプロジェクト情報へ（空の項目と、前回ツールが
    # 書いた値のままの項目だけ。利用者が入れた値は変えない）
    if fill_title and elevation_mode == "section":
        written, title_notes = fill_title_block(client, spec, OUT_DIR)
        if written:
            print("  表題欄: プロジェクト情報に " + "・".join(f"{k}={v}" for k, v in written.items()))
        for n in title_notes:
            print(f"  表題欄: {n}")

    # 足場のレイアウト一式を PDF に（サブセット「仮設足場」だけ。失敗しても配置は止めない）
    pdf = None
    if elevation_mode == "section" and spec.get("pdf", True):
        pdf = publish_scaffold_pdf(client, OUT_DIR / "PDF",
                                   str(spec.get("pdf_publisher_set") or DEFAULT_PUBLISHER_SET),
                                   prefix=str(spec.get("project_name") or "足場"))
        for n in pdf.notes:
            print(f"  PDF: {n}")
        if pdf.files:
            print(f"  PDF: {len(pdf.files)}枚を {OUT_DIR / 'PDF'} に発行（{'・'.join(p.stem for p in pdf.files)}）")
        activate_floor_plan(client)

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
    sheet = sections[0].layout_name if sections else ""
    sec_txt = (f"立面図 {n_sec}面（断面図ビューポイント→レイアウト「{sheet}」{'に1枚' if sections and all(p.layout_name == sheet for p in sections) else '（面ごと）'}、1/{sections[0].scale}）・"
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
    return {"result": r, "spec": spec, "lines": lines, "elevations": elevs, "details": details,
            "sections": sections, "plan_sheet": plan_sheet, "detail_sheet": detail_sheet, "pdf": pdf, "elevation_mode": elevation_mode,
            "replaced": replaced, "verdict": v}


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
