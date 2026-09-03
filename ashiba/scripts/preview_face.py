"""サンプルの指定面を実機に置いて、平面／立面／3Dの大判プレビューを保存する.

GetElementPreviewImage は固定縮尺で描くので、既定の900pxでは立面の下部しか
映らない。4000pxで取ると全層の壁つなぎ・付帯設備まで目視できる
（壁つなぎの上層が消えていた255文字切れは、これで確認した）。

使い方:
  python3 scripts/preview_face.py <example> <edge_index> [plan,elev,3d] [--size 4000x3000]
出力: out/view_check/<example>_辺<n>_<view>.png
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ashiba.cli import load_spec, solve_all  # noqa: E402
from ashiba.gdl_params import line_params  # noqa: E402
from ashiba.tapir_adapter import ArchicadClient, TapirError  # noqa: E402
from dev_gsm_iterate import build_current_gsm  # noqa: E402


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__)
        return 2
    ex, edge = args[0], int(args[1])
    views = (args[2] if len(args) > 2 else "plan,elev,3d").split(",")
    size = "4000x3000"
    for a in sys.argv[1:]:
        if a.startswith("--size"):
            size = a.split("=", 1)[1] if "=" in a else sys.argv[sys.argv.index(a) + 1]
    width, height = (int(v) for v in size.lower().split("x"))

    c = ArchicadClient()
    name, gsm = build_current_gsm("ashiba_line", ROOT / "out" / "gsm_dev")
    try:
        c.add_file_to_embedded_library(str(gsm), gsm.name)
    except TapirError:
        pass    # 同じ内容の部品が既にある
    r = solve_all(load_spec(ROOT / "examples" / f"{ex}.json"))
    ep = next(e for e in r.model.plan.edges if e.edge_index == edge)
    base = line_params(
        r.model, ep, stair_plan=r.stair_plan, openings=r.openings,
        platforms=r.platforms, bracket_sections=r.brackets,
    )
    out = ROOT / "out" / "view_check"
    out.mkdir(parents=True, exist_ok=True)
    placed: list[dict] = []
    try:
        for v in views:
            el = c.create_object(name, 0, -60000 if v == "elev" else 0)
            placed.append(el)
            c.set_gdl_parameters(
                el, {**base, "viewMode": "elev" if v == "elev" else "plan",
                     "faceName": f"辺{edge}"}, name,
            )
            resp = c.tapir(
                "GetElementPreviewImage",
                {"elementId": el["elementId"], "imageType": "3D" if v == "3d" else "2D",
                 "width": width, "height": height},
            )
            p = out / f"{ex}_辺{edge}_{v}.png"
            p.write_bytes(base64.b64decode(resp["previewImage"]))
            print("保存:", p.relative_to(ROOT))
    finally:
        if placed:
            c.delete_elements(placed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
