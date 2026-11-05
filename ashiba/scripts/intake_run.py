"""取り入れ口を平面の線で付ける・外す（パレットのボタン「取り入れ口」）.

利用者の指定（2026-10-24）「取り入れ口を作る仕組みを考えて作成して」。平面で、資材を取り込む幅に足場の面に沿って
線を引き、その線を選んで押す。線が半分以上かかるスパンに寄せ、窓で層（例 3-5・全部）を選んで「付ける」と、
条件の上書き（~/ashiba_spec.json の intakes）に控えて置き直す。そのスパンの外側の固定の手すり・中桟と幅木を
外して可動手すりを付ける（ashiba.intakes）。同じ面の重なる取り入れ口は「外す」で外せる。置き直したら目印の線は消す。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ashiba.plan_pick import along, posts_of, spans_covered  # noqa: E402
from ashiba.tapir_adapter import ArchicadClient  # noqa: E402
from guide_lines import building_plan, delete_guides, not_in_plan_hint, selected_guides  # noqa: E402


def overlaps(item: dict, face: str, a: float, b: float, posts_end) -> bool:
    if str(item.get("face")) != face:
        return False
    s = float(item.get("start_mm", 0.0))
    e = posts_end(s, int(item.get("span_count", 1) or 1))
    return min(e, b) - max(s, a) > 1.0


def updated_intakes(items: list[dict], face: str, start: float, n: int, levels: str, add: bool, posts) -> list[dict]:
    """今の intakes → 選んだ面・スパンの取り入れ口を付けた（外した）並び（重なる前の指定は外す）."""
    def end_of(s, k):
        i = min(range(len(posts)), key=lambda j: abs(posts[j] - s))
        return posts[min(len(posts) - 1, i + k)]

    b = end_of(start, n)
    out = [it for it in items if not overlaps(it, face, start, b, end_of)]
    if add:
        out.append({"face": face, "start_mm": round(start), "span_count": n, "levels": levels or "全部"})
    return out


def main() -> int:
    import run_from_archicad as R
    from form_dialog import show_form

    c = ArchicadClient()
    guides = selected_guides(c)
    if not guides:
        print("取り入れ口: 平面で、資材を取り込む幅に足場の面に沿って線を引き、その線を選んでから押してください"
              + not_in_plan_hint(c))
        return 1
    _el, segs = guides[0]
    p1, p2 = segs[0]
    plan = building_plan([p1, p2])
    if plan is None:
        print("取り入れ口: 線の近くの足場の配置の控え（plan.json）がありません。先に「配置」してください")
        return 1
    hit = along(plan.get("edges") or [], p1, p2)
    if hit is None:
        print("取り入れ口: 足場に沿った線が見つかりません。取り込む幅に、足場の面に沿って線を引いてください")
        return 1
    e, t0, t1 = hit
    face = str(e.get("face") or f"辺{e['edge_index']}")
    off = float((e.get("gdl_params") or {}).get("faceOff") or 0.0) * 1000.0
    start, n = spans_covered(e, t0, t1)
    posts = [off + x for x in posts_of(e)]
    start += off
    body = R.load_spec_override()
    items = list(body.get("intakes") or [])
    res = show_form({"title": "取り入れ口", "intro": (f"{face}の始点から {start:.0f}〜（{n}スパン）に取り入れ口を付けます。"
                                                   "固定の手すり・中桟と幅木を外して可動手すりにし、シートは巻き上げ式にします。"),
                     "fields": [{"key": "levels", "label": "層（例 3-5・全部）", "kind": "text", "value": "全部"},
                                {"key": "spans", "label": "スパン数", "kind": "choice", "options": ["1", "2", "3", "4"],
                                 "value": str(max(1, min(4, n)))}],
                     "buttons": [{"id": "add", "label": "付ける"}, {"id": "remove", "label": "外す"},
                                 {"id": "cancel", "label": "やめる"}]})
    if not res or res.get("button") not in ("add", "remove"):
        print("取り入れ口: やめました（何も変えていません）")
        return 0
    vals = res.get("values") or {}
    n = int(str(vals.get("spans") or n))
    lv = str(vals.get("levels") or "全部").strip()
    new = updated_intakes(items, face, start, n, lv, res["button"] == "add", posts)
    if new:
        body["intakes"] = new
    else:
        body.pop("intakes", None)
    R.SPEC_OVERRIDE.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"取り入れ口: {face} {start:.0f}〜（{n}スパン・{lv}層）を" + ("付けました" if res["button"] == "add" else "外しました")
          + f"（{R.SPEC_OVERRIDE.name} の intakes {len(new)}箇所）")
    print("---- 置き直します")
    R.main(outline_mm=plan.get("outline_mm"))
    delete_guides(c, guides)
    print("取り入れ口: 目印の線を消しました")
    return 0


if __name__ == "__main__":
    sys.exit(main())
