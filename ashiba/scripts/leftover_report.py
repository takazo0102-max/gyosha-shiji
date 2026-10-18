"""足場の断面・レイアウトを工事名ごとに数え、使っていない工事名の残骸を示す（消すのは --remove のときだけ）.

使い方:
  python3 scripts/leftover_report.py                       # 一覧（読むだけ）
  python3 scripts/leftover_report.py --remove "スモーク small_brk"   # その工事名の断面・レイアウトを消す

「使用中」は、足場条件の部品に入っている工事名。断面は控え（Desktop/ashiba_out と out/smoke/*/ の
elevation_sections.json）に GUID があるものだけ消せる（断面と名前の対応は API で取れない）。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ashiba.elevation_sections import (  # noqa: E402
    _tree,
    activate_floor_plan,
    load_record,
    remove_elevations,
    walk_tree,
)
from ashiba.leftovers import group, lines  # noqa: E402
from ashiba.tapir_adapter import ArchicadClient  # noqa: E402


def _records() -> dict[str, str]:
    """控えにある {断面名: GUID}（ツールバーとスモークの分を合わせる）."""
    import run_from_archicad as tb

    rec = dict(load_record(tb.OUT_DIR))
    for d in sorted((ROOT / "out" / "smoke").glob("*")):
        rec.update(load_record(d))
    return rec


def main() -> int:
    args = sys.argv[1:]
    remove = args[args.index("--remove") + 1] if "--remove" in args and args.index("--remove") + 1 < len(args) else None
    c = ArchicadClient()
    import run_from_archicad as tb

    activate_floor_plan(c)
    sections = [i["name"] for i in walk_tree(_tree(c, "ProjectMap")) if i.get("type") == "SectionItem"]
    layouts = [i["name"] for i in walk_tree(_tree(c, "LayoutBook")) if i.get("type") == "LayoutItem"]
    active = [str(p.get("projName") or "") for _e, _o, p in tb.read_spec_objects(c)]
    uses = group(sections, layouts, active)
    if remove is None:
        for line in lines(uses):
            print(line)
        return 0
    target = next((u for u in uses if u.prefix == remove), None)
    if target is None:
        print(f"「{remove}」の断面・レイアウトはありません")
        return 1
    if target.in_use:
        print(f"「{remove}」は足場条件の部品で使用中なので消しません（ツールバーの再実行で置き換わります）")
        return 1
    rec = _records()
    guids = [rec[n] for n in target.sections if n in rec]
    n_sec, n_lay, left = remove_elevations(c, target.sections, target.layouts, guids)
    activate_floor_plan(c)
    print(f"「{remove}」: 断面{n_sec}・レイアウト{n_lay}を消しました")
    if left:
        print("控えの無い断面が残っています（プロジェクトマップで手で消してください）: " + "・".join(left))
    return 0


if __name__ == "__main__":
    sys.exit(main())
