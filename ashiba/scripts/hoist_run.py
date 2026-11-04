"""昇降機を線で置く（パレットのボタン「昇降機」）.

利用者の指定（2026-10-28）「レールと線を引いて外つけか中に914幅で入れるか選べるようにして」。平面で、昇降機を据えたい所に
足場の面に沿って線（ガイドレールの芯から芯）を1本引き、その線を選んで押す。窓で機種・取付け（外付け／足場の幅 914 の中）・
乗り込む層を選んで「置く」と、昇降機の部品（ashiba_hoist）を線の中点の外に置き、全体を置き直す（配置が部品を読んで面に
合わせる）。線の近くに昇降機の部品があれば、その部品を置き換える（「外す」で消す）。置き直したら目印の線は消す。
部品は直接置いても使える（部品の設定「足場の幅の中に据える（914）」で同じことを選べる）。
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ashiba.tapir_adapter import ArchicadClient, TapirError  # noqa: E402

NEAR_MM = 3000.0           # 線の中点からこの範囲の昇降機の部品は「同じ所の昇降機」とみなす
MOUNTS = ("外付け（足場の外側建地の列の外）", "内（足場の幅 914 の中）")


def face_of_line(groups, p1, p2):
    """線のいちばん近い面 → (面番号, 面名, 中点の面に沿った位置 mm, 線の長さ mm, 外向きの単位ベクトル, 外側の列の点). 無ければ None."""
    mx, my = (p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0
    best = None
    for _label, r in groups:
        m = r.model
        for ep in m.plan.edges:
            (sx, sy), (ex, ey) = ep.start_post, ep.end_post
            n = math.hypot(ex - sx, ey - sy) or 1.0
            ux, uy = (ex - sx) / n, (ey - sy) / n
            nx, ny = -uy, ux                          # 躯体側
            row = float(m.row_spacing_of(ep.edge_index))
            ox, oy = sx - nx * row, sy - ny * row      # 外側の列の始点
            t = (mx - ox) * ux + (my - oy) * uy
            d = abs((mx - ox) * nx + (my - oy) * ny)
            if -500.0 <= t <= float(sum(ep.spans)) + 500.0 and (best is None or d < best[0]):
                best = (d, ep.edge_index, m.face_name(ep.edge_index), t, (-nx, -ny), (ox + ux * t, oy + uy * t))
    if best is None:
        return None
    length = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    return best[1], best[2], best[3], length, best[4], best[5]


def model_choices(length_mm: float) -> list[str]:
    """機種の選択肢（線の長さに枠組間隔・ガイドレール芯が近いロングスパンを先に）."""
    from ashiba.hoist_models import load_hoist_models

    ms = list(load_hoist_models().values())

    def key(m):
        span = m.frame_span_mm or m.post_spacing_mm or m.cage_len_mm
        return (0 if m.kind == "ロングスパン" else 1, abs(float(span) - length_mm))

    return [f"{m.model_id}｜{m.name}" for m in sorted(ms, key=key)]


def main() -> int:
    import run_from_archicad as R
    # 足場の「開口」の関数（scaffold_opening_run.py。床の開口養生 opening_run.py とは別。2026-11-01 の上書きで読めなくなっていた）
    from scaffold_opening_run import OUT_DIR, building_of, guide_line
    from ashiba.cli import solve_groups

    c = ArchicadClient()
    g = guide_line(c)
    if g is None:
        print("昇降機: 平面で、昇降機を据えたい所に足場の面に沿って線（ガイドレールの芯から芯）を1本引き、"
              "その線を選んでから押してください")
        return 1
    line_el, p1, p2 = g
    plan, used = building_of(p1, p2)
    if plan is None or used is None:
        print(f"昇降機: 線の近くの足場の配置の控え（plan.json・spec_used.json）が {OUT_DIR} にありません。先に「配置」してください")
        return 1
    outline = plan.get("outline_mm") or []
    groups = solve_groups({**{k: v for k, v in used.items() if k != "hoists"}, "outline_mm": outline})
    f = face_of_line(groups, p1, p2)
    if f is None:
        print("昇降機: 線の近くに足場の面がありません。足場の面に沿って線を引いてください")
        return 1
    ei, face, pos, length, out_dir, on_row = f
    R.ensure_parts(c)
    objs = R.read_hoist_objects(c, outline)
    mx, my = (p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0
    near = [o for o in objs if math.hypot(o[1][0] - mx, o[1][1] - my) <= NEAR_MM]
    old = near[0] if near else None
    choices = model_choices(length)
    cur = str((old[2] if old else {}).get("hoModel") or "")
    model_value = next((x for x in choices if x.startswith(cur + "｜")), choices[0]) if cur else choices[0]
    inside_now = old is not None and str(old[2].get("hoInside", "")).strip().lower() in ("1", "1.0", "true")
    from form_dialog import show_form

    intro = (f"{face}の始点から {pos:.0f}mm（線の長さ {length:.0f}）に昇降機を据えます。外付けは荷台が足場の外側建地の列の外を"
             "昇り降りし、荷取りステージは荷取用金具と梁枠。足場の幅 914 の中に据えるときは、昇降路の足場を全高で抜き、"
             "荷取りステージは両横の足場の端から内側ブラケットを出して敷板を引きます。")
    buttons = [{"id": "place", "label": "置く"}]
    if old is not None:
        buttons.append({"id": "remove", "label": "外す"})
        intro += f" 線の近くに昇降機（{cur or '機種なし'}）があります。置くと置き換えます。"
    buttons.append({"id": "cancel", "label": "やめる"})
    res = show_form({"title": "昇降機", "intro": intro, "buttons": buttons, "fields": [
        {"key": "_s", "label": f"昇降機（{face}）", "kind": "section"},
        {"key": "model", "label": "機種", "kind": "choice", "options": choices, "value": model_value},
        {"key": "mount", "label": "取付け", "kind": "choice", "options": list(MOUNTS),
         "value": MOUNTS[1] if inside_now else MOUNTS[0]},
        {"key": "levels", "label": "乗り込むフロア（下から 1,2,… の番号 例 2,4。空は全部のフロア）", "kind": "text",
         "value": str((old[2] if old else {}).get("landLevels") or "")},
    ]})
    if not res or res.get("button") in (None, "cancel"):
        print("昇降機: やめました（何も変えていません）")
        return 0
    if old is not None:
        c.delete_elements([old[0]])
    if res["button"] == "remove":
        print(f"昇降機: {face}の昇降機（{cur or '機種なし'}）を外しました")
    else:
        v = res.get("values") or {}
        model_id = str(v.get("model") or choices[0]).split("｜")[0]
        inside = str(v.get("mount") or "").startswith("内")
        # 外側の列から 900 外に置く（配置が面に寄せる。hoist_objects.hoists_from_objects）
        x, y = on_row[0] + out_dir[0] * 900.0, on_row[1] + out_dir[1] * 900.0
        try:
            el = c.create_object(R.versioned_part_name("ashiba_hoist"), x, y)
            c.set_gdl_parameters(el, {"hoModel": model_id, "hoInside": bool(inside),
                                      "landLevels": str(v.get("levels") or "").strip()})
        except TapirError as e:
            print(f"昇降機: 部品を置けませんでした（{e}）")
            return 1
        print(f"昇降機: {face}の始点から {pos:.0f}mm に {model_id}（{'足場の幅の中' if inside else '外付け'}）を置きました")
    print("---- 置き直します")
    R.main(outline_mm=outline, out_dir=OUT_DIR)
    try:
        c.delete_elements([line_el])          # 目印の線
        print("昇降機: 目印の線を消しました")
    except TapirError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
