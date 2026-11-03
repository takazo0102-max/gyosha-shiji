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
    "ashiba_bform": ("equip",),
    "ashiba_sform": ("equip",),
    "ashiba_yamadome": ("equip",),
    "ashiba_kakoi": ("equip",),
    "ashiba_crane": ("equip",),
    "ashiba_plate": ("equip",),
    "ashiba_kodai": ("equip",),
    "ashiba_route": ("equip",),
    "ashiba_house": ("equip",),
    "ashiba_opening": ("equip",),
    "ashiba_fence": ("equip",),
    "ashiba_lifeline": ("equip",),
    "ashiba_tube": ("equip",),
    "ashiba_machine": ("equip",),
    "ashiba_tower": ("equip",),
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


# 一度で色分けする組み合わせ（GLOOBE の「カラー印刷」に当たる。2026-11-02 の開発ループ）。区分ごとの色の見当（R, G, B 0〜1）で、
# プロジェクトのペンセットからいちばん近い色のペンを選ぶ（ペンセットごとに番号が違うので番号では決めない）。白黒は全部を黒に近いペン
COLOR_SCHEME = {
    "post": (0.85, 0.10, 0.10),     # 赤
    "line": (0.10, 0.30, 0.85),     # 青
    "deck": (0.10, 0.60, 0.20),     # 緑
    "stair": (0.70, 0.10, 0.70),    # 紫
    "equip": (0.95, 0.55, 0.00),    # 橙
    "tie": (0.00, 0.65, 0.75),      # 水色
    "net": (0.55, 0.35, 0.15),      # 茶
    "sheet": (0.50, 0.50, 0.50),    # 灰
    "dim": (0.00, 0.00, 0.00),      # 黒
}
PRESETS = ("カラー", "白黒")


def _rgb(hexc: str) -> tuple[float, float, float]:
    h = hexc.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def nearest_pen(table: list, rgb: tuple) -> int:
    """[(番号, "#RRGGBB", 説明)] から色 rgb にいちばん近いペンの番号（同じ近さなら小さい番号）."""
    best = min(table, key=lambda r: (sum((a - b) ** 2 for a, b in zip(_rgb(r[1]), rgb)), r[0]))
    return int(best[0])


def preset_pens(table: list, preset: str) -> dict[str, int]:
    """組み合わせ（カラー・白黒）→ {区分: ペンの番号}."""
    if not table:
        return {}
    if preset == "白黒":
        black = nearest_pen(table, (0.0, 0.0, 0.0))
        return {k: black for k, _p, _l, _d in PEN_KEYS}
    return {k: nearest_pen(table, COLOR_SCHEME[k]) for k, _p, _l, _d in PEN_KEYS}


# 描き方の決め（scripts/gdl_draft.py）の太線・細線・範囲の線（利用者の指定 2026-11-04「平面図を CAD の平面図レベルに」）
DRAFT_PARTS = frozenset({"ashiba_machine", "ashiba_crane", "ashiba_tower"})
ZONE_RGB = (0.85, 0.10, 0.10)          # 範囲の線（作業半径・立入禁止）は赤に近いペン


def draft_pens(rows: list, base: int) -> dict[str, int]:
    """[(番号, "#RRGGBB", 太さ mm)] と線のペン base → {penBold, penThin, penZone, penMask}.
    太線は base と同じ色でいちばん太いペン、細線はいちばん細いペン（同じ太さなら小さい番号）、範囲の線は赤に近い細いペン、
    下の線を隠す塗りは白のペン（無ければ 0＝隠さない）。ペンセットが読めなければ base のまま（太さは描き分けない）."""
    if not rows:
        return {"penBold": base, "penThin": base, "penZone": base}
    by = {int(i): (h.upper(), float(w)) for i, h, w in rows}
    col = by.get(int(base), ("#000000", 0.0))[0]
    same = [(w, i) for i, (h, w) in by.items() if h == col]
    if not same:
        return {"penBold": base, "penThin": base, "penZone": base}
    bold = max(same, key=lambda t: (t[0], -t[1]))[1]
    thin = min(same, key=lambda t: (t[0], t[1]))[1]
    dist = min(sum((a - b) ** 2 for a, b in zip(_rgb(h), ZONE_RGB)) for h, _w in by.values())
    reds = [(w, i) for i, (h, w) in by.items() if sum((a - b) ** 2 for a, b in zip(_rgb(h), ZONE_RGB)) <= dist + 1e-9]
    zone = min(reds)[1]
    whites = sorted(i for i, (h, _w) in by.items() if h == "#FFFFFF")
    return {"penBold": bold, "penThin": thin, "penZone": zone, "penMask": whites[0] if whites else 0}
