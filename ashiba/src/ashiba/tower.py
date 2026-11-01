"""タワークレーン（建築用のジブ起伏式クライミングクレーン）（部品 ashiba_tower）.

利用者の指定（2026-11-01）「タワークレーンも追加してちょ」。寸法と定格荷重はメーカーの図面（北川鉄工所 kiw.co.jp の PANF）と
レンタル会社の仕様書（産業リーシング CLIMBING CRANE CATALOG 2025）の値（m・t）。出典は SOURCES、調べたメモは
docs/調査_タワークレーン.md。【目安】は資料に数値が無く決めた値（部品のパラメータで直せる）: ジブの根元の位置と高さ・
カウンタウエイトの寸法・運転室の寸法・基礎の厚さ（基礎は現場ごとに設計する）・質量（3社とも公開資料に無い）。

ジブの長さ: 資料はジブの呼び（＝最大作業半径）だけで実長の表が無いので、北川の最小起伏角 15°（公表）で呼びの半径に届く長さを
算出する（jib_length）。タダノ（旧IHI）と小川の最小起伏角も 15° とする（数値が無い）。

定格荷重: 表の点（作業半径 → t）の間は、両側の点の小さい方（安全側。0m の欄が 3.5m より小さい機種もそれで効く）。ジブは
その呼び以上で一番短い表。

手続き・資格・点検・風・航空・敷地外は e-Gov の現行版の条文と航空局の実施要領（令和8年9月版）で確かめた（docs/調査_タワークレーン_法令.md）。
公的な数値が見つからないもの（建物とマストの離れ・基礎の算定式・壁つなぎの建物側の検討・オーバースイングの許可の要否）は判定せず、
「越える／越えない」とメーカー資料・関係先の確認の欄にとどめる。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from ashiba.oversail import oversail

MIN_LUFF = 15.0           # 最小起伏角 度（北川 公表。他社は数値が無く同じとする）
PIV_X = 1.0               # ジブの根元（旋回中心から前）m【目安】
PIV_H = 2.0               # ジブの根元の高さ（旋回体を受ける面から）m【目安】
LIGHT_H = 60.0            # 航空障害灯の要る高さ m（航空法51条。地表から）
LIGHT_MID_H = 90.0        # これ以上はジブ先端に中光度赤色（航空局 実施要領 第6章(10) 図7-23・7-24）
LIGHT_JIB = 45.0          # ジブが これを超えると途中に 45m 以下の間隔で低光度を足す（同上）
WIND_STOP = 10.0          # 作業中止の強風 10分間平均 m/s（ク則31条の2）
WIND_CHECK = 30.0         # これを超える瞬間風速の後は点検 m/s（ク則37条）

SOURCES = {
    "K1": "北川鉄工所 JCL730NKD 図面 730NKD-PANF.pdf p.1（kiw.co.jp）",
    "K2": "北川鉄工所 JCL280GK 図面 280GK-PANF.pdf p.1（kiw.co.jp）",
    "K3": "北川鉄工所 JCL080SKA 図面 080SKA-PANF.pdf p.1（kiw.co.jp）",
    "K6": "北川鉄工所 SPSS（EXCEL 版）取扱説明書 p.3（支えの間隔の目安）",
    "S1": "産業リーシング CLIMBING CRANE CATALOG 2025 JCL730NKD（印刷頁 13）",
    "S2": "産業リーシング CLIMBING CRANE CATALOG 2025 JCC-V600S（印刷頁 15）、南信重機 JCC-V600S 仕様",
    "S4": "産業リーシング CLIMBING CRANE CATALOG 2025 JCC-TS300S（印刷頁 26）",
    "S5": "産業リーシング CLIMBING CRANE CATALOG 2025 JCL280GK（印刷頁 27）",
    "S6": "産業リーシング CLIMBING CRANE CATALOG 2025 OTS-90NH 小川製作所（印刷頁 31）",
}


@dataclass(frozen=True)
class Tower:
    key: str
    name: str                 # 平面の注記・帳票の名前
    model: str                # メーカーと型式
    max_t: float              # 最大定格荷重 t（つり上げ荷重）
    jibs: tuple               # ジブの呼び m（＝最大作業半径）
    rated: dict               # {ジブの呼び: {作業半径: t}}
    mast_w: float             # マストの断面 m
    mast_seg: float           # マスト1本の長さ m
    free_h: float             # 最大自立高さ m（基礎の上面から旋回体を受ける面）
    frame_h: float            # Aフレーム頂部の高さ（旋回体を受ける面から）m
    frame_x: float            # Aフレーム頂部の旋回中心から後ろ m
    tail_r: float             # 後端旋回半径 m
    front: float              # 旋回中心から旋回体の前端 m
    width: tuple              # 旋回体の幅（左, 右）m
    jib_w: float              # ジブの断面の幅 m
    base_w: float             # ベース（クロスベース・ベースフレーム）の外形 m
    max_lift_h: float         # 最大揚程 m
    source: str
    climb: str = ""           # クライミング（方式・最大フロアクライミング高さ）
    tie_rule: bool = False    # 北川の支えの目安（K6）が使える
    guesses: str = ""


def _r(text: str) -> dict:
    """「半径:t 半径:t …」→ {半径: t}."""
    return {float(a): float(b) for a, b in (x.split(":") for x in text.split())}


TOWERS = {
    "jcl730": Tower("jcl730", "タワークレーン 27.5t", "北川鉄工所 JCL730NKD", 27.5, (32.0, 37.0, 40.0, 45.0, 48.0, 53.0),
                    {32.0: _r("3:22 5:27.5 26.5:27.5 28:25.7 30:23.5 32:21.5"),
                     45.0: _r("3:22 5:27.5 24:27.5 25:26.5 30:21.5 35:17.3 40:14.2 45:12.0"),
                     53.0: _r("3:22 5:24 21:24 25:21 30:17.4 35:14.2 40:11.5 45:9.5 50:8.2 53:7.5")},
                    1.9, 6.0, 51.455, 13.151, 4.1, 6.6, 2.26, (2.7, 4.1), 2.3, 4.6, 305.0, "K1",
                    climb="油圧クライミング（ストローク 1.5m）・最大フロアクライミング高さ 41.307m（S1）", tie_rule=True,
                    guesses="ジブの根元・カウンタウエイトと運転室の寸法・質量（資料に無い）。ベースは伸縮架台 7,620×4,580 か"
                            "ベースフレーム 4,600×2,380（図は 4.6m 角で描く）"),
    "v600": Tower("v600", "タワークレーン 25t", "タダノ（旧IHI運搬機械）JCC-V600S", 25.0, (32.0, 37.0, 40.0, 46.0, 52.0),
                  {32.0: _r("0:10 3.5:25 27:25 28:23.84 30:21.8 32:20"),
                   52.0: _r("0:10 3.5:25 24.5:25 30:18.97 35:15.08 40:12.09 45:9.9 50:8.17 52:7.5")},
                  1.9, 6.0, 38.954, 12.15, 5.1, 8.1, 2.77, (2.461, 4.256), 2.39, 4.313, 250.0, "S2",
                  climb="最大フロアクライミング高さ 28.9m・クライミング装置の高さ 2.7m（S2）",
                  guesses="最小起伏角（15° とした）・ジブの根元・カウンタウエイトと運転室の寸法・質量（資料に無い）"),
    "ts300": Tower("ts300", "タワークレーン 14t", "タダノ（旧IHI運搬機械）JCC-TS300S", 14.0, (23.0, 27.0, 32.0, 37.0),
                   {23.0: _r("3:14 22:14 23:13"), 37.0: _r("3:14 18:14 20:12.64 25:10.19 30:8.5 35:7.39 37:7.0")},
                   1.35, 7.2, 47.794, 11.5, 3.25, 6.6, 2.243, (2.48, 3.386), 1.74, 4.25, 150.0, "S4",
                   climb="最大フロアクライミング高さ 37.805m・装置 4.6m（S4）",
                   guesses="最小起伏角（15° とした）・ジブの根元・カウンタウエイトと運転室の寸法・質量（資料に無い）"),
    "jcl280": Tower("jcl280", "タワークレーン 14t（中型）", "北川鉄工所 JCL280GK（4本掛け）", 14.0, (24.0, 30.0, 33.0, 36.0, 39.0, 45.0),
                    {24.0: _r("3:14 20:14 22:12.8 24:11.5"), 39.0: _r("3:10 20:10 25:8.37 30:7.0 35:5.82 39:5.0"),
                     45.0: _r("0:6 20:6 25:5.18 30:4.49 35:3.92 40:3.42 45:3.0")},
                    1.35, 7.2, 46.755, 10.16, 4.0, 5.0, 1.7475, (1.73, 2.85), 1.3, 4.118, 160.0, "K2",
                    climb="油圧クライミング（ストローク 1.8m）・最大フロアクライミング高さ 37.85m（S5）", tie_rule=True,
                    guesses="ジブの根元・カウンタウエイトと運転室の寸法・質量（資料に無い）。45m ジブは2本掛け（最大 7t）の表"),
    "jcl080": Tower("jcl080", "タワークレーン 2.8t", "北川鉄工所 JCL080SKA", 2.8, (24.0, 30.0, 36.0, 42.0),
                    {24.0: _r("3:2.8 24:2.8"), 30.0: _r("3:2.8 30:2.8"), 36.0: _r("3:2.8 26.5:2.8 36:1.8"),
                     42.0: _r("3:2.8 20:2.8 31:1.8 42:1.2")},
                    1.17, 7.0, 41.663, 9.719, 2.5, 3.8, 1.359, (1.5, 2.0), 1.1, 2.2, 140.0, "K3",
                    climb="電動油圧クライミング（ストローク 1.75m）", tie_rule=True,
                    guesses="Aフレーム頂部の前後の位置（2.5m とした）・ジブの断面（1.1m とした）・ジブの根元・カウンタウエイトと"
                            "運転室の寸法・質量（資料に無い）"),
    "ots90": Tower("ots90", "タワークレーン 2.8t（小川）", "小川製作所 OTS-90NH", 2.8, (20.0, 25.0, 30.0),
                   {20.0: _r("3:2.8 20:2.8"), 30.0: _r("3:2.8 25:2.8 26:2.6 27:2.5 28:2.3 29:2.2 30:2.0")},
                   1.25, 6.0, 41.04, 7.5, 2.9, 3.967, 1.53, (1.97, 2.1), 1.176, 4.073, 75.0, "S6",
                   guesses="最小起伏角（15° とした）・ジブの根元・カウンタウエイトと運転室の寸法・質量（資料に無い）"),
}


@dataclass
class Check:
    item: str
    status: str
    detail: str


@dataclass
class Placed:
    name: str
    tower: Tower
    mast: float = 0.0                 # マストの高さ m（基礎の上面から旋回体を受ける面）
    radius: float = 0.0               # 作業半径 m（0＝最大作業半径の 6 割）
    load_t: float = 0.0               # 吊り荷 t（フック・玉掛け用具込み）
    jib: float = 0.0                  # ジブの呼び m（0＝作業半径に届く一番短いもの）
    ties_mm: list = field(default_factory=list)
    tie_dir: float = 180.0
    tie_len: float = 2.0
    origin: tuple = (0.0, 0.0)        # マストの芯 mm
    heading: float = 0.0              # ジブの向き 度
    checks: list = field(default_factory=list)


def find(key: str) -> Tower:
    if key in TOWERS:
        return TOWERS[key]
    hits = [t for t in TOWERS.values() if key and (key.lower() in t.model.lower() or key in t.name)]
    if len(hits) == 1:
        return hits[0]
    raise KeyError(f"機種は {'・'.join(TOWERS)} のどれか（{key}）")


def model_code(key: str) -> int:
    return list(TOWERS).index(key) + 1


def jib_length(nominal: float) -> float:
    """ジブの呼び（最小起伏角での作業半径）に届くジブの長さ m（根元 PIV_X から。算出）."""
    return round((nominal - PIV_X) / math.cos(math.radians(MIN_LUFF)), 3)


def pick_jib(t: Tower, radius: float, jib: float = 0.0) -> float:
    if jib:
        return min((j for j in t.jibs if j >= jib - 1e-6), default=t.jibs[-1])
    return min((j for j in t.jibs if j >= radius - 1e-6), default=t.jibs[-1])


def rated_at(t: Tower, jib: float, radius: float) -> Optional[float]:
    """定格荷重 t（ジブはその呼び以上で一番短い表、表の点の間は両側の小さい方。表の外は None）."""
    keys = sorted(k for k in t.rated if k >= jib - 1e-6)
    if not keys:
        return None
    rows = t.rated[keys[0]]
    rs = sorted(rows)
    if radius > rs[-1] + 1e-6 or radius > jib + 1e-6:
        return None
    lo = [r for r in rs if r <= radius + 1e-6]
    hi = [r for r in rs if r >= radius - 1e-6]
    vals = ([rows[lo[-1]]] if lo else []) + ([rows[hi[0]]] if hi else [])
    return min(vals) if vals else None


def luff_angle(radius: float, jib_len: float) -> float:
    """作業半径に届く起伏角 度（根元 PIV_X から）."""
    c = max(-1.0, min(1.0, (radius - PIV_X) / jib_len))
    return math.degrees(math.acos(c))


def tie_checks(t: Tower, mast: float, ties_m: list) -> list[Check]:
    """北川の支えの目安（K6 p.3）: 支えの上の自立高さ ≦ 最大自立高さ×2/3、支えの間隔は 最大自立高さ×1/5 以上・最大自立高さ以下."""
    out = []
    if mast <= t.free_h + 1e-6 and not ties_m:
        return [Check("自立", "OK", f"マスト {mast:g}m ≦ 最大自立高さ {t.free_h:g}m（支え無し）")]
    if not ties_m:
        return [Check("壁つなぎ", "NG", f"マスト {mast:g}m が最大自立高さ {t.free_h:g}m を超えるのに支え（壁つなぎ）が無い")]
    if not t.tie_rule:
        return [Check("壁つなぎ", "要確認", "支えの間隔はメーカーに確認（北川以外は目安が公開されていない）")]
    hs = sorted(ties_m)
    above = mast - hs[-1]
    lim = t.free_h * 2 / 3
    out.append(Check("支えの上の自立高さ", "OK" if above <= lim + 1e-6 else "NG",
                     f"{above:.2f}m ≦ 最大自立高さ×2/3 {lim:.2f}m（北川 SPSS 取扱説明書 p.3 の目安）"))
    gaps = [b - a for a, b in zip([0.0] + hs[:-1], hs)]
    lo, hi = t.free_h / 5, t.free_h
    bad = [g for g in gaps if g < lo - 1e-6 or g > hi + 1e-6]
    out.append(Check("支えの間隔", "OK" if not bad else "NG",
                     f"間隔 {'・'.join(f'{g:.1f}' for g in gaps)}m（{lo:.1f}〜{hi:.1f}m。北川 SPSS 取扱説明書 p.3 の目安）"))
    return out


def check(p: Placed, boundary: list | None = None, roads: set | None = None) -> Placed:
    t = p.tower
    p.mast = p.mast or t.free_h
    jib = pick_jib(t, p.radius or t.jibs[0] * 0.6, p.jib)
    p.jib = jib
    p.radius = p.radius or round(jib * 0.6, 1)
    p.checks = []
    cap = rated_at(t, jib, p.radius)
    if cap is None:
        p.checks.append(Check("定格荷重", "NG", f"ジブ {jib:g}m で作業半径 {p.radius:g}m は表の外"))
    else:
        st = "OK" if p.load_t <= cap + 1e-9 else "NG"
        p.checks.append(Check("定格荷重", st if p.load_t else "注意",
                              f"ジブ {jib:g}m・半径 {p.radius:g}m → {cap:g}t" + (f" ／ 吊り荷 {p.load_t:g}t" if p.load_t else "（吊り荷を入れて判定）")))
    p.checks += tie_checks(t, p.mast, [z / 1000 for z in p.ties_mm])
    top = p.mast + t.frame_h
    jl = jib_length(jib)
    ang = luff_angle(p.radius, jl)
    tip = p.mast + PIV_H + jl * math.sin(math.radians(ang))
    hi = max(top, tip)
    p.checks.append(Check("航空障害灯", "注意" if hi >= LIGHT_H else "OK",
                          f"最も高い所 {hi:.1f}m（Aフレーム {top:.1f}m・ジブの先 {tip:.1f}m。避雷針等を足す）" +
                          ("。60m 以上は航空障害灯と昼間障害標識（航空法51条・51条の2）: " + "／".join(aviation(hi, jl))
                           if hi >= LIGHT_H else "＜ 60m")))
    if boundary:
        c = p.origin
        for what, r in (("ジブ（最大作業半径）", jib), ("カウンタウエイト（後端旋回半径）", t.tail_r)):
            over = oversail(c, r * 1000, boundary, roads)
            if over:
                p.checks.append(Check("敷地の外へ", "要確認", f"{what} R{r:g}m が " + "・".join(
                    f"辺{o.edge + 1}{'（道路）' if o.road else ''} {o.over / 1000:.1f}m" for o in over) + " 出る。" +
                    ("道路の上は所轄警察署（道路使用 道交法77条）と道路管理者へ連絡・協議（公衆災害防止対策要綱 第29）。"
                     if any(o.road for o in over) else "") +
                    "隣地の上は所有者の承諾（民法207条）、旋回の制限（回転ストッパー）の要否を（同要綱 第36・37）"))
    return p


def part_params(p) -> dict:
    """部品 ashiba_tower のパラメータ（p は Placed か Tower）."""
    if isinstance(p, Tower):
        p = Placed("", p)
        check(p)
    t = p.tower
    jl = jib_length(p.jib)
    ang = luff_angle(p.radius, jl)
    return {"tcModel": model_code(t.key), "tcType": 1, "tcName": f"{p.name} {t.name}" if p.name else t.name,
            "tcNote": f"{t.model}・ジブ {p.jib:g}m", "slew": 0.0,
            "msW": t.mast_w, "msH": p.mast, "msSeg": t.mast_seg, "baseW": t.base_w, "baseD": 1.5,
            "tailR": t.tail_r, "cwW": round(min(t.width) * 2 * 0.8, 3), "cwH": 2.0, "cwL": 1.5,
            "dkW": round(t.width[0] + t.width[1], 3), "upF": t.front, "frH": t.frame_h, "frX": t.frame_x,
            "pvX": PIV_X, "pvH": PIV_H, "jbL": jl, "jbA": round(ang, 2), "jbW": t.jib_w, "hkD": 10.0,
            "maxR": p.jib, "tieZ": ",".join(f"{z:.0f}" for z in p.ties_mm), "tieA": p.tie_dir, "tieL": p.tie_len,
            "avN": light_count(p)}


def light_count(p: Placed) -> int:
    """3D に描く航空障害灯（0＝要らない・1＝塔頂とジブ先端・2 以上＝ジブの途中に avN−1 個）."""
    t = p.tower
    jl = jib_length(p.jib)
    tip = p.mast + PIV_H + jl * math.sin(math.radians(luff_angle(p.radius, jl)))
    if max(p.mast + t.frame_h, tip) < LIGHT_H:
        return 0
    return 1 + max(0, math.ceil(jl / LIGHT_JIB - 1e-9) - 1)


RIGGING_T = 0.05          # 玉掛け用具 t（crane.py と同じ）
HOOK_TOP = 2.0            # ジブの先からフックの巻上げの限りまで m【目安】（資料に無い）
JUDGE = ("揚重可能", "重すぎ", "遠すぎ", "高すぎ")


def tower_from_params(ps: dict) -> Tower:
    """置いた部品のパラメータ（tcModel）→ 機種（0 や範囲外は一番大きい機種）."""
    keys = list(TOWERS)
    i = int(ps.get("tcModel", 0) or 0)
    return TOWERS[keys[i - 1]] if 1 <= i <= len(keys) else TOWERS[keys[0]]


def judge_lift(t: Tower, jib: float, mast: float, radius: float, need_z: float, load_t: float) -> tuple[str, Optional[float]]:
    """揚重判定（据え付けたジブの呼び jib のまま）: 遠すぎ＝ジブの呼びより遠い、高すぎ＝その半径でジブを起こしたときの
    フックの限り（ジブの先 − HOOK_TOP）が要る高さに届かない、重すぎ＝吊り荷＋玉掛け用具 ＞ 定格荷重（ク則23条）.
    m・t。戻りは（判定, 定格荷重）."""
    cap = rated_at(t, jib, radius)
    if cap is None or radius > jib + 1e-6:
        return JUDGE[2], None
    jl = jib_length(jib)
    tip = mast + PIV_H + jl * math.sin(math.radians(luff_angle(radius, jl)))
    if tip - HOOK_TOP < need_z:
        return JUDGE[3], cap
    if load_t + RIGGING_T > cap + 1e-9:
        return JUDGE[1], cap
    return JUDGE[0], cap


def jib_axis(ps: dict, origin: tuple, heading_deg: float) -> tuple[tuple, tuple]:
    """置いた部品のパラメータ（m・度）→ ジブの中心軸（根元・先）の図面の座標 mm（干渉チェック用）."""
    a = math.radians(heading_deg + float(ps.get("slew", 0.0)))
    mh, pvx, pvh = float(ps.get("msH", 40.0)), float(ps.get("pvX", PIV_X)), float(ps.get("pvH", PIV_H))
    jl, ja = float(ps.get("jbL", 30.0)), float(ps.get("jbA", 45.0))
    if int(ps.get("tcType", 1) or 1) == 2:
        ja = 0.0
    r1 = pvx + jl * math.cos(math.radians(ja))
    z0, z1 = mh + pvh, mh + pvh + jl * math.sin(math.radians(ja))
    p0 = (origin[0] + pvx * 1000.0 * math.cos(a), origin[1] + pvx * 1000.0 * math.sin(a), origin[2] + z0 * 1000.0)
    p1 = (origin[0] + r1 * 1000.0 * math.cos(a), origin[1] + r1 * 1000.0 * math.sin(a), origin[2] + z1 * 1000.0)
    return p0, p1


def procedures(t: Tower) -> list[tuple[str, str]]:
    """つり上げ荷重の区分ごとの手続き・資格・点検（ク則・安衛法。条文は e-Gov の現行版）."""
    out = []
    if t.max_t >= 3.0:
        out += [("設置届", "工事開始の 30 日前までに労働基準監督署長へ（安衛法88条・ク則5条）。短い期間でも要る。添付: 明細書・組立図・"
                           "ジブ・塔・脚の強度計算書・据付箇所の周囲の状況・基礎の概要（ク則5条）"),
                ("落成検査", "荷重試験 定格荷重の 1.25 倍・安定度試験 1.27 倍（ク則6条）。クレーン検査証は 2 年、現場に備え付け（ク則9・10条）"),
                ("変更", "クライミングで塔の構成が明細書の範囲を越える・ジブの長さを変えるときは変更届・変更検査（ク則44・45条）の"
                         "対象になり得る（どこまでが変更かの公的な線引きは見つからない。監督署に確認）")]
    elif t.max_t >= 0.5:
        out.append(("設置報告", "あらかじめ設置報告書（ク則11条）"))
    out += [("運転", "クレーン・デリック運転士免許（ク則22条）" if t.max_t >= 5 else "特別教育（ク則21条）"),
            ("玉掛け", "玉掛け技能講習（ク則221条）" if t.max_t >= 1 else "特別教育（ク則222条）"),
            ("合図", "合図を定めて合図者を指名（ク則25条）。複数の業者がいるときは特定元方事業者が合図を統一（安衛則639条）"),
            ("組立て・解体", "作業指揮者を選び、立入禁止・悪天候の中止（ク則33条）。クライミングを含める条文は見つからないが、"
                             "業界の作業指揮者教育は組立て・解体と合わせて扱う"),
            ("点検", "年次・月次の定期自主検査（ク則34・35条）・作業開始前（36条）・瞬間風速 30m/s 超の後と中震以上の地震の後（37条）。記録は 3 年"),
            ("強風", f"10分間平均 {WIND_STOP:g}m/s 以上で作業を中止し（ク則31条の2）、ジブを固定する等（31条の3）"),
            ("定格荷重の表示", "玉掛けをする所に定格荷重の表を掲げる（ク則24条の2）。吊り荷＋玉掛け用具 ≦ 定格荷重（23条）"),
            ("安定度・基礎", "構造規格15条の安定度（1.4 倍・1.1 倍＋水平動荷重＋作動時風荷重・後方 0.3 倍・暴風時無負荷）をメーカーの"
                             "計算書で確認。基礎の反力・転倒モーメント・アンカーはメーカー資料の値で（公的な算定法は見つからない）")]
    return out


def aviation(height: float, jib_len: float) -> list[str]:
    """航空障害灯・昼間障害標識（航空法51条・51条の2、実施要領 第6章(10) 図7-23・7-24）。60m 未満は空."""
    if height < LIGHT_H:
        return []
    mid = max(0, math.ceil(jib_len / LIGHT_JIB - 1e-9) - 1)
    out = ["Aフレーム頂部（塔頂）: " + ("中光度赤色" if height >= LIGHT_MID_H and jib_len > LIGHT_JIB else "低光度（32cd）"),
           "ジブ先端: " + ("中光度赤色" if height >= LIGHT_MID_H else "低光度（32cd）")]
    if mid:
        out.append(f"ジブの途中: 低光度を {mid} 個（45m 以下のほぼ等間隔）")
    out += ["昼間障害標識: ジブを黄赤と白の 7 等分に塗る",
            "届出: 設置したら遅滞なく東京航空局か大阪航空局へ（航空法施行規則238条。仮設は設置期間、地上高・海抜高・緯度経度・"
            "灯の位置と数の図）。空港の制限表面に近い所は事前に相談（航空法49条）"]
    return out


def overlaps(placed: list[Placed]) -> list[Check]:
    """複数台のジブの旋回範囲の重なり（法令に数値の基準は無い。配置計画・合図の統一を 安衛則638条の3・639条）."""
    out = []
    for i, a in enumerate(placed):
        for b in placed[i + 1:]:
            d = math.hypot(a.origin[0] - b.origin[0], a.origin[1] - b.origin[1]) / 1000
            if d < a.jib + b.jib:
                out.append(Check("旋回範囲の重なり", "要確認", f"{a.name} と {b.name}（芯々 {d:.1f}m ＜ {a.jib:g}＋{b.jib:g}m）。"
                                 "高さの差・旋回の制限・合図の統一を計画に（安衛則638条の3・639条）"))
    return out


def report(placed: list[Placed]) -> str:
    lines = ["# タワークレーンの計画と判定", "",
             "| 名前 | 機種 | 最大定格荷重 | マスト | ジブ | 作業半径 | クライミング |", "|---|---|---|---|---|---|---|"]
    for p in placed:
        t = p.tower
        lines.append(f"| {p.name} | {t.name} | {t.max_t:g}t | {p.mast:g}m（□{t.mast_w * 1000:.0f}） | {p.jib:g}m | "
                     f"{p.radius:g}m | {t.climb or '—'} |")
    lines += ["", "## 判定", "", "| 名前 | 項目 | 結果 | 内容 |", "|---|---|---|---|"]
    for p in placed:
        for c in p.checks:
            lines.append(f"| {p.name} | {c.item} | {c.status} | {c.detail} |")
    for c in overlaps(placed):
        lines.append(f"| — | {c.item} | {c.status} | {c.detail} |")
    lines += ["", "## 手続き・資格・点検（クレーン等安全規則ほか）", ""]
    for t in {p.tower.key: p.tower for p in placed}.values():
        lines.append(f"### {t.name}（{t.model}・つり上げ荷重 {t.max_t:g}t）")
        lines += [f"- {a}: {b}" for a, b in procedures(t)]
        lines.append("")
    lines += ["", "## 出典と目安", ""]
    for p in placed:
        t = p.tower
        lines.append(f"- {t.name}（{t.model}）: {SOURCES[t.source]}" + (f"。【目安】{t.guesses}" if t.guesses else ""))
    return "\n".join(lines) + "\n"
