"""実機E2Eテスト: スラブ躯体 → 外形取得 → 割付 → 足場ライン4辺配置 → 検証.

Archicad 28 + Tapir 1.5.8 で実行。配置結果はプロジェクトに残す
（目視確認用。--cleanup で削除）。

使い方:
  python3 scripts/e2e_archicad_test.py --slab <GUID>      # 既存スラブを使う
  python3 scripts/e2e_archicad_test.py                    # スラブも新規作成
  python3 scripts/e2e_archicad_test.py --series=nikken_nd1900   # 系列を指定（既定 shinwa_A）
"""

from __future__ import annotations

import base64
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import json  # noqa: E402

from ashiba.cli import solve_all  # noqa: E402
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

    # 3. 割付（CLI・ツールバー・全機能E2Eと同じ solve_all で解く。手順を写すと
    #    solve_all に足した処理が抜けて検定結果がズレる）
    series = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--series=")), "shinwa_A")
    print(f"系列 {series}")
    spec = json.loads((ROOT / "examples" / "rect_30x20.json").read_text(encoding="utf-8"))
    spec.update({
        "project_name": "E2E基本", "series_id": series,
        "outline_mm": [[x, y] for (x, y) in outline_mm], "period_days": 90,
    })
    r = solve_all(spec)
    model, plan, elevation = r.model, r.model.plan, r.model.elevation
    checks = {k: sum(1 for c in r.checks if c.status == st) for k, st in (("ok", "OK"), ("warn", "WARN"), ("ng", "NG"))}
    print(f"割付OK: 支柱位置{plan.total_posts}/層, 層数{elevation.n_levels}, "
          f"法規 {checks}, 総重量{r.quantity.total_weight_kg}kg, 判定 {'成立' if r.verdict['ok'] else '是正'}")

    # 4. 配置（現行HSFをコンパイルして埋め込みライブラリへ。部品名は内容ハッシュ。
    #    以前は検証済みGSMの固定名 ashiba_line_v2 を前提にしていて、
    #    その部品を読み込んでいないプロジェクトでは「Not found library part」で止まった）
    object_name = OBJECT_NAME
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        from dev_gsm_iterate import build_current_gsm

        work = ROOT / "out" / "gsm_dev"
        work.mkdir(parents=True, exist_ok=True)
        object_name, gsm = build_current_gsm("ashiba_line", work)
        try:
            c.add_file_to_embedded_library(str(gsm), gsm.name)
        except Exception:
            pass   # 同じ内容なら既に入っている
        print(f"部品: {object_name}（現行HSF）")
    except Exception as e:   # コンパイル環境が無ければ固定名で試す
        print(f"現行HSFの注入に失敗（{e}）。部品名 {OBJECT_NAME} で配置します")
    placed = place_scaffold_lines(model, object_name, c, stair_plan=r.stair_plan,
                                  platforms=r.platforms, terrain=r.terrain)
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
