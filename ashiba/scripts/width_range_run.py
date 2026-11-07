"""足場の幅を途中の床から変える範囲を平面の線で決める（パレットのボタン「幅の変更」）.

利用者の指定（2026-10-25）「拡張が全ての足場になってしまうから直すのところで線を引いた範囲限定にする」。平面で、幅を
変えたいところに足場の面に沿って線を引き（何本でも・面をまたいでもよい）、その線を選んで押す。線が半分以上かかる
スパンに寄せ、窓で幅の変え方（拡幅 610→914・914→1219／縮幅 914→610・1219→914。いまの足場の幅から選べるもの）と
幅を変える床の段を選んで「付ける」と、条件の上書きファイルの width_change に範囲（「南面[a-b]」）を足して置き直す。
「外す」は線がかかる範囲を、「全部外す」は全部の範囲を戻す。目印の線は消す。

  python3 scripts/width_range_run.py
  ASHIBA_FORM_ANSWER='{"button":"add","values":{"mode":"拡幅 610→914","level":"3"}}' python3 scripts/width_range_run.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ashiba.tapir_adapter import ArchicadClient  # noqa: E402
from asagao_range_run import picked_ranges, same_building_edges  # noqa: E402
from guide_lines import building_plan, delete_guides, not_in_plan_hint, selected_guides  # noqa: E402


def current_width(edges: list[dict]) -> int:
    """置いてある足場の幅（建地列の間隔 mm。区切った下の部品の rowW）."""
    for e in edges:
        g = e.get("gdl_params") or {}
        if g.get("rowW"):
            return int(round(float(g["rowW"]) * 1000.0))
    return 0


def merged_faces(old: list[str], keys: list[str], add: bool) -> list[str]:
    """幅を変える範囲（「南面」「南面[a-b]」）に線の範囲を足す・外す. 外すときは同じ面で重なる範囲を外す."""
    from ashiba.face_forms import split_key

    if add:
        return list(dict.fromkeys(list(old) + list(keys)))
    out = []
    for f in old:
        face, a, b = split_key(f)
        hit = False
        for k in keys:
            kf, ka, kb = split_key(k)
            if kf != face:
                continue
            if a is None or ka is None or (ka < b - 1.0 and kb > a + 1.0):
                hit = True
        if not hit:
            out.append(f)
    return out


def updated_width_change(cur: dict | None, mode_label: str, level: int, keys: list[str], button: str) -> dict | None:
    """条件の上書きの width_change を、窓の答えで作り直す（範囲が無くなれば None）."""
    from ashiba.width_change import parse_spec

    if button == "clear":
        return None
    cur = parse_spec(cur) or {}
    faces = list(cur.get("faces") or [])
    faces = merged_faces(faces, keys, button == "add")
    if not faces:
        return None
    v = parse_spec(mode_label) or {}
    return {"label": mode_label, "from_mm": v.get("from_mm"), "to_mm": v.get("to_mm"), "level": int(level),
            "faces": faces}


def main() -> int:
    import run_from_archicad as R
    from form_dialog import show_form

    from ashiba.width_change import labels_for, parse_spec

    c = ArchicadClient()
    guides = selected_guides(c)
    body = R.load_spec_override()
    cur = parse_spec(body.get("width_change"))
    if not guides and not cur:
        print("幅の変更: 平面で、足場の幅を変えたいところに足場の面に沿って線を引き、その線を選んでから押してください"
              + not_in_plan_hint(c))
        return 1
    plan = building_plan([p for _el, segs in guides for seg in segs for p in seg]) if guides else None
    if guides and plan is None:
        print("幅の変更: 線の近くの足場の配置の控え（plan.json）がありません。先に「配置」してください")
        return 1
    keys, _lengths, missed = picked_ranges(same_building_edges(plan), guides) if plan else ([], {}, [])
    if guides and not keys:
        print("幅の変更: 足場に沿った線が見つかりません。幅を変えるスパンに、足場の面に沿って線を引いてください")
        return 1
    width = int(cur.get("from_mm")) if cur and cur.get("from_mm") else current_width(plan.get("edges") or []) if plan else 0
    modes = labels_for(width)
    if not modes:
        print(f"幅の変更: いまの足場の幅 {width} からは拡幅ブラケット 305 で変えられません（610・914・1219 の足場で使えます）")
        return 1
    shown = "、".join(k.replace("[", " ").replace("-", "〜").rstrip("]") if "[" in k else f"{k} 全部" for k in keys)
    have = "、".join(cur.get("faces") or []) if cur else ""
    intro = ((f"線がかかるスパン: {shown}（面の始点の支柱から mm）。" if keys else "")
             + (f"いま幅を変えている範囲: {have}（{cur.get('label')}・{cur.get('level')}段目の床から）。" if have else "")
             + "拡幅ブラケット（日建 NDBK03H 305）を幅を変える床のコマで元の外側の支柱に掛け、その床から上を新しい幅にします。"
             "幅の変え方と段はすべての範囲で共通です。")
    if missed:
        intro += f" 足場に沿っていない線 {len(missed)}本は使いません。"
    mode0 = cur.get("label") if cur and cur.get("label") in modes else modes[0]
    buttons = ([{"id": "add", "label": "付ける"}, {"id": "remove", "label": "外す"}] if keys else []) \
        + ([{"id": "clear", "label": "全部外す"}] if cur else []) + [{"id": "cancel", "label": "やめる"}]
    res = show_form({"title": "幅の変更（拡幅・縮幅）", "intro": intro,
                     "fields": [{"key": "mode", "label": "幅の変え方", "kind": "choice", "options": modes, "value": mode0},
                                {"key": "level", "label": "幅を変える床（段）", "kind": "text",
                                 "value": str((cur or {}).get("level") or 3),
                                 "help": "この段の床から上が新しい幅（1＝最下段の床。2 以上）"}],
                     "buttons": buttons})
    if not res or res.get("button") not in ("add", "remove", "clear"):
        print("幅の変更: やめました（何も変えていません）")
        return 0
    vals = res.get("values") or {}
    try:
        level = int(str(vals.get("level") or "").strip())
    except ValueError:
        level = 0
    if res["button"] in ("add", "remove") and not keys:
        # 線を選ばずに押して「付ける」を選ぶと、条件だけ書いて置き直しで止まっていた（2026-11-07 ループの試験）
        print("幅の変更: 付ける・外すは、足場の面に沿って線を引いて選んでから押してください（何も変えていません）")
        return 1
    if res["button"] == "add" and level < 2:
        print(f"幅の変更: 幅を変える床の段「{vals.get('level')}」は 2 以上の数字にしてください（何も変えていません）")
        return 1
    new = updated_width_change(body.get("width_change"), str(vals.get("mode") or mode0), level or int((cur or {}).get("level") or 2),
                               keys, res["button"])
    if new:
        body["width_change"] = new
    else:
        body.pop("width_change", None)
    R.SPEC_OVERRIDE.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("幅の変更: " + (f"{new['label']}（{new['level']}段目の床から）: {'、'.join(new['faces'])}" if new else "幅を変える範囲はありません")
          + f"（{R.SPEC_OVERRIDE.name} の width_change）")
    print("---- 置き直します")
    if plan is None:                                     # 線を選ばずに「全部外す」: いちばん新しい配置の控えの建物で置き直す
        found = sorted(R.OUT_DIR.rglob("*_plan.json"), key=lambda q: -q.stat().st_mtime)
        plan = json.loads(found[0].read_text(encoding="utf-8")) if found else None
    outline = (plan or {}).get("outline_mm")
    from ashiba.tapir_adapter import TapirError

    try:
        R.main(outline_mm=outline) if outline else R.main()
    except TapirError as e:
        print(f"幅の変更: 置き直せませんでした（{e}）。条件は控えたので、躯体スラブを選んで「配置」で置き直してください")
        return 1
    if guides:
        delete_guides(c, guides)
        print("幅の変更: 目印の線を消しました")
    return 0


if __name__ == "__main__":
    sys.exit(main())
