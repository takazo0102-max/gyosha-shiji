"""根切り（掘削）の形・根切り図・土量（利用者の指定 2026-11-02: 根切り図も作れるようにして 掘削のオブジェクト躯体選択して
掘削底深さと法面を選べるようにして ねぎりずを作成できるようにしてちょ 山留めまでの中途半ば部分は掘削するようにして）.

選んだ躯体（基礎・地中梁・耐圧盤・ピットの床など）の外形と下端から、掘削の面を細かい升目の高さで求める:

  床付け（掘削底）＝ 躯体の下端 − 地業の厚さ（捨てコン・砕石）。--depth を指定すれば全部をその深さで（平らに）
  法尻 ＝ 躯体の外形を余掘りの幅だけ広げた線。そこから法面の勾配 1:n（高さ 1 に水平 n）で GL まで上げる
  升目の掘削面の高さ ＝ min(GL, 各躯体の 床付け＋法尻からの距離÷n)。深さの違う躯体・重なり・角はこれでまとまる

山留め（名前に「山留」が付くレイヤーの壁か、選んだ閉じた線）があれば、その内側は山留めの面まで垂直に掘り、内側の残り
（躯体の掘削と山留めの間の中途半端な所）は一般の根切り底（既定は躯体の床付けのいちばん浅い高さ）まで掘る。山留めの外は掘らない。
根切りと根切りの間に残る幅 1.1m 以下の細い地山も掘る（隣の浅い方の床付けまで。GLOOBE の根切りの手引きの決め）。

法面の勾配の「自動」は公共建築数量積算基準（令和5年）の法の係数: 深さ 1.5m 未満は垂直、1.5〜5m は 1:0.3、5m 以上は 1:0.6
（普通土）。砂の地山は 1.5m 以上を 1:1.5（国交省 土木工事数量算出要領の目安）。

出典:
- 労働安全衛生規則 356条（手掘りの掘削面のこう配: 岩盤・堅い粘土は高さ 5m 未満 90°・5m 以上 75°、その他の地山は 2m 未満 90°・
  2〜5m 75°・5m 以上 60°。奥行 2m 以上の水平な段で区切る）・357条（砂は 35° 以下か高さ 5m 未満、発破等で崩れやすい地山は 45° 以下
  か 2m 未満）・361条（崩壊のおそれは土止め支保工）。機械掘削には356条は掛からないが、同じ値を目安に見る
- 建築基準法施行令136条の3第4項（深さ 1.5m 以上の根切りは山留め。崩壊のおそれ等が無い場合を除く。公衆災害防止対策要綱の 1.5m は
  令和元年の改正で消えた）、安衛法施行令6条9号・10号（掘削面の高さ 2m 以上は地山の掘削作業主任者、土止め支保工は作業主任者）
- 公共建築数量積算基準（令和5年）第3編: 作業上のゆとり幅 0.5m（余掘り。土間・犬走り等は 0.1m）・法の係数・山留め壁と躯体間の
  余幅 1.0m（本文 p.7）、砂利地業等の数量は面積×厚さで躯体側面より 0.1m の出幅（本文 p.9）。公共建築工事標準仕様書（令和7年版）
  4.6.3: 砂利地業 60mm・4.6.4: 捨コン 50mm（特記がなければ。本文 p.23）。土間は砂利地業の上に防湿層を直接施工（4.6.3(5)・4.6.5(3)）
  なので捨コンは既定で無し（目安）。土量変化率 L は農水省の施工パッケージ型積算基準の値（建築では目安）。調べたメモは docs/調査_根切り.md
- 埋戻し（GLOOBE 2026 の埋め戻し形状に当たる。利用者の指定 2026-11-02「全部入れて」）: 公共建築数量積算基準（令和5年）本文 p.7
  「根切りの数量から根切り基準線以下の基礎又は地下構築物の体積、砂利地業及び捨コンクリートの体積を控除した数量」、建設発生土は
  「根切り及びすきとりの数量から埋戻し及び盛土の数量を減じた数量」（p.7〜8）。土砂は地山数量で、締固めによる減少は考えない（p.6）。
  ピット・地下室（名前・レイヤーに「ピット」「地下」）は床から GL までを空洞として埋め戻さない。10t ダンプ 1台の積載は地山の土砂で
  5.5m³（長崎県 土木積算基準 残土の注意事項 H19.4.1。目安）。搬出が 500m³ 以上は再生資源利用促進計画の作成・掲示・5年保存（資源
  有効利用促進法の省令改正 R5.1.1 施行。国交省 建設業課「建設工事から発生する土の搬出先の明確化等」p.2〜3）
- 沿道掘削（利用者の指定 2026-11-02 の「各図面を参考に」の続き。施工図の手引きの根切・山留計画図）: 東京都北多摩北部建設事務所
  「沿道掘削協議申請案内」p.1〜2（https://www.kensetsu.metro.tokyo.lg.jp/documents/d/kensetsu/p_endoukussaku）。沿道区域は道路
  境界から、前面道路の総幅員 20m 以上で 5m・6m 以上 20m 未満で 3m・6m 未満で総幅員の 1/2。道路境界線から 45 度の影響斜線より
  深く掘るときは道路管理者と事前協議（道路法44条の沿道区域。区市町村の要綱で深さの基準が違うので管理者に確かめる）。
  山留めの H 鋼（外づら）と道路境界の離隔は最低 5cm（同 p.2）
- 釜場（施工図の手引き p.24・p.36: 排水は水中ポンプ、下水へは沈砂槽を通して届出）: 公的な寸法の基準は無いので、□1000×800・
  床付けから 600 掘り下げ・周りに砕石 200 を【目安】とする（設備施工の教科書 地下ピット湧水処理と釜場設計、ミキヤ 釜場排水
  透水ネット付パイプ。docs/調査_根切り.md・reports/根切り図の徹底調査.md の B1）。自動は、躯体（出幅 0.1m）の無い平らな床付けの
  うち、いちばん深く、掘削の縁（山留め際）に近い所に1か所。レイヤー名に「釜場」の閉じた線を選べばその形で
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

# 既定（調べた値は docs/調査_根切り.md。目安は帳票にそう書く）
MARGIN_MM = 500.0                # 余掘り（積算基準の作業上のゆとり幅 0.5m）
GRAVEL_MM = 60.0                 # 砕石（砂利）地業の厚さ（標仕 4.6.3 特記なし）
LEAN_MM = 50.0                   # 捨てコンの厚さ（標仕 4.6.4 特記なし）
BASE_MM = GRAVEL_MM + LEAN_MM    # 地業の厚さの合計 110
DOMA_MARGIN_MM = 100.0           # 土間・犬走り等の余掘り（積算基準 0.1m）
DOMA_GRAVEL_MM = 60.0            # 土間の砕石
DOMA_LEAN_MM = 0.0               # 土間の捨てコン（防湿層を砂利の上に直接。目安）
DOMA_WORDS = ("土間", "犬走", "DOMA")   # 名前・レイヤーにこれがあれば土間とみなす
SPREAD_MM = 100.0                # 地業の出幅（積算基準 砂利地業等: 躯体側面より 0.1m）
YAMADOME_GAP_MM = 1000.0         # 山留め壁と躯体の間の余幅（積算基準の標準 1.0m）
VOID_WORDS = ("ピット", "地下", "PIT")   # 名前・レイヤーにこれがあれば、床から GL までを空洞（埋め戻さない）
DUMP_M3 = 5.5                    # 10t ダンプ 1台の積載（地山の土砂。長崎県 H19 の換算値。目安）
RECYCLE_M3 = 500.0               # 搬出がこれ以上は再生資源利用促進計画（資源有効利用促進法の省令 R5.1.1〜）
KAMABA_W, KAMABA_D = 1000.0, 800.0    # 釜場の大きさ（目安）
KAMABA_DEPTH_MM = 600.0          # 床付けからの掘り下げ（目安）
KAMABA_GRAVEL_MM = 200.0         # 釜場の周りの砕石（目安。有孔パイプの周りに巻く）
ROAD_GAP_MM = 50.0               # 山留めの H 鋼（外づら）と道路境界の離隔の最低（北多摩北部建設事務所 沿道掘削協議申請案内 p.2）


def endo_width(road_w_mm: float) -> float:
    """沿道区域の幅 mm（道路境界から。前面道路の総幅員 20m 以上 5m・6m 以上 3m・6m 未満は総幅員の 1/2）."""
    if road_w_mm >= 20000.0:
        return 5000.0
    if road_w_mm >= 6000.0:
        return 3000.0
    return road_w_mm / 2.0
LEVEL_COLORS = ((1.00, 0.90, 0.55), (0.98, 0.72, 0.35), (0.90, 0.50, 0.25), (0.75, 0.30, 0.20), (0.55, 0.20, 0.35),
                (0.35, 0.20, 0.50))   # 床付けの高さの色分け（浅い→深い）
LEVEL_GRAYS = ((0.88, 0.88, 0.88), (0.75, 0.75, 0.75), (0.62, 0.62, 0.62), (0.50, 0.50, 0.50), (0.38, 0.38, 0.38),
               (0.25, 0.25, 0.25))
SLOPES = (0.0, 0.3, 0.5, 0.8, 1.0, 1.5)   # 法面の勾配 1:n の選び（0＝垂直＝山留め。None＝自動）
STRIP_MM = 1100.0                # これ以下の幅で根切りの間に残る地山は掘る（GLOOBE の手引きの例）
LOOSE = {"岩盤・堅い粘土": 1.25, "その他": 1.20, "砂": 1.20, "崩れやすい（発破等）": 1.20}   # 土量変化率 L（目安）
SOILS = {"岩盤・堅い粘土": (5000.0, 90.0, 75.0, None), "その他": (2000.0, 90.0, 75.0, (5000.0, 60.0)),
         "砂": (5000.0, 35.0, None, None), "崩れやすい（発破等）": (2000.0, 45.0, None, None)}
YAMADOME_DEPTH_MM = 1500.0       # これ以上の深さを垂直に掘るなら山留め（建築基準法施行令136条の3第4項）
FOREMAN_MM = 2000.0              # 掘削面の高さがこれ以上は地山の掘削作業主任者（安衛法施行令6条9号）
STEP_MAX_CELLS = 250_000         # 升目の数の上限（越えれば升目を粗く）


@dataclass
class Footprint:
    """躯体1つの平面の外形（mm）と下端の高さ（プロジェクトの高さ mm）."""
    name: str
    pts: list[tuple[float, float]]
    bottom: float
    kind: str = "基礎"                    # "基礎"（基礎・地中梁・耐圧盤など）・"土間"（土間・犬走り等）・"地下"（ピット・地下室の床）
    top: Optional[float] = None           # 上端（省くと GL まで躯体とみなす）


@dataclass
class Check:
    item: str
    status: str
    message: str


@dataclass
class Negiri:
    name: str
    zones: list[Footprint]
    gl: float = 0.0                       # GL（設計 GL の高さ mm）
    margin: float = MARGIN_MM             # 基礎の余掘り
    gravel: float = GRAVEL_MM             # 基礎の砕石
    lean: float = LEAN_MM                 # 基礎の捨てコン
    doma_margin: float = DOMA_MARGIN_MM   # 土間の余掘り・砕石・捨てコン
    doma_gravel: float = DOMA_GRAVEL_MM
    doma_lean: float = DOMA_LEAN_MM
    slope: Optional[float] = None         # 1:n の n（0＝垂直・None＝自動＝積算基準の法の係数）
    depth: Optional[float] = None         # 掘削底を全部この高さに（プロジェクトの高さ mm）
    soil: str = "その他"
    yamadome: list = field(default_factory=list)   # 山留めの内側の面の多角形（mm）。空＝山留め無し
    road: list = field(default_factory=list)       # 道路境界線 [((x, y), (x, y)), …]（mm）。空＝沿道掘削を見ない
    road_width: float = 0.0               # 前面道路の総幅員 mm（沿道区域の幅を決める）
    kamaba: list = field(default_factory=list)     # 釜場の形 [多角形]（選んだ線）
    kamaba_auto: int = 0                  # 自動で置く釜場の数（0＝置かない）
    kamaba_depth: float = KAMABA_DEPTH_MM
    general: Optional[float] = None       # 山留めの内側の一般の根切り底（省くと床付けのいちばん浅い高さ）
    step: float = 50.0                    # 升目 mm（広い現場は STEP_MAX_CELLS に収まるよう粗く）
    # 結果
    origin: tuple = (0.0, 0.0)
    nx: int = 0
    ny: int = 0
    z: list = field(default_factory=list)          # 升目の掘削面の高さ（行 j・列 i）
    levels: list = field(default_factory=list)     # 床付けの高さ（浅い順）
    top_rings: list = field(default_factory=list)  # 法肩（掘削の外形。GL）
    bottom_rings: dict = field(default_factory=dict)   # 床付けの高さ → 法尻の輪（その高さの平らな所の外形）
    edge_rings: dict = field(default_factory=dict)     # 床付けの高さ → その高さからさらに深く掘る所の縁（下の段の法肩）
    volume: float = 0.0                   # 掘削土量 m³（地山）
    strips: int = 0                       # 埋めた細い地山の升目の数
    slopes: list = field(default_factory=list)    # 躯体ごとの（深さ, 勾配 n）
    area: float = 0.0                     # 掘削の面積（法肩の内）m²
    ground: dict = field(default_factory=dict)   # 地業の数量 {"砕石": (面積 m², 体積 m³), "捨てコン": (…)}（出幅 0.1m）
    gaps: list = field(default_factory=list)     # 山留め壁と躯体の間 [(躯体の名前, 距離 mm, はみ出す)]
    body: float = 0.0                     # 根切り基準線（GL）以下の躯体の体積 m³（ピット・地下室の空洞を含む）
    backfill: float = 0.0                 # 埋戻し m³（地山。積算基準: 根切り−躯体−砕石−捨てコン）
    fill: list = field(default_factory=list)       # 升目の埋戻しの厚さ mm
    fill_rings: list = field(default_factory=list)  # 埋戻しの範囲の輪
    endo: dict = field(default_factory=dict)        # 沿道掘削 {"zone", "inside", "over", "worst", "near"}（road が無ければ空）
    pits: list = field(default_factory=list)        # 置いた釜場 [{"pts", "floor", "bottom", "auto"}]
    checks: list[Check] = field(default_factory=list)

    @property
    def base(self) -> float:
        """基礎の地業の厚さ（砕石＋捨てコン）."""
        return self.gravel + self.lean


def _seg_dist(p, a, b) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def inside(p, poly) -> bool:
    x, y = p
    n = len(poly)
    c = False
    for i in range(n):
        (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % n]
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0) + x0:
            c = not c
    return c


def poly_dist(p, poly) -> float:
    """点から多角形までの距離（中は 0）."""
    if inside(p, poly):
        return 0.0
    return min(_seg_dist(p, poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly)))


def _convex(poly) -> bool:
    s = 0
    for i in range(len(poly)):
        (ax, ay), (bx, by), (cx, cy) = poly[i - 2], poly[i - 1], poly[i]
        cr = (bx - ax) * (cy - by) - (by - ay) * (cx - bx)
        if abs(cr) > 1e-6:
            if s and (cr > 0) != (s > 0):
                return False
            s = cr
    return True


def _edge_dist_fn(poly):
    """凸の多角形は辺ごとの外向きの距離の大きい方（法面の角が尖る＝普通の根切りの形）、凹は点からの距離（角は丸い）."""
    if len(poly) >= 3 and _convex(poly):
        pts = poly if _area(poly) > 0 else list(reversed(poly))
        lines = []
        for i in range(len(pts)):
            (ax, ay), (bx, by) = pts[i], pts[(i + 1) % len(pts)]
            L = math.hypot(bx - ax, by - ay)
            if L > 1e-6:
                lines.append((ax, ay, (by - ay) / L, -(bx - ax) / L))     # 外向きの法線（反時計回りの右）
        return lambda p: max(0.0, max((p[0] - ax) * nx + (p[1] - ay) * ny for ax, ay, nx, ny in lines))
    return lambda p: poly_dist(p, poly)


def zone_slope(n: Negiri, depth_mm: float) -> float:
    """その深さで使う勾配 1:n の n（指定が無ければ積算基準の法の係数。砂は 1.5m 以上を 1:1.5）."""
    if n.slope is not None:
        return n.slope
    if depth_mm < YAMADOME_DEPTH_MM:
        return 0.0
    if n.soil == "砂":
        return 1.5
    return 0.3 if depth_mm < 5000.0 else 0.6


def is_doma(f: Footprint) -> bool:
    return f.kind == "土間"


def margin_of(n: Negiri, f: Footprint) -> float:
    return n.doma_margin if is_doma(f) else n.margin


def layers_of(n: Negiri, f: Footprint) -> tuple[float, float]:
    """(砕石, 捨てコン) の厚さ mm."""
    return (n.doma_gravel, n.doma_lean) if is_doma(f) else (n.gravel, n.lean)


def base_of(n: Negiri, f: Footprint) -> float:
    return sum(layers_of(n, f))


def floor_level(n: Negiri, f: Footprint) -> float:
    """床付け（掘削底）の高さ: --depth か、躯体の下端−地業の厚さ（砕石＋捨てコン）."""
    return n.depth if n.depth is not None else f.bottom - base_of(n, f)


def solve(n: Negiri) -> Negiri:
    """升目の掘削面の高さと、法肩・法尻の輪・土量・判定."""
    zones = [f for f in n.zones if len(f.pts) >= 3]
    if not zones and not n.yamadome:
        n.checks = [Check("躯体", "NG", "掘る躯体が無い（床・梁・柱・壁を選ぶ）")]
        return n
    lv = {id(f): floor_level(n, f) for f in zones}
    deep = max([n.gl - v for v in lv.values()] + [0.0])
    reach = max([n.margin] + [margin_of(n, f) for f in zones]) + deep * max(zone_slope(n, deep), 1.5 if n.slope is None else 0.0) + STRIP_MM + n.step
    xs = [p[0] for f in zones for p in f.pts] + [p[0] for p in n.yamadome]
    ys = [p[1] for f in zones for p in f.pts] + [p[1] for p in n.yamadome]
    x0, x1, y0, y1 = min(xs) - reach, max(xs) + reach, min(ys) - reach, max(ys) + reach
    step = n.step
    while ((x1 - x0) / step) * ((y1 - y0) / step) > STEP_MAX_CELLS:
        step *= 1.5
    n.step = step
    n.nx, n.ny = int(math.ceil((x1 - x0) / step)) + 1, int(math.ceil((y1 - y0) / step)) + 1
    n.origin = (x0, y0)
    general = None
    if n.yamadome:
        general = n.general if n.general is not None else (max(lv.values()) if lv else n.gl - YAMADOME_DEPTH_MM)
    z = [[n.gl] * n.nx for _ in range(n.ny)]
    own = [[n.gl] * n.nx for _ in range(n.ny)]          # 升目を掘る床付けの高さ（細い地山を埋める高さに使う）
    # 山留めの内側は一般の根切り底まで（中途半端な所を残さない）・外は掘らない
    in_y = None
    if n.yamadome:
        in_y = [[inside((x0 + i * step, y0 + j * step), n.yamadome) for i in range(n.nx)] for j in range(n.ny)]
        for j in range(n.ny):
            for i in range(n.nx):
                if in_y[j][i]:
                    z[j][i] = min(z[j][i], general)
                    own[j][i] = general
    slopes = []
    gmask = [[0.0] * n.nx for _ in range(n.ny)]          # 升目の砕石・捨てコンの厚さ（出幅 0.1m の内。重なりは厚い方）
    lmask = [[0.0] * n.nx for _ in range(n.ny)]
    for f in zones:
        b = lv[id(f)]
        s = zone_slope(n, n.gl - b)
        slopes.append((n.gl - b, s))
        mg = margin_of(n, f)
        tg, tl = layers_of(n, f)
        r = max(mg, SPREAD_MM) + max(0.0, n.gl - b) * s + step
        fx = [p[0] for p in f.pts]
        fy = [p[1] for p in f.pts]
        dist = _edge_dist_fn(f.pts)
        i0, i1 = max(0, int((min(fx) - r - x0) / step)), min(n.nx - 1, int((max(fx) + r - x0) / step) + 1)
        j0, j1 = max(0, int((min(fy) - r - y0) / step)), min(n.ny - 1, int((max(fy) + r - y0) / step) + 1)
        for j in range(j0, j1 + 1):
            for i in range(i0, i1 + 1):
                d0 = dist((x0 + i * step, y0 + j * step))
                if d0 <= SPREAD_MM + 1e-6:
                    gmask[j][i] = max(gmask[j][i], tg)
                    lmask[j][i] = max(lmask[j][i], tl)
                if in_y is not None and not in_y[j][i]:
                    continue                                   # 山留めの外は掘らない
                d = max(0.0, d0 - mg)
                if d > 1e-6 and s <= 0.0:
                    continue                                   # 垂直: 余掘りの線の外は掘らない
                zz = b + (d / s if s > 0 else 0.0)
                if zz < z[j][i]:
                    z[j][i] = zz
                    own[j][i] = b
    n.z = z
    n.strips = fill_strips(n, own, in_y)
    n.pits = dig_pits(n, zones, lv, in_y)
    n.slopes = slopes
    cell = (step / 1000.0) ** 2
    n.volume = sum(max(0.0, n.gl - v) for row in z for v in row) / 1000.0 * cell
    n.area = sum(1 for row in z for v in row if v < n.gl - 1.0) * cell
    n.levels = sorted({round(v, 1) for v in list(lv.values()) + ([general] if general is not None else [])}, reverse=True)
    n.ground = {}
    for key, mask in (("砕石", gmask), ("捨てコン", lmask)):
        a = sum(1 for row in mask for v in row if v > 0) * cell
        if a > 0:
            n.ground[key] = (a, sum(v for row in mask for v in row) / 1000.0 * cell)
    n.gaps = yamadome_gaps(n, zones) if n.yamadome else []
    backfill(n, zones, lv)
    n.endo = endo_check(n) if n.road else {}
    n.top_rings = rings(n, lambda v: v < n.gl - 1.0)
    n.bottom_rings = {L: rings(n, lambda v, L=L: v <= L + 1.0) for L in n.levels}
    n.edge_rings = {L: rings(n, lambda v, L=L: v < L - 1.0) for L in n.levels[:-1]}
    n.checks = checks(n, general)
    return n


def backfill(n: Negiri, zones: list, lv: dict) -> None:
    """升目ごとに、掘った高さから GL までのうち躯体・地業（出幅 0.1m の内）・ピットの空洞の占める区間を除いた厚さを埋め戻す."""
    x0, y0 = n.origin
    step = n.step
    occ = [[[] for _ in range(n.nx)] for _ in range(n.ny)]
    for f in zones:
        b = f.bottom
        top = n.gl if f.kind == "地下" or f.top is None else min(n.gl, f.top)
        under = lv[id(f)]
        dist = _edge_dist_fn(f.pts)
        fx = [p[0] for p in f.pts]
        fy = [p[1] for p in f.pts]
        r = SPREAD_MM + step
        i0, i1 = max(0, int((min(fx) - r - x0) / step)), min(n.nx - 1, int((max(fx) + r - x0) / step) + 1)
        j0, j1 = max(0, int((min(fy) - r - y0) / step)), min(n.ny - 1, int((max(fy) + r - y0) / step) + 1)
        for j in range(j0, j1 + 1):
            for i in range(i0, i1 + 1):
                d = dist((x0 + i * step, y0 + j * step))
                if d <= 1e-6:
                    occ[j][i].append((min(under, b), max(b, top)))
                elif d <= SPREAD_MM + 1e-6 and under < b:
                    occ[j][i].append((under, b))               # 出幅の地業
    cell = (step / 1000.0) ** 2
    fill = [[0.0] * n.nx for _ in range(n.ny)]
    body = 0.0
    for j in range(n.ny):
        for i in range(n.nx):
            z = n.z[j][i]
            if z >= n.gl - 1.0:
                continue
            used, cur = 0.0, z
            for lo, hi in sorted(occ[j][i]):
                lo, hi = max(lo, cur), min(hi, n.gl)
                if hi > lo:
                    used += hi - lo
                    cur = hi
            fill[j][i] = max(0.0, n.gl - z - used)
            body += used
    gv = sum(v for _a, v in n.ground.values())
    n.fill = fill
    n.body = max(0.0, body / 1000.0 * cell - gv)
    n.backfill = sum(v for row in fill for v in row) / 1000.0 * cell
    n.fill_rings = [r for r in rings(n, lambda v: v > 1.0, fill) if abs(_area(r)) >= (3 * step) ** 2]


def dig_pits(n: Negiri, zones: list, lv: dict, in_y) -> list:
    """釜場を掘る（升目の高さを 床付け−掘り下げ に）. 指定の形が無く kamaba_auto なら、躯体（出幅 0.1m）の無い平らな床付けで
    □KAMABA_W×KAMABA_D が入る所のうち、床付けがいちばん深く、（道路があれば沿道区域の外で）掘削の外形（法肩）にいちばん近い所."""
    x0, y0 = n.origin
    st = n.step
    shapes = [[tuple(p) for p in k] for k in n.kamaba if len(k) >= 3]
    auto = not shapes and n.kamaba_auto > 0
    if auto:
        busy = [[False] * n.nx for _ in range(n.ny)]
        for f in zones:
            dist = _edge_dist_fn(f.pts)
            fx = [p[0] for p in f.pts]
            fy = [p[1] for p in f.pts]
            r = SPREAD_MM + st
            for j in range(max(0, int((min(fy) - r - y0) / st)), min(n.ny, int((max(fy) + r - y0) / st) + 2)):
                for i in range(max(0, int((min(fx) - r - x0) / st)), min(n.nx, int((max(fx) + r - x0) / st) + 2)):
                    if dist((x0 + i * st, y0 + j * st)) <= SPREAD_MM + 1e-6:
                        busy[j][i] = True
        wi, dj = int(math.ceil(KAMABA_W / st)), int(math.ceil(KAMABA_D / st))
        best = None
        for L in sorted(set(round(v, 1) for v in lv.values()) | ({round(min(min(r) for r in n.z), 1)} if n.yamadome else set())):
            ok = [[1 if (not busy[j][i] and abs(n.z[j][i] - L) < 1.0) else 0 for i in range(n.nx)] for j in range(n.ny)]
            S = [[0] * (n.nx + 1) for _ in range(n.ny + 1)]           # 積分画像
            for j in range(n.ny):
                row = 0
                for i in range(n.nx):
                    row += ok[j][i]
                    S[j + 1][i + 1] = S[j][i + 1] + row
            for j in range(0, n.ny - dj, 2):
                for i in range(0, n.nx - wi, 2):
                    if S[j + dj][i + wi] - S[j][i + wi] - S[j + dj][i] + S[j][i] == wi * dj:
                        cx, cy = x0 + (i + wi / 2) * st, y0 + (j + dj / 2) * st
                        edge = min((min(_seg_dist((cx, cy), r[k], r[(k + 1) % len(r)]) for k in range(len(r)))
                                    for r in n.top_rings), default=0.0) if n.top_rings else 0.0
                        # 道路があれば沿道区域（の外）を先に（釜場は深く掘るので道路から離す）
                        near_road = 0
                        if n.road:
                            zone = endo_width(n.road_width) if n.road_width > 0 else 5000.0
                            dr = min(_seg_dist((cx, cy), a, b) for a, b in n.road)
                            near_road = 1 if dr <= zone + math.hypot(KAMABA_W, KAMABA_D) / 2 else 0
                        key = (L, near_road, edge)
                        if best is None or key < best[0]:
                            best = (key, cx, cy)
            if best is not None:
                break                                                # いちばん深い床付けで見つかれば止める
        if best is not None:
            _k, cx, cy = best
            shapes = [[(cx - KAMABA_W / 2, cy - KAMABA_D / 2), (cx + KAMABA_W / 2, cy - KAMABA_D / 2),
                       (cx + KAMABA_W / 2, cy + KAMABA_D / 2), (cx - KAMABA_W / 2, cy + KAMABA_D / 2)]]
    out = []
    for poly in shapes:
        cx = sum(p[0] for p in poly) / len(poly)
        cy = sum(p[1] for p in poly) / len(poly)
        ci, cj = int(round((cx - x0) / st)), int(round((cy - y0) / st))
        if not (0 <= ci < n.nx and 0 <= cj < n.ny):
            continue
        floor = n.z[cj][ci]
        if floor >= n.gl - 1.0:
            continue                                                 # 掘らない所には置かない
        bottom = floor - n.kamaba_depth
        for j in range(n.ny):
            for i in range(n.nx):
                if inside((x0 + i * st, y0 + j * st), poly):
                    n.z[j][i] = min(n.z[j][i], bottom)
        out.append({"pts": poly, "floor": floor, "bottom": bottom, "auto": auto})
    return out


def endo_check(n: Negiri) -> dict:
    """沿道区域の中の掘削: 道路境界からの距離 d の所は深さ d まで（45° の影響斜線）。それより深い所の升目の数と、いちばん
    超える所（超える深さ mm・境界からの距離 mm）。山留めと道路境界のいちばん近い距離も."""
    zone = endo_width(n.road_width) if n.road_width > 0 else 5000.0
    x0, y0 = n.origin
    inside_n, over_n, worst = 0, 0, None
    for j in range(n.ny):
        for i in range(n.nx):
            dep = n.gl - n.z[j][i]
            if dep <= 1.0:
                continue
            p = (x0 + i * n.step, y0 + j * n.step)
            d = min(_seg_dist(p, a, b) for a, b in n.road)
            if d > zone:
                continue
            inside_n += 1
            if dep > d + 1.0:
                over_n += 1
                if worst is None or dep - d > worst[0]:
                    worst = (dep - d, d, dep)
    near = None
    if n.yamadome:
        ym = n.yamadome
        near = min(min(_seg_dist(q, a, b) for a, b in n.road) for q in ym)
    return {"zone": zone, "inside": inside_n, "over": over_n, "worst": worst, "near": near}


def surplus(n: Negiri) -> float:
    """建設発生土 m³（地山。根切り−埋戻し）."""
    return max(0.0, n.volume - n.backfill)


def dumps(n: Negiri) -> int:
    """10t ダンプの延べ台数（発生土の地山 ÷ 1台の積載）."""
    return int(math.ceil(surplus(n) / DUMP_M3 - 1e-9)) if surplus(n) > 0 else 0


def yamadome_gaps(n: Negiri, zones: list) -> list:
    """基礎の躯体ごとの山留め壁（内側の面）までのいちばん近い距離 mm と、山留めの外へはみ出すか（土間は除く）."""
    out = []
    ym = n.yamadome
    for f in zones:
        if is_doma(f):
            continue
        out_side = any(not inside(p, ym) for p in f.pts)
        d = min([_seg_dist(p, ym[k], ym[(k + 1) % len(ym)]) for p in f.pts for k in range(len(ym))]
                + [_seg_dist(q, f.pts[k], f.pts[(k + 1) % len(f.pts)]) for q in ym for k in range(len(f.pts))])
        out.append((f.name, d, out_side))
    return out


def level_color(n: Negiri, L: float, gray: bool = False) -> tuple[float, float, float]:
    """床付けの高さ L の色（浅い順に LEVEL_COLORS。白黒は灰の濃さ）."""
    pal = LEVEL_GRAYS if gray else LEVEL_COLORS
    k = n.levels.index(L) if L in n.levels else 0
    if len(n.levels) > len(pal):
        k = round(k * (len(pal) - 1) / (len(n.levels) - 1))
    return pal[min(k, len(pal) - 1)]


def _grow(mask: list, r: int) -> list:
    """升目の真偽の並びを正方形 (2r+1) で広げる（行と列に分けて、累積和で）."""
    ny, nx = len(mask), len(mask[0])
    rows = []
    for row in mask:
        acc = [0]
        for v in row:
            acc.append(acc[-1] + (1 if v else 0))
        rows.append([acc[min(nx, i + r + 1)] - acc[max(0, i - r)] > 0 for i in range(nx)])
    out = [[False] * nx for _ in range(ny)]
    for i in range(nx):
        acc = [0]
        for j in range(ny):
            acc.append(acc[-1] + (1 if rows[j][i] else 0))
        for j in range(ny):
            out[j][i] = acc[min(ny, j + r + 1)] - acc[max(0, j - r)] > 0
    return out


def fill_strips(n: Negiri, own: list, in_y) -> int:
    """根切りの間に残る幅 STRIP_MM 以下の地山を掘る（閉じの処理: 掘る所を半分の幅だけ広げてから縮める）。埋めた所は隣の浅い方の
    床付けまで掘り、そこから法面の勾配で上げる → 埋めた升目の数."""
    r = int(round(STRIP_MM / 2.0 / n.step))
    if r < 1 or not n.z:
        return 0
    E = [[v < n.gl - 1.0 for v in row] for row in n.z]
    grown = _grow(E, r)
    closed = [[not v for v in row] for row in _grow([[not v for v in row] for row in grown], r)]
    C = [[closed[j][i] and not E[j][i] and (in_y is None or in_y[j][i]) for i in range(n.nx)] for j in range(n.ny)]
    seen = [[False] * n.nx for _ in range(n.ny)]
    filled = 0
    for j0 in range(n.ny):
        for i0 in range(n.nx):
            if not C[j0][i0] or seen[j0][i0]:
                continue
            comp, stack, level = [], [(i0, j0)], None
            seen[j0][i0] = True
            while stack:
                i, j = stack.pop()
                comp.append((i, j))
                for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ii, jj = i + di, j + dj
                    if 0 <= ii < n.nx and 0 <= jj < n.ny:
                        if C[jj][ii] and not seen[jj][ii]:
                            seen[jj][ii] = True
                            stack.append((ii, jj))
                        elif E[jj][ii]:
                            level = own[jj][ii] if level is None else max(level, own[jj][ii])
            if level is None:
                continue
            s = zone_slope(n, n.gl - level)
            # 埋めた所から法面の勾配で上げる（8方向の距離を広げていく）
            dist = {p: 0.0 for p in comp}
            front = list(comp)
            reach = (n.gl - level) * s
            while front:
                nxt = []
                for i, j in front:
                    for di, dj, w in ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
                                      (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)):
                        ii, jj = i + di, j + dj
                        if not (0 <= ii < n.nx and 0 <= jj < n.ny) or (in_y is not None and not in_y[jj][ii]):
                            continue
                        d = dist[(i, j)] + w * n.step
                        if d <= reach and d < dist.get((ii, jj), math.inf):
                            dist[(ii, jj)] = d
                            nxt.append((ii, jj))
                front = nxt
            for (i, j), d in dist.items():
                zz = level + (d / s if s > 0 else (0.0 if d == 0 else n.gl - level))
                if zz < n.z[j][i]:
                    n.z[j][i] = zz
            filled += len(comp)
    return filled


def rings(n: Negiri, pred, grid=None) -> list[list[tuple[float, float]]]:
    """升目の条件 pred を満たす所の外形（升目の境目を辿って輪にし、まっすぐな所をまとめる）。grid を省くと掘削面の高さ."""
    s = n.step
    x0, y0 = n.origin
    on = [[pred(v) for v in row] for row in (n.z if grid is None else grid)]
    edges: dict = {}
    for j in range(n.ny):
        for i in range(n.nx):
            if not on[j][i]:
                continue
            # 升目 (i, j) は中心 (x0+i*s, y0+j*s)。角は格子点 (i, j)〜(i+1, j+1)（左下が i, j）
            for di, dj, a, b in ((0, -1, (i, j), (i + 1, j)), (1, 0, (i + 1, j), (i + 1, j + 1)),
                                 (0, 1, (i + 1, j + 1), (i, j + 1)), (-1, 0, (i, j + 1), (i, j))):
                ii, jj = i + di, j + dj
                if not (0 <= ii < n.nx and 0 <= jj < n.ny and on[jj][ii]):
                    edges.setdefault(a, []).append(b)          # 反時計回り（角で2つの升目が触れる点は行き先が2つ）
    out = []
    while edges:
        start = next(iter(edges))
        ring = [start]
        cur = edges[start].pop()
        if not edges[start]:
            del edges[start]
        while cur != start and cur in edges:
            ring.append(cur)
            nxt = edges[cur].pop()
            if not edges[cur]:
                del edges[cur]
            cur = nxt
        if len(ring) >= 4:
            pts = [(x0 + (i - 0.5) * s, y0 + (j - 0.5) * s) for i, j in ring]
            out.append(simplify(pts, s * 0.75))
    out.sort(key=lambda r: -abs(_area(r)))
    return out


def _area(r) -> float:
    return sum(r[i][0] * r[(i + 1) % len(r)][1] - r[(i + 1) % len(r)][0] * r[i][1] for i in range(len(r))) / 2.0


def simplify(ring: list, tol: float) -> list:
    """閉じた輪の頂点を減らす（Douglas–Peucker。いちばん遠い2点で分けて両側を）."""
    if len(ring) <= 4:
        return ring
    a = 0
    b = max(range(len(ring)), key=lambda k: math.dist(ring[0], ring[k]))

    def dp(pts):
        if len(pts) <= 2:
            return pts
        dmax, k = max(((_seg_dist(pts[m], pts[0], pts[-1]), m) for m in range(1, len(pts) - 1)), default=(0.0, 0))
        if dmax <= tol:
            return [pts[0], pts[-1]]
        left, right = dp(pts[:k + 1]), dp(pts[k:])
        return left[:-1] + right

    first = dp(ring[a:b + 1])
    second = dp(ring[b:] + [ring[0]])
    out = first[:-1] + second[:-1]
    return out if len(out) >= 3 else ring


def max_angle(soil: str, height_mm: float) -> float:
    """安衛則356条・357条の掘削面のこう配の上限（度）."""
    lim, a_low, a_mid, high = SOILS.get(soil, SOILS["その他"])
    if soil in ("砂", "崩れやすい（発破等）"):
        return 90.0 if height_mm < lim else a_low
    if height_mm < lim:
        return a_low
    if high and height_mm >= high[0]:
        return high[1]
    return a_mid


def slope_angle(n_ratio: float) -> float:
    """勾配 1:n → 角度（度）."""
    return 90.0 if n_ratio <= 0 else math.degrees(math.atan(1.0 / n_ratio))


def checks(n: Negiri, general) -> list[Check]:
    c = []
    deep = max([n.gl - v for v in n.levels] + [0.0])
    if n.yamadome:
        c.append(Check("山留め", "OK", f"山留めの内側は山留めの面まで垂直に掘り、残りの所も一般の根切り底 GL{general - n.gl:+,.0f} まで掘る"
                                     "（躯体の掘削と山留めの間に中途半端な土を残さない）。山留めの外は掘らない。山留め壁と躯体の間は"
                                     "積算基準で 1.0m"))
        for nm, d, out_side in n.gaps:
            if out_side:
                c.append(Check("山留めとの間", "NG", f"{nm} が山留めの外へはみ出す（山留めの位置か躯体の選びを確かめる）"))
            elif d < YAMADOME_GAP_MM - 1.0:
                c.append(Check("山留めとの間", "WARN", f"{nm} と山留め壁の間 {d:,.0f}mm が積算基準の標準 {YAMADOME_GAP_MM:,.0f} より狭い"
                                                    "（型枠の組立て・解体と防水の作業の幅。山留めを外へ出すか、型枠・防水の工法を確かめる）"))
    else:
        steep = [(h, s) for h, s in n.slopes if s <= 0.0 and h >= YAMADOME_DEPTH_MM - 1e-6]
        if steep:
            h = max(x for x, _s in steep)
            c.append(Check("山留め", "NG", f"垂直に掘る深さ {h:,.0f} が {YAMADOME_DEPTH_MM:,.0f} 以上なのに山留めが無い → 山留めか法面"
                                         "（建築基準法施行令136条の3第4項・安衛則361条）"))
    worst = None
    for h, s in n.slopes:
        if n.yamadome and s <= 0.0:
            continue
        ang, lim = slope_angle(s), max_angle(n.soil, h)
        if worst is None or ang - lim > worst[0] - worst[1]:
            worst = (ang, lim, h, s)
    if worst:
        ang, lim, h, s = worst
        c.append(Check("法面のこう配", "OK" if ang <= lim + 1e-6 else "NG",
                       f"{'垂直' if s <= 0 else f'1:{s:g}'}（{ang:.0f}°）・掘削面の高さ {h:,.0f}・地山「{n.soil}」の上限 {lim:.0f}°"
                       "（安衛則356条・357条。機械掘削も同じ値を目安に）" + ("。勾配は自動（積算基準の法の係数）" if n.slope is None else "")))
    if n.strips:
        c.append(Check("細い地山", "OK", f"根切りの間に残る幅 {STRIP_MM:,.0f} 以下の地山も掘る（隣の浅い方の床付けまで）"))
    doma = any(is_doma(f) for f in n.zones)
    c.append(Check("床付け", "OK", "、".join(f"GL{v - n.gl:+,.0f}" for v in n.levels)
                   + f"（躯体の下端−砕石 {n.gravel:.0f}−捨てコン {n.lean:.0f}"
                   + (f"。土間は砕石 {n.doma_gravel:.0f}・捨てコン {n.doma_lean:.0f}" if doma else "")
                   + ("" if n.depth is None else "。掘削底を指定") + f"）。余掘り {n.margin:.0f}"
                   + (f"・土間 {n.doma_margin:.0f}（積算基準の土間・犬走り等）" if doma else "")))
    if deep >= FOREMAN_MM:
        c.append(Check("作業主任者", "OK", f"掘削面の高さ {deep:,.0f} が 2m 以上 → 地山の掘削作業主任者（安衛法施行令6条9号）"
                                        + ("・土止め支保工作業主任者（6条10号）" if n.yamadome else "")))
    if n.kamaba_auto and not n.kamaba and not n.pits:
        c.append(Check("釜場", "WARN", f"□{KAMABA_W:,.0f}×{KAMABA_D:,.0f} の釜場を置ける、躯体の無い平らな床付けが無い（余掘りの帯だけ）。"
                                     "余掘りを広げるか、レイヤー名に「釜場」の閉じた線で位置を指定する"))
    for k, p in enumerate(n.pits, 1):
        xs = [q[0] for q in p["pts"]]
        ys = [q[1] for q in p["pts"]]
        c.append(Check("釜場", "OK", f"釜場{k}: □{max(xs) - min(xs):,.0f}×{max(ys) - min(ys):,.0f}・床付け GL{p['floor'] - n.gl:+,.0f} から "
                                   f"{n.kamaba_depth:,.0f} 下げて底 GL{p['bottom'] - n.gl:+,.0f}、周りに砕石 {KAMABA_GRAVEL_MM:.0f}（寸法は目安）"
                                   + ("。自動で躯体の無い平らな床付けの、いちばん深く掘削の縁に近い所に置いた" if p["auto"] else "")
                                   + "。水中ポンプは2台1組・土砂をこまめに除く・掘削の進みに合わせて移す。下水へは沈砂槽を通して放流し、下水道局へ届出"
                                   "（施工図の手引き p.24・p.36）"))
    if n.endo:
        e = n.endo
        wtxt = f"前面道路の総幅員 {n.road_width / 1000:g}m → " if n.road_width > 0 else "幅員の指定なし → 最大の "
        if e["over"]:
            ex, d, dep = e["worst"]
            c.append(Check("沿道掘削", "WARN", f"{wtxt}沿道区域 {e['zone'] / 1000:g}m の中で、道路境界から 45° の影響斜線より深く掘る"
                                            f"（境界から {d:,.0f} の所で深さ {dep:,.0f}、斜線より {ex:,.0f} 深い）→ 道路管理者と事前協議"
                                            "（掘削工事仕様書・断面図・山留計画図・計算書・引照点詳細図・現況写真。道路法44条。東京都の建設事務所の"
                                            "案内による。区市町村の要綱は深さの基準が違うので確かめる）"))
        elif e["inside"]:
            c.append(Check("沿道掘削", "OK", f"{wtxt}沿道区域 {e['zone'] / 1000:g}m の中で掘るが、道路境界から 45° の影響斜線より浅い"
                                          "（区市町村によっては深さ 0.5m 以上で許可が要るので管理者に確かめる）"))
        else:
            c.append(Check("沿道掘削", "OK", f"{wtxt}沿道区域 {e['zone'] / 1000:g}m の中では掘らない"))
        if e["near"] is not None and e["near"] < ROAD_GAP_MM - 1e-6:
            c.append(Check("沿道掘削", "WARN", f"山留めの面と道路境界の間 {e['near']:,.0f}mm が {ROAD_GAP_MM:.0f} より狭い（H 鋼の外づらと道路境界の"
                                            "離隔は最低 5cm。山留め壁の厚さぶん内へ）"))
    sp = surplus(n)
    if sp >= RECYCLE_M3:
        c.append(Check("建設発生土", "WARN", f"搬出 {sp:,.0f}m³（地山）が {RECYCLE_M3:,.0f}m³ 以上 → 再生資源利用促進計画の作成・"
                                           "発注者への説明・現場掲示・5年保存、搬出先の盛土規制法の許可と受領書の確認"
                                           "（資源有効利用促進法の省令。R5.1.1〜）"))
    c.append(Check("点検", "OK", "作業開始前・大雨の後・中震以上の地震の後に地山の浮石・き裂・湧水を点検（安衛則358条）。掘削の前に"
                                "地質・埋設物を調べ、掘削の時期と順序を決める（355条）"))
    return c


def report(n: Negiri) -> str:
    out = [f"# 根切り図 {n.name}", "",
           "出典: 労働安全衛生規則 355条〜358条・361条、建築基準法施行令136条の3、安衛法施行令6条、公共建築数量積算基準（令和5年）・"
           "公共建築工事標準仕様書（地業）。土量変化率は目安。調べたメモは docs/調査_根切り.md", "",
           f"- GL: {n.gl:,.0f}（プロジェクトの高さ）・余掘り {n.margin:.0f}（土間 {n.doma_margin:.0f}）・砕石 {n.gravel:.0f}・"
           f"捨てコン {n.lean:.0f}（土間 {n.doma_gravel:.0f}・{n.doma_lean:.0f}）・法面 "
           + ("自動（積算基準の法の係数）" if n.slope is None else
              ("垂直" if n.slope <= 0 else f"1:{n.slope:g}（{slope_angle(n.slope):.0f}°）")) + f"・地山「{n.soil}」"
           + ("・山留めあり" if n.yamadome else ""),
           f"- 掘削の面積（法肩の内）: {n.area:,.1f} m²・掘削土量（地山）: {n.volume:,.1f} m³（升目 {n.step:.0f}mm で計算）・"
           f"ほぐした土量の目安 {n.volume * LOOSE.get(n.soil, 1.2):,.1f} m³（土量変化率 L {LOOSE.get(n.soil, 1.2):g}。運搬の台数の見当）",
           "", "| 躯体 | 種類 | 下端 | 砕石・捨てコン | 余掘り | 床付け |", "|---|---|---|---|---|---|"]
    for f in n.zones:
        g, l = layers_of(n, f)
        out.append(f"| {f.name} | {f.kind} | GL{f.bottom - n.gl:+,.0f} | {g:.0f}・{l:.0f} | {margin_of(n, f):.0f} | "
                   f"GL{floor_level(n, f) - n.gl:+,.0f} |")
    if n.ground:
        out += ["", "地業の数量（積算基準: 面積×厚さ、躯体側面より出幅 0.1m。重なりは厚い方で1回）", "",
                "| 地業 | 面積 | 体積 |", "|---|---|---|"]
        out += [f"| {k} | {a:,.1f} m² | {v:,.2f} m³ |" for k, (a, v) in n.ground.items()]
    lf = LOOSE.get(n.soil, 1.2)
    out += ["", "埋戻しと建設発生土（積算基準 p.7〜8: 埋戻し＝根切り−GL 以下の躯体−砕石−捨てコン、発生土＝根切り−埋戻し。"
            "地山の数量。ピット・地下室は床から GL までを空洞として埋め戻さない）", "",
            "| 項目 | 数量 |", "|---|---|",
            f"| 根切り | {n.volume:,.1f} m³ |",
            f"| GL 以下の躯体（空洞を含む） | {n.body:,.1f} m³ |",
            f"| 砕石・捨てコン | {sum(v for _a, v in n.ground.values()):,.1f} m³ |",
            f"| 埋戻し | {n.backfill:,.1f} m³ |",
            f"| 建設発生土（搬出・地山） | {surplus(n):,.1f} m³ |",
            f"| 搬出のほぐした量（L {lf:g}。目安） | {surplus(n) * lf:,.1f} m³ |",
            f"| 10t ダンプ（1台 地山 {DUMP_M3:g}m³。目安） | 延べ {dumps(n)} 台 |",
            "", "根切りの土を埋戻しに使えないときは根切りの全量を搬出する（積算基準 p.8）。仮置きの場所が無いときも同じ。"]
    out += ["", "| 判定 | 結果 | 内容 |", "|---|---|---|"]
    out += [f"| {c.item} | {c.status} | {c.message} |" for c in n.checks]
    return "\n".join(out) + "\n"


def contour_lines(n: Negiri) -> list[tuple[float, list, str]]:
    """高さの線 [(高さ, 輪, "法肩"|"法尻")]: 床付けの高さごとの平らな所の外形（法尻）と、そこからさらに深く掘る所の縁（法肩）."""
    out = []
    for L in n.levels:
        out += [(L, r, "法尻") for r in n.bottom_rings.get(L, [])]
        out += [(L, r, "法肩") for r in n.edge_rings.get(L, [])]
    return out


def mesh_data(n: Negiri) -> list[dict]:
    """Tapir CreateMeshes の meshesData（法肩の輪ごとに1枚。外形は GL、床付けの高さの線を高さの線に。m）。垂直に掘る所は同じ
    平面の線が違う高さで重なるので、深い方を 20mm 内へ寄せる（メッシュの点に2つの高さを持たせない）."""
    out = []
    for top in n.top_rings:
        subs, used = [], [(n.gl, top)]
        for L, r, _kind in contour_lines(n):
            if not inside(_centroid(r), top):
                continue
            if any(_same(r, q) and abs(h - L) < 1.0 for h, q in used):
                continue                                       # 同じ高さの同じ線
            rr = r
            if any(_same(r, q) for _h, q in used):
                rr = _shrink(r, 20.0)
            used.append((L, rr))
            subs.append({"coordinates": [{"x": x / 1000.0, "y": y / 1000.0, "z": (L - n.gl) / 1000.0} for x, y in rr + rr[:1]]})
        out.append({"level": n.gl / 1000.0,
                    "polygonCoordinates": [{"x": x / 1000.0, "y": y / 1000.0, "z": 0.0} for x, y in top],
                    "sublines": subs})
    return out


def _centroid(r):
    return (sum(p[0] for p in r) / len(r), sum(p[1] for p in r) / len(r))


def _same(a, b, tol: float = 1.0) -> bool:
    return len(a) == len(b) and all(min(math.dist(p, q) for q in b) <= tol for p in a)


def _shrink(r, d: float):
    c = _centroid(r)
    out = []
    for p in r:
        L = math.dist(p, c) or 1.0
        out.append((p[0] + (c[0] - p[0]) * d / L, p[1] + (c[1] - p[1]) * d / L))
    return out
