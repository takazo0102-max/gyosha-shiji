"""選んだ足場の面に朝顔を付ける・外す（パレットの「朝顔の面」）.

利用者の指定（2026-10-24）「朝顔あとで必要箇所を選べるようにしたい」。配置のあとで、朝顔の要る面（道路・隣地・人の通る側）
の足場ラインを選んで押すと「朝顔を付ける／朝顔を外す／全部の面に付ける」の一覧を出し、足場条件の部品の「朝顔を付ける面」
（asagaoFaces。空＝全部の面）に書いて配置し直す。部品が無ければ条件ファイル ashiba_spec.json の asagao.faces に書く。

使い方（Archicad で足場ラインを選んでから）:
  python3 scripts/asagao_faces.py                       # 一覧から選ぶ
  ASHIBA_ASAGAO_MODE=朝顔を外す python3 scripts/asagao_faces.py   # 一覧を出さずに（試験用）
  --no-apply で書くだけ（配置し直さない）
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ashiba.face_forms import faces_of_lines  # noqa: E402
from ashiba.spec_form import ASAGAO_MODES, updated_asagao_faces  # noqa: E402
from ashiba.tapir_adapter import ArchicadClient, is_ashiba_part  # noqa: E402

OUT_DIR = Path(os.environ.get("ASHIBA_OUT") or (Path.home() / "Desktop" / "ashiba_out"))
SPEC_DEFAULT = Path(os.environ.get("ASHIBA_SPEC") or (Path.home() / "Desktop" / "ashiba_spec.json"))


def _choose(faces: list[str]) -> str | None:
    env = os.environ.get("ASHIBA_ASAGAO_MODE")
    if env:
        return env
    q = lambda t: '"' + t.replace("\\", "\\\\").replace('"', '\\"') + '"'
    script = ("choose from list {" + ", ".join(q(t) for t in ASAGAO_MODES) + "} with title " + q("朝顔の面")
              + " with prompt " + q("・".join(faces) + " の朝顔") + " default items {" + q(ASAGAO_MODES[0]) + "}"
              + " OK button name " + q("決定") + " cancel button name " + q("やめる"))
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    out = (r.stdout or "").strip()
    return None if r.returncode != 0 or not out or out == "false" else out


def main() -> int:
    c = ArchicadClient()
    sel = c.get_selected_elements()
    origins = []
    for e, d in zip(sel, c.get_details(sel) if sel else []):
        dd = d.get("details") or {}
        if not is_ashiba_part((dd.get("libPart") or {}).get("name", ""), ("ashiba_line",)):
            continue
        o = dd.get("origin") or {}
        origins.append((float(o.get("x", 0)) * 1000.0, float(o.get("y", 0)) * 1000.0))
    if not origins:
        print("朝顔の面: 朝顔を付ける・外す面の足場ラインを選んでから押してください")
        return 1
    plans = [json.loads(p.read_text(encoding="utf-8"))
             for p in sorted(OUT_DIR.rglob("*_plan.json"), key=lambda p: -p.stat().st_mtime)]
    plan, faces = faces_of_lines(plans, origins)
    if plan is None or not faces:
        print(f"朝顔の面: 選んだ足場の配置の控え（plan.json）が {OUT_DIR} にありません。先に「配置」してください")
        return 1
    mode = _choose(faces)
    if not mode:
        print("朝顔の面: やめました")
        return 0
    if mode not in ASAGAO_MODES:
        print(f"朝顔の面: 「{mode}」は {'・'.join(ASAGAO_MODES)} のどれかです")
        return 2
    import run_from_archicad as tb
    from ashiba.cli import all_face_names
    from ashiba.spec_object import pick_spec_object

    outline = plan.get("outline_mm") or []
    every = all_face_names({"outline_mm": outline})
    hit = None
    try:
        # 古い版の部品（「付ける面」の項目が無い）は今の版に置き換えてから書く（無い項目を送ると全部落ちる）
        tb.ensure_parts(c)
        tb.apply_spec_object(c, {**tb.SPEC, **tb.load_spec_override(), "outline_mm": outline})
        hit = pick_spec_object(tb.read_spec_objects(c), outline)
    except Exception:          # 部品が読めなくても JSON に書けば通る
        hit = None
    if hit is not None and hit[1]:
        old = str((hit[1] or {}).get("asagaoFaces") or "")
        new = updated_asagao_faces(old, every, faces, mode)
        c.set_gdl_parameters(hit[0], {"asagaoFaces": new})
        where = "足場条件の部品「朝顔を付ける面」"
    else:
        spec = json.loads(SPEC_DEFAULT.read_text(encoding="utf-8")) if SPEC_DEFAULT.exists() else {}
        asg = spec.get("asagao") if isinstance(spec.get("asagao"), dict) else {}
        old = asg.get("faces") or ""
        new = updated_asagao_faces(old, every, faces, mode)
        if new:
            asg["faces"] = new
        else:
            asg.pop("faces", None)
        if asg:
            spec["asagao"] = asg
        else:
            spec.pop("asagao", None)
        SPEC_DEFAULT.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        where = str(SPEC_DEFAULT)
    print(f"朝顔の面: {'・'.join(faces)} → {mode}（{where}）。朝顔を付ける面: {new or '全部の面'}")
    if "--no-apply" in sys.argv:
        return 0
    if not outline:
        print("朝顔の面: plan.json に躯体外形がありません。スラブを選んで「配置」してください")
        return 1
    # 全部を置き直さない（利用者の指摘 2026-10-24: 朝顔の配置が再度配置してしまう）。付け外しが変わった面の足場ラインの
    # 朝顔と、その面の壁つなぎ（朝顔の取付部）だけを入れ替え、帳票を書き直す
    try:
        if update_in_place(c, plan, every, old, new):
            return 0
    except Exception as e:     # 直せなければ全部を置き直す（前の動き）
        print(f"朝顔の面: その面だけ直せませんでした（{e}）。全部を置き直します")
    os.environ["ASHIBA_SPEC"] = str(SPEC_DEFAULT)
    print("---- 配置し直します")
    tb.main(outline_mm=outline, out_dir=OUT_DIR)
    return 0


def update_in_place(c, plan: dict, every: list[str], old: str, new: str) -> bool:
    """付け外しが変わった面だけ: 足場ラインの朝顔（asagaoList・asaCutList）と、その面の壁つなぎの部品を入れ替える.

    配置のときの条件の控え（<工事名>_spec_used.json）で解き直して値を出す。控えが無い（古い配置）なら False.
    """
    import run_from_archicad as tb
    from ashiba.attachments import TIE_OBJECT, _frame, tie_placements
    from ashiba.cli import parse_asagao_faces, solve_groups, write_outputs
    from ashiba.gdl_params import line_params
    from ashiba.span_readback import match_edge

    outline = plan.get("outline_mm") or []
    used = [p for p in sorted(OUT_DIR.glob("*_spec_used.json"), key=lambda p: -p.stat().st_mtime)
            if (json.loads(p.read_text(encoding="utf-8")).get("outline_mm") or []) == outline]
    if not used:
        return False
    spec = json.loads(used[0].read_text(encoding="utf-8"))
    on_old = set(parse_asagao_faces(old) or every) - {"なし"}
    on_new = set(parse_asagao_faces(new) or every) - {"なし"}
    changed = (on_old ^ on_new) & set(every)
    asg = dict(spec.get("asagao") or {}) if isinstance(spec.get("asagao"), dict) else {}
    if new:
        asg["faces"] = new
    else:
        asg.pop("faces", None)
    spec["asagao"] = asg
    if not asg:
        spec.pop("asagao", None)
    groups = solve_groups(spec)
    if not changed:
        print("朝顔の面: 付け外しは変わりませんでした")
        return True
    # この建物の足場ライン（区切った部品も）と壁つなぎの部品
    objs = c.objects_for_slab(outline, (tb.LINE_OBJECT, TIE_OBJECT))
    det = c.get_details(objs) if objs else []
    lines_by_face: dict[str, list] = {}
    ties: list[tuple[dict, tuple[float, float]]] = []
    from ashiba.tapir_adapter import is_ashiba_part

    for e, d in zip(objs, det):
        dd = d.get("details") or {}
        name = (dd.get("libPart") or {}).get("name", "")
        o = dd.get("origin") or {}
        xy = (float(o.get("x", 0)) * 1000.0, float(o.get("y", 0)) * 1000.0)
        if is_ashiba_part(name, (tb.LINE_OBJECT,)):
            pe = None
            for p in [plan] + [json.loads(q.read_text(encoding="utf-8")) for q in OUT_DIR.rglob("*_plan.json")
                               if q.parent != OUT_DIR]:
                pe = match_edge(p.get("edges") or [], xy)
                if pe is not None:
                    break
            if pe is not None:
                lines_by_face.setdefault(str(pe.get("face") or ""), []).append(e)
        elif is_ashiba_part(name, (TIE_OBJECT,)):
            ties.append((e, xy))
    n_line = n_del = n_add = 0
    tie_name = tb.versioned_part_name(TIE_OBJECT)
    mats = {}
    try:
        mats = c.find_member_surfaces()
    except Exception:
        pass
    for _lb, r in groups:
        m = r.model
        for ep in m.plan.edges:
            face = m.face_name(ep.edge_index)
            if face not in changed:
                continue
            p = line_params(m, ep, stair_plan=r.stair_plan, openings=r.openings, platforms=r.platforms,
                            bracket_sections=r.brackets, terrain=r.terrain)
            els = lines_by_face.get(face) or []
            if els:
                c.set_gdl_parameters_many([(el, {"asagaoList": p["asagaoList"], "asaCutList": p["asaCutList"]})
                                           for el in els])
                n_line += len(els)
            # その面の壁つなぎ（面の線から建地列の外まで・始点〜終点の内）を消して、解き直した分を置く
            o, u, nrm, _ang = _frame(ep)
            length = float(sum(ep.spans))
            reach = float(m.post_row_spacing_mm) + 600.0
            gone = []
            for el, (x, y) in ties:
                t = (x - o[0]) * u[0] + (y - o[1]) * u[1]
                dn = (x - o[0]) * nrm[0] + (y - o[1]) * nrm[1]
                if -1.0 <= t <= length + 1.0 and -reach <= dn <= 1.0:
                    gone.append(el)
            if gone:
                c.delete_elements(gone)
                n_del += len(gone)
                ties = [(el, xy) for el, xy in ties if el not in gone]
            every_tie = m.wall_ties
            try:
                m.wall_ties = [t for t in every_tie if t.edge_index == ep.edge_index]
                mine = tie_placements(m, bool(m.config.line_mode_3d))
            finally:
                m.wall_ties = every_tie
            if mine:
                made = c.create_objects([(tie_name, pl.x_mm, pl.y_mm) for pl in mine])
                extra = {"matTie": mats["matScaf"]} if mats.get("matScaf") else {}
                c.set_gdl_parameters_many([(el, {**pl.params, **extra}) for pl, el in zip(mine, made) if el is not None])
                n_add += sum(1 for el in made if el is not None)
    _lb0, r0 = groups[0]
    # 平面の部材名ラベル（「朝顔（突出 2000）」など。寸法はそのまま）も直す（利用者の指定 2026-10-24: 朝顔の面でラベルも一緒に直して）
    n_lab = 0
    try:
        from ashiba.elevation_sections import activate_floor_plan, building_key, fit_scale, plan_region_mm
        from ashiba.plan_labels import plan_labels, replace_plan_labels

        activate_floor_plan(c)
        region = plan_region_mm(r0.model)
        scale = fit_scale((region[2] - region[0], region[3] - region[1]), (841.0, 594.0)) or 200
        labels = plan_labels(r0.model, r0.stair_plan, text_scale=float(scale), platforms=r0.platforms)
        first_line = next((els[0] for els in lines_by_face.values() if els), None)
        floor = tb.line_floor(c, [first_line]) if first_line is not None else None
        n_lab = replace_plan_labels(c, OUT_DIR, building_key(r0.model.plan.outline.vertices), labels, floor_index=floor)
    except Exception as e:
        print(f"朝顔の面: 平面のラベルを直せませんでした（{e}）")
    write_outputs(r0, OUT_DIR)
    used[0].write_text(json.dumps(spec, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"朝顔の面: {'・'.join(sorted(changed))} の朝顔を直しました（足場ライン {n_line}本・壁つなぎ {n_del}本を"
          f" {n_add}本に入れ替え、平面のラベル {n_lab}個を置き直し。ほかの部品はそのまま）。帳票も書き直しました")
    return True


if __name__ == "__main__":
    sys.exit(main())
