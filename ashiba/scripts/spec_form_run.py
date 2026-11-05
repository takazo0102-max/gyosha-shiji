"""この建物の足場の条件を窓で変える（パレットのボタン「条件」）.

利用者の指定（2026-10-24）「条件の部分がどうやるのかわからない」。以前は足場条件の部品を選ぶだけで、設定ダイアログ（⌘T）
を開くのは利用者の手だった。押すと条件の窓が前に出て、足場の種類・系列・幅・手すり・階段・朝顔・養生・高さ・立面断面を
選べる。「保存して配置」で置き直し、「保存」は足場条件の部品に控えるだけ（次の配置で使う）。
建物は選んでいる躯体スラブ（無ければ最後に配置した建物）。足場条件の部品がまだ無ければ建物の左下に置く。
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

from ashiba.tapir_adapter import ArchicadClient, TapirError, get_selected_outline_mm  # noqa: E402

OUT_DIR = Path(os.environ.get("ASHIBA_OUT") or (Path.home() / "ashiba_out"))  # 試験は ASHIBA_OUT で別の場所に


def _outline(c: ArchicadClient):
    try:
        return [list(p) for p in get_selected_outline_mm(c)], True
    except (TapirError, ValueError, KeyError, IndexError):
        pass
    plans = sorted(OUT_DIR.glob("*_plan.json"), key=lambda p: p.stat().st_mtime)
    if plans:
        return json.loads(plans[-1].read_text(encoding="utf-8")).get("outline_mm"), False
    return None, False


def _slab_guid(c: ArchicadClient, outline) -> str:
    """外形に合う躯体スラブの GUID（配置に渡す）。見つからなければ空."""
    xs = [float(p[0]) for p in outline]
    ys = [float(p[1]) for p in outline]
    try:
        els = c.tapir("GetElementsByType", {"elementType": "Slab"}).get("elements", [])
        for e, d in zip(els, c.get_details(els) if els else []):
            pts = (d.get("details") or {}).get("polygonOutline") or []
            if not pts:
                continue
            sx = [p["x"] * 1000.0 for p in pts]
            sy = [p["y"] * 1000.0 for p in pts]
            if (abs(min(sx) - min(xs)) < 50 and abs(max(sx) - max(xs)) < 50
                    and abs(min(sy) - min(ys)) < 50 and abs(max(sy) - max(ys)) < 50):
                return str(e["elementId"]["guid"])
    except TapirError:
        pass
    return ""


def main() -> int:
    import run_from_archicad as R
    from ashiba.elevation_sections import activate_floor_plan

    c = ArchicadClient()
    activate_floor_plan(c)
    outline, selected = _outline(c)
    if not outline:
        print("建物が分かりません。躯体スラブを選んでから押してください")
        return 1
    spec = dict(R.SPEC)
    spec.update(R.load_spec_override())
    spec["outline_mm"] = outline
    R.ensure_parts(c)                            # 新しい版の足場条件の部品（項目が増えた）を入れておく
    spec = R.apply_spec_object(c, spec)          # 部品があれば読む。無ければ今の条件で置く
    _new, button, _asked = R.ask_conditions(c, spec, ("place", "保存して配置"), (("save", "保存"),))
    if not button:
        print("条件: やめました（何も変えていません）")
        return 0
    if button != "place":
        print("条件: 保存しました。「配置」を押すと、この条件で置き直します")
        return 0
    env = dict(os.environ, PYTHONIOENCODING="utf-8", ASHIBA_ASK_SPEC="0")
    if not selected:
        guid = _slab_guid(c, outline)
        if not guid:
            print("条件: 保存しました。躯体スラブが見つからないので、スラブを選んで「配置」を押してください")
            return 0
        env["ASHIBA_SLAB"] = guid[:8]
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "run_from_archicad.py")], cwd=ROOT,
                          capture_output=True, text=True, env=env)
    sys.stdout.write(proc.stdout or "")
    sys.stdout.write(proc.stderr or "")
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
