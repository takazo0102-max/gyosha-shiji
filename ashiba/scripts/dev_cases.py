"""実機検証用の建物（セットバック・上の階の張り出し・鉄骨）をスラブで作り、置いて、片付ける.

利用者の指定（2026-10-24）「先ほどループでしたものを実機で試して」。利用者の建物から離れた所（--at）に、階ごとのスラブで
建物を作る。作ったスラブの GUID は ashiba_out/dev_cases.json に控え、clear で消す（足場は remove_from_archicad で）。

  python3 scripts/dev_cases.py create setback  [--at -60000,-82000]   # 1〜3階 24×10m、4〜6階は南を 3m 下げる
  python3 scripts/dev_cases.py create overhang [--at -20000,-82000]   # 1階 24×10m、2〜4階は南へ 2m 張り出す
  python3 scripts/dev_cases.py create sidebridge --at x,y              # 1〜2階 6×5m、3〜4階は西へ 1m 張り出す（張り出しの
                                                                        # 横の面の隅を拡幅・張出ブラケットで繋ぐ形の確認）
  python3 scripts/dev_cases.py create slope --at x,y                   # 12×8m・3階（軒 9m）と、建物を囲む斜面の敷地メッシュ
                                                                        # （西が高く東へ 1.5m 下がる。南は境界が近い）。メッシュの
                                                                        # 外形を敷地境界にする・足元の勾配の確認
  python3 scripts/dev_cases.py create box --at x,y                     # 12×8m・3階（軒 9m）の平らな建物（枠組・昇降機などの確認）
  python3 scripts/dev_cases.py create ell --at x,y                     # L 字 16×12m・3階（軒 9m）（一側足場の隅・面の組の隅の確認）
  python3 scripts/dev_cases.py place <名前>                           # その建物の足場を置く（条件の窓なし）
  python3 scripts/dev_cases.py clear [<名前>]                          # 足場と作ったスラブを消す
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ashiba.tapir_adapter import ArchicadClient  # noqa: E402

REC = Path.home() / "Desktop" / "ashiba_out" / "dev_cases.json"
DEFAULT_AT = {"setback": (-60000.0, -82000.0), "overhang": (-20000.0, -82000.0)}


def _rect(ox, oy, x0, y0, x1, y1):
    return [(ox + x0, oy + y0), (ox + x1, oy + y0), (ox + x1, oy + y1), (ox + x0, oy + y1)]


def floors(kind: str, ox: float, oy: float) -> list[tuple[list, float]]:
    """[(外形, 天端 mm)]。先頭が地面の床（選ぶスラブ）."""
    if kind == "setback":
        low = _rect(ox, oy, 0, 0, 24000, 10000)
        up = _rect(ox, oy, 0, 3000, 24000, 10000)
        return [(low, 0.0)] + [(low, h) for h in (3000.0, 6000.0, 9000.0)] + [(up, h) for h in (12000.0, 15000.0, 18000.0)]
    if kind == "overhang":
        low = _rect(ox, oy, 0, 0, 24000, 10000)
        big = _rect(ox, oy, 0, -2000, 24000, 10000)
        return [(low, 0.0)] + [(big, h) for h in (3000.0, 6000.0, 9000.0, 12000.0)]
    if kind in ("slope", "box"):
        low = _rect(ox, oy, 0, 0, 12000, 8000)
        return [(low, 0.0)] + [(low, h) for h in (3000.0, 6000.0, 9000.0)]
    if kind == "ell":
        # L 字（南 16m・東 6m 入って北 6m）。インチの一側足場の隅の隙間・面の組の隅の確認（2026-10-26 のループ）
        el = [(ox, oy), (ox + 16000, oy), (ox + 16000, oy + 6000), (ox + 8000, oy + 6000), (ox + 8000, oy + 12000),
              (ox, oy + 12000)]
        return [(el, 0.0)] + [(el, h) for h in (3000.0, 6000.0, 9000.0)]
    if kind == "sidebridge":
        low = _rect(ox, oy, 0, 0, 6000, 5000)
        big = _rect(ox, oy, -1000, 0, 6000, 5000)
        return [(low, 0.0), (low, 3000.0)] + [(big, h) for h in (6000.0, 9000.0)]
    raise SystemExit(f"形が分かりません: {kind}（setback / overhang / sidebridge / slope / box / ell）")


# 斜面の見本の敷地メッシュ（建物の外形から 西 4m・東 4m・北 3m・南 1.3m。西の端が GL±0、東の端が −1.5m）
SLOPE_SITE = (-4000.0, -1300.0, 16000.0, 11000.0)
SLOPE_DROP_MM = 1500.0


def slope_mesh(ox: float, oy: float) -> dict:
    """斜面の見本の敷地メッシュ（Tapir CreateMeshes の meshesData の1件。m）."""
    x0, y0, x1, y1 = SLOPE_SITE

    def z(x):
        return -SLOPE_DROP_MM * (x - x0) / (x1 - x0) / 1000.0

    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return {"level": 0.0, "polygonCoordinates": [{"x": (ox + x) / 1000.0, "y": (oy + y) / 1000.0, "z": z(x)} for x, y in pts]}


def load() -> dict:
    return json.loads(REC.read_text(encoding="utf-8")) if REC.exists() else {}


def save(d: dict) -> None:
    REC.parent.mkdir(parents=True, exist_ok=True)
    REC.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 2
    c = ArchicadClient()
    rec = load()
    if a[0] == "create":
        kind = a[1]
        at = next((x.split("=", 1)[1] if "=" in x else a[i + 1] for i, x in enumerate(a) if x.startswith("--at")), None)
        ox, oy = (float(v) for v in at.split(",")) if at else DEFAULT_AT[kind]
        guids = []
        for poly, top in floors(kind, ox, oy):
            el = c.create_slab(poly, level=top / 1000.0, thickness=0.2)
            guids.append(el["elementId"]["guid"])
        if kind == "slope":
            res = c.tapir("CreateMeshes", {"meshesData": [slope_mesh(ox, oy)]}).get("elements", [])
            if res and "elementId" in res[0]:
                guids.append(res[0]["elementId"]["guid"])
            else:
                print(f"slope: 敷地メッシュを作れませんでした（{res}）")
        rec[kind] = {"guids": guids, "outline_mm": [list(p) for p in floors(kind, ox, oy)[0][0]]}
        save(rec)
        print(f"{kind}: スラブ・メッシュ {len(guids)}個を作りました（地面の床 {guids[0][:8]}）")
        return 0
    if a[0] == "place":
        kind = a[1]
        import run_from_archicad as R

        os.environ["ASHIBA_ASK_SPEC"] = "0"
        # 足場条件の部品は条件ファイルより優先されるので、試験の条件（ASHIBA_DEV_SPEC）を効かせるため先に消す
        from ashiba.spec_object import pick_spec_object

        hit = pick_spec_object(R.read_spec_objects(c), rec[kind]["outline_mm"], reach_mm=12000.0)
        if hit is not None:
            c.delete_elements([hit[0]])
        # 窓を出さない（幅の選択の窓も。利用者の画面に出て止まった）。条件は条件の上書き＋ここで足す値
        extra = json.loads(os.environ.get("ASHIBA_DEV_SPEC") or "{}")
        R.main(outline_mm=rec[kind]["outline_mm"],
               spec_override={**R.load_spec_override(), "scaffold_width_mm": 914, "stairs": {"layout": "自動"},
                              # 利用者の建物と工事名を分ける（帳票の控え・図面のレイアウトを上書きしない）
                              "project_name": f"検証_{kind}", **extra})
        return 0
    if a[0] == "clear":
        kinds = [a[1]] if len(a) > 1 else list(rec)
        for kind in kinds:
            r = rec.pop(kind, None)
            if not r:
                continue
            objs = c.objects_for_slab(r["outline_mm"], ("ashiba_line", "ashiba_detail", "ashiba_tie", "ashiba_net",
                                                        "ashiba_netbk", "ashiba_sheet", "ashiba_cstep", "ashiba_bridge", "ashiba_stage", "ashiba_kbrk",
                                                        "ashiba_spec"), margin_mm=6000.0)
            # 足場条件の部品は建物の左下の外（9m 下）に置くので、外形の範囲では拾えない。この建物の部品を選んで消す
            import run_from_archicad as R
            from ashiba.spec_object import pick_spec_object

            hit = pick_spec_object(R.read_spec_objects(c), r["outline_mm"], reach_mm=12000.0)
            if hit is not None:
                objs.append(hit[0])
            els = objs + [{"elementId": {"guid": g}} for g in r["guids"]]
            if els:
                c.delete_elements(els)
            print(f"{kind}: 足場の部品 {len(objs)}個とスラブ {len(r['guids'])}枚を消しました")
        save(rec)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
