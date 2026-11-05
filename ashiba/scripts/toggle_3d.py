"""足場の3Dの細かさを切り替える（パレットのボタン「3D表示」）.

利用者の指摘（2026-10-19・10-20）: 足場が重くて使いづらい。押すたびに、プロジェクトにある足場ライン・
壁つなぎ・水平ネット・ネットブラケットの3Dを 自動 → 軽量 → 線 → ブロック → 精細 → 自動 … と切り替える
（足場ラインの detail3d、付属の部品は lineMode）。部材の位置・本数は変わらない（数量も同じ）。
ブロックは部材を描かずスパン×層の半透明の箱で足場の占める空間を出す（参考: smartCON Planner の3D「ブロック」。
躯体・庇・隣地との取り合いを見るとき。付属の部品は線にする）。

使い方:
  python3 scripts/toggle_3d.py            # 次の段階へ
  python3 scripts/toggle_3d.py 軽量        # 段階を指定（自動／精細／軽量／線／ブロック）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ashiba.tapir_adapter import ArchicadClient, is_ashiba_part  # noqa: E402

# detail3d: 0=自動 1=精細 2=軽量 3=線 4=ブロック（3d.gdl と同じ）
STEPS = ((0, "自動"), (2, "軽量"), (3, "線"), (4, "ブロック"), (1, "精細"))
ATTACH = ("ashiba_tie", "ashiba_net", "ashiba_netbk", "ashiba_sheet")


def _scope(c, lines, attach):
    """足場（足場ライン・付属の部品）を選んでいればそれだけ、選んでいなければ全部（利用者の指定 2026-11-05「使いやすいように」:
    1本を選んで押しても見本を含むプロジェクトの全部が変わっていた）. → (lines, attach, 説明)."""
    try:
        sel = {e["elementId"]["guid"].upper() for e in c.get_selected_elements()}
    except Exception:
        sel = set()
    sl = [e for e in lines if e["elementId"]["guid"].upper() in sel]
    sa = [e for e in attach if e["elementId"]["guid"].upper() in sel]
    if sl or sa:
        return sl, sa, "選んだ足場"
    return lines, attach, "プロジェクトの全部の足場"


def _values(c, els, names) -> list[dict]:
    """部品ごとの値 {name: value}（持っていない部品は空）. 200個ずつ読む."""
    out = []
    for i in range(0, len(els), 200):
        resp = c.tapir("GetGDLParametersOfElements", {"elements": els[i:i + 200]})
        for item in resp.get("gdlParametersOfElements", []):
            out.append({row.get("name"): row.get("value") for row in item.get("gdlParameters", item.get("parameters", []))
                        if row.get("name") in names})
    return out


def next_step(current: int) -> tuple[int, str]:
    codes = [c for c, _ in STEPS]
    i = codes.index(current) if current in codes else 0
    return STEPS[(i + 1) % len(STEPS)]


def main() -> int:
    want = next((a for a in sys.argv[1:] if not a.startswith("--")), None)
    c = ArchicadClient()
    objs = c.tapir("GetElementsByType", {"elementType": "Object"}).get("elements", [])
    lines, attach = [], []
    for e, d in zip(objs, c.get_details(objs) if objs else []):
        lp = (d.get("details", {}).get("libPart") or {})
        name = lp.get("name", "") if isinstance(lp, dict) else ""
        if is_ashiba_part(name, ("ashiba_line",)):
            lines.append(e)
        elif is_ashiba_part(name, ATTACH):
            attach.append(e)
    if not lines:
        print("足場ラインがありません（先にツールバーで配置してください）")
        return 1
    lines, attach, where = _scope(c, lines, attach)
    if want:
        step = next(((c_, n) for c_, n in STEPS if n == want), None)
        if step is None:
            print(f"段階が分かりません: {want}（{'／'.join(n for _, n in STEPS)}）")
            return 2
    else:
        # 今の状態は値を持つ部品の多い方（最初の1本が古い版で値を持たないと、いつも同じ段に進んだ）
        vals = [int(round(float(v["detail3d"] or 0))) for v in _values(c, lines, ("detail3d",)) if "detail3d" in v]
        cur = max(set(vals), key=vals.count) if vals else 0
        step = next_step(cur)
    code, label = step
    n = c.set_gdl_parameters_many([(e, {"detail3d": code}) for e in lines])
    m = c.set_gdl_parameters_many([(e, {"lineMode": code in (3, 4)}) for e in attach]) if attach else 0
    print(f"足場部品 3D表示: {label}（{where}: 足場ライン {n}本・壁つなぎ／ネット類 {m}個）")
    print("自動は面の大きさで精細と軽量を選びます。モデル表示オプションの「足場の3D」を指定していればそちらが優先です")
    return 0


if __name__ == "__main__":
    sys.exit(main())
