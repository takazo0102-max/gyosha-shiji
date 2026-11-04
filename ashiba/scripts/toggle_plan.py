"""足場の平面の表現を切り替える（パレットのボタン「平面表示」）.

利用者の指定（2026-10-23）: 平面も詳細モード機能追加して。押すたびに、プロジェクトにある足場ラインの平面を
詳細 → 精細（実寸）→ 単線 → 詳細 … と切り替える。
- 詳細: 建地列・支柱・床の対角線・壁つなぎ・付帯設備・寸法（提出図用。従来の平面）
- 精細（実寸）: 支柱・コマ・布材・腕木を太さどおり、踏板を幅どおり、幅木（詳細図・納まり用）
- 単線: 建地列と支柱位置・床の対角線だけ（割付検討用）
モデル表示オプション（ashiba_mvo）の「平面の表現」が「部品の設定に従う（詳細）」（既定）ならこの切替が効く。
単線・精細を指定していればそちらが優先。

使い方:
  python3 scripts/toggle_plan.py            # 次の段階へ
  python3 scripts/toggle_plan.py 精細        # 段階を指定（詳細／精細／単線）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ashiba.tapir_adapter import ArchicadClient, is_ashiba_part  # noqa: E402

# (名前, planSimple, planReal)
STEPS = (("詳細", False, False), ("精細", False, True), ("単線", True, False))


def current_step(params: dict) -> str:
    if params.get("planSimple"):
        return "単線"
    return "精細" if params.get("planReal") else "詳細"


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


def next_step(current: str) -> tuple[str, bool, bool]:
    names = [s[0] for s in STEPS]
    i = names.index(current) if current in names else 0
    return STEPS[(i + 1) % len(STEPS)]


def main() -> int:
    want = next((a for a in sys.argv[1:] if not a.startswith("--")), None)
    c = ArchicadClient()
    objs = c.tapir("GetElementsByType", {"elementType": "Object"}).get("elements", [])
    lines = []
    for e, d in zip(objs, c.get_details(objs) if objs else []):
        lp = (d.get("details", {}).get("libPart") or {})
        name = lp.get("name", "") if isinstance(lp, dict) else ""
        if is_ashiba_part(name, ("ashiba_line",)):
            lines.append(e)
    if not lines:
        print("足場ラインがありません（先にツールバーで配置してください）")
        return 1
    lines, _a, where = _scope(c, lines, [])
    if want:
        step = next((s for s in STEPS if s[0] == want.replace("（実寸）", "")), None)
        if step is None:
            print(f"段階が分かりません: {want}（{'／'.join(s[0] for s in STEPS)}）")
            return 2
    else:
        # 今の状態は値を持つ部品の多い方（最初の1本が古い版で値を持たないと、いつも「精細」に進んで切り替わらなかった）
        names = [current_step({k: bool(float(v[k] or 0)) for k in v}) for v in _values(c, lines, ("planSimple", "planReal"))
                 if "planReal" in v or "planSimple" in v]
        step = next_step(max(set(names), key=names.count) if names else "詳細")
    label, simple, real = step
    n = c.set_gdl_parameters_many([(e, {"planSimple": simple, "planReal": real}) for e in lines])
    print(f"足場の平面表示: {label}{'（実寸）' if real else ''}（{where}: 足場ライン {n}本）")
    print("モデル表示オプションの「平面の表現」で単線・精細を指定していればそちらが優先です")
    return 0


if __name__ == "__main__":
    sys.exit(main())
