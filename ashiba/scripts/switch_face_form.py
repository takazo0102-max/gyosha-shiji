"""選んだ足場（区切った部品なら、その部品の範囲だけ）を別の種類の足場に切り替える（パレットの「面の切替」）.

利用者の指定（2026-10-24）「面の切り替えはやめて選択した足場の変更に切り替えて」: 区切った部品を選んで押すと、その部品の
範囲（区間）だけを切り替える（face_forms の「南面[10974-16461]=ブラケット足場（支柱）」。面の途中で種類が変わり、切れ目は
開放端）。区切っていない足場ラインを選んだときは面全体。区間を「元に戻す」と、その区間は元の足場に戻る。

利用者の指定（2026-10-22）「面ごとやブロックを違う足場に切り替えれるようコマンド作って」。足場ラインを選んで押すと
種類の一覧（本足場・一側足場・ブラケット足場（支柱・単管）・単管抱き足場・単管本足場・枠組足場・元に戻す）を出し、
選んだ面をその種類にして「配置」を実行し直す。切り替えは足場条件の部品の「面の切替」（faceForms）に書く
（部品が無ければ条件ファイル ashiba_spec.json の face_forms）。

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


def piece_key(face: str, p: dict) -> str:
    """選んだ足場ラインの部品 → 切り替えの面の名前（面全体なら「南面」、区切った部品なら区間つき「南面[a-b]」）.

    区間は元の割付の面の始点の支柱から mm（部品の faceOff＋部品の範囲 pxA〜pxB）。faceLen は元の面の長さ。
    """
    from ashiba.face_forms import range_key
    from ashiba.segments import piece_of, spans_m

    try:
        pc = piece_of(p)
    except ValueError:
        return face
    off = float(p.get("faceOff") or 0.0)
    full = float(p.get("faceLen") or 0.0) or sum(spans_m(p))
    a, b = (off + pc.pxA) * 1000.0, (off + pc.pxB) * 1000.0
    if a < 1.0 and b > full * 1000.0 - 1.0:
        return face
    return range_key(face, a, b)


def main() -> int:
    from explode_line import _params

    c = ArchicadClient()
    sel = c.get_selected_elements()
    picked = []
    for e, d in zip(sel, c.get_details(sel) if sel else []):
        dd = d.get("details") or {}
        if not is_ashiba_part((dd.get("libPart") or {}).get("name", ""), ("ashiba_line",)):
            continue
        o = dd.get("origin") or {}
        picked.append(((float(o.get("x", 0)) * 1000.0, float(o.get("y", 0)) * 1000.0), _params(c, e)))
    if not picked:
        print("面の切替: 切り替える足場ライン（区切った部品ならその範囲だけ）を選んでから押してください")
        return 1
    plans = [json.loads(p.read_text(encoding="utf-8"))
             for p in sorted(OUT_DIR.rglob("*_plan.json"), key=lambda p: -p.stat().st_mtime)]
    plan, faces = None, []
    for origin, p in picked:
        pl, fs = faces_of_lines(plans, [origin])
        if pl is None or not fs:
            continue
        plan = plan or pl
        key = piece_key(fs[0], p)
        if key not in faces:
            faces.append(key)
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
