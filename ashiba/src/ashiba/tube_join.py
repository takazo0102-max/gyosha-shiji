"""別の足場を単管でつなぐ（部品 ashiba_tube。GLOOBE の「別の足場と接続する単管」に当たる。2026-11-02 の開発ループ）.

隣り合う別の足場（別の面・別の系列・建物の間で繋がらない所）の支柱から支柱へ、平面に線を1本引き、層の高さごとに単管を
直交クランプで留めて繋ぐ。手すり・中桟の高さにも足せる（足場の間のすき間が開口になる所）、層の間に斜めの補強（自在クランプ）も。
規格品で発注できる詳細さで（利用者の指定 2026-11-01: イメージじゃなく実際の規定の長さで発注できるくらい詳細に）。

出典（調べた資料）:
- 日建リース工業 仮設資材カタログ Vol.10 p372 単管パイプ（STK500 φ48.6×2.4、長さ別の重さ。足場用は 2.0〜6.0M、0.5〜1.8M は
  型枠用・ピン無し）・p378 兼用直交クランプ ARC1（0.73kg・スベリ耐力 4.9kN）・兼用自在クランプ ARC2（0.70kg・3.43kN）
- 労働安全衛生規則 570条1項3号（鋼管の接続部又は交差部は適合した附属金具で確実に接続・緊結）・4号（筋かいで補強）、
  563条1項3号ロ（わく組以外の足場は手すり等及び中桟等。高さ 85cm 以上・35〜50cm は 552条1項4号）
単管の端の突き出し（クランプの外へ 50mm 以上・支柱の間隔の 1/4 以下）は opening_guard と同じ決め（目安）。クランプは支柱の
コマ・緊結部を避けて付ける（くさび式は布材の緊結部の上下）。

GLOOBE 2026 の「単管の単独入力（火打ち）」「壁つなぎの単管配置」に当たるもの（利用者の指定 2026-11-02「全部入れて 進めて」）:
- 火打ち: L 字に接する足場の入隅・出隅を、平面で斜めの単管で結ぶ（隅の支柱から両側へ同じ程度の所の支柱どうし）。線は
  「片方の面の支柱 → 隅の支柱 → もう片方の面の支柱」の3点で引く。水平の単管と鉛直の支柱は平面の角度に関係なく直交クランプ
- 単管の壁つなぎ: S造で柱の位置に支柱が無いとき、支柱から支柱へ単管を渡し、その単管から柱へ壁つなぎを取る。単管は壁つなぎの
  力を受ける単純梁なので、受けられる力 P = fb·Z·L/(a·b)（a・b は壁つなぎから両端の支柱まで）を確かめる。単管 φ48.6×2.4 の
  Z 3.83cm³・fb 23,520N/cm²（日建 p453 の検討の値。hoarding と同じ）、壁つなぎの許容 4.41kN（仮設工業会の認定基準。capacity.csv）
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .opening_guard import OVER_MM, MID_H, RAIL_H, TUBES, order_table

CLAMPS = {"ARC1": ("ARC1 兼用直交クランプ", 0.73, 4.9), "ARC2": ("ARC2 兼用自在クランプ", 0.70, 3.43)}   # 品番 → (品名, kg, スベリ耐力 kN)
TUBE_MAX = max(TUBES)                    # 6.0M（7.0M は型枠用のみ）
SPAN_MIN = 100.0                         # 支柱どうしが近すぎる（同じ支柱）
TIE_KN = 4.41                            # 壁つなぎの許容耐力（仮設工業会の認定基準。data/capacity.csv）
DOUBLE_GAP_MM = 100.0                    # 2本抱かせるときの上の単管の高さの差（クランプの幅。目安）
TIE_REACH_MM = 2000.0                    # 単管からこれより遠い柱には取らない（壁つなぎの最長 KS1000 の 1,060 を越えても知らせる）
HIUCHI_ANGLES = (45.0, 135.0)            # 火打ちを掛けられる隅の角（これを外れると斜めの単管が面に沿いすぎる。目安）


def pick_tube(need: float) -> int:
    """要る長さ need mm 以上でいちばん短い単管の長さ mm（無ければ 0）."""
    return min((t for t in TUBES if t >= need - 1e-6), default=0)


@dataclass
class Check:
    item: str
    status: str
    message: str


@dataclass
class Join:
    name: str
    a: tuple[float, float]               # 始めの足場の支柱の芯 mm
    b: tuple[float, float]               # 終わりの足場の支柱の芯 mm
    levels: list[float]                  # つなぐ高さ（足場の立つ面から）mm
    guard: bool = False                  # 各層の上に手すり・中桟の単管も
    brace: bool = False                  # 層の間に斜めの補強
    tube: int = 0                        # 横の単管の長さ mm
    brace_tubes: list[int] = field(default_factory=list)
    kind: str = "つなぎ"                  # "つなぎ"・"火打ち"・"壁つなぎ"
    corner: tuple = ()                   # 火打ち: 隅の支柱の芯 mm
    ties: list = field(default_factory=list)       # 壁つなぎ: [(線の始めから mm, 柱の側 +1 左/−1 右, 柱の面まで mm)]
    tie_parts: list = field(default_factory=list)  # 壁つなぎ: 品番の並び（ties と同じ順。選んでから）
    tie_kg: list = field(default_factory=list)     # 壁つなぎ: 1本の重さ kg（ties と同じ順）
    double: bool = False                 # 壁つなぎ: 単管を上下2本抱かせる
    checks: list[Check] = field(default_factory=list)
    quantity: list[tuple[str, float, str]] = field(default_factory=list)

    @property
    def span(self) -> float:
        return math.dist(self.a, self.b)

    @property
    def rows(self) -> list[float]:
        """横の単管の高さ mm（層の高さ＋手すり・中桟）."""
        out = []
        for z in sorted(self.levels):
            out.append(z)
            if self.guard:
                out += [z + MID_H, z + RAIL_H]
        return out


def plan_join(j: Join) -> Join:
    c = j.checks = []
    L = j.span
    j.tube = pick_tube(L + 2.0 * OVER_MM) if L >= SPAN_MIN else 0
    if L < SPAN_MIN:
        c.append(Check("長さ", "NG", "線の始めと終わりが同じ支柱（つなぐ相手の足場の支柱まで線を引く）"))
    elif not j.tube:
        c.append(Check("長さ", "NG", f"支柱の間 {L:.0f}mm は単管 {TUBE_MAX / 1000:.1f}M に両端の突き出し {OVER_MM:.0f} を足して届かない → "
                                    "間に支柱（単管の建地とベース・根がらみ）を立てて2本に分ける"))
    else:
        ov = (j.tube - L) / 2.0
        st = "OK" if ov <= L / 4.0 + 1e-6 or j.tube == min(TUBES) else "WARN"
        c.append(Check("長さ", st, f"支柱の間 {L:.0f}mm に単管 {j.tube / 1000:.1f}M（両端の突き出し {ov:.0f}mm"
                                   + ("" if st == "OK" else f"。支柱の間の 1/4 {L / 4:.0f} を超えるので、短い単管を選ぶか端を切る") + "）"))
    if not j.levels:
        c.append(Check("高さ", "NG", "つなぐ高さが無い"))
    j.brace_tubes = []
    lv = sorted(j.levels)
    if j.brace and L >= SPAN_MIN:
        for z0, z1 in zip(lv, lv[1:]):
            need = math.hypot(L, z1 - z0) + 2.0 * OVER_MM
            t = pick_tube(need)
            j.brace_tubes.append(t)
            if not t:
                c.append(Check("斜めの補強", "NG", f"{z0:.0f}〜{z1:.0f} の斜めは {need:.0f}mm で単管 6.0M に入らない → 1層おきに掛ける"))
    nm, kg, slip = CLAMPS["ARC1"]
    c.append(Check("緊結", "OK", f"単管の両端を {nm}（スベリ耐力 {slip:g}kN）で支柱に留める（安衛則570条1項3号）。くさび式は支柱のコマ・"
                                "布材の緊結部を避けて上下にずらす"))
    if j.guard:
        c.append(Check("手すり", "OK", f"層ごとに手すり {RAIL_H:.0f}・中桟 {MID_H:.0f}（安衛則563条1項3号ロ・552条: 85cm 以上・35〜50cm）。足場の間の"
                                     "すき間に作業床が無いときは、床の端として幅木・ネットも要る"))
    if j.brace:
        nm2, _kg2, slip2 = CLAMPS["ARC2"]
        c.append(Check("斜めの補強", "OK", f"層の間に斜めの単管を {nm2}（スベリ耐力 {slip2:g}kN）で（向きを層ごとに変える。安衛則570条1項4号の筋かい）"))
    if j.kind == "火打ち":
        _check_hiuchi(j)
    if j.kind == "壁つなぎ":
        _check_ties(j)
    _quantity(j)
    return j


def corner_angle(j: Join) -> float:
    """火打ちの隅の角（度。隅の支柱から両側の支柱への向きのなす角）."""
    (ax, ay), (cx, cy), (bx, by) = j.a, j.corner, j.b
    u, v = (ax - cx, ay - cy), (bx - cx, by - cy)
    nu, nv = math.hypot(*u), math.hypot(*v)
    if nu < 1e-6 or nv < 1e-6:
        return 0.0
    return math.degrees(math.acos(max(-1.0, min(1.0, (u[0] * v[0] + u[1] * v[1]) / (nu * nv)))))


def _check_hiuchi(j: Join) -> None:
    c = j.checks
    ang = corner_angle(j)
    la, lb = math.dist(j.a, j.corner), math.dist(j.b, j.corner)
    lo, hi = HIUCHI_ANGLES
    if not (lo - 1e-6 <= ang <= hi + 1e-6):
        c.append(Check("火打ち", "NG", f"隅の角 {ang:.0f}° は {lo:.0f}〜{hi:.0f}° の外（面がほぼ一直線か折り返し）→ 隅の支柱を通る3点で引き直す"))
        return
    ratio = max(la, lb) / max(1.0, min(la, lb))
    st = "OK" if ratio <= 2.0 + 1e-6 else "WARN"
    c.append(Check("火打ち", st, f"隅の角 {ang:.0f}°・隅から {la:.0f}／{lb:.0f}mm の支柱を斜めの単管で結ぶ（平面の三角形で隅の変形を止める）"
                                + ("" if st == "OK" else "。片側が他方の2倍を超えるので、隅から同じ程度の支柱を選ぶ（目安）")
                                + "。足場の天端より上に掛けるときは支柱を単管で継ぎ足す"))


def tube_capacity_kn(L: float, a: float, double: bool = False) -> float:
    """支柱の間 L・片方の支柱から a の所に壁つなぎの力を受ける単管（単純梁）が受けられる力 kN: P = fb·Z·L/(a·b)."""
    from .hoarding import FB_TUBE, TUBE_Z

    b = L - a
    if a <= 0 or b <= 0:
        return float("inf")
    m = FB_TUBE * TUBE_Z * (2 if double else 1)                      # N·cm
    return m * (L / 10.0) / ((a / 10.0) * (b / 10.0)) / 1000.0


def _check_ties(j: Join) -> None:
    c = j.checks
    L = j.span
    if not j.ties:
        c.append(Check("壁つなぎ", "NG", "単管の上に取る柱が無い（鉄骨柱を一緒に選ぶか --tie-at で単管の始めからの位置を）"))
        return
    for k, (x, _side, need) in enumerate(j.ties):
        if not (0.0 < x < L):
            c.append(Check("壁つなぎ", "NG", f"{x:.0f}mm は支柱の間の外 → 支柱の間に柱が来る区間に線を引く"))
            continue
        cap = tube_capacity_kn(L, x, j.double)
        cap2 = tube_capacity_kn(L, x, True)
        nm = j.tie_parts[k] if k < len(j.tie_parts) else ""
        st = "OK" if cap >= TIE_KN - 1e-6 else "WARN"
        # 2本で足りるときだけ2本を勧める（2本でも足りないのに「2本抱かせる」と出ていた 2026-11-05）
        fix = ("単管を2本抱かせる（2本で " + f"{cap2:.2f}kN）、" if not j.double and cap2 >= TIE_KN - 1e-6 else
               ("" if j.double else f"2本でも {cap2:.2f}kN で足りないので、"))
        c.append(Check("壁つなぎ", st, f"始めから {x:.0f}mm・柱の面まで {need:.0f}mm（{nm or '品は長さで選ぶ'}）。単管"
                                      + ("2本" if j.double else "") + f"が受けられる力 {cap:.2f}kN"
                                      + (f" ≧ 壁つなぎの許容 {TIE_KN:g}kN" if st == "OK" else
                                         f" ＜ 壁つなぎの許容 {TIE_KN:g}kN → {fix}柱を支柱の近くで取る、"
                                         f"又はその壁つなぎの受け持ちの風荷重を {cap:.2f}kN 以下に（構造計算書で確かめる）")))
        if need > TIE_REACH_MM:
            c.append(Check("壁つなぎ", "NG", f"柱の面まで {need:.0f}mm は {TIE_REACH_MM:.0f} を超える → 単管を柱の近くに渡す"))
    nm, _kg, slip = CLAMPS["ARC1"]
    c.append(Check("緊結（壁つなぎ）", "OK" if TIE_KN / 2.0 <= slip else "WARN",
                   f"単管の両端の {nm} は壁つなぎの力を2つで受ける（1つ {TIE_KN / 2:.2f}kN ≦ スベリ耐力 {slip:g}kN）。"
                   "柱の側は鉄骨柱用の壁つなぎ金具（クランプ）で、溶接・穴あけは構造の設計者に確かめる"))


def _quantity(j: Join) -> None:
    q = j.quantity = []
    if not j.tube or not j.levels:
        return
    rows = j.rows
    use = {"火打ち": "火打ち", "壁つなぎ": "壁つなぎの受け"}.get(j.kind, "つなぎ・手すり")
    per = 2 if j.kind == "壁つなぎ" and j.double else 1
    q.append((f"単管 {j.tube / 1000:.1f}M（{use}）", len(rows) * per, f"本（{TUBES[j.tube]:g}kg）"))
    braces = [t for t in j.brace_tubes if t]
    for t in sorted(set(braces), reverse=True):
        q.append((f"単管 {t / 1000:.1f}M（斜めの補強）", braces.count(t), f"本（{TUBES[t]:g}kg）"))
    nm, kg, _s = CLAMPS["ARC1"]
    q.append((nm, 2 * len(rows) * per, f"個（{kg:g}kg。単管の両端）"))
    if j.kind == "壁つなぎ":
        for k in range(len(j.ties)):
            name = j.tie_parts[k] if k < len(j.tie_parts) else "壁つなぎ"
            kg = j.tie_kg[k] if k < len(j.tie_kg) else 0.0
            q.append((f"壁つなぎ {name}（単管から柱へ）", len(j.levels), f"本（{kg:g}kg）" if kg else "本"))
    if braces:
        nm2, kg2, _s2 = CLAMPS["ARC2"]
        q.append((nm2, 2 * len(braces), f"個（{kg2:g}kg。斜めの両端）"))


def part_params(j: Join) -> dict:
    zs = sorted(j.levels)
    if j.kind == "壁つなぎ" and j.double:
        zs = sorted(zs + [z + DOUBLE_GAP_MM for z in zs])            # 2本目は 1本目のすぐ上（クランプの幅だけあけて）
    return {"tbL": j.span / 1000.0, "tbLen": (j.tube or j.span) / 1000.0, "zList": ",".join(f"{z:.0f}" for z in zs),
            "gdOn": bool(j.guard), "brOn": bool(j.brace and any(j.brace_tubes)), "tbName": j.name,
            "tbNote": (f"単管 {j.tube / 1000:.1f}M×{len(j.rows) * (2 if j.kind == '壁つなぎ' and j.double else 1)}本"
                                                                     if j.tube else "単管が届かない")}   # 名前（火打ち1・壁つなぎ1）が種類を言う


def tie_spots(j: Join) -> list[dict]:
    """壁つなぎの部品（ashiba_tie）を置く所: [{"x", "y"（mm）, "faceAng"（度。+Y が柱の側）, "tieL"（mm）, "name"}]."""
    ux, uy = (j.b[0] - j.a[0]) / (j.span or 1.0), (j.b[1] - j.a[1]) / (j.span or 1.0)
    ang = math.degrees(math.atan2(uy, ux))
    out = []
    for k, (x, side, need) in enumerate(j.ties):
        out.append({"x": j.a[0] + ux * x, "y": j.a[1] + uy * x, "faceAng": ang if side > 0 else ang + 180.0, "tieL": need,
                    "name": j.tie_parts[k] if k < len(j.tie_parts) else ""})
    return out


def columns_on(j: Join, columns: list) -> list:
    """柱 [(芯 (x, y), 半分の大きさ mm（線に直角の向き）)] のうち、線の支柱の間に来るもの → [(始めから mm, 側, 柱の面まで mm)]."""
    L = j.span
    if L < SPAN_MIN:
        return []
    ux, uy = (j.b[0] - j.a[0]) / L, (j.b[1] - j.a[1]) / L
    out = []
    for (cx, cy), half in columns:
        dx, dy = cx - j.a[0], cy - j.a[1]
        x = dx * ux + dy * uy
        y = -dx * uy + dy * ux                                          # 左が +
        if 0.0 < x < L and abs(y) - half <= TIE_REACH_MM:
            out.append((x, 1 if y > 0 else -1, max(0.0, abs(y) - half)))
    return sorted(out)


def pick_tie(master, need_mm: float) -> str:
    """柱の面までの長さに合う壁つなぎの品番（attachments.tie_name と同じ選び方: 伸縮の範囲が合う最短、無ければ最長）."""
    if master is None:
        return ""
    cands = sorted((p for p in master.by_category("壁つなぎ") if p.adjustable_range()), key=lambda p: p.adjustable_range()[1])
    if not cands:
        p = next(iter(master.by_category("壁つなぎ")), None)
        return p.model_no if p is not None else ""
    fit = next((p for p in cands if p.covers(int(round(need_mm)))), None)
    return (fit or cands[-1]).model_no


def tie_weight(master, name: str) -> float:
    p = next((p for p in master.by_category("壁つなぎ") if p.model_no == name), None) if master is not None else None
    return float(p.weight_kg) if p is not None else 0.0


def report(joins: list[Join]) -> str:
    kinds = {j.kind for j in joins}
    title = "火打ちの単管" if kinds == {"火打ち"} else "単管に壁つなぎ" if kinds == {"壁つなぎ"} else "別の足場を単管でつなぐ"
    out = [f"# {title}", "",
           "出典: 日建リース工業 仮設資材カタログ Vol.10 p372（単管パイプ）・p378（兼用クランプ）・p453（単管の Z・fb）、壁つなぎは部材マスタの系列の品（日建は p100）、"
           "労働安全衛生規則 563条1項3号ロ・570条1項3号・4号、仮設工業会の認定基準（壁つなぎ 4.41kN）。"
           "単管の端の突き出し（50mm 以上・支柱の間隔の 1/4 以下）と火打ちの角は目安", "",
           "| つなぎ | 支柱の間 | 判定 | 内容 |", "|---|---|---|---|"]
    tot: dict[str, list] = {}
    for j in joins:
        for x in j.checks:
            out.append(f"| {j.name} | {j.span / 1000:.2f}m | {x.status} | {x.item}: {x.message} |")
        for a, n, u in j.quantity:
            row = tot.setdefault(a, [0.0, u])
            row[0] += n
    out += order_table(tot, ("単管", "ARC1", "ARC2", "壁つなぎ")) + [""]
    return "\n".join(out)
