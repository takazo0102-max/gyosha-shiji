"""工程の模型の足場の高さ（stepH）を部品の 3D スクリプトに入れる共通の決め（利用者の指定 2026-11-04「工程表に合わせて
モデルを自動作成できるようにして」）.

scripts/step_run.py が外部足場の部品に stepH（部品の原点から m）を入れると、その高さより上を 3D に描かない（まだ組み上がって
いない）。0 は全部を描く。ashiba_line・ashiba_sheet は自前で切る（3d.gdl に手で入れた）。そのほかの外部足場の部品は
wrap() で 3D スクリプトの頭に CUTPOLY を、終わりに CUTEND を足す（途中の end で抜ける部品は CUTEND まで届かないが、切りは
スクリプトの終わりで解ける）.

  生成する部品: SCRIPT_3D を wrap(SCRIPT_3D) で書き、パラメータに PARAM（_param の引数）を足す
  手で書いた HSF: python3 scripts/gdl_step.py で 3d.gdl と paramlist.xml に足す（入っていれば何もしない）
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HSF = ROOT / "gdl" / "hsf"
NAME = "stepH"
DESC = "工程の模型の足場の高さ（部品の原点から。この高さより上を 3D に描かない。0＝全部。scripts/step_run.py が入れる）"
PARAM = ("Length", NAME, DESC, 0)
MARK = "! 工程の模型（scripts/gdl_step.py）"
HEAD = (MARK + ": stepH より上はまだ組み上がっていない\n"
        "if stepH > 0.001 then\n"
        "\trotx 90\n"
        "\tcutpoly 4, -1000, stepH, 1000, stepH, 1000, 1000, -1000, 1000\n"
        "\tdel 1\n"
        "endif\n")
TAIL = "if stepH > 0.001 then cutend\n"
# 手で書いた HSF の外部足場の部品（ashiba_line・ashiba_sheet は 3d.gdl に手で入れてある）
HAND_PARTS = ("ashiba_tie", "ashiba_net", "ashiba_netbk", "ashiba_cstep", "ashiba_bridge", "ashiba_stage", "ashiba_member")


def wrap(script: str) -> str:
    """3D スクリプトの頭（BOM と最初のコメントの後）に切りを、終わりに CUTEND を足す. 入っていればそのまま."""
    if MARK in script:
        return script
    bom = "﻿" if script.startswith("﻿") else ""
    body = script[len(bom):]
    lines = body.splitlines(keepends=True)
    k = 0
    while k < len(lines) and lines[k].lstrip().startswith("!"):
        k += 1
    head = "".join(lines[:k])
    rest = "".join(lines[k:])
    if rest and not rest.endswith("\n"):
        rest += "\n"
    return bom + head + HEAD + rest + TAIL


def param_xml() -> str:
    return (f'\t\t<Length Name="{NAME}">\n'
            f"\t\t\t<Description><![CDATA[\"{DESC}\"]]></Description>\n"
            "\t\t\t<Value>0</Value>\n"
            "\t\t</Length>\n")


def add_to_hsf(part: str, hsf: Path = HSF) -> bool:
    """手で書いた HSF に stepH を足す. 足したら True."""
    d = hsf / part
    s3 = d / "scripts" / "3d.gdl"
    pl = d / "paramlist.xml"
    changed = False
    t = s3.read_text(encoding="utf-8")
    w = wrap(t)
    if w != t:
        s3.write_text(w, encoding="utf-8")
        changed = True
    x = pl.read_text(encoding="utf-8")
    if not re.search(rf'Name="{NAME}"', x):
        i = x.rindex("</Parameters>")
        j = x.rindex("\n", 0, i) + 1
        pl.write_text(x[:j] + param_xml() + x[j:], encoding="utf-8")
        changed = True
    return changed


def main() -> int:
    for p in HAND_PARTS:
        print(f"{p}: {'足しました' if add_to_hsf(p) else '入っています'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
