"""場内の車両動線と敷鉄板（開発ループ 2026-11-01: 前に挙げた「他に必要な仮設材」の3番。部品 ashiba_route＋ashiba_plate）.

通路の中心線（ポリライン。始め＝ゲートの側）から、通路の帯・曲がり角の掃引（車両の外側前端角 Ro と内側後輪 ri の円）・敷鉄板の割付・
検定を出す。

出典（調べた資料。場内通路の幅を数値で決めた法令は無い）:
- 建設工事公衆災害防止対策要綱（建築工事編 第21・22・24、土木工事編 第23）: 車道 1車線 3.0m 以上・2車線 5.5m 以上、
  歩行者通路 0.75m 以上（多い所 1.5m）。第20・23: ゲートに誘導員、有効な幅と高さ、扉は引戸か内開き
- 道路構造令 第4条（設計車両 普通自動車 12.0×2.5m・前端 1.5・軸距 6.5・最小回転半径 12m）、車両制限令 第3条
- メーカーの主要諸元: 三菱ふそう ファイター（4t ダンプ R4.8・中型生コン R5.8）・スーパーグレート（大型生コン R6.8）、いすゞ ギガ
  （10t ダンプ R6.6）、タダノ GR-250N-1（25t ラフター 4輪操舵 R5.0）
- 掃引の式（剛体・回転中心は後軸の線上）: a＝√(R²−L²)、Ro＝√((a＋(W−T)/2)²＋(L＋F)²)、ri＝a−(W＋T)/2。4輪操舵は L＝軸距/2
- 敷鉄板: 日建リース 仮設資材カタログ Vol.10 p394（5×20＝1,524×6,096・1,604kg）。継ぎ目は千鳥、重ね敷きは半面交互（堀 2018
  建設機械施工 Vol.70 No.2: 完全重複は端部で一枚敷きと同じ・転倒は履帯が板の端に乗ったとき）
- 安衛則 151条の3・6・7（車両系の運行経路・必要な幅・誘導者）
- 搬入トラック・トレーラー連結車（2026-11-04 利用者の指定「場内通路にトレーラーも入れて進めて」）: 寸法は machine の種類 13・14
  （research_notes/搬入車両/）。曲がり角は src/ashiba/swept_sim.py の追従の軌跡（トラクタの前軸を円弧に沿わせ、後軸・トレーラーは
  少しずつ追従。【目安】）、ポールトレーラーはメーカーの表の所要道路幅
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .steel_plate import PlateLayout, layout as plate_layout

MARGIN_MM = 250.0                      # 曲がり角の掃引から通路の縁までの余裕（片側。目安）
SIDE_MM = 500.0                        # 直線の車幅の両側の余裕（目安）
ONE_LANE_MIN, TWO_LANE_MIN = 3000.0, 5500.0   # 要綱の車道の幅
ONE_WAY_MM, TWO_WAY_MM = 4000.0, 6000.0       # 既定の通路の幅（目安: 一方通行 4.0m・対面 6.0m）

# 車両: 名前, L（回転中心の線→前軸 mm）, F（前軸→前端）, W（全幅）, T（輪距）, R（最小回転半径＝最外側前輪の中心 mm）
VEHICLES = {
    "4t": ("4t ダンプ（ふそう ファイター FK）", 2910.0, 1100.0, 2190.0, 1780.0, 4800.0),
    "10t": ("10t ダンプ（いすゞ ギガ 6×4）", 3880.0, 1370.0, 2490.0, 2060.0, 6600.0),
    "mixer": ("大型生コン車（ふそう FV 4.5m³）", 3920.0, 1400.0, 2490.0, 2050.0, 6800.0),
    "mixer_m": ("中型生コン車（ふそう ファイター 3.2m³）", 3190.0, 1150.0, 2300.0, 1900.0, 5800.0),
    "R25": ("25t ラフテレーンクレーン（4輪操舵）", 1750.0, 6350.0, 2620.0, 2170.0, 5000.0),
    "std": ("道路構造令 普通自動車（12m 級）", 6500.0, 1500.0, 2500.0, 2000.0, 12000.0),
}


def vehicle_name(v: str) -> str:
    if v in VEHICLES:
        return VEHICLES[v][0]
    from .machine import MACHINES

    m = MACHINES[v]
    return f"{m.name}（{m.model.split('（')[0]}）"


def vehicle_width(v: str) -> float:
    """車体の幅 mm（連結車はトラクタとトレーラー・積荷の大きい方）."""
    if v in VEHICLES:
        return VEHICLES[v][3]
    from .swept_sim import rig

    return rig(v).width * 1000.0


def vehicle_turn_r(v: str) -> float:
    if v in VEHICLES:
        return VEHICLES[v][5]
    from .machine import MACHINES

    m = MACHINES[v]
    return float(m.params.get("tnR", 0) or m.turn_r) * 1000.0


def vehicle_keys() -> list[str]:
    from .swept_sim import truck_keys

    return list(VEHICLES) + truck_keys()


def swept(v: str, a: float | None = None) -> tuple[float, float]:
    """車両 v が外側前輪の横距離 a（省くと最小回転半径）で回るときの (Ro 外側前端角の半径, ri 内側後輪の車体内側の半径) mm."""
    _n, L, F, W, T, R = VEHICLES[v]
    if a is None:
        a = math.sqrt(max(R * R - L * L, 0.0))
    return math.hypot(a + (W - T) / 2.0, L + F), a - (W + T) / 2.0


def corner_need(v: str, defl_deg: float, tangent_mm: float, width_mm: float = 0.0) -> tuple[float, float, float, float]:
    """曲がり角（折れ角 defl_deg）を回るのに要る通路の幅 mm と、そのときの (Ro, ri, Rc 中心線の円の半径)。
    回転中心 O は角の二等分線の上。通路の外の縁（中心線から W/2）は O から Rc＋W/2、内の角は (Rc−W/2)/cos(θ/2) にあるので、
    Rc−W/2＋余裕 ≦ … のように、Ro＋余裕 ≦ Rc＋W/2 と ri − 余裕 ≧ (Rc−W/2)/cos(θ/2)。両方を満たす最小の W は
    Ro − ri·cos(θ/2) ＋ 余裕×(1＋cos(θ/2))。車両は最小回転半径より大きく回ってもよいので a を振って一番狭い W を取る。
    角の手前の直線（tangent_mm）が足りないと大きく回れない（Rc·tan(θ/2) ≦ tangent_mm）."""
    th = math.radians(abs(defl_deg))
    if th < math.radians(2.0):
        return 0.0, 0.0, 0.0, 0.0
    if v not in VEHICLES:                                    # 搬入トラック・トレーラー: 追従の軌跡
        from .swept_sim import corner as sim_corner

        cs = sim_corner(v, defl_deg, tangent_mm / 1000.0, width_mm / 1000.0, MARGIN_MM / 1000.0)
        return cs.need * 1000.0, cs.ro * 1000.0, cs.ri * 1000.0, cs.rc * 1000.0 if cs.ok_turn else -1.0
    c = math.cos(th / 2.0)
    _n, L, _F, _W, _T, R = VEHICLES[v]
    a0 = math.sqrt(max(R * R - L * L, 0.0))
    best = None
    for i in range(0, 601):
        a = a0 + i * 50.0
        ro, ri = swept(v, a)
        if ri <= MARGIN_MM:
            continue
        need = ro - ri * c + MARGIN_MM * (1.0 + c)
        w = max(need, width_mm)
        rc = ro + MARGIN_MM - w / 2.0                       # 外の縁にちょうど沿う中心線の半径（一番小さく回る）
        if rc * math.tan(th / 2.0) > tangent_mm:
            continue
        if best is None or need < best[0]:
            best = (need, ro, ri, rc)
    if best is None:                                         # 直線が短くて回れない: 最小回転半径で回ったとき
        ro, ri = swept(v)
        return ro - ri * c + MARGIN_MM * (1.0 + c), ro, ri, -1.0
    return best


@dataclass
class Corner:
    at: tuple[float, float]
    defl: float                        # 折れ角（度。左折＋）
    need: float                        # 要る幅 mm
    ro: float
    ri: float
    rc: float                          # 中心線の円の半径（−1＝直線が短くて回れない）
    status: str = "OK"


@dataclass
class Check:
    item: str
    status: str
    message: str


@dataclass
class RoutePlan:
    name: str
    pts: list[tuple[float, float]]
    width: float
    vehicle: str
    two_way: bool = False
    corners: list[Corner] = field(default_factory=list)
    plates: list[tuple[tuple[float, float], float, PlateLayout]] = field(default_factory=list)   # (隅, 向き 度, 割付)
    checks: list[Check] = field(default_factory=list)
    quantity: list[tuple[str, float, str]] = field(default_factory=list)

    @property
    def length(self) -> float:
        return sum(math.dist(a, b) for a, b in zip(self.pts, self.pts[1:]))


def _unit(a, b):
    d = math.dist(a, b) or 1.0
    return ((b[0] - a[0]) / d, (b[1] - a[1]) / d)


def route_plan(name: str, pts: list, width: float = 0.0, vehicle: str = "10t", two_way: bool = False,
               plates: bool = True, plate_code: str = "NT22×5×20", across: bool = False) -> RoutePlan:
    pts = [tuple(map(float, p)) for p in pts]
    if width <= 0:
        width = TWO_WAY_MM if two_way else ONE_WAY_MM
    p = RoutePlan(name, pts, width, vehicle, two_way)
    vname, vw, vr = vehicle_name(vehicle), vehicle_width(vehicle), vehicle_turn_r(vehicle)
    sim = vehicle not in VEHICLES
    if sim:
        from .swept_sim import rig
    segs = [math.dist(a, b) for a, b in zip(pts, pts[1:])]
    for i in range(1, len(pts) - 1):
        u1, u2 = _unit(pts[i - 1], pts[i]), _unit(pts[i], pts[i + 1])
        defl = math.degrees(math.atan2(u1[0] * u2[1] - u1[1] * u2[0], u1[0] * u2[0] + u1[1] * u2[1]))
        tan_av = min(segs[i - 1] / (1.0 if i == 1 else 2.0), segs[i] / (1.0 if i == len(pts) - 2 else 2.0))
        need, ro, ri, rc = corner_need(vehicle, defl, tan_av, width)
        st = "OK" if need <= width + 1.0 and rc >= 0 else "NG"
        p.corners.append(Corner(pts[i], defl, need, ro, ri, rc, st))
    c = p.checks
    lane = TWO_LANE_MIN if two_way else ONE_LANE_MIN
    straight = (2.0 * vw + 2.0 * SIDE_MM) if two_way else (vw + 2.0 * SIDE_MM)   # 対面は縁に 0.25 ずつ・すれ違い 0.5
    c.append(Check("通路の幅", "OK" if width >= max(lane, straight) else "NG",
                   f"{'対面' if two_way else '一方'}通行 {width / 1000:.1f}m ≧ 要綱の車道 {lane / 1000:.1f}m・{vname} の車幅 "
                   f"{vw / 1000:.2f}m{'×2' if two_way else ''}＋余裕 → {straight / 1000:.2f}m（建設工事公衆災害防止対策要綱。安衛則 151条の6: 運行経路に必要な幅）"))
    for k, cn in enumerate(p.corners, 1):
        if cn.rc < 0:
            msg = f"角{k}（{abs(cn.defl):.0f}°{'左' if cn.defl > 0 else '右'}）: 手前・先の直線が短く、{vname} が回れない（角を減らすか直線を長く）"
        elif sim and rig(vehicle).catalog_w:
            msg = (f"角{k}（{abs(cn.defl):.0f}°{'左' if cn.defl > 0 else '右'}）: メーカーの表の所要道路幅 {cn.need / 1000:.1f}m"
                   "（後ろの台車がかじを切るポールトレーラー。曲がる角度によらず）"
                   + ("" if cn.status == "OK" else f" → 角を {(cn.need - width) / 1000:.1f}m 拡幅（内側の隅を切る）"))
        else:
            msg = (f"角{k}（{abs(cn.defl):.0f}°{'左' if cn.defl > 0 else '右'}）: "
                   + ("追従の軌跡で外側 R" if sim else "外側前端角 R") + f"{cn.ro / 1000:.1f}m・"
                   + ("内側（トレーラーの内側の辺）R" if sim and _is_trailer(vehicle) else "内側後輪 R") + f"{cn.ri / 1000:.1f}m"
                   f"（中心線 R{cn.rc / 1000:.1f}m）で要る幅 {cn.need / 1000:.1f}m"
                   + ("【目安】" if sim else "")
                   + ("" if cn.status == "OK" else f" → 角を {(cn.need - width) / 1000:.1f}m 拡幅（内側の隅を切る）"))
        c.append(Check(f"曲がり角 {k}", cn.status, msg))
    c.append(Check("最小回転半径", "OK", f"{vname} R{vr / 1000:.1f}m（諸元表。迷う車両は道路構造令の普通自動車 R12m で見る）。"
                                     "曲がり角の内側の隅（仮囲い・柱・山留め）は ri の円より外、外側の障害物は Ro の円より外に"
                                     + ("" if not (sim and _is_trailer(vehicle)) else
                                        "。ポールトレーラーはトレクス PTB212 の表の連結最小回転半径" if rig(vehicle).catalog_w else
                                        "。トレーラー連結車はトラクタの値がカタログに無く、設計車両・車両制限令の 12m で見る【目安】")))
    if sim:
        r = rig(vehicle)
        last = math.dist(pts[-2], pts[-1])
        need_l = r.length * 1000.0 + 2000.0
        c.append(Check("荷下ろしの直線", "OK" if last >= need_l else "要確認",
                       f"終わりの直線 {last / 1000:.1f}m {'≧' if last >= need_l else '＜'} 車長 {r.length:.1f}m＋2m"
                       "（荷下ろしの位置で車体をまっすぐに止める。場内で切り返すなら転回の場所と誘導員。安衛則 151条の6・7）"
                       + ("。トレーラーは公道からゲートへ入る曲がりも同じ軌跡で見る（ゲートの有効幅・歩道の切下げは道路管理者と協議）"
                          if _is_trailer(vehicle) else "")))
    c.append(Check("ゲート・誘導", "OK", "ゲートは通路の幅以上の有効な幅と高さ、扉は引戸か内開き、出入りに交通誘導員（要綱 第20・23）。"
                                      "歩道の切下げは道路管理者と協議（道路に鉄板を置いて段差を消すのは不法占用）。タイヤ洗浄を出口の手前に"))
    if plates:
        _place_plates(p, plate_code, across)
        c.append(Check("敷鉄板", "OK", f"{plate_code}（厚さ 22）を{'横' if across else '縦'}敷き、継ぎ目は千鳥。曲がり角は通路の幅だけ"
                                     "重ねて掃引の範囲を覆う（重ねた端は段差の処理、上下の継ぎ目を揃えない＝半面交互）。板の端・継ぎ目を"
                                     "轍の下に置かない"))
    _quantity(p)
    return p


def _is_trailer(v: str) -> bool:
    from .machine import MACHINES

    return v in MACHINES and MACHINES[v].kind == 14


def _place_plates(p: RoutePlan, code: str, across: bool) -> None:
    """区間ごとに敷鉄板の範囲（曲がり角では通路の幅の半分だけ延ばして重ねる）。隅は区間の向きの右手前。
    縦敷きの 5×20 は 6.1m ずつなので、余りは 5×10（3.0m）で埋めて行き過ぎを 3m 未満に。行き過ぎは曲がり角の重なりへ:
    始めの区間はゲートに、終わりの区間は終わりにそろえ、間の区間は真ん中に."""
    n = len(p.pts)
    half = "NT22×5×10"
    for i, (a, b) in enumerate(zip(p.pts, p.pts[1:])):
        u = _unit(a, b)
        v = (-u[1], u[0])
        ext0 = p.width / 2.0 if i > 0 else 0.0
        ext1 = p.width / 2.0 if i < n - 2 else 0.0
        ln = math.dist(a, b) + ext0 + ext1
        pieces = [plate_layout(ln, p.width, code, along_y=across)]
        if not across and code == "NT22×5×20":
            n20 = int(ln // 6096.0)
            rem = ln - n20 * 6096.0
            if n20 and 0.02 * 3048.0 < rem <= 3048.0 * 1.02:
                pieces = [plate_layout(n20 * 6096.0, p.width, code), plate_layout(rem, p.width, half)]
        total = sum(x.lx for x in pieces)
        over = total - ln
        back = ext0 + (0.0 if i == 0 or n == 2 else over if i == n - 2 else over / 2.0)
        s0 = -back
        for lay in pieces:
            corner = (a[0] + u[0] * s0 - v[0] * lay.ly / 2.0, a[1] + u[1] * s0 - v[1] * lay.ly / 2.0)
            p.plates.append((corner, math.degrees(math.atan2(u[1], u[0])), lay))
            s0 += lay.lx


def _quantity(p: RoutePlan) -> None:
    from .steel_plate import quantity as plate_q

    q = p.quantity
    q.append(("場内通路", round(p.length / 1000.0, 1), f"m・幅 {p.width / 1000:.1f}m・曲がり角 {len(p.corners)}か所"))
    if p.plates:
        q += plate_q([lay for _c, _a, lay in p.plates])
    q.append(("交通誘導員（ゲート）", 1, "人（出入りの時間帯）"))


def _ints(vals) -> str:
    return ",".join(str(int(round(x))) for x in vals)


def part_params(p: RoutePlan) -> dict:
    """部品 ashiba_route のパラメータ。座標は始めの点からの mm（文字のパラメータは 255 字まで）."""
    o = p.pts[0]
    loc = [(x - o[0], y - o[1]) for x, y in p.pts]
    # 通路の帯（左の縁を始めから終わり、右の縁を終わりから始め。角は留め）
    left, right = [], []
    hw = p.width / 2.0
    for i, q in enumerate(loc):
        if i == 0:
            u = _unit(loc[0], loc[1])
            nv, s = (-u[1], u[0]), 1.0
        elif i == len(loc) - 1:
            u = _unit(loc[-2], loc[-1])
            nv, s = (-u[1], u[0]), 1.0
        else:
            u1, u2 = _unit(loc[i - 1], q), _unit(q, loc[i + 1])
            n1, n2 = (-u1[1], u1[0]), (-u2[1], u2[0])
            m = (n1[0] + n2[0], n1[1] + n2[1])
            mm = math.hypot(*m) or 1.0
            nv = (m[0] / mm, m[1] / mm)
            s = 1.0 / max(nv[0] * n1[0] + nv[1] * n1[1], 0.2)
        left.append((q[0] + nv[0] * hw * s, q[1] + nv[1] * hw * s))
        right.append((q[0] - nv[0] * hw * s, q[1] - nv[1] * hw * s))
    band = left + right[::-1]
    ax, ay, ar, aa, at = [], [], [], [], []
    for cn in p.corners:
        if cn.rc <= 0:
            continue
        i = p.pts.index(cn.at)
        q = loc[i]
        u1, u2 = _unit(loc[i - 1], q), _unit(q, loc[i + 1])
        th = math.radians(abs(cn.defl))
        side = 1.0 if cn.defl > 0 else -1.0                  # 左折は左に回転中心
        bis = (u2[0] - u1[0], u2[1] - u1[1])
        bl = math.hypot(*bis) or 1.0
        d = cn.rc / math.cos(th / 2.0)
        o_ = (q[0] + bis[0] / bl * d, q[1] + bis[1] / bl * d)
        t1 = (q[0] - u1[0] * cn.rc * math.tan(th / 2.0), q[1] - u1[1] * cn.rc * math.tan(th / 2.0))
        a0 = math.degrees(math.atan2(t1[1] - o_[1], t1[0] - o_[0]))
        a1 = a0 + side * math.degrees(th)
        ax.append(o_[0])
        ay.append(o_[1])
        ar += [cn.ro, cn.ri]
        aa += [min(a0, a1), max(a0, a1)]
        at.append(0 if cn.status == "OK" else int(round((cn.need - p.width) / 100.0)))    # 拡幅 ×0.1m
    return {"cX": _ints(x for x, _y in loc), "cY": _ints(y for _x, y in loc), "eX": _ints(x for x, _y in band),
            "eY": _ints(y for _x, y in band), "aX": _ints(ax), "aY": _ints(ay), "aR": _ints(ar), "aA": _ints(aa),
            "aW": _ints(at), "rtW": p.width / 1000.0, "rtName": p.name,
            "rtVeh": f"{'対面' if p.two_way else '一方'}通行 幅{p.width / 1000:.1f}m {vehicle_name(p.vehicle).split('（')[0]}"}


def report(plans: list[RoutePlan]) -> str:
    out = ["# 場内の車両動線と敷鉄板", "",
           "出典: 建設工事公衆災害防止対策要綱・道路構造令 第4条・車両制限令 第3条・各社の主要諸元表（ふそう・いすゞ・タダノ）・"
           "日建リース 仮設資材カタログ Vol.10 p394・堀 2018（敷鉄板の重ね敷き）。場内通路の幅を数値で決めた法令は無く、幅・余裕は目安。"
           "搬入トラック・トレーラーの曲がり角は追従の軌跡（トラクタの前軸を円弧に沿わせ、後軸とトレーラーを少しずつ追従させた車体の外形が"
           "中心線から出る量。research_notes/搬入車両/トレーラー.md 4.2）で【目安】、ポールトレーラーはトレクス PTB212 の所要道路幅", ""]
    for p in plans:
        out += [f"## {p.name}", "", f"- 長さ {p.length / 1000:.1f}m・幅 {p.width / 1000:.1f}m（{'対面' if p.two_way else '一方'}通行）・"
                f"車両 {vehicle_name(p.vehicle)}", "", "| 検定 | 判定 | 内容 |", "|---|---|---|"]
        out += [f"| {x.item} | {x.status} | {x.message} |" for x in p.checks]
        out += ["", "| 品名 | 数 | 注 |", "|---|---|---|"] + [f"| {a} | {b:g} | {c} |" for a, b, c in p.quantity] + [""]
    return "\n".join(out)
