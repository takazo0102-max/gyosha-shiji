"""実機E2Eテスト: スラブ躯体 → 外形取得 → 割付 → 足場ライン4辺配置 → 検証.

Archicad 28 + Tapir 1.5.8 で実行。配置結果はプロジェクトに残す
（目視確認用。--cleanup で削除）。

使い方:
  python3 scripts/e2e_archicad_test.py --slab <GUID>      # 既存スラブを使う
  python3 scripts/e2e_archicad_test.py                    # スラブも新規作成
"""

from __future__ import annotations

import base64
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ashiba.elevation_solver import solve_elevation  # noqa: E402
from ashiba.law_check import run_all_checks, summary  # noqa: E402
from ashiba.master import load_master  # noqa: E402
from ashiba.model import ScaffoldConfig, ScaffoldModel  # noqa: E402
from ashiba.plan_solver import solve_plan  # noqa: E402
from ashiba.quantity import take_off  # noqa: E402
from ashiba.tapir_adapter import (  # noqa: E402
    ArchicadClient,
    _extract_polygon,
    place_scaffold_lines,
)

OBJECT_NAME = "ashiba_line_v2"   # 検証済みGSMの部品名
SLAB_POLY_MM = [(200000, 200000), (230000, 200000), (230000, 220000), (200000, 220000)]


def main() -> None:
    slab_guid = None
    if "--slab" in sys.argv:
        slab_guid = sys.argv[sys.argv.index("--slab") + 1]

    c = ArchicadClient()
    assert c.is_alive(), "Archicadが応答しません"
    print(f"Tapir {c.tapir_version()} 接続OK")

    # 1. 躯体スラブ
    if slab_guid:
        slab = {"elementId": {"guid": slab_guid}}
    else:
        slab = c.create_slab(SLAB_POLY_MM)
        print(f"スラブ作成: {slab['elementId']['guid']}")

    # 2. 外形取得
    det = c.get_details([slab])[0]
    poly = _extract_polygon(det)
    assert poly, f"外形が取れません: {det.get('type')}"
    outline_mm = [(x * 1000.0, y * 1000.0) for (x, y) in poly]
    print(f"外形取得: {len(outline_mm)}点")

    # 3. 割付
    master = load_master("shinwa_A")
    plan = solve_plan(outline_mm, master)
    elevation = solve_elevation(16300, master=master)
    model = ScaffoldModel(
        master=master, plan=plan, elevation=elevation,
        config=ScaffoldConfig(period_days=90), building_height_mm=16000,
    )
    checks = summary(run_all_checks(model))
    q = take_off(model)
    print(f"割付OK: 支柱位置{plan.total_posts}/層, 層数{elevation.n_levels}, "
          f"法規 {checks}, 総重量{q.total_weight_kg}kg")

    # 4. 配置
    placed = place_scaffold_lines(model, OBJECT_NAME, c)
    print(f"足場ライン {len(placed)}本 配置")

    # 5. 検証: 角度・パラメータ
    details = c.get_details(placed)
    ok = True
    for ep, edge, d in zip(model.plan.edges, model.plan.outline.edges, details):
        want = math.atan2(edge.direction[1], edge.direction[0]) % (2 * math.pi)
        got = float(d["details"].get("angle", 0.0)) % (2 * math.pi)
        good = abs(want - got) < 1e-6 or abs(abs(want - got) - 2 * math.pi) < 1e-6
        ok = ok and good
        print(f"  辺{ep.edge_index}: 角度 {math.degrees(got):6.1f}° "
              f"(期待 {math.degrees(want):6.1f}°) {'OK' if good else 'NG'} "
              f"スパン{len(ep.spans)} 離れ{ep.standoff:.0f}")

    # 6. 目視用プレビュー保存
    out = ROOT / "out" / "e2e"
    out.mkdir(parents=True, exist_ok=True)
    for i, elem in enumerate(placed[:2]):
        for img_type in ("3D", "2D"):
            resp = c.tapir(
                "GetElementPreviewImage",
                {"elementId": elem["elementId"], "imageType": img_type,
                 "width": 700, "height": 700},
            )
            p = out / f"edge{i}_{img_type}.png"
            p.write_bytes(base64.b64decode(resp["previewImage"]))
            print(f"  保存: {p}")

    if "--cleanup" in sys.argv:
        c.delete_elements(placed + ([slab] if not slab_guid else []))
        print("テスト要素を削除")

    print("E2E " + ("成功" if ok else "失敗（角度不一致あり）"))
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
