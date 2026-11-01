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
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from ashiba.cli import result_dict, solve_all, solve_groups, write_outputs  # noqa: E402
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
    place_width_change_lines,
    read_ground_model,
)
from ashiba.elevation_sections import (  # noqa: E402
    activate_floor_plan,
    building_key,
    load_record,
    load_record_meta,
    remove_elevations,
    remove_stale_prefixes,
    place_plan_sheet,
    place_section_elevations,
    save_record,
)

# ---- 条件入力（Phase 2でUIダイアログ化。当面はここを編集する） ----
# キー名と既定値は入力JSONと同じ（ashiba/cli.py のスキーマ参照）
SPEC = {
    "project_name": "足場計画",
    # くさび式はフィート寸法の日建 ND1800 が既定（利用者の指定 2026-10-23: くさび式は 610・914・1219・1829）
    "series_id": "nikken_nd1800",
    "module": "",                  # "metric" でメートル（1800/1500/1200/900/600）。series_id を空にすれば既定の系列
    "eaves_height_mm": 15400,      # 軒高
    "guard_extra_mm": 900,         # 最上層作業床固定点 = 軒高 + 手すり分
    "period_days": 90,
    "site": {"region": "関東(内陸)", "sheet_type": "メッシュシート"},
}
LINE_OBJECT = "ashiba_line"
DETAIL_OBJECT = "ashiba_detail"
# 足場ラインから分けた部材（壁つなぎ・水平ネット・ネットブラケット）。置き換え・撤去で一緒に拾う
ATTACHMENT_OBJECTS = ("ashiba_tie", "ashiba_net", "ashiba_netbk", "ashiba_sheet", "ashiba_member", "ashiba_xsec",
                      "ashiba_cstep", "ashiba_bridge", "ashiba_kbrk", "ashiba_hstage")
# 配置とは別に置く部品（内部ステージ足場・昇降機。配置の置き直しでは消さない。昇降機は配置で読み取って面に合わせ直す）
SEPARATE_OBJECTS = ("ashiba_stage", "ashiba_hoist", "ashiba_walkway", "ashiba_box", "ashiba_side", "ashiba_cfill", "ashiba_wform", "ashiba_cform", "ashiba_bform", "ashiba_sform", "ashiba_yamadome", "ashiba_kakoi", "ashiba_crane", "ashiba_plate", "ashiba_kodai")
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
    "series_id": "nikken_nd1800",
    "_series_id": "nikken_nd1800（既定・フィート寸法）/ nikken_nd1900 / shinwa_A / shinwa_B / waku（枠組）",
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


def read_hoist_objects(client, outline_mm, reach_mm: float = 15000.0, part: str = "ashiba_hoist") -> list:
    """建物（外形）のまわり reach_mm の中に置いてある昇降機の部品（part。荷取りステージは ashiba_hstage）を
    (要素, 原点mm, パラメータ) の一覧で返す."""
    xs = [float(p[0]) for p in outline_mm]
    ys = [float(p[1]) for p in outline_mm]
    objs = client.tapir("GetElementsByType", {"elementType": "Object"}).get("elements", [])
    found = []
    for e, d in zip(objs, client.get_details(objs) if objs else []):
        dd = d.get("details", {})
        lp = dd.get("libPart") or {}
        if not is_ashiba_part(lp.get("name", "") if isinstance(lp, dict) else "", (part,)):
            continue
        o = dd.get("origin") or {}
        x, y = float(o.get("x", 0)) * 1000.0, float(o.get("y", 0)) * 1000.0
        if not (min(xs) - reach_mm <= x <= max(xs) + reach_mm and min(ys) - reach_mm <= y <= max(ys) + reach_mm):
            continue
        resp = client.tapir("GetGDLParametersOfElements", {"elements": [e]})
        item = (resp.get("gdlParametersOfElements") or [{}])[0]
        raw = item.get("gdlParameters", item.get("parameters", []))
        params = ({p.get("name"): p.get("value") for p in raw} if isinstance(raw, list) else
                  {k: (v.get("value") if isinstance(v, dict) else v) for k, v in raw.items()})
        found.append((e, (x, y), params))
    return found


def _choose_width_dialog(choices) -> str | None:
    labels = [c.label for c in choices]
    q = lambda t: '"' + t.replace("\\", "\\\\").replace('"', '\\"') + '"'
    script = ("choose from list {" + ", ".join(q(t) for t in labels) + "} with title " + q("足場の幅")
              + " with prompt " + q("足場の幅（建地列の間隔）を選んでください。センチはメートル系、インチはインチ系の足場になります")
              + " default items {" + q(labels[0]) + "} OK button name " + q("決定") + " cancel button name " + q("既定のまま"))
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    out = (r.stdout or "").strip()
    return None if r.returncode != 0 or not out or out == "false" else out


def choose_width_at_start(client, spec: dict, interactive: bool, persist: bool = True) -> dict:
    """足場の幅を始めに選ぶ（利用者の指定 2026-10-22: 足場の幅が始めに選べるようにして、インチとセンチで）.

    幅がまだ無い建物（ashiba.widths.needs_width_choice）だけ。ASHIBA_WIDTH（"914"・"90cm"・"36in"・"3ft" など）が
    あれば一覧を出さずにそれを使う（試験用）。選んだ幅はこの建物の足場条件の部品（幅・モジュール・系列）に書き、
    部品が無ければ条件ファイルに書くので、次からは聞かない。
    """
    from ashiba.widths import apply_width_choice, find_choice, needs_width_choice, ordered_choices

    if not needs_width_choice(spec):
        return spec
    env = os.environ.get("ASHIBA_WIDTH", "").strip()
    if env:
        choice = find_choice(env)
    elif interactive and os.environ.get("ASHIBA_ASK_WIDTH", "1") != "0":
        choice = find_choice(_choose_width_dialog(ordered_choices(spec)))
    else:
        return spec
    if choice is None:
        print("  幅: 選ばなかったので系列の既定の幅で置きます")
        return spec
    new, notes = apply_width_choice(spec, choice)
    where = ""
    if persist:
        from ashiba.spec_object import pick_spec_object

        hit = None
        try:
            hit = pick_spec_object(read_spec_objects(client), spec.get("outline_mm") or [])
        except TapirError:
            hit = None
        if hit is not None:
            try:
                client.set_gdl_parameters(hit[0], {"scaffW": int(choice.width_mm), "moduleKind": choice.module,
                                                   "seriesId": str(new.get("series_id") or "")})
                where = "足場条件の部品"
            except TapirError as e:
                print(f"  幅: 足場条件の部品に書けませんでした（{e}）")
    if not where and SPEC_OVERRIDE.exists() and interactive:
        try:
            body = json.loads(SPEC_OVERRIDE.read_text(encoding="utf-8"))
            body.update({"scaffold_width_mm": int(choice.width_mm), "module": choice.module})
            if "series_id" not in new:
                body.pop("series_id", None)
            SPEC_OVERRIDE.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            where = SPEC_OVERRIDE.name
        except (OSError, ValueError):
            pass
    print("  幅: " + "・".join(notes) + (f"（{where}に控えました）" if where else ""))
    return new


def ensure_parts(client) -> tuple[str, str]:
    """同梱の配布GSM（足場ライン・詳細図・表示設定・足場条件・付属部品）を埋め込みライブラリに入れる → (足場ライン, 詳細図) の部品名.

    配置のほか、足場条件の部品を書き換えるボタン（条件・朝顔の面）も先に呼ぶ（新しい版の部品が無いと置き換えられない）。
    """
    line_part = versioned_part_name(LINE_OBJECT)
    detail_part = versioned_part_name(DETAIL_OBJECT)
    # MVO部品は置かないが、ライブラリに入っていればモデル表示オプションに「仮設足場の表示設定」が出る
    added = client.ensure_embedded_parts([
        (GDL_DIR / f"{LINE_OBJECT}.gsm", line_part), (GDL_DIR / f"{DETAIL_OBJECT}.gsm", detail_part),
        (GDL_DIR / f"{MVO_OBJECT}.gsm", versioned_part_name(MVO_OBJECT)),
        (GDL_DIR / f"{SPEC_OBJECT}.gsm", versioned_part_name(SPEC_OBJECT)),
        *((GDL_DIR / f"{b}.gsm", versioned_part_name(b)) for b in ATTACHMENT_OBJECTS + SEPARATE_OBJECTS),
    ])
    if added:
        print(f"配布GSMを埋め込みライブラリへ追加: {', '.join(added)}")
    return line_part, detail_part


def ask_conditions(client, spec: dict, ok: tuple, extra: tuple = ()) -> tuple[dict, object, bool]:
    """条件の窓を出す → (新しい条件, 押したボタンの id か False（やめた）, 窓を出せたか).

    選んだ値はこの建物の足場条件の部品に書く。窓を作れない（swiftc が無い等）ときは今の条件のまま続ける。
    """
    from ashiba.spec_form import apply_form, form_spec, object_params
    from ashiba.spec_object import pick_spec_object
    from form_dialog import show_form

    intro = ("この建物の足場の条件です。変えたいところを選んで「" + ok[1] + "」を押してください。"
             "選んだ値は建物の左下の「足場条件」の部品に控え、次からはその値が出ます。")
    try:
        res = show_form(form_spec(spec, "仮設足場の条件", intro, [ok, *extra, ("cancel", "やめる")]))
    except (RuntimeError, OSError) as e:
        print(f"注意: 条件の窓を開けませんでした（{e}）。今の条件で続けます")
        return spec, ok[0], False
    if not res or res.get("button") in (None, "cancel"):
        return spec, False, True
    new, notes = apply_form(spec, res.get("values") or {})
    print("条件: " + "・".join(notes))
    try:
        hit = pick_spec_object(read_spec_objects(client), new["outline_mm"])
        if hit is not None:
            client.set_gdl_parameters(hit[0], object_params(new))
            print("足場条件: 選んだ条件を部品に控えました")
    except TapirError as e:
        print(f"注意: 足場条件の部品に書けませんでした（{e}）。今回の配置は選んだ条件で続けます")
    return new, res.get("button"), True


def upgrade_spec_object(client, el: dict, new_params: dict, added) -> dict:
    """置いてある足場条件の部品が古い版（新しい項目が無い・選択肢が古い）なら、値を引き継いで今の版に置き換える → 値."""
    name = versioned_part_name(SPEC_OBJECT)
    try:
        det = client.tapir("GetDetailsOfElements", {"elements": [el]}).get("detailsOfElements", [{}])[0]
    except TapirError:
        det = {}
    placed_name = ((det.get("details") or {}).get("libPart") or {}).get("name", name)
    if added or placed_name != name:
        from ashiba.master import SERIES_LABELS, series_from_label

        if new_params.get("seriesId"):
            new_params["seriesId"] = SERIES_LABELS.get(series_from_label(new_params["seriesId"]),
                                                       new_params["seriesId"])
        try:
            o = (det.get("details") or {}).get("origin") or {}
            new_el = client.create_object(name, float(o.get("x", 0)) * 1000.0, float(o.get("y", 0)) * 1000.0)
            client.set_gdl_parameters(new_el, new_params, name)
            client.delete_elements([el])
            print("足場条件の部品を今の版に置き換えました（値は引き継ぎ"
                  + (f"、新しい項目 {', '.join(added)} は既定値" if added else "") + "）")
        except TapirError as e:
            print(f"足場条件の部品を今の版に置き換えられませんでした（{e}）。新しい項目は既定値で続けます")
    return new_params


def asagao_off_by_default(spec: dict) -> dict:
    """朝顔を付ける面の指定が無ければ付けない（「なし」）。利用者の指定（2026-10-24）「配置で朝顔が勝手に配置される。
    なしして線で朝顔の範囲追加できるようにして」。付けるのはパレットの「朝顔の範囲」（線）・「朝顔の面」（足場ライン）で、
    全部の面は「全部」。段数は高さで決まるので、要る高さで付けていなければ法規チェック#10 が知らせる."""
    a = spec.get("asagao")
    if a is False or (isinstance(a, dict) and a.get("faces")):
        return spec
    return {**spec, "asagao": {**(a if isinstance(a, dict) else {}), "faces": "なし"}}


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
        from ashiba.spec_object import upgrade_params

        _el, params = hit
        new_params, added = upgrade_params(params)
        # 部材編集の欄が無い古い版: JSON の member_edits を欄に入れて引き継ぐ（空の欄は「編集なし」になる）
        from ashiba.spec_object import EDIT_FIELDS

        if any(k in EDIT_FIELDS for k in added):
            fresh = params_from_spec(spec)
            for k in EDIT_FIELDS:
                if k in added:
                    new_params[k] = fresh[k]
        params = upgrade_spec_object(client, _el, new_params, added)
        obj = spec_from_params(params)
        for msg in obj.pop("_edit_errors", []):
            print(f"部材編集の欄が読めません: {msg}")
        if obj.get("member_edits"):
            print(f"部材編集: {len(obj['member_edits'])}件（足場条件の部品の「部材編集」ページ）")
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


def read_slabs_near(client, outline_mm, margin_mm: float = 10000.0) -> list[dict]:
    """建物の外形のまわり（margin まで）にあるスラブの外形と天端（入力の slabs の形）.

    張り出した上の階は外形から数 m。30m まで拾っていたので、28m 離れた別棟のスラブまで数えていた（実機 2026-10-25）。"""
    from ashiba.slab_heights import slabs_from_details

    try:
        els = client.tapir("GetElementsByType", {"elementType": "Slab"}).get("elements", [])
        if not els:
            return []
        det = client.tapir("GetDetailsOfElements", {"elements": els}).get("detailsOfElements", [])
    except TapirError:
        return []
    xs = [float(p[0]) for p in outline_mm]
    ys = [float(p[1]) for p in outline_mm]
    x0, x1, y0, y1 = min(xs) - margin_mm, max(xs) + margin_mm, min(ys) - margin_mm, max(ys) + margin_mm
    out = []
    for sl in slabs_from_details(det):
        px = [p[0] for p in sl.polygon]
        py = [p[1] for p in sl.polygon]
        if max(px) < x0 or min(px) > x1 or max(py) < y0 or min(py) > y1:
            continue
        out.append({"polygon_mm": [list(p) for p in sl.polygon], "top_mm": sl.top_mm, "thickness_mm": sl.thickness_mm})
    return out


def place_attachments(client, r, lines: list[dict]) -> tuple[list[dict], list[str]]:
    """壁つなぎ・水平ネット・ネットブラケットを別の部品として置く（足場ラインの GDL とは別。利用者の指定）.

    置いた要素と注意を返す。壁つなぎが全部置けたら足場ラインの tieObj を True にして、ライン側の壁つなぎを消す
    （置けなければライン側に描いたまま）。
    """
    from ashiba.attachments import (BRIDGE_OBJECT, CSTEP_OBJECT, HOIST_OBJECT, HSTAGE_OBJECT, KBRK_OBJECT, NET_OBJECT,
                                    NETBK_OBJECT, SHEET_OBJECT, TIE_OBJECT, bridge_placements, cstep_placements,
                                    hoist_placements, hoist_stage_placements, kbrk_placements, net_placements,
                                    sheet_placements, tie_placements)

    notes: list[str] = []
    line_mode = bool(r.model.config.line_mode_3d)
    # 拡幅・縮幅の面の上の部品（新しい幅の足場ライン）。壁つなぎ・ブラケットを部品で置いたときの切り替えも同じに
    upper: list[dict] = []
    if getattr(r.model, "width_change", None) is not None:
        try:
            upper = place_width_change_lines(
                r.model, versioned_part_name(LINE_OBJECT), client, stair_plan=r.stair_plan, openings=r.openings,
                platforms=r.platforms, bracket_sections=r.brackets, terrain=r.terrain, floor_index=line_floor(client, lines))
            print(f"  {r.model.width_change.label}: 上の足場ライン {len(upper)}本")
        except TapirError as e:
            notes.append(f"拡幅・縮幅の上の足場ラインを置けませんでした（{e}）")
    lines = list(lines) + upper
    pls = (tie_placements(r.model, line_mode) + net_placements(r.model, line_mode)
           + sheet_placements(r.model, line_mode, r.stair_plan) + cstep_placements(r.model, line_mode)
           + bridge_placements(r.model, line_mode) + kbrk_placements(r.model, line_mode)
           + hoist_placements(r.model, r.platforms) + hoist_stage_placements(r.model, r.platforms))
    if not pls:
        return upper, notes
    names = {b: versioned_part_name(b) for b in (TIE_OBJECT, NET_OBJECT, NETBK_OBJECT, SHEET_OBJECT, CSTEP_OBJECT,
                                                 BRIDGE_OBJECT, KBRK_OBJECT, HOIST_OBJECT, HSTAGE_OBJECT)}
    mats = {}
    try:
        mats = client.find_member_surfaces()
    except TapirError:
        pass
    els = client.create_objects([(names[p.part], p.x_mm, p.y_mm) for p in pls])
    pairs = []
    for p, el in zip(pls, els):
        if el is None:
            continue
        extra = {}
        if p.part == TIE_OBJECT and mats.get("matScaf"):
            extra["matTie"] = mats["matScaf"]
        if p.part == NETBK_OBJECT and (mats.get("matDeck") or mats.get("matScaf")):
            extra["matBk"] = mats.get("matDeck") or mats["matScaf"]   # NL500 は鋼製（溶融亜鉛めっき）
        if p.part in (CSTEP_OBJECT, BRIDGE_OBJECT) and mats.get("matDeck"):
            extra["matDeck"] = mats["matDeck"]
        if p.part == KBRK_OBJECT and mats.get("matDeck"):
            extra["matBk"] = mats["matDeck"]     # 拡幅・張出ブラケットは鋼製（溶融亜鉛めっき）
        pairs.append((el, {**p.params, **extra}))
    # 設定に失敗した部品は既定の値のまま残る（昇降機が初期の機種のまま置かれていた: 真偽のパラメータに 0/1 を渡して
    # 1回分まるごと失敗。2026-10-28）。黙って通さず数を出す
    n_set = client.set_gdl_parameters_many(pairs)
    if n_set < len(pairs):
        notes.append(f"付属部品のパラメータを {n_set}/{len(pairs)} 個しか設定できませんでした（部品の版が古いか、値の型が"
                     "違います。設定できなかった部品は既定の形のままです）")
    placed = upper + [el for el in els if el is not None]
    n_tie = sum(1 for p in pls if p.part == TIE_OBJECT)
    tie_ok = sum(1 for p, el in zip(pls, els) if p.part == TIE_OBJECT and el is not None)
    if n_tie and tie_ok == n_tie:
        client.set_gdl_parameters_many([(line, {"tieObj": True}) for line in lines])
    elif n_tie:
        notes.append(f"壁つなぎの部品を {tie_ok}/{n_tie} 本しか置けませんでした（足場ラインの壁つなぎを残します）")
    n_net = sum(1 for p in pls if p.part == NET_OBJECT)
    n_bk = sum(1 for p in pls if p.part == NETBK_OBJECT)
    if n_net:
        print(f"  水平ネット {n_net}枚・ネットブラケット {n_bk}個（第{'・'.join(str(v) for v in r.model.config.horizontal_net_levels)}層）")
    n_sheet = sum(1 for p in pls if p.part == SHEET_OBJECT)
    if n_sheet:
        print(f"  養生シート（{r.model.config.sheet_type}）{n_sheet}面")
    # 拡幅・張出ブラケットを部品で置いたら、足場ラインの GDL はブラケットの腕・方杖・補強単管を描かない（brkObj）
    n_kb = sum(1 for p, el in zip(pls, els) if p.part == KBRK_OBJECT and el is not None)
    if n_kb:
        client.set_gdl_parameters_many([(line, {"brkObj": True}) for line in lines])
        print(f"  拡幅・張出ブラケット {n_kb}基")
    n_cs = sum(1 for p in pls if p.part == CSTEP_OBJECT)
    if n_cs:
        print(f"  コーナーステップ {n_cs}箇所（隅の隙間 " + "・".join(
            f"{c.gap_mm:.0f}" for c in r.model.plan.corner_steps if c.edge_index >= 0) + "mm）")
    return placed, notes


def line_floor(client, lines: list[dict]):
    """足場ラインを置いたフロアの番号（読めなければ None＝現在のフロア）."""
    if not lines:
        return None
    try:
        det = client.tapir("GetDetailsOfElements", {"elements": lines[:1]}).get("detailsOfElements", [])
        return int(det[0]["floorIndex"]) if det and "floorIndex" in det[0] else None
    except (TapirError, KeyError, TypeError, ValueError):
        return None


def place_plan_annotations(client, r, out_dir, lines: list[dict], extra=()) -> tuple[int, int]:
    """平面図に寸法（寸法ツール）と部材名のラベルを置き、GUID を建物ごとに控える。(寸法数, ラベル数) を返す.

    前回この建物に置いた分は控えの GUID で消してから置く。寸法が置けた足場ラインは dimTool=True にして、
    部品が描くスパン寸法と二重にしない（置けなければ部品の寸法のまま）。失敗しても配置は止めない。
    extra は面の切替の組 [(結果, その組の足場ライン)]。寸法は組の面にも付ける（ブラケットの面だけ部品の寸法だった）。
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
    for rr, ll in [(r, lines)] + [(rg, lg) for rg, lg in extra]:
        if not ll:
            continue
        try:
            res = client.tapir("CreateAssociativeDimensions",
                               {"dimensionsData": plan_dimension_data(rr.model, ll, rr.platforms, rr.stair_plan)})
            made = [el for el in res.get("elements", [])]
            ok = [el["elementId"]["guid"] for el in made if "elementId" in el]
            guids += ok
            n_dim += len(ok)
            # 面ごとに2本（スパン・全長）。両方置けた面だけ部品の寸法を消す。その後ろに面ごとの離れ寸法 2本
            nl = len(ll)
            for k, line in enumerate(ll):
                pair = made[2 * k:2 * k + 2]
                so = made[2 * nl + 2 * k:2 * nl + 2 * k + 2]
                upd = {}
                if len(pair) == 2 and all("elementId" in el for el in pair):
                    upd["dimTool"] = True
                if len(so) == 2 and all("elementId" in el for el in so):
                    upd["dimSoTool"] = True
                if upd:
                    client.set_gdl_parameters(line, upd)
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


def make_drawings(client, spec: dict, r, groups, lines: list, attach: list, line_part: str, detail_part: str,
                  tapir_v: str, mode: str | None = None, fill_title: bool = True) -> dict:
    """立面図・断面図・平面図・詳細図のレイアウトと PDF を作る（配置の最後、またはパレットの「図面を作る」）.

    mode を渡さなければ条件の elevation_mode。配置では "section" も作らず最後に回す（defer_drawings）。
    """
    x0 = min(v[0] for v in r.model.plan.outline.vertices)
    y0 = min(v[1] for v in r.model.plan.outline.vertices)
    elevs = []
    elevation_mode, mode_notes = choose_elevation_mode(str(mode or spec.get("elevation_mode") or ELEVATION_MODE), tapir_v)
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
                                            others=[(rg.model, rg.stair_plan, rg.terrain) for _lb, rg in groups[1:]],
                                            on_sections=lambda res: save_record(OUT_DIR, res, prev, bkey, prefix))
        save_record(OUT_DIR, sections, prev, bkey, prefix)
        # 足場断面図（A-A・B-B の面ごと）も同じサブセットのレイアウトへ。既定は Archicad の断面図ビューポイントで
        # 3Dを切る（案2）。cross_section_mode=drafted なら2Dの作図の形の部品（ashiba_xsec）を平面の下の行に置いて
        # 1/50 で切り抜く（案1。利用者の指定 2026-10-23: 元に戻して → 既定を断面図ビューポイントに戻した）
        from ashiba.cross_sections import cross_layout_name, cross_section_specs, place_cross_sections, split_cross_specs

        cross_mode = str(spec.get("cross_section_mode") or "section")
        try:
            if cross_mode == "section":
                prev2 = load_record(OUT_DIR)
                cross = place_cross_sections(r.model, client, prefix=prefix, previous=prev2, terrain=r.terrain,
                                             stair_plan=r.stair_plan, openings=r.openings, platforms=r.platforms,
                                             others=[(rg.model, rg.stair_plan, rg.terrain) for _lb, rg in groups[1:]],
                                             on_sections=lambda res: save_record(OUT_DIR, res, prev2, bkey, prefix))
                save_record(OUT_DIR, cross, prev2, bkey, prefix)
                if cross:
                    lays = list(dict.fromkeys(pl.layout_name for pl in cross if pl.layout_name)) or [cross_layout_name(prefix)]
                    print(f"  断面図: {'・'.join(pl.face_name for pl in cross)}（レイアウト「{'」「'.join(lays)}」）")
                for pl in cross:
                    for n in pl.notes:
                        print(f"  断面図（{pl.face_name}）: {n}")
            else:
                # 前に断面図ビューポイントで作った断面（A-A など）とそのレイアウトは片付ける
                prev2 = load_record(OUT_DIR)
                full = cross_section_specs(r.model, prefix, r.stair_plan, r.openings, r.platforms)
                old_names = [x.name for x in full] + [x.name for x in split_cross_specs(r.model, full)]
                if any(n in prev2 for n in old_names):
                    activate_floor_plan(client)
                    remove_elevations(client, [n for n in old_names if n in prev2], [cross_layout_name(prefix)],
                                      [prev2[n] for n in old_names if n in prev2])
                    rec = {k: v for k, v in prev2.items() if k not in old_names}
                    (OUT_DIR / "elevation_sections.json").write_text(
                        json.dumps(rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                from ashiba.xsec import XSEC_OBJECT, XSEC_OFFSET_MM, place_xsec

                stories_mm = [float(st.get("level_mm", 0.0)) for st in (spec.get("stories") or [])]
                xsec_parts, xs = place_xsec(client, r.model, versioned_part_name(XSEC_OBJECT), (x0, y0 + XSEC_OFFSET_MM),
                                            prefix, r.stair_plan, r.openings, r.platforms, stories_mm,
                                            floor_index=line_floor(client, lines))
                attach.extend(xsec_parts)
                if xs.layouts:
                    print(f"  断面図: {len(xsec_parts)}面を2Dの断面の形で（レイアウト「{'」「'.join(xs.layouts)}」に 1/{xs.scale}）")
                for n in xs.notes:
                    print(f"  断面図: {n}")
        except TapirError as e:
            print(f"  断面図: 作れませんでした（{e}）")
        # 足場平面図も同じサブセットのレイアウトへ（配置フロアの平面を足場の範囲で切り抜く）
        cuts = ([{"label": s_.face_name.split("-")[0], "start": s_.start_mm, "end": s_.end_mm}
                 for s_ in cross_section_specs(r.model, prefix, r.stair_plan, r.openings, r.platforms)]
                if cross_mode == "section" else [])
        plan_sheet = place_plan_sheet(r.model, client, prefix=str(spec.get("project_name") or "足場"),
                                      floor_index=line_floor(client, lines), stair_plan=r.stair_plan,
                                      other_models=[rg.model for _lb, rg in groups[1:]], cuts=cuts)
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
                                              prefix=str(spec.get("project_name") or "足場"),
                                              floor_index=line_floor(client, lines))
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

    return {"elevations": elevs, "sections": sections, "plan_sheet": plan_sheet, "details": details,
            "detail_sheet": detail_sheet, "pdf": pdf, "elevation_mode": elevation_mode}


def stale_margin_mm(main_model, other_models) -> float:
    """前回の配置を拾う範囲の、本体の外形からの余裕 mm. 張り出した上の階の上段（跳ね出し）の足場ラインは原点が
    本体の外形の外（張り出し＋離れ）にあり、外形＋1m では拾えず置き直すたびに重なって残っていた（実機 2026-10-25:
    跳ね出しの上段の足場ラインが3本重なっていた）. ほかの組の外形がはみ出す分と、その離れ・建地列間隔を足す."""
    vs = main_model.plan.outline.vertices
    x0, x1 = min(v[0] for v in vs), max(v[0] for v in vs)
    y0, y1 = min(v[1] for v in vs), max(v[1] for v in vs)
    extra = 0.0
    for m in other_models:
        out = max([0.0] + [max(x0 - v[0], v[0] - x1, y0 - v[1], v[1] - y1) for v in m.plan.outline.vertices])
        if out > 1.0:
            so = max((float(e.standoff) for e in m.plan.edges), default=0.0)
            extra = max(extra, out + so + float(m.post_row_spacing_mm))
    return 1000.0 + extra


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
    line_part, detail_part = ensure_parts(client)
    # 足場条件の部品: あればその条件を JSON より優先して使う。無ければいまの条件で置く
    if use_spec_object:
        spec = apply_spec_object(client, spec)
    # 条件の窓（足場の種類・系列・幅・手すり・幅木・層間ネット・階段・養生・高さ・立面断面）を出して選んでから置く
    # （利用者の指定 2026-10-24: 配置の時 足場の種類選べるようにして。条件の部分がどうやるのかわからない）。
    # 選んだ値は足場条件の部品に書く。スクリプトから（spec_override・ASHIBA_ASK_SPEC=0）や、解き直し・面の切替など
    # 外形を渡して置き直すとき（outline_mm）は出さない
    asked = False
    if (use_spec_object and spec_override is None and outline_mm is None
            and os.environ.get("ASHIBA_ASK_SPEC", "1") != "0"):
        spec, go, asked = ask_conditions(client, spec, ("place", "配置"))
        if not go:
            print("配置: やめました（足場は置き直していません）")
            return {"cancelled": True}
    # 足場の幅を始めに選ぶ（幅がまだ無い建物だけ。センチとインチの一覧。選んだ幅は部品・条件ファイルに控える）
    if not asked:
        spec = choose_width_at_start(client, spec, interactive=spec_override is None, persist=use_spec_object)
    # 建物のフロア（層別数量にフロア名を付け、フロアごとに合計する）
    if not spec.get("stories"):
        try:
            st = client.tapir("GetStories", {}).get("stories", [])
            spec["stories"] = [{"name": s["name"], "level_mm": float(s["level"]) * 1000.0,
                                "height_mm": float(s.get("height", 0.0) or 0.0) * 1000.0} for s in st]
        except (TapirError, KeyError, TypeError, ValueError):
            pass
    # 敷地メッシュがあれば高低差を拾う（無ければ平坦として解く）
    ground = read_ground_model(client, outline_mm=spec["outline_mm"])
    if ground.ignored_meshes:
        print(f"敷地メッシュ{ground.ignored_meshes}個は建物の範囲外（{MESH_MARGIN_MM / 1000:.0f}m以上離れている）"
              "なので、この棟の地盤には使いません")
    if not ground.is_flat:
        spec["ground_points_mm"] = [list(p) for p in ground.points]
    # 敷地境界線（レイヤー名に 敷地・境界 のポリライン。道路 のレイヤーに沿う辺は道路境界）。条件で指定が無ければ拾う
    if not spec.get("site_boundary_mm"):
        from ashiba.site_boundary import read_boundary_from_archicad

        bnd, roads = read_boundary_from_archicad(client, spec["outline_mm"])
        if bnd:
            spec["site_boundary_mm"] = [list(p) for p in bnd]
            spec["road_edges"] = sorted(roads)
            print(f"  敷地境界線: {len(bnd)}辺" + (f"（道路境界 {len(roads)}辺）" if roads else ""))
        elif spec.get("boundary_from_mesh", True) and ground.mesh_outlines:
            # 境界線のポリラインが無ければ、敷地メッシュの外形を敷地境界にする（利用者の指定 2026-10-24）
            from ashiba.site_boundary import boundary_from_meshes

            bnd = boundary_from_meshes(ground.mesh_outlines, spec["outline_mm"])
            if bnd:
                spec["site_boundary_mm"] = [list(p) for p in bnd]
                print(f"  敷地境界線: 敷地メッシュの外形から {len(bnd)}辺")
    # 高さはスラブの天端から（面ごと・セットバック対応。足場条件の「高さをスラブから」を外せば軒高の入力どおり）
    if spec.get("height_from_slabs", True) and not spec.get("slabs"):
        slabs = read_slabs_near(client, spec["outline_mm"])
        if slabs:
            spec["slabs"] = slabs
            print(f"高さ: 建物まわりのスラブ{len(slabs)}枚の天端から面ごとに決めます")

    # 面ごとに足場を切り替えた建物（face_forms）は面の組ごとに解く。先頭の組（切り替えていない面）を従来どおり
    # 帳票・立面・詳細図まで出し、ほかの組は足場ラインと付属部品を置いて帳票を「切替_種類」に出す
    # 敷地境界を越える面は、張り出しの小さい形式（一側足場→単管抱き足場）に替えて解き直す（繰り返し）
    from ashiba.site_boundary import plan_within_boundary

    spec = asagao_off_by_default(spec)
    # 置いてある昇降機の部品（ashiba_hoist）を読み、いちばん近い面に合わせて入力の hoists にする（利用者の指定 2026-10-27:
    # 昇降機は別オブジェクトで配置できるように）。読んだ部品は消し、解いたあとで面に合わせた位置に置き直す
    hoist_objs = read_hoist_objects(client, spec["outline_mm"])
    # 荷取りステージの部品（ashiba_hstage）も読む。部品で調整した床の高さを昇降機の入力に写し、部品は消して置き直す
    # （原点が足場の外側建地の列の上なので、外形＋1m の範囲で拾う前回の配置の片付けでは拾えず、置くたびに重なった）
    stage_objs = read_hoist_objects(client, spec["outline_mm"], part="ashiba_hstage")
    if stage_objs:
        client.delete_elements([e for e, _p, _q in stage_objs])
    if hoist_objs:
        from ashiba.hoist_objects import hoists_from_objects

        pre = solve_groups({k: v for k, v in spec.items() if k != "hoists"})
        hs, h_notes = hoists_from_objects(hoist_objs, pre, stage_objs)
        for n in h_notes:
            print(f"  昇降機: {n}")
        if hs:
            spec["hoists"] = hs
            client.delete_elements([e for e, _p, _q in hoist_objs])
    spec, fit_notes = plan_within_boundary(spec)
    for n in fit_notes:
        print(f"  敷地境界: {n}")
    groups = solve_groups(spec)
    _label0, r = groups[0]
    # 解いた条件の控え（朝顔の面のように、全部を置き直さずに一部の部品だけ直すボタンが同じ条件で解き直す）
    try:
        (OUT_DIR / f"{r.file_stem}_spec_used.json").write_text(
            json.dumps(spec, ensure_ascii=False, default=str), encoding="utf-8")
    except OSError:
        pass
    if len(groups) > 1:
        # 平面のラベルは、実際に描く切断線（先頭の組の断面図・全部の面の立面図）の端を避ける
        from ashiba.gdl_params import drawn_section_lines

        lines = drawn_section_lines(groups)
        for _lb, rg in groups:
            rg.model.section_lines_mm = lines
    write_outputs(r, OUT_DIR)
    write_sample_spec(OUT_DIR)
    result = result_dict(r, OUT_DIR)

    lines = place_scaffold_lines(
        r.model, line_part, client, stair_plan=r.stair_plan,
        openings=r.openings, platforms=r.platforms, bracket_sections=r.brackets,
        terrain=r.terrain,
    )
    # 壁つなぎ・水平ネット・ネットブラケットは別の部品（失敗しても配置は止めない）
    try:
        attach, attach_notes = place_attachments(client, r, lines)
    except TapirError as e:
        attach, attach_notes = [], [f"壁つなぎ・水平ネットの部品を置けませんでした（{e}）"]
    for n in attach_notes:
        print(f"  注意: {n}")
    group_lines: list = []
    group_sets: list = []                   # 平面の寸法を付ける (組の結果, 組の足場ライン)
    main_floor = line_floor(client, lines)  # 上段も本体と同じ階に置く（その階の平面に出す）
    for label, rg in groups[1:]:
        tier = label.startswith("上段")          # セットバックの上の階（途中の屋根の上から。setback_tiers）
        gdir = OUT_DIR / (label if tier else f"切替_{label}")
        write_outputs(rg, gdir)
        lg = place_scaffold_lines(
            rg.model, line_part, client, stair_plan=rg.stair_plan,
            openings=rg.openings, platforms=rg.platforms, bracket_sections=rg.brackets,
            terrain=rg.terrain, floor_index=main_floor,
        )
        try:
            ag, ag_notes = place_attachments(client, rg, lg)
        except TapirError as e:
            ag, ag_notes = [], [f"壁つなぎ・水平ネットの部品を置けませんでした（{e}）"]
        group_lines += lg + ag
        group_sets.append((rg, lg))
        vg = result_dict(rg, gdir)["verdict"]
        print(f"  {'上段（途中の屋根から）' if tier else '面の切替'}: {'・'.join(rg.model.plan.face_names())} を {label}（{rg.model.config.form_label}・"
              f"{rg.model.master.system_name}）で 足場ライン{len(lg)}本 — " + ("成立" if vg["ok"] else "是正が必要")
              + f"（帳票は {gdir.name}）")
        for b in vg["blockers"]:
            print(f"    是正: {b}")
        for n in ag_notes:
            print(f"    注意: {n}")
    # 同じスラブでの再実行は前回の配置を置き換える。外形や離れ・系列が変わると位置が
    # ずれるので「同じ位置」ではなく「このスラブに対して置いたもの」（外形の範囲と
    # 立面図・詳細図の行）で拾い、今回置いた分だけ残す（枠組→くさびの切替で7個残った）。
    # 図面（立面・断面・平面・詳細）と PDF より先に消す。後で消していたので、前回の部品（古い版のラベル・
    # 向きを誤った足場ライン）が PDF に重なって出ていた（2026-10-23 実機）
    placed_now = {e["elementId"]["guid"] for e in lines + attach + group_lines}
    stale = [
        e for e in client.objects_for_slab(
            r.model.plan.outline.vertices, (LINE_OBJECT, DETAIL_OBJECT) + ATTACHMENT_OBJECTS,
            elevation_offset_mm=ELEVATION_OFFSET_MM, detail_offset_mm=DETAIL_OFFSET_MM,
            margin_mm=stale_margin_mm(r.model, [rg.model for _lb, rg in groups[1:]]),
        ) if e["elementId"]["guid"] not in placed_now
    ]
    if stale and spec.get("_protect_guids"):
        # 足場の箱から続けて置くとき（box_run）: 同じ「箱を足場に」で先に置いた足場（斜めの角の隣の足場など）は片付けない。
        # 範囲で拾うと、角で接する隣の足場の壁つなぎ・シートまで消していた（実機 2026-10-31）
        keep = set(spec["_protect_guids"])
        stale = [e for e in stale if e["elementId"]["guid"] not in keep]
    if stale and spec.get("_same_base_only"):
        # 足場の箱から置くとき（box_run）: 同じ立つ高さの前の配置だけ片付ける。セットバックの上の階の箱は下の箱の範囲の中に
        # あるので、範囲だけで拾うと下の箱の足場まで消していた
        zb = float(spec.get("base_height_mm") or 0.0)
        dets = client.get_details(stale)
        stale = [e for e, d in zip(stale, dets)
                 if abs(float(((d.get("details") or {}).get("origin") or {}).get("z", 0.0)) * 1000.0 - zb) < 500.0]
    if stale:
        client.delete_elements(stale)
    replaced = len(stale)
    # 平面の部材名ラベル（引出線つき）。前回この建物に置いたラベルは控えの GUID で消してから置く
    plan_dim_n, plan_label_n = place_plan_annotations(client, r, OUT_DIR, lines, extra=group_sets)
    x0 = min(v[0] for v in r.model.plan.outline.vertices)
    y0 = min(v[1] for v in r.model.plan.outline.vertices)
    # 立面図・断面図は、足場を調整し終えてからパレットの「図面を作る」で作る（利用者の指定 2026-10-24: 立面図断面図は
    # 最後に調整してから作るようにして）。配置のたびに作るのは elevation_mode "each" のときだけ
    req = str(spec.get("elevation_mode") or ELEVATION_MODE)
    if req == "each":
        req = "section"
    elif req == "section" and os.environ.get("ASHIBA_DRAWINGS_NOW") != "1":
        req = "later"
        print("  図面: 立面図・断面図・平面図のレイアウトは、調整が済んだらパレットの「図面を作る」で作ります"
              "（断面は平面に線を引いて選んでから押すと、その線で切ります）")
    dw = make_drawings(client, spec, r, groups, lines, attach, line_part, detail_part, tapir_v, mode=req,
                       fill_title=fill_title)
    elevs, sections, plan_sheet = dw["elevations"], dw["sections"], dw["plan_sheet"]
    details, detail_sheet, pdf, elevation_mode = dw["details"], dw["detail_sheet"], dw["pdf"], dw["elevation_mode"]

    v = result["verdict"]
    n_sec = sum(1 for pl in sections if pl.drawing_guid)
    sheets = list(dict.fromkeys(pl.layout_name for pl in sections if pl.layout_name))
    scales = "・".join(dict.fromkeys(f"1/{pl.scale}" for pl in sections if pl.drawing_guid)) or "-"
    sec_txt = (f"立面図 {n_sec}面（断面図ビューポイント→レイアウト「{'」「'.join(sheets)}」、{scales}）・"
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
            "replaced": replaced, "verdict": v, "group_sets": group_sets,
            "attachments": list(attach) + [e for _rg, lg in group_sets for e in lg] + list(group_lines)}


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
