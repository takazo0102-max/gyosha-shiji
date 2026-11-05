"""朝顔を付ける範囲を平面の線で決める（パレットのボタン「朝顔の範囲」）.

利用者の指定（2026-10-24）「配置で朝顔が勝手に配置される。なしして線で朝顔の範囲追加できるようにして」。配置では朝顔を
付けない。平面で、朝顔の要るところ（道路・隣地・人の通る側）に足場の面に沿って線を引き（何本でも・ポリラインの折れ目ごと
でもよい）、その線を選んで押す。線が半分以上かかるスパンに寄せ、窓で「付ける／外す」を選ぶと、足場条件の部品の「朝顔を
付ける面」（asagaoFaces。面の一部は「南面[a-b]」＝元の面の始点の支柱から mm）に書き、変わった面の朝顔と取付部の壁つなぎ
だけを入れ替える。目印の線は消す。

  python3 scripts/asagao_range_run.py                         # 窓で付ける・外すを選ぶ
  ASHIBA_FORM_ANSWER='{"button":"add"}' python3 scripts/asagao_range_run.py   # 窓を出さずに（試験用）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ashiba.geometry import same_outline  # noqa: E402
from ashiba.plan_pick import along, posts_of, spans_covered  # noqa: E402
from ashiba.tapir_adapter import ArchicadClient  # noqa: E402
from guide_lines import OUT_DIR, building_plan, delete_guides, not_in_plan_hint, selected_guides  # noqa: E402


def same_building_edges(plan: dict) -> list[dict]:
    """線の近くの建物の、すべての組の面（面の切替で組が分かれていれば、ほかの組の plan.json の面も）."""
    outline = plan.get("outline_mm") or []
    out = list(plan.get("edges") or [])
    seen = {plan.get("_path")}
    for p in sorted(OUT_DIR.rglob("*_plan.json"), key=lambda q: -q.stat().st_mtime):
        if str(p) in seen:
            continue
        seen.add(str(p))
        try:
            other = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if same_outline(other.get("outline_mm"), outline):
            out += list(other.get("edges") or [])
    return out


def face_of(e: dict) -> str:
    return str(e.get("face") or f"辺{e['edge_index']}")


def full_range(e: dict, t0: float, t1: float) -> tuple[float, float, float]:
    """線の区間（その部品の面の始点から）→ 線がかかるスパンの (始め, 終わり, 元の面の長さ)（元の面の始点の支柱から mm）.

    面の途中で種類を切り替えた区間の部品は faceOff（元の面での区間の始め）を足す。faceLen は元の面の長さ。
    """
    g = e.get("gdl_params") or {}
    start, n = spans_covered(e, t0, t1)
    posts = posts_of(e)
    i0 = min(range(len(posts)), key=lambda i: abs(posts[i] - start))
    end = posts[min(len(posts) - 1, i0 + n)]
    off = float(g.get("faceOff") or 0.0) * 1000.0
    full = float(g.get("faceLen") or 0.0) * 1000.0 or posts[-1]
    return off + start, off + end, full


def picked_ranges(edges: list[dict], guides) -> tuple[list[str], dict[str, float], list[str]]:
    """選んだ線 → (付け外しする面・区間のキー, 面の長さ, 読めなかった線の説明)."""
    from ashiba.face_forms import range_key

    keys: list[str] = []
    lengths: dict[str, float] = {}
    missed: list[str] = []
    for _el, segs in guides:
        for p1, p2 in segs:
            hit = along(edges, p1, p2)
            if hit is None:
                missed.append(f"({p1[0]:.0f},{p1[1]:.0f})〜({p2[0]:.0f},{p2[1]:.0f})")
                continue
            e, t0, t1 = hit
            a, b, full = full_range(e, t0, t1)
            face = face_of(e)
            lengths[face] = full
            key = face if a < 1.0 and b > full - 1.0 else range_key(face, a, b)
            if key not in keys:
                keys.append(key)
    return keys, lengths, missed


def main() -> int:
    from asagao_faces import apply_change, write_asagao_faces
    from form_dialog import show_form

    from ashiba.cli import all_face_names
    from ashiba.spec_form import ASAGAO_MODES

    c = ArchicadClient()
    guides = selected_guides(c)
    if not guides:
        print("朝顔の範囲: 平面で、朝顔を付けたい（外したい）ところに足場の面に沿って線を引き、その線を選んでから押してください"
              + not_in_plan_hint(c))
        return 1
    pts = [p for _el, segs in guides for seg in segs for p in seg]
    plan = building_plan(pts)
    if plan is None:
        print("朝顔の範囲: 線の近くの足場の配置の控え（plan.json）がありません。先に「配置」してください")
        return 1
    keys, lengths, missed = picked_ranges(same_building_edges(plan), guides)
    if not keys:
        print("朝顔の範囲: 足場に沿った線が見つかりません。朝顔の要るスパンに、足場の面に沿って線を引いてください")
        return 1
    shown = "、".join(k.replace("[", " ").replace("-", "〜").rstrip("]") if "[" in k else f"{k} 全部" for k in keys)
    intro = (f"線がかかるスパン: {shown}（面の始点の支柱から mm）。朝顔を「付ける」か「外す」を選んでください。"
             "段数は足場の高さで決まります（10m以上で1段・20m以上で2段）。")
    if missed:
        intro += f" 足場に沿っていない線 {len(missed)}本は使いません。"
    res = show_form({"title": "朝顔の範囲", "intro": intro, "fields": [],
                     "buttons": [{"id": "add", "label": "付ける"}, {"id": "remove", "label": "外す"},
                                 {"id": "cancel", "label": "やめる"}]})
    if not res or res.get("button") not in ("add", "remove"):
        print("朝顔の範囲: やめました（何も変えていません）")
        return 0
    mode = ASAGAO_MODES[0] if res["button"] == "add" else ASAGAO_MODES[1]
    outline = plan.get("outline_mm") or []
    every = all_face_names({"outline_mm": outline})
    old, new, where = write_asagao_faces(c, outline, every, keys, mode, lengths)
    print(f"朝顔の範囲: {shown} → {mode}（{where}）。朝顔を付ける面: {new}")
    if "--no-apply" in sys.argv:
        return 0
    rc = apply_change(c, plan, every, old, new, "朝顔の範囲")
    delete_guides(c, guides)
    print("朝顔の範囲: 目印の線を消しました")
    return rc


if __name__ == "__main__":
    sys.exit(main())
