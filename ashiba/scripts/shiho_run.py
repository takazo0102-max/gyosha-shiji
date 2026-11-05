"""切梁・腹起し（パレットの「切梁・腹起し」）. 手で引いた線から山留め支保工の部材を置く.

利用者の指定（2026-11-06）「縦横の切梁と中間杭も足して 切張り・腹起こしは手動でできるようにして LOD高く」。

  python3 scripts/shiho_run.py                                   # 選んだ線から。窓で部材（切梁・腹起し・火打ち・中間杭）・形・段を選ぶ
  python3 scripts/shiho_run.py --kind strut --levels 1000,4000    # 切梁を GL-1000・GL-4000 の2段に
  python3 scripts/shiho_run.py --kind wale --shape H-350          # 腹起し
  python3 scripts/shiho_run.py --kind strut --tier upper          # 上段の切梁（下段と交わる所に交差部の金物）
  python3 scripts/shiho_run.py --kind pile --bottom 9000          # 線の両端に中間杭（先端 GL-9000）
  python3 scripts/shiho_run.py --no-cross-piles                   # 切梁の交点に中間杭を置かない
  python3 scripts/shiho_run.py --remove                          # 置いた支保工を消す

線（線・ポリラインは折れ目ごと）1本を部材1本の芯とし、段ごとに部品 ashiba_shiho を1つ置く（割付・数量は src/ashiba/shiho.py）。
切梁は 主材（30HA の定尺）・補助ピース・キリンジャッキに割り付け、ジャッキは千鳥に。切梁の段（下段・上段）は「自動」なら最初に引いた
向きが下段、それに交わる向きが上段（上段は H 1本分上）で、交わる所に交差部の金物と中間杭（線の上の交点。段をまとめて1本）を置く。
段（深さ）の既定は、線を囲む「山留め壁」の腹起しの段（無ければ GL-1000）。部品はレイヤー「仮設_山留め」に。控えは ashiba_out/支保工.json
（押すたびに控えの線から全部を置き直す。同じ線を選び直すと置き換え）、数量は ashiba_out/支保工.md.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

RECORD = "支保工.json"
KIND_LABELS = {"strut": "切梁", "wale": "腹起し", "hiuchi": "火打ち", "pile": "中間杭"}
TIERS = {"自動（最初の向きが下段）": None, "下段": 0, "上段（H 1本分上）": 1}


def _depths(text) -> list[float]:
    out = []
    for x in str(text or "").replace("、", ",").replace("GL-", "").replace("GL", "").split(","):
        x = x.strip()
        if x:
            out.append(abs(float(x)))
    return out


def enclosing_wall(out_dir: Path, pts: list) -> dict:
    """線を囲む「山留め壁」の要点（腹起しの段・根切りの深さ・根入れ・GL）. 無ければ空."""
    from ywall_run import RECORD as YREC, wall_from

    from ashiba.negiri import inside

    try:
        rec = json.loads((Path(out_dir) / YREC).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not pts:
        return {}
    mid = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    for v in rec.values():
        if not v.get("closed"):
            continue
        try:
            w = wall_from(v)
        except (KeyError, ValueError):
            continue
        if inside(mid, w.pts):
            return {"name": w.name, "wales": list(w.wales), "depth": w.depth, "embed": w.embed_mm, "gl": w.gl}
    return {}


def build(rec: dict) -> list:
    """控え → 部材（切梁・腹起し・火打ち、切梁の交点の中間杭、手で指した中間杭）."""
    from ashiba import shiho as SH

    lines = [dict(v, a=tuple(v["a"]), b=tuple(v["b"])) for v in rec.get("lines", {}).values()]
    bars = [ln for ln in lines if ln["kind"] != "pile"]
    members = SH.manual(bars)
    SH.hiuchi_sides(members)
    cross = SH.crossings(members)
    bottom = float(rec.get("pile_bottom") or 9000.0)
    if rec.get("cross_piles", True) and cross:
        members += SH.make_piles(members, cross, top=0.0, bottom=bottom, name="交点")
    piles = [ln for ln in lines if ln["kind"] == "pile"]
    if piles:
        members += SH.manual_piles(piles, top=0.0, bottom=bottom)
    return members


def ask(a, n_lines: int, near: dict) -> bool:
    """窓で部材・形・段を選ぶ. やめたら False."""
    from form_dialog import show_form

    from ashiba import shiho as SH

    res = show_form({
        "title": "切梁・腹起し",
        "intro": f"選んだ線 {n_lines}本（ポリラインは折れ目ごと）を部材の芯として、段ごとに置きます。"
                 + (f"「{near['name']}」の中なので、段はその腹起しの段にしています。" if near.get("wales") else "")
                 + "切梁は主材の定尺・補助ピース・キリンジャッキに割り付け、上段の切梁は下段と交わる所に交差部の金物と中間杭を置きます。",
        "fields": [
            {"key": "name", "label": "名前", "kind": "text", "value": a.name or ""},
            {"key": "kind", "label": "部材", "kind": "choice", "options": list(KIND_LABELS.values()), "value": KIND_LABELS[a.kind]},
            {"key": "shape", "label": "形（リース材 30HA・35HA・40HA）", "kind": "choice", "options": list(SH.SHAPES), "value": a.shape},
            {"key": "levels", "label": "段（芯の深さ GL から mm。カンマ区切り）", "kind": "text", "value": a.levels},
            {"key": "tier", "label": "切梁の段", "kind": "choice", "options": list(TIERS),
             "value": next(k for k, v in TIERS.items() if v == a.tier_no)},
            {"key": "jack", "label": "キリンジャッキ（切梁）", "kind": "choice", "options": ["切梁1本に1台（千鳥）", "無し"],
             "value": "無し" if a.no_jack else "切梁1本に1台（千鳥）"},
            {"key": "cross", "label": "切梁の交点に中間杭", "kind": "choice", "options": ["置く", "置かない"],
             "value": "置かない" if a.no_cross_piles else "置く"},
            {"key": "bottom", "label": "中間杭の先端 GL から mm", "kind": "number", "value": f"{a.bottom:.0f}"},
            {"key": "gl", "label": "GL の高さ mm（プロジェクトの 0 から）", "kind": "number", "value": f"{a.gl:.0f}"},
        ],
        "buttons": [{"id": "place", "label": "置く"}, {"id": "cancel", "label": "やめる"}]})
    if not res or res.get("button") != "place":
        return False
    v = res.get("values") or {}
    inv = {lab: k for k, lab in KIND_LABELS.items()}
    a.kind = inv.get(str(v.get("kind")), a.kind)
    a.name = str(v.get("name") or "")
    a.shape = str(v.get("shape") or a.shape)
    a.levels = str(v.get("levels") or a.levels)
    a.tier_no = TIERS.get(str(v.get("tier")), a.tier_no)
    a.no_jack = str(v.get("jack")) == "無し"
    a.no_cross_piles = str(v.get("cross")) == "置かない"
    for key in ("bottom", "gl"):
        try:
            setattr(a, key, float(str(v.get(key)).replace(",", "")))
        except (TypeError, ValueError):
            pass
    return True


def main(argv=None) -> int:
    import argparse

    from ashiba import shiho as SH

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kind", default=None, choices=list(KIND_LABELS), help="部材（strut 切梁・wale 腹起し・hiuchi 火打ち・pile 中間杭）")
    ap.add_argument("--shape", default=None, choices=list(SH.SHAPES), help="形（既定 H-300）")
    ap.add_argument("--levels", default=None, help="段（芯の深さ GL から mm、カンマ区切り）")
    ap.add_argument("--tier", default=None, choices=("auto", "lower", "upper"), help="切梁の段（auto＝最初の向きが下段）")
    ap.add_argument("--no-jack", action="store_true", help="切梁にキリンジャッキを入れない")
    ap.add_argument("--no-cross-piles", action="store_true", help="切梁の交点に中間杭を置かない")
    ap.add_argument("--bottom", type=float, default=None, help="中間杭の先端 GL から mm")
    ap.add_argument("--name", default="", help="名前")
    ap.add_argument("--gl", type=float, default=None, help="GL の高さ mm（プロジェクトの 0 から）")
    ap.add_argument("--remove", action="store_true", help="置いた支保工を消す")
    a = ap.parse_args(argv)

    import run_from_archicad as R
    from ashiba.pens import gdl_pens, parse_pens
    from ashiba.tapir_adapter import ArchicadClient
    from excav_run import _delete_alive
    from guide_lines import selected_guides
    from ywall_run import LAYER, SHIHO_PART, layer_index, place_members

    c = ArchicadClient()
    R.OUT_DIR.mkdir(parents=True, exist_ok=True)
    rec_path = R.OUT_DIR / RECORD
    try:
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rec = {}
    rec.setdefault("lines", {})
    if a.remove:
        n = _delete_alive(c, rec.get("guids", []))
        rec_path.write_text(json.dumps({"lines": {}, "guids": []}, ensure_ascii=False), encoding="utf-8")
        print(f"切梁・腹起し: 部品 {n}個を消しました")
        return 0
    segs = [(el["elementId"]["guid"], i, sa, sb) for el, ss in selected_guides(c) for i, (sa, sb) in enumerate(ss)]
    if not segs:
        print("切梁・腹起し: 部材の芯の線（線・ポリライン。ポリラインは折れ目ごとに1本）を選んでから押してください")
        return 1
    asked = a.kind is None and a.shape is None and a.levels is None and a.tier is None and a.bottom is None and a.gl is None
    near = enclosing_wall(R.OUT_DIR, [p for _g, _i, sa, sb in segs for p in (sa, sb)])
    a.kind = a.kind or "strut"
    a.shape = a.shape or "H-300"
    a.levels = a.levels or ",".join(f"{z:.0f}" for z in (near.get("wales") or [1000.0]))
    a.tier_no = {"lower": 0, "upper": 1}.get(a.tier or "auto")
    if a.bottom is None:
        a.bottom = float(rec.get("pile_bottom") or (near["depth"] + near["embed"] if near else max(_depths(a.levels)) + 4000.0))
    a.gl = near.get("gl", 0.0) if a.gl is None else a.gl
    if asked and not ask(a, len(segs), near):
        print("切梁・腹起し: やめました（何も置いていません）")
        return 0
    depths = _depths(a.levels)
    if not depths:
        print("切梁・腹起し: 段（芯の深さ GL から mm）を入れてください")
        return 1
    for k, (g, i, sa, sb) in enumerate(segs, 1):
        key = f"{g}:{i}"
        nm = a.name if a.name and len(segs) == 1 else (f"{a.name}{k}" if a.name else f"{KIND_LABELS[a.kind]}{len(rec['lines']) + 1}")
        old = rec["lines"].get(key) or {}
        rec["lines"][key] = {"kind": a.kind, "a": list(sa), "b": list(sb), "depths": depths, "shape": a.shape, "tier": a.tier_no,
                             "jack": not a.no_jack, "name": old.get("name") if old.get("kind") == a.kind else nm}
    rec["cross_piles"] = not a.no_cross_piles
    rec["pile_bottom"] = a.bottom
    rec["gl"] = a.gl

    R.ensure_parts(c)
    spec = {**R.SPEC, **R.load_spec_override()}
    pens = gdl_pens(parse_pens(spec.get("pens")), SHIHO_PART)
    from pen_colors import draft_pens_for

    pens.update(draft_pens_for(c, pens.get("penEquip", 1)))
    _delete_alive(c, rec.get("guids", []))                # 控えの線から全部を置き直す（交差部・交点の中間杭がそろう）
    members = build(rec)
    rec["guids"] = place_members(c, members, float(rec.get("gl", 0.0)), layer_index(c), pens)
    rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    md = R.OUT_DIR / "支保工.md"
    md.write_text(SH.report(members, "山留め支保工（手で引いた線から）"), encoding="utf-8")
    cnt = {k: sum(1 for m in members if m.kind == k) for k in KIND_LABELS}
    nx = sum(len(m.crossings) for m in members if m.kind == "strut")
    print("切梁・腹起し: " + "・".join(f"{KIND_LABELS[k]} {n}本" for k, n in cnt.items() if n) + (f"・交差部 {nx}か所" if nx else "")
          + f"（部品 {len(rec['guids'])}個・レイヤー {LAYER}。数量: {md}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
