"""plan.json からArchicadへ足場を再配置する（割付を解き直さない）.

plan.json は「GDL配置・再編集用の機械可読データ」なので、これだけで
配置できなければ意味がない。このスクリプトはその実証と検証を兼ねる:
配置したあとGDLパラメータを読み戻し、JSONの値と一致するか確かめる。

使い方:
  python3 scripts/place_from_plan_json.py out/xxx_plan.json [--keep]
"""

from __future__ import annotations

import base64
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ashiba.tapir_adapter import ArchicadClient, TapirError  # noqa: E402
from dev_gsm_iterate import build_current_gsm  # noqa: E402

# 照合は plan.json が送った全パラメータで行う。対象を手で並べていたときは、
# パラメータを増やすたびに照合対象から漏れ、12個が黙って未検証になっていた


def _same(sent, got) -> bool:
    """送った値と読み戻した値が同じか（数値は誤差、文字列は表記の揺れを吸収）."""
    if got is None:
        return False
    try:
        return abs(float(sent) - float(got)) <= 1e-6
    except (TypeError, ValueError):
        pass
    return str(sent).strip() == str(got).strip()


def _values(resp: dict) -> dict:
    """GetGDLParametersOfElements の応答 → {name: value}."""
    out = {}
    for item in resp.get("gdlParametersOfElements", []):
        for row in item.get("gdlParameters", item.get("parameters", [])):
            out[row.get("name")] = row.get("value")
    return out


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    plan_path = Path(sys.argv[1])
    keep = "--keep" in sys.argv
    data = json.loads(plan_path.read_text(encoding="utf-8"))
    print(f"読込: {plan_path.name} 系列{data['series_id']} "
          f"辺{len(data['edges'])} H{data['scaffold_height_mm']}mm")

    c = ArchicadClient()
    assert c.is_alive(), "Archicadが応答しません"

    work = ROOT / "out" / "gsm_dev"
    work.mkdir(parents=True, exist_ok=True)
    name, gsm = build_current_gsm("ashiba_line", work)
    try:
        c.add_file_to_embedded_library(str(gsm), gsm.name)
    except TapirError:
        pass
    print(f"部品: {name}")

    placed, mismatches = [], []
    checked = 0
    for e in data["edges"]:
        pl, params = e["placement"], e["gdl_params"]
        elem = c.create_object(name, pl["x_mm"], pl["y_mm"])
        placed.append(elem)
        if abs(pl["angle_deg"]) > 1e-9:
            c.rotate_element(
                elem, math.radians(pl["angle_deg"]), pl["x_mm"], pl["y_mm"]
            )
        c.set_gdl_parameters(elem, params)

        got = _values(c.get_gdl_parameters(elem))
        for k, v in params.items():
            if not _same(v, got.get(k)):
                mismatches.append(f"辺{e['edge_index']} {k}: "
                                  f"{v!r} → {got.get(k)!r}")
        checked += len(params)
    print(f"配置: {len(placed)}本 / 照合 {checked}パラメータ"
          f"（1本あたり{checked // max(len(placed), 1)}）")

    out = ROOT / "out" / "replace_check"
    out.mkdir(parents=True, exist_ok=True)
    for img in ("3D", "2D"):
        resp = c.tapir(
            "GetElementPreviewImage",
            {"elementId": placed[0]["elementId"], "imageType": img,
             "width": 900, "height": 900},
        )
        p = out / f"再配置_{img}.png"
        p.write_bytes(base64.b64decode(resp["previewImage"]))
        print(f"プレビュー: {p}")

    if not keep:
        c.delete_elements(placed)
        print(f"テスト要素 {len(placed)}個を削除（--keep で残せます）")

    if mismatches:
        print("\n読み戻しが一致しません:")
        for m in mismatches:
            print("  ", m)
        raise SystemExit(1)
    print("\nplan.json からの再配置 成功（全パラメータ一致）")


if __name__ == "__main__":
    main()
