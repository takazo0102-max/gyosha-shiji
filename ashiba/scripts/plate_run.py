"""敷鉄板（パレットの「敷鉄板」）.

利用者の指定（2026-11-01）「敷鉄板はホットスポットで広げれるようにして 別オブジェクトにして」。

  python3 scripts/plate_run.py                         # 選んだ線・ポリラインの範囲（始めの辺の向き）を覆う敷鉄板
  python3 scripts/plate_run.py --type NT22×5×20 --along-y --layers 2
  python3 scripts/plate_run.py --width 3048            # 線1本なら幅（既定は1枚の短い辺）
  python3 scripts/plate_run.py --remove                # 置いた敷鉄板を消す

部品 ashiba_plate を範囲に1つ（src/ashiba/steel_plate.py が枚数と重さ）。置いたあとは平面のホットスポット（右の辺・上の辺の
真ん中）で引けば広がり、1枚の倍数に切り上がる。前に同じ線に置いたものは控え（ashiba_out/敷鉄板.json）で消して置き直す。
数量は ashiba_out/敷鉄板.md.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

PART = "ashiba_plate"
RECORD = "敷鉄板.json"
ALIAS = {"5x20": "NT22×5×20", "5x10": "NT22×5×10", "4x8": "NT22×4×8", "3x6": "NT22×3×6"}


def plate_code(text: str) -> str:
    from ashiba.steel_plate import PLATES

    t = text.replace("×", "x").replace("X", "x").replace("NT22x", "").strip()
    code = ALIAS.get(t, text)
    if code not in PLATES:
        raise SystemExit(f"敷鉄板は {'・'.join(PLATES)} のどれか（{text}）")
    return code


def extent(pts: list, width: float = 0.0) -> tuple[tuple[float, float], float, float, float]:
    """点列 → 始めの辺の向きにそろえた範囲 (隅, 長さ X, 長さ Y, 向き 度)。線1本なら幅 width を左へ."""
    a, b = pts[0], pts[1]
    L = math.dist(a, b) or 1.0
    u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
    v = (-u[1], u[0])
    s = [(p[0] - a[0]) * u[0] + (p[1] - a[1]) * u[1] for p in pts]
    t = [(p[0] - a[0]) * v[0] + (p[1] - a[1]) * v[1] for p in pts]
    s0, s1, t0, t1 = min(s), max(s), min(t), max(t)
    if t1 - t0 < 1.0:
        t1 = t0 + width
    corner = (a[0] + u[0] * s0 + v[0] * t0, a[1] + u[1] * s0 + v[1] * t0)
    return corner, s1 - s0, t1 - t0, math.degrees(math.atan2(u[1], u[0]))


def report(rows: list) -> str:
    from ashiba.steel_plate import THICK_MM, quantity

    out = ["# 敷鉄板", "", "出典: 日建リース工業 仮設資材カタログ Vol.10 p394（厚板鋼板・敷鉄板固定金具 小判君）", "",
           "| 範囲 | 敷鉄板 | 並べ方 | 広さ | 枚数 | 重さ |", "|---|---|---|---|---|---|"]
    for name, lay in rows:
        out.append(f"| {name} | {lay.code}（厚さ {THICK_MM:.0f}） | {lay.nx}×{lay.ny}{'・2段（十字）' if lay.layers >= 2 else ''} | "
                   f"{lay.lx:.0f}×{lay.ly:.0f} | {lay.count} | {lay.kg / 1000:.1f}t |")
    out += ["", "| 品名 | 数 | 注 |", "|---|---|---|"] + [f"| {a} | {b:g} | {c} |" for a, b, c in quantity([x for _n, x in rows])]
    out += ["", "置いたあとは平面のホットスポット（右の辺・上の辺の真ん中）で引いて広げる（1枚の倍数に切り上がる）。"
            "移動式クレーンのアウトリガは鉄板の中央に（クレーン等安全規則 70条の4）。"]
    return "\n".join(out)


def main(argv=None) -> int:
    from ashiba.naming import ordinal, prune_gone

    import argparse

    import run_from_archicad as R
    from ashiba.pens import gdl_pens, parse_pens
    from ashiba.steel_plate import PLATES, layout, part_params
    from ashiba.tapir_adapter import ArchicadClient, read_ground_model
    from excav_run import _delete_alive, _place
    from guide_lines import selected_guides
    from kakoi_run import chains

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--type", default="NT22×5×10", help=f"敷鉄板（{'・'.join(PLATES)}。5x10 などでも）")
    ap.add_argument("--along-y", action="store_true", help="長い辺を範囲の Y（始めの辺と直角）に")
    ap.add_argument("--layers", type=int, default=1, choices=(1, 2), help="段数（2＝上の段を十字に）")
    ap.add_argument("--width", type=float, default=0.0, help="線1本のときの幅 mm（既定は1枚の短い辺）")
    ap.add_argument("--z", type=float, default=None, help="置く高さ mm（省くと敷地メッシュ、無ければ 0）")
    ap.add_argument("--remove", action="store_true", help="置いた敷鉄板を消す")
    a = ap.parse_args(argv)
    c = ArchicadClient()
    rec_path = R.OUT_DIR / RECORD
    try:
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rec = {}
    rec = prune_gone(c, rec)                     # Archicad で消したものは控えから除く（番号・帳票）
    if a.remove:
        n = _delete_alive(c, list(rec.values()))
        rec_path.write_text("{}", encoding="utf-8")
        print(f"敷鉄板: {n}個を消しました")
        return 0
    code = plate_code(a.type)
    lines = [(k, pts) for k, pts, _closed in chains(selected_guides(c)) if len(pts) >= 2]
    if not lines:
        print("敷鉄板: 敷く範囲の線（ポリライン・線）を選んでから押してください。置いたあとはホットスポットで広げられます")
        return 1
    R.ensure_parts(c)
    part = R.versioned_part_name(PART)
    spec = {**R.SPEC, **R.load_spec_override()}
    pens = gdl_pens(parse_pens(spec.get("pens")), PART)
    from pen_colors import draft_pens_for

    pens.update(draft_pens_for(c, pens.get("penEquip", 1)))      # 外形は太線・細部は細線（scripts/gdl_draft.py）
    ground = None
    if a.z is None:
        gm = read_ground_model(c, [p for _k, pts in lines for p in pts])
        ground = gm.elevation_at if getattr(gm, "points", None) else None
    rows = []
    fresh = 0
    for _n, (key, pts) in enumerate(lines, 1):
        n = ordinal(rec, key, fresh)                    # 名前の番号は控えの続き（同じ線は前の番号のまま）
        fresh += key not in rec
        if key in rec:
            _delete_alive(c, [rec[key]])
        width = a.width or PLATES[code][1]
        corner, lx, ly, ang = extent(pts, width)
        lay = layout(lx, ly, code, a.along_y, a.layers)
        z = a.z if a.z is not None else (ground(*corner) if ground else 0.0)
        el = _place(c, part, corner, z, ang)
        if el is None:
            continue
        c.set_gdl_parameters(el, {**part_params(lay, f"敷鉄板{n}"), **pens})
        rec[key] = el["elementId"]["guid"]
        rows.append((f"敷鉄板{n}", lay))
        print(f"  敷鉄板{n}: {code} {lay.nx}×{lay.ny}（{lay.lx:.0f}×{lay.ly:.0f}）・{lay.count}枚・{lay.kg / 1000:.1f}t")
    R.OUT_DIR.mkdir(parents=True, exist_ok=True)
    rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    md = R.OUT_DIR / "敷鉄板.md"
    md.write_text(report(rows), encoding="utf-8")
    print(f"敷鉄板: {len(rows)}か所に置きました（数量: {md}）。ホットスポットで広げられます")
    return 0


if __name__ == "__main__":
    sys.exit(main())
