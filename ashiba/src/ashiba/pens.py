"""図面のペン（利用者の指定 2026-10-24: ペンカラーを選べるコマンド作って）.

足場の部品は区分ごとのペン（GDL の PenColor パラメータ）で平面・立面を描く。パレットの「ペン」で区分ごとに選び、
置いてある部品をその場で書き換え、足場条件の部品の penList に控えて次の配置でも使う。0・未指定は 1（従来の見え方）。
"""

from __future__ import annotations

from typing import Optional

# (キー, GDL のパラメータ名, 窓の表示名, 中身)
PEN_KEYS = (
    ("post", "penPost", "支柱", "支柱（コマ・コーナーの建地も）"),
    ("line", "penLine", "足場の線", "建地列・布材・手すり・根がらみ"),
    ("deck", "penDeck", "床", "床の対角線・踏板・コーナーステップ"),
    ("stair", "penStair", "階段", "階段室"),
    ("equip", "penEquip", "付帯設備", "荷受けステージ・昇降機・朝顔・ブラケット・梁枠"),
    ("tie", "penTie", "壁つなぎ", "壁つなぎ（▼。立面は ◎）"),
    ("net", "penNet", "層間ネット", "層間ネット・ネットブラケット"),
    ("sheet", "penSheet", "養生", "養生シート・防音パネル"),
    ("dim", "penDim", "寸法・文字", "寸法・部材の名前の文字"),
)
PARAM_OF = {k: p for k, p, _l, _d in PEN_KEYS}

# 部品ごとに持っているペンの区分
PART_PENS = {
    "ashiba_line": ("post", "line", "deck", "stair", "equip", "tie", "dim"),
    "ashiba_tie": ("tie",),
    "ashiba_net": ("net",),
    "ashiba_netbk": ("net",),
    "ashiba_sheet": ("sheet",),
    "ashiba_cstep": ("deck",),
    "ashiba_bridge": ("equip",),
    "ashiba_kbrk": ("equip",),
    "ashiba_stage": ("post", "line", "deck"),
    "ashiba_walkway": ("equip",),
    "ashiba_box": ("equip",),
    "ashiba_side": ("equip",),
    "ashiba_cfill": ("equip",),
    "ashiba_wform": ("equip",),
    "ashiba_cform": ("equip",),
}


def parse_pens(value) -> dict[str, int]:
    """「post=3,deck=5」か {"post": 3} → {"post": 3, ...}（知らない区分・1〜255 の外は捨てる）."""
    if not value:
        return {}
    items = value.items() if isinstance(value, dict) else (
        tuple(t.split("=", 1)) for t in str(value).replace("、", ",").split(",") if "=" in t)
    out = {}
    for k, v in items:
        k = str(k).strip()
        try:
            n = int(float(str(v).strip()))
        except ValueError:
            continue
        if k in PARAM_OF and 1 <= n <= 255:
            out[k] = n
    return out


def format_pens(pens: dict[str, int]) -> str:
    """{"post": 3} → 「post=3」（区分の順。1 は書かない）."""
    return ",".join(f"{k}={int(pens[k])}" for k, _p, _l, _d in PEN_KEYS if int(pens.get(k, 1) or 1) != 1)


def gdl_pens(pens: Optional[dict], part: str) -> dict[str, int]:
    """部品に渡すペンのパラメータ（その部品が持つ区分だけ。未指定は 1）."""
    pens = pens or {}
    return {PARAM_OF[k]: int(pens.get(k, 1) or 1) for k in PART_PENS.get(part, ())}


def part_base(name: str) -> str:
    """版つきの部品名（ashiba_line_4dea39f3）→ 基本名（ashiba_line）."""
    for base in sorted(PART_PENS, key=len, reverse=True):
        if name == base or name.startswith(base + "_"):
            return base
    return ""
