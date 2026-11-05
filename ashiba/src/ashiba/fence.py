"""歩行者の安全（仮設歩道の区画・バリケード・車両防護柵）（開発ループ 2026-11-01: 他に必要な仮設材の6番。部品 ashiba_fence）.

線（ポリライン）に沿って、選んだ製品を規格の1基ずつ並べる（利用者の指定 2026-11-01: イメージじゃなく実際の規定の長さで発注できる
くらい詳細に）。日建リース工業 仮設資材カタログ Vol.10:
- PPフェンス PP1512G（p397）: 1,500×1,214・5.0kg、PPジョイント PPJ 0.08kg・PPウェイト PPW 13.0kg（支柱ごとに1つ）・PPパイプ PPP 0.1kg
- スタンドバリケード C型 BS020（p397）: H935・幅 460・4.35kg（クランプつき）。間に単管の横桟を上下2段
- バルカンバリア JW4型 BBJW4（p396）: 4,115×560×814・463kg（車両の侵入防止。アンカーで固定すると防護柵の設置基準の A種相当）
- 仮設ガードレール GR50（p395）: 5.0m・567.29kg（H-300 の台にガードレール、支柱 φ114.3 を 2m ごと）

建設工事公衆災害防止対策要綱（建築工事編）: 歩行者用通路は幅 0.75m 以上（歩行者の多い所は 1.5m 以上）・有効高さ 2.1m 以上、車両の
通路とは柵等で区分、出入口に誘導員（第20〜24 の趣旨。数値の条番号は原典で確かめる）。夜間は保安灯で柵の位置を示す（目安）.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .opening_guard import TUBES, order_table

# 種類 → (名前, 品番, 1基の長さ mm, 高さ mm, 奥行 mm, kg, 車両を止めるか)
KINDS = {
    1: ("PPフェンス", "PP1512G", 1500.0, 1214.0, 300.0, 5.0, False),
    2: ("スタンドバリケード C型＋単管", "BS020", 1800.0, 935.0, 460.0, 4.35, False),
    3: ("バルカンバリア JW4型", "BBJW4", 4115.0, 814.0, 560.0, 463.0, True),
    4: ("仮設ガードレール 5.0M", "GR50", 5000.0, 775.0, 300.0, 567.29, True),
}
KIND_KEYS = {"pp": 1, "stand": 2, "vulcan": 3, "guardrail": 4}
WALK_MIN, WALK_BUSY, WALK_H = 750.0, 1500.0, 2100.0
BAR_TUBE = 2000                        # スタンドの間の横桟（単管 2.0M を 1.8m の間に掛ける）


@dataclass
class Check:
    item: str
    status: str
    message: str


@dataclass
class FenceRun:
    name: str
    pts: list[tuple[float, float]]
    kind: int = 1
    walk_w: float = 0.0                # 歩行者通路の幅（0＝見ない）
    busy: bool = False                 # 歩行者が多い
    road_side: bool = False            # 車両の通路と接する
    units: list[int] = field(default_factory=list)      # 区間ごとの基数
    over: list[float] = field(default_factory=list)     # 区間ごとの行き過ぎ mm
    checks: list[Check] = field(default_factory=list)
    quantity: list[tuple[str, float, str]] = field(default_factory=list)

    @property
    def length(self) -> float:
        return sum(math.dist(a, b) for a, b in zip(self.pts, self.pts[1:]))


def plan_run(r: FenceRun) -> FenceRun:
    name, code, unit, h, _d, kg, stops = KINDS[r.kind]
    r.units, r.over = [], []
    for a, b in zip(r.pts, r.pts[1:]):
        L = math.dist(a, b)
        n = max(1, math.ceil(L / unit - 0.02))
        r.units.append(n)
        r.over.append(0.0 if r.kind == 2 else n * unit - L)  # スタンドは間を詰めて合わせる
    c = r.checks = []
    total = sum(r.units)
    rigid = r.kind in (3, 4)                                 # 防護柵は切れない（PPフェンスは端の1枚を重ねる）
    c.append(Check("割付", "OK" if not rigid or max(r.over) <= unit * 0.5 else "WARN",
                   f"{name}（{code}・1基 {unit:.0f}・高さ {h:.0f}）を {total}基。区間の端の行き過ぎ 最大 {max(r.over):.0f}"
                   + ("（区間の線を基の長さに合わせる）" if rigid and max(r.over) > unit * 0.5 else
                      "（端の1枚を重ねる）" if r.kind == 1 and max(r.over) > 0 else "")))
    if r.walk_w:
        need = WALK_BUSY if r.busy else WALK_MIN
        c.append(Check("歩行者通路の幅", "OK" if r.walk_w >= need else "NG",
                       f"幅 {r.walk_w:.0f} ≧ {need:.0f}（{'歩行者の多い所 ' if r.busy else ''}建設工事公衆災害防止対策要綱）・有効高さ "
                       f"{WALK_H:.0f} 以上（上に足場・朝顔があれば防護）"))
    if r.road_side:
        c.append(Check("車両との区分", "OK" if stops else "WARN",
                       f"車両の通路と接する: {name}" + ("（車両の侵入を防ぐ）" if stops else " は車両を止めない。工事車両が並走する所は"
                                                     "バルカンバリア・仮設ガードレールなど防護柵を")))
    c.append(Check("表示・夜間", "OK", "歩行者の誘導の表示、夜間は保安灯で柵の位置を示す（目安）、出入口に誘導員"))
    _quantity(r)
    return r


def _quantity(r: FenceRun) -> None:
    name, code, unit, _h, _d, kg, _s = KINDS[r.kind]
    q = r.quantity = []
    n = sum(r.units)
    segs = len(r.units)
    if r.kind == 1:
        q.append((f"{code} {name}", n, f"枚（{kg:g}kg）"))
        q.append(("PPJ PPジョイント", n - 1, "個（0.08kg）"))
        q.append(("PPW PPウェイト", n + segs, "個（13.0kg。支柱ごと）"))
    elif r.kind == 2:
        q.append(("BS020 スタンドバリケード C型", n + segs, "台（4.35kg。クランプつき）"))
        q.append((f"単管 {BAR_TUBE / 1000:.1f}M（横桟 上下2段）", 2 * n, f"本（{TUBES[BAR_TUBE]:g}kg）"))
    else:
        q.append((f"{code} {name}", n, f"基（{kg:g}kg）"))
    if r.kind == 3:
        q.append(("BBJW4 の連結（付属のピン）・アンカー（長期の規制）", n, "か所"))
    elif r.kind == 4:
        q.append(("ジョイント M16 ボルト（GR50 の継ぎ）", 4 * max(0, n - 1), "本"))
    q.append(("保安灯（夜間）", math.ceil(r.length / 10000.0) + 1, "個（10m ごと＋端の目安）"))


def part_params(r: FenceRun) -> dict:
    o = r.pts[0]
    return {"fcKind": r.kind, "cX": ",".join(str(int(round(x - o[0]))) for x, _y in r.pts),
            "cY": ",".join(str(int(round(y - o[1]))) for _x, y in r.pts), "fcName": r.name}


def report(runs: list[FenceRun]) -> str:
    out = ["# 歩行者の安全（仮設歩道の区画・バリケード・防護柵）", "",
           "出典: 日建リース工業 仮設資材カタログ Vol.10 p395〜397、建設工事公衆災害防止対策要綱（歩行者用通路 幅 0.75m・多い所 1.5m・"
           "有効高さ 2.1m）。保安灯の間隔は目安", "", "| 柵 | 長さ | 判定 | 内容 |", "|---|---|---|---|"]
    tot: dict[str, list] = {}
    for r in runs:
        for x in r.checks:
            out.append(f"| {r.name} | {r.length / 1000:.1f}m | {x.status} | {x.item}: {x.message} |")
        for a, n, u in r.quantity:
            row = tot.setdefault(a, [0.0, u])
            row[0] += n
    out += order_table(tot, ("PP1512G", "PPJ", "PPW", "BS020", "単管", "BBJW4", "GR50", "ジョイント", "保安灯")) + [""]
    return "\n".join(out)
