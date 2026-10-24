"""階段の位置を平面の線で変える（パレットのボタン「階段の位置」）.

利用者の指定（2026-10-24）「階段の位置変更も追加して 平面で線書いた位置へ」。平面で、階段を置きたいところに足場の面に
沿って線を1本引き、その線を選んで押す。線が半分以上かかるスパンに寄せ、窓で「どの階段を動かすか（新しく足すか）」と
スパン数を確かめて置き直す。位置は条件の上書き（~/Desktop/ashiba_spec.json の stairs.positions）に控え、置き直したら
目印の線は消す。階段が付けられない面（ブラケット足場など）は置き直しの検定が知らせる。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ashiba.plan_pick import along, spans_covered  # noqa: E402
from ashiba.tapir_adapter import ArchicadClient  # noqa: E402
from guide_lines import building_plan, delete_guides, not_in_plan_hint, selected_guides  # noqa: E402

NEW = "新しく足す"


def tower_label(face: str, t: dict) -> str:
    a = float(t["start_mm"])
    b = a + float(t.get("length_mm") or 0.0)
    return f"{face} {a:.0f}〜{b:.0f}（{int(t.get('span_count', 2))}スパン）"


def positions_after(towers: list[dict], faces: dict, pick: str, labels: list[str], face: str, start: float,
                    n: int) -> list[dict]:
    """今の階段の並び → 選んだ1つを線の位置に動かした（か足した）stairs.positions."""
    out = []
    for t, lab in zip(towers, labels):
        if lab == pick:
            continue
        out.append({"face": faces.get(int(t["edge_index"]), f"辺{t['edge_index']}"),
                    "start_mm": float(t["start_mm"]), "span_count": int(t.get("span_count", 2))})
    out.append({"face": face, "start_mm": float(start), "span_count": int(n), "reason": "平面の線で指定"})
    return out


def main() -> int:
    import run_from_archicad as R
    from ashiba.span_readback import merge_stairs
    from form_dialog import show_form

    c = ArchicadClient()
    guides = selected_guides(c)
    if not guides:
        print("階段の位置: 平面で、階段を置きたいところに足場の面に沿って線を1本引き、その線を選んでから押してください"
              + not_in_plan_hint(c))
        return 1
    _el, segs = guides[0]
    p1, p2 = segs[0]
    plan = building_plan([p1, p2])
    if plan is None:
        print("階段の位置: 線の近くの足場の配置の控え（plan.json）がありません。先に「配置」してください")
        return 1
    hit = along(plan.get("edges") or [], p1, p2)
    if hit is None:
        print("階段の位置: 足場に沿った線が見つかりません。階段を置きたいスパンに、足場の面に沿って線を引いてください")
        return 1
    e, t0, t1 = hit
    face = str(e.get("face") or f"辺{e['edge_index']}")
    start, n = spans_covered(e, t0, t1)
    faces = {int(x["edge_index"]): str(x.get("face") or f"辺{x['edge_index']}") for x in plan.get("edges") or []}
    towers = list((plan.get("stairs") or {}).get("towers") or [])
    labels = [tower_label(faces.get(int(t["edge_index"]), "?"), t) for t in towers]
    # 同じ面のいちばん近い階段を既定に（無ければ最初の階段）
    near = sorted(range(len(towers)), key=lambda i: (int(towers[i]["edge_index"]) != int(e["edge_index"]),
                                                     abs(float(towers[i]["start_mm"]) - start)))
    default = labels[near[0]] if near else NEW
    n_def = n if n >= 2 or not near else int(towers[near[0]].get("span_count", 2))
    intro = (f"{face}の始点から {start:.0f} に階段を置きます（線がかかるスパン {n}）。動かす階段とスパン数を選んで"
             "「動かす」を押してください。階段室は 2スパン（1層ずつ折り返し）が普通です。")
    res = show_form({"title": "階段の位置", "intro": intro, "fields": [
        {"key": "_s", "label": f"階段（{face}）", "kind": "section"},
        {"key": "which", "label": "動かす階段", "kind": "choice", "options": labels + [NEW], "value": default},
        {"key": "spans", "label": "スパン数", "kind": "choice", "options": ["1", "2", "3", "4"], "value": str(n_def)},
    ], "buttons": [{"id": "move", "label": "動かす"}, {"id": "cancel", "label": "やめる"}]})
    if not res or res.get("button") != "move":
        print("階段の位置: やめました（何も変えていません）")
        return 0
    vals = res.get("values") or {}
    pick = str(vals.get("which") or default)
    n_use = int(str(vals.get("spans") or n_def))
    pos = positions_after(towers, faces, pick, labels, face, start, n_use)
    body = R.load_spec_override()
    body = merge_stairs(body, pos)
    R.SPEC_OVERRIDE.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"階段の位置: {face} {start:.0f}〜（{n_use}スパン）" + (f"へ {pick} を動かしました" if pick != NEW else "に足しました")
          + f"（{R.SPEC_OVERRIDE.name} の stairs.positions {len(pos)}箇所）")
    print("---- 置き直します")
    R.main(outline_mm=plan.get("outline_mm"))
    delete_guides(c, guides)
    print("階段の位置: 目印の線を消しました")
    return 0


if __name__ == "__main__":
    sys.exit(main())
