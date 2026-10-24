"""選んだ足場の面（区切った部品・複数の面＝ブロックでもよい）を別の種類の足場に切り替える（パレットの「面の切替」）.

利用者の指定（2026-10-24）「足場の切り替えも線の位置で変更できるようにして」: 平面で、切り替えたい面に沿って線（ポリライン
なら角を回って何面でも）を引き、その線を選んで押してもよい。線が沿う面を切り替える（面の一部に引いても面全体。目印の線は消す）。
以前の指定（2026-10-22）「面ごとやブロックを違う足場に切り替えれるようコマンド作って」。足場ラインを選んで押すと
種類の一覧（本足場・一側足場・ブラケット足場（支柱・単管）・単管抱き足場・単管本足場・枠組足場・元に戻す）を出し、
選んだ面をその種類にして「配置」を実行し直す。切り替えは足場条件の部品の「面の切替」（faceForms）に書く
（部品が無ければ条件ファイル ashiba_spec.json の face_forms）。区切った部品を選んだときは、その面全体を切り替える。

使い方（Archicad で足場ラインを選んでから）:
  python3 scripts/switch_face_form.py                     # 一覧から種類を選ぶ
  ASHIBA_FACE_FORM=単管抱き足場 python3 scripts/switch_face_form.py   # 一覧を出さずに（試験用）
  --no-apply で書くだけ（配置し直さない）。ASHIBA_OUT で配置の控え（plan.json）の場所、ASHIBA_SPEC で条件ファイル
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

from ashiba.face_forms import FACE_FORMS, RESET, faces_of_lines, format_face_forms, updated_face_forms  # noqa: E402
from ashiba.tapir_adapter import ArchicadClient, is_ashiba_part  # noqa: E402

OUT_DIR = Path(os.environ.get("ASHIBA_OUT") or (Path.home() / "Desktop" / "ashiba_out"))
SPEC_DEFAULT = Path(os.environ.get("ASHIBA_SPEC") or (Path.home() / "Desktop" / "ashiba_spec.json"))


def _choose(faces: list[str]) -> str | None:
    env = os.environ.get("ASHIBA_FACE_FORM")
    if env:
        return env
    items = list(FACE_FORMS) + [RESET]
    q = lambda t: '"' + t.replace("\\", "\\\\").replace('"', '\\"') + '"'
    script = ("choose from list {" + ", ".join(q(t) for t in items) + "} with title " + q("面の切替")
              + " with prompt " + q("・".join(faces) + " を切り替える足場の種類") + " OK button name " + q("切替")
              + " cancel button name " + q("やめる"))
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
    from guide_lines import building_plan, delete_guides, not_in_plan_hint, selected_guides

    guides = [] if origins else selected_guides(c)
    if guides:
        from ashiba.plan_pick import along

        plan = building_plan([p for _e, segs in guides for seg in segs for p in seg])
        faces = []
        for _e, segs in guides:
            for a, b in segs:
                hit = along((plan or {}).get("edges") or [], a, b)
                if hit is not None:
                    name = str(hit[0].get("face") or f"辺{hit[0]['edge_index']}")
                    if name not in faces:
                        faces.append(name)
        if plan is not None and not faces:
            print("面の切替: 足場に沿った線が見つかりません。切り替えたい面に沿って線を引いてください")
            return 1
    elif not origins:
        print("面の切替: 平面で、切り替えたい面に沿って線を引いて選ぶか、足場ライン（区切った部品でもよい）を選んでから"
              "押してください" + not_in_plan_hint(c))
        return 1
    else:
        plans = [json.loads(p.read_text(encoding="utf-8"))
                 for p in sorted(OUT_DIR.rglob("*_plan.json"), key=lambda p: -p.stat().st_mtime)]
        plan, faces = faces_of_lines(plans, origins)
    if plan is None or not faces:
        print(f"面の切替: 選んだ足場の配置の控え（plan.json）が {OUT_DIR} にありません。先に「配置」してください")
        return 1
    form = _choose(faces)
    if not form:
        print("面の切替: やめました")
        return 0
    import run_from_archicad as tb
    from ashiba.spec_object import pick_spec_object

    outline = plan.get("outline_mm") or []
    hit = None
    try:
        hit = pick_spec_object(tb.read_spec_objects(c), outline)
    except Exception:          # 部品が読めなくても JSON に書けば切り替えは通る
        hit = None
    if hit is not None and hit[1]:
        cur = str((hit[1] or {}).get("faceForms") or "")
        ff = updated_face_forms(cur, faces, form)
        c.set_gdl_parameters(hit[0], {"faceForms": format_face_forms(ff)})
        where = "足場条件の部品「面の切替」"
    else:
        spec = json.loads(SPEC_DEFAULT.read_text(encoding="utf-8")) if SPEC_DEFAULT.exists() else {}
        ff = updated_face_forms(spec.get("face_forms"), faces, form)
        if ff:
            spec["face_forms"] = ff
        else:
            spec.pop("face_forms", None)
        SPEC_DEFAULT.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        where = str(SPEC_DEFAULT)
    print(f"面の切替: {'・'.join(faces)} → {form}（{where}）。いまの切り替え: {format_face_forms(ff) or 'なし'}")
    if "--no-apply" in sys.argv:
        return 0
    if not outline:
        print("面の切替: plan.json に躯体外形がありません。スラブを選んで「配置」してください")
        return 1
    os.environ["ASHIBA_SPEC"] = str(SPEC_DEFAULT)
    print("---- 配置し直します")
    tb.main(outline_mm=outline, out_dir=OUT_DIR)
    if guides:
        delete_guides(c, guides)
        print("面の切替: 目印の線を消しました")
    return 0


if __name__ == "__main__":
    sys.exit(main())
