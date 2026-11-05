"""搬入トラック・トレーラー連結車が場内通路の曲がり角を回る軌跡（追従＝トラクトリクスで少しずつ動かす）.

開発ループ（2026-11-04 利用者の指定「場内通路にトレーラーも入れて進めて」）。車両の寸法は src/ashiba/machine.py の搬入車両
（種類 13 搬入トラック・14 トレーラー連結車）の値をそのまま使う。

やり方（research_notes/搬入車両/トレーラー.md 4.2 の「追従」。出典で確かめた式ではなく【目安】）:
- 運転手はトラクタ（単車はその車）の前軸の中心を、手前の直線 → 半径 Rg の円弧 → 先の直線に沿わせる（通路の中心線から外へ e ずらす）
- 前軸を少し（0.2m）動かすたびに、後軸の中心を「前の位置から前軸の新しい位置へ向かう直線上で、前軸から L の距離」に置き直す。
  キングピンは後軸の中心の前 c（カプラオフセット）、トレーラーの後軸群の中心も同じやり方でキングピンから L2 の距離に置き直す
- 車体（トラクタ・トレーラー）の外形の点が、通路の中心線（角は外が丸い）からどれだけ外・内へ出るかを見て、要る幅＝
  2×（外・内の大きい方＋余裕）。e は外と内が釣り合うように、Rg は最小（ハンドルいっぱい）から角の手前の直線が許すところまで振って
  一番狭く済むもの
- ハンドルいっぱいの前軸の半径は、最小回転半径 R（最外側のわだち）から 後軸の中心 Rr＝√(R²−L²)−Tf/2、前軸の中心 √(Rr²＋L²)
  （Tf は前の輪距。連結車は machine.swept_path と同じく後ろの輪距＋0.2）
- 定常円旋回（machine.swept_path）は曲がり続けたときの値で、直角に曲がり終えるときは軌跡がそこまで内へ入らない。長い円弧を回ると
  定常円旋回の値に近づく（テストで照合）
- ポールトレーラーは後ろの台車がかじを切るので追従では表せず、メーカーの表の所要道路幅（トレクス PTB212 と UD GW 10.5m）を使う
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .machine import MACHINES

DS = 0.2               # 前軸を動かす刻み m
SIDE_STEP = 0.6        # 車体の横の辺の点の間隔 m


@dataclass(frozen=True)
class Rig:
    key: str
    name: str
    L: float                      # 前軸〜後軸（2軸は2本の中心）
    F: float                      # 前軸〜前端
    B: float                      # 前軸〜後端
    W: float                      # 車体の幅
    rg_min: float                 # ハンドルいっぱいのときの前軸の中心の半径（ポールトレーラーは使わない）
    c: float = 0.0                # カプラオフセット（後軸の中心から前が +）
    L2: float = 0.0               # キングピン〜トレーラーの後軸群の中心
    tF: float = 0.0               # キングピン〜トレーラーの前端
    tB: float = 0.0               # キングピン〜トレーラーの後端
    tW: float = 0.0               # トレーラーの幅
    trailer: bool = False
    catalog_w: float = 0.0        # メーカーの表の所要道路幅（ポールトレーラー）

    @property
    def width(self) -> float:
        return max(self.W, self.tW)

    @property
    def length(self) -> float:
        if not self.trailer:
            return self.F + self.B
        return self.F + self.L - self.c + self.tB


def truck_keys() -> list[str]:
    """場内通路に使える搬入車両（machine の種類 13・14）."""
    return [k for k, m in MACHINES.items() if m.kind in (13, 14)]


def rig(key: str) -> Rig:
    m = MACHINES[key]
    ps = m.params
    nR, sp = int(ps.get("nRear", 1)), float(ps.get("rearSp", 0))
    L = float(ps["wb"]) + (sp / 2 if nR >= 2 else 0.0)
    F = float(ps["frOv"])
    B = float(ps["carL"]) - F
    W = float(ps["carW"])
    R = float(ps.get("tnR", 0) or m.turn_r)
    trailer = m.kind == 14
    tf = float(ps.get("trT", W - 0.4)) + (0.2 if trailer else 0.0)
    rr = math.sqrt(max(R * R - L * L, 0.0)) - tf / 2
    rg = math.hypot(rr, L)
    if not trailer:
        return Rig(key, m.name, L, F, B, W, rg)
    L2 = float(ps["tlAx"]) + (int(ps.get("tlN", 1)) - 1) * float(ps.get("tlSp", 0)) / 2
    tW = max(float(ps["tlW"]), float(ps.get("cgW", 0) or 0))
    cat = float(ps.get("tkW", 0) or 0) if int(ps.get("tlK", 1)) == 3 else 0.0
    return Rig(key, m.name, L, F, B, W, rg, float(ps.get("kpC", 0)), L2, float(ps["tlF"]), float(ps["tlB"]), tW, True, cat)


def _outline(front: float, back: float, w: float) -> list[tuple[float, float]]:
    """車体の外形の点（基準点から前が +x、左が +y）: 4隅と横の辺の点."""
    n = max(int(math.ceil((front + back) / SIDE_STEP)), 1)
    xs = [front - (front + back) * i / n for i in range(n + 1)]
    return [(x, s * w / 2) for x in xs for s in (1.0, -1.0)]


def simulate(r: Rig, guide: list[tuple[float, float]]):
    """前軸の中心を guide（等間隔の点）に沿わせ、各時点の車体の外形の点（世界の座標）を返す. 始めは guide の向きにまっすぐ."""
    hx, hy = guide[1][0] - guide[0][0], guide[1][1] - guide[0][1]
    hl = math.hypot(hx, hy)
    hx, hy = hx / hl, hy / hl
    rear = (guide[0][0] - hx * r.L, guide[0][1] - hy * r.L)
    kp = (rear[0] + hx * r.c, rear[1] + hy * r.c)
    tax = (kp[0] - hx * r.L2, kp[1] - hy * r.L2)
    body = _outline(r.F, r.B, r.W)
    tbody = _outline(r.tF, r.tB, r.tW) if r.trailer else []
    for f in guide:
        dx, dy = rear[0] - f[0], rear[1] - f[1]
        d = math.hypot(dx, dy) or 1.0
        rear = (f[0] + dx / d * r.L, f[1] + dy / d * r.L)
        hx, hy = (f[0] - rear[0]) / r.L, (f[1] - rear[1]) / r.L
        pts = [(f[0] + hx * x - hy * y, f[1] + hy * x + hx * y) for x, y in body]
        if r.trailer:
            kp = (rear[0] + hx * r.c, rear[1] + hy * r.c)
            dx, dy = tax[0] - kp[0], tax[1] - kp[1]
            d = math.hypot(dx, dy) or 1.0
            tax = (kp[0] + dx / d * r.L2, kp[1] + dy / d * r.L2)
            gx, gy = (kp[0] - tax[0]) / r.L2, (kp[1] - tax[1]) / r.L2
            pts += [(kp[0] + gx * x - gy * y, kp[1] + gy * x + gx * y) for x, y in tbody]
        yield f, rear, tax, pts


def corner_guide(th: float, rg: float, before: float, after: float) -> list[tuple[float, float]]:
    """角を原点、手前の直線を −x から +x、左へ th（ラジアン）曲がる中心線に、半径 rg の円弧で沿う前軸の道（DS の刻み）."""
    t = rg * math.tan(th / 2)
    out = []
    s, arc = 0.0, rg * th
    total = before + arc + after
    while s <= total + 1e-9:
        if s < before:
            out.append((-t - before + s, 0.0))
        elif s < before + arc:
            a = (s - before) / rg
            out.append((-t + rg * math.sin(a), rg - rg * math.cos(a)))
        else:
            q = s - before - arc
            out.append((t * math.cos(th) + q * math.cos(th), t * math.sin(th) + q * math.sin(th)))
        s += DS
    return out


def lateral(q: tuple[float, float], th: float) -> float:
    """点 q の中心線からのずれ m（内＝左が +）. 中心線は手前の半直線（x≦0, y＝0）と先の半直線（原点から th の向き）、角の外は丸い."""
    x, y = q
    best = None
    if x <= 0:
        best = (abs(y), y)
    ux, uy = math.cos(th), math.sin(th)
    t = x * ux + y * uy
    if t >= 0:
        p = ux * y - uy * x
        if best is None or abs(p) < best[0]:
            best = (abs(p), p)
    v = math.hypot(x, y)
    if best is None or v < best[0]:
        best = (v, -v)
    return best[1]


@dataclass
class CornerSim:
    need: float          # 要る幅 m
    rg: float            # 前軸の円弧の半径 m
    e: float             # 前軸の道を中心線から外へずらす量 m
    ro: float            # 回転の中心から外側の一番遠い点 m（円弧の範囲）
    ri: float            # 回転の中心から内側の一番近い点 m（円弧の範囲）
    rc: float            # 回転の中心から中心線までの半径 m（rg − e）
    inner: float         # 内へ出る量 m（中心線から。e を入れたあと）
    outer: float         # 外へ出る量 m
    ok_turn: bool = True     # 角の手前・先の直線で回れる


def _evaluate(r: Rig, th: float, rg: float, margin: float):
    t = rg * math.tan(th / 2)
    before = r.length + 2.0
    after = 1.5 * r.length + 2.0
    cand = []
    for _f, _rr, _ta, pts in simulate(r, corner_guide(th, rg, before, after)):
        ds = [(lateral(q, th), q) for q in pts]
        cand.append(max(ds)[1])
        cand.append(min(ds)[1])
    bx, by = -math.sin(th / 2), math.cos(th / 2)           # 内へ向く二等分線
    e = 0.0
    inn = out = 0.0
    for _ in range(4):
        s = e / math.cos(th / 2)
        tx, ty = -bx * s, -by * s                          # 外へ動かす
        lats = [lateral((q[0] + tx, q[1] + ty), th) for q in cand]
        inn, out = max(lats), -min(lats)
        if abs(inn - out) < 0.01:
            break
        e += (inn - out) / 2
    need = 2 * (max(inn, out) + margin)
    s = e / math.cos(th / 2)
    ox, oy = -t - bx * s, rg - by * s                       # 前軸の円弧の中心（外へ動かしたあと）
    a0, a1 = -math.pi / 2, -math.pi / 2 + th
    ro, ri = 0.0, 1e9
    for q in cand:
        qx, qy = q[0] - bx * s, q[1] - by * s
        a = math.atan2(qy - oy, qx - ox)
        if a0 - 1e-6 <= a <= a1 + 1e-6:
            d = math.hypot(qx - ox, qy - oy)
            ro, ri = max(ro, d), min(ri, d)
    return CornerSim(need, rg, e, ro, ri if ri < 1e9 else 0.0, rg - e, inn, out)


def corner(key: str, defl_deg: float, tangent_m: float, width_m: float = 0.0, margin: float = 0.25) -> CornerSim | None:
    """車両 key が折れ角 defl_deg の角を回るのに要る幅. 角の手前・先の直線 tangent_m が許す半径（rg·tan(θ/2) ≦ tangent_m）で一番狭く
    済むものを探す（width_m より狭くはしない）。2° 未満は None。ポールトレーラーはメーカーの表の所要道路幅."""
    th = math.radians(abs(defl_deg))
    if th < math.radians(2.0):
        return None
    r = rig(key)
    if r.catalog_w:
        # 外側が連結最小回転半径、内側はそこから所要道路幅だけ内（後ろの台車がかじを切るので中心線の円はその真ん中）
        R = float(MACHINES[key].params.get("tnR", 0) or MACHINES[key].turn_r)
        rc = R - r.catalog_w / 2
        ok = rc * math.tan(th / 2) <= tangent_m
        h = r.catalog_w / 2 - margin
        return CornerSim(r.catalog_w, rc, 0.0, R, R - r.catalog_w, rc, h, h, ok)
    lim = tangent_m / math.tan(th / 2)
    ok = r.rg_min <= lim
    best = None
    rg = r.rg_min
    step = 1.0
    top = min(lim, r.rg_min + 24.0) if ok else r.rg_min
    while rg <= top + 1e-9:
        c = _evaluate(r, th, rg, margin)
        if best is None or max(c.need, width_m) < max(best.need, width_m) - 1e-6:
            best = c
        if c.need <= width_m:
            break
        rg += step
    if best.rg > r.rg_min and best.rg < top:                 # 細かく
        for d in (-0.5, 0.5):
            c = _evaluate(r, th, best.rg + d, margin)
            if c.need < best.need:
                best = c
    best.ok_turn = ok
    return best
