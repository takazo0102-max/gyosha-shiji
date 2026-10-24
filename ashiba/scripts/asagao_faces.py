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
        new = updated_asagao_faces(str((hit[1] or {}).get("asagaoFaces") or ""), every, faces, mode)
        c.set_gdl_parameters(hit[0], {"asagaoFaces": new})
        where = "足場条件の部品「朝顔を付ける面」"
    else:
        spec = json.loads(SPEC_DEFAULT.read_text(encoding="utf-8")) if SPEC_DEFAULT.exists() else {}
        asg = spec.get("asagao") if isinstance(spec.get("asagao"), dict) else {}
        new = updated_asagao_faces(asg.get("faces") or "", every, faces, mode)
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
    os.environ["ASHIBA_SPEC"] = str(SPEC_DEFAULT)
    print("---- 配置し直します")
    tb.main(outline_mm=outline, out_dir=OUT_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
