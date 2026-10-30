"""内部足場（内部ステージ足場）: 室内の範囲に支柱を格子に立て、上の作業床を全面に張る足場. 部品 ashiba_stage.

利用者の指定（2026-10-24）「内部足場の内部ステージ足場の機能追加して検証して」。吹抜け・高天井の天井・壁上部の作業で、
室内に格子状に支柱を立てて最上段に全面の作業床（ステージ）を張る。
- 範囲: 平面の長方形（4点。向きは自由）。壁から CLEAR_MM 離して、両方向に系列のスパンで割る
- 高さ: 作業床の高さ（床から）を指定。支柱はコマの位置に合わせ、作業床の高さは最寄りの段（以下）にする
- 部材: 支柱（格子）・ジャッキ・根がらみと各段の布材（両方向）・最上段の全面の踏板・外周の手すり・中桟・幅木・
  外周の構面の筋かい（5スパン以下ごと）・昇降の階段（隅の1スパンに折り返し。利用者の指定 2026-10-29 はしごにしない）
- 検証: 支柱1本の軸力（自重＋作業床＋積載）と許容耐力、1スパンあたりの積載と作業床の許容積載、高さと短辺の比
  （4 を超えたら控え・壁つなぎ）、作業床の高さ 2m 以上の手すり・幅木・昇降設備

型枠支保工として使う（"use": "支保工"。利用者の指定 2026-10-28）: 上のスラブの型枠を受ける。設計荷重＝23.5kN/m³×スラブ厚＋型枠
0.39＋積載 1.47kN/m²、支柱1本の軸力をメーカーの支保工の承認値（つなぎ方別）と比べ、上端の水平荷重 5%（枠組 2.5%）を筋かいで受け、
大引受けジャッキの繰出し・水平つなぎの間隔・設置届（支柱高さ 3.5m 以上）を見る。

EVシャフトの中に組む（"use": "EVシャフト"・"floors_mm"。利用者の指定 2026-10-28）: 各階の床に近い段にも全面の作業床、
壁との隙間 30cm 以下なら外周の手すりを省き、各階で四方の壁に壁つなぎ、昇降は階段。乗場開口の養生を注意に。

階段の上に組む（"stair"。利用者の指定 2026-10-28）: 踏面ごとの支柱を段の高さだけ短くし、ジャッキ（足りなければ敷板 2枚まで）
で作業床の段にそろえる。底板が段鼻・蹴上げにかかる列を知らせる。

入力: interior_stages: [{"name": "吹抜け", "corners_mm": [[x,y],[x,y],[x,y],[x,y]], "deck_mm": 6000,
       "live_kn_m2": 1.5, "base_mm": 0, "use": "足場"|"支保工", "slab_mm": 200, "tie": "片方向つなぎ材",
       "access": "階段"|"はしご"}]
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Optional

from .master import FRAME, TUBE

CLEAR_MM = 150.0             # 壁から外周の支柱まで
LIVE_DEFAULT_KN_M2 = 1.5     # 作業床の積載（軽作業・仕上げ）
DECK_DEAD_KN_M2 = 0.25       # 踏板の自重
POST_SELF_KN_PER_M = 0.15    # 支柱＋布材・筋かいの自重（支柱1本・高さ1m あたりの目安）
STAGE_H_RATIO = 0.025        # 棚足場の照査水平荷重（自重に対する比。指針）
STAGE_FS_MIN = 2.0           # 転倒安定度の下限
DECK_GAP_MAX_MM = 30         # 作業床のすき間の上限（安衛則563条: 3cm 以下）
STAGE_WIDTH_MAX_MM = 1219    # 足場の幅（短手のスパン）の上限（利用者の指定 2026-10-29）
RIGHT_ANGLE_TOL_DEG = 2.0    # 範囲の角が直角からこれ以上ずれたら長方形でない
HB_LIMIT = 4.0               # 高さ／短辺がこれを超えたら控え・壁つなぎ
BRACE_EVERY_SPANS = 5
FIT_SLACK_MM = 900.0         # 壁際の余り（片側 CLEAR_MM に足して両側でこれ以内）
GUARD_MM = 900               # 手すりの高さ（作業床から）
# 型枠支保工として使う（利用者の指定 2026-10-28: 型枠支保工で使うよ、内部足場はステージ）。建災防東京支部
# 「計画届作成の手引（第6版）」14章・参考資料2: 設計荷重＝固定荷重（鉄筋コンクリート 2400kg/m³×厚さ＋型枠 40kg/m²）＋
# 積載荷重 150kg/m²（安衛則240条）。水平荷重は設計荷重の 5%（鋼管枠を支柱にするときは 2.5%）。支柱高さ 3.5m 以上は設置届
RC_KN_M3 = 23.5              # 鉄筋コンクリートの自重 2400kg/m³
FORM_KN_M2 = 0.39            # 型枠の自重 40kg/m²
SHORING_LIVE_KN_M2 = 1.47    # 積載荷重 150kg/m²（作業荷重＋衝撃荷重）
SHORING_H_RATIO = 0.05       # 水平荷重（鋼管枠以外の支柱）
SHORING_H_RATIO_FRAME = 0.025
SHORING_NOTIFY_MM = 3500     # 支柱高さ（ベース板〜上部ベース板）がこれ以上なら設置届
TIE_PITCH_MAX_MM = 2000      # 水平つなぎ（くさびは各段の布材）の間隔
BRACE_CLAMP_KN = 3.43        # 単管の筋かいを留める自在クランプの許容耐力（350kgf。手引 p242）
UHEAD_EXT_TARGET_MM = 150    # 支柱の積み方を選ぶときの繰出しのねらい（上下に調整の余地を残す）
UHEAD_EXT_MAX_MM = 350       # 大引受けジャッキ（Uジャッキ）の繰出しの上限（仮設工業会の承認の組立基準）
FORM_DEPTH_MM = 175          # スラブ下端から大引の下端まで（せき板12＋根太60＋大引100 の目安）
# 階段の上に組む（利用者の指定 2026-10-28: 内部足場は階段でよく使う）。踏面ごとに支柱を立て、作業床の段（コマ）に合わせて
# 支柱を短くし、残りをジャッキで受ける。ジャッキで受けきれない分は敷板（2枚まで）。報告 地足場と内部足場: ジャッキは
# 段差を埋める道具ではない・敷板／敷角は2段以上はさまない（安衛則242条の考え方）
# EVシャフトの中に組む（利用者の指定 2026-10-28: 内部足場はステージとEV部分）。ピットから積み上げ、各階の床の高さに近い段に
# 全面の作業床。四方の壁が近いので外周の手すりは張らず（壁との隙間 30cm 以下）、各階で四方の壁に壁つなぎ。乗場開口は
# 安衛則519条の囲い・手すり・覆いと表示（報告 地足場と内部足場）
SCAFFOLD_CHIEF_MM = 5000     # 吊り・張出し・高さ5m以上の足場の組立て等は作業主任者（安衛則565条）
SHAFT_WALL_GAP_MAX_MM = 300  # 作業床の端と壁の隙間がこれ以下なら外周の手すりを省く
SHAFT_TIE_V_MAX_MM = {"wedge": 5000, "frame": 9000}   # 壁つなぎの垂直間隔（安衛則570条1項5号: 単管5m・わく組9m）
PLATE_HALF_MM = 70           # ジャッキベースの底板（140角）の半分。踏面の端（段鼻・蹴上げ）からこれ以上離す
SHIM_BOARD_MM = 35           # 敷板1枚の厚さ
SHIM_BOARDS_MAX = 2
STAIR_LANE_MM = 450          # 階段枠の幅（ND NDAL4518K 450）
LANDING_STEP_MAX_MM = 400    # 階段の上: 建物の踊り場と作業床の段差がこれを超えたら昇降を足す（踏み越えられる目安）
LOW_LANDING_STEP_MM = 650   # EVシャフトのいちばん下の踊り場へ踏台で上がれる高さの目安
STAIR_FIRST_TOL_MM = 300     # 階段の1台目（地面から最初の段）が層の高さからずれてよい幅
NEGARAMI_MAX_MM = 600        # 支柱の下端から最初の布材（根がらみ）までの上限の目安
# 型枠支保工としての仮設工業会の承認（日建リース 足場カタログ ダーウィン 2024 の抜粋。報告 地足場と内部足場）
SHORING_APPROVAL = {"nikken_nd1800": "仮設工業会 承認第88-164号（NDシステム1800型 型枠支保工）",
                    "nikken_nd1900": "仮設工業会 承認第101-164号（NDシステム1900型 型枠支保工）",
                    "nikken_strong": "仮設工業会 承認第128号（ストロング型 型わく支保工）",
                    "albatross": "仮設工業会 システム承認（アルバトロス型枠支保工。承認番号はスギコに確かめる）"}
# 支保工の承認の支柱間隔の下限（アルバトロス p060・p061: 610〜1829、強力斜材 45.0kN仕様は 914〜1829）。457 の升目には
# 先行手摺ブレスが無い
SHORING_MIN_SPAN = {"albatross": 610}
SHORING_MIN_SPAN_STRONG45 = 914
SHORING_TIES = ("片方向つなぎ材", "両方向つなぎ材", "ブレース")   # 支保工の承認値はつなぎ方で決まる（日建 ND1800: 18／25／22kN）


def shoring_ties(caps: Optional[dict]) -> tuple[str, ...]:
    """系列の支保工のつなぎ方（capacity.csv の「支保工許容支持力」のキーの順）。無ければ日建の3種.

    アルバトロスは梁間×桁行の組み方（先行手摺ブレス×先行手摺ブレス 22.7kN … 先行手摺ブレス＋布材×先行手摺ブレス＋布材
    33.5kN。スギコ カタログ p060）."""
    keys = [k for (item, k) in (caps or {}) if item == "支保工許容支持力"]
    return tuple(dict.fromkeys(keys)) or SHORING_TIES


@dataclass
class StageCheck:
    item: str
    status: str              # OK / WARN / NG
    message: str


@dataclass
class StageResult:
    name: str
    origin: tuple[float, float]       # 外周の支柱の始めの角（mm）
    u: tuple[float, float]            # 長い方の辺の向き
    v: tuple[float, float]            # もう一方（u から左回り 90°）
    spans_u: list[int]
    spans_v: list[int]
    levels: list[int]                 # 根がらみ＋各段（足場の立つ面から mm）。最後が作業床
    deck_mm: int
    base_mm: float
    posts: list[int]                  # 支柱の構成（下から）
    jack_mm: int
    live_kn_m2: float
    quantity: list[tuple[str, int, int, str]] = field(default_factory=list)   # (分類, 呼び寸法, 数, 用途)
    checks: list[StageCheck] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    top_mm: int = 0                   # 支柱の天端（足場の立つ面から mm）
    ceiling_mm: Optional[float] = None   # 天井（上の階の床の下端。足場の立つ面から mm。分からなければ None）
    use: str = "足場"                 # "足場"（作業床だけ）か "支保工"（上のスラブの型枠を受ける）
    slab_mm: float = 0.0              # 支保工: 受けるスラブの厚さ
    design_kn_m2: float = 0.0         # 支保工: 設計荷重（固定＋積載）
    tie: str = ""                     # 支保工: つなぎ方（SHORING_TIES）
    series_id: str = ""               # 系列（設置届の承認番号に使う）
    h_ratio: float = 0.0              # 支保工: 上端の水平荷重の比（5%、鋼管枠 2.5%）
    uhead_ext_mm: Optional[int] = None   # 支保工: 大引受けジャッキの繰出し（天井が分かるとき）
    upper_levels: list[int] = field(default_factory=list)   # 支保工: 作業床の段のほかに足す布材の段（水平つなぎ）
    stair_feet: list[dict] = field(default_factory=list)    # 階段の上の支柱（段の高さ・支柱・ジャッキ・敷板・踏面の端）
    deck_levels: list[int] = field(default_factory=list)    # 最上段のほかの作業床の段（EVシャフトの各階）
    open_end: bool = False            # 長手の終わりの短辺を出入口にする（外周の手すり・中桟・幅木なし。仮設通路の島）
    end_post_kn: float = 0.0          # 出入口の辺の支柱1本に掛かるほかの荷重（仮設通路の反力。kN）
    floors_mm: list[float] = field(default_factory=list)    # EVシャフト: 各階の床の高さ（足場の立つ面から）
    guard: bool = True                # 最上段の外周の手すり・中桟・幅木
    stair_flights: list[tuple[int, int]] = field(default_factory=list)   # 昇降の階段（下の段, 上の段）。隅の1スパンに折り返し
    stair_fh: int = 0                 # 階段1台の高さ（系列の層の高さ）
    inner_braces: int = 0             # 支保工: 内側の通りに足す交さ筋かい（各層・各方向の組数）
    form: Optional[dict] = None       # 支保工: 型枠の計算（部材・間隔の上限・検定）
    access: str = "階段"              # 昇降: "階段"（隅の1スパンの階段枠）・"はしご"・"建物の階段"（階段の上）・"ハッチ"・"なし"（仮設通路の終わりの島）
    hatch_levels: list[int] = field(default_factory=list)   # ハッチ付布板（梯子内蔵）を置く段（EVシャフト）
    wall_gap_mm: float = 0.0          # 作業床の端と壁（範囲の辺）の隙間の大きい方

    @property
    def length_u(self) -> float:
        return float(sum(self.spans_u))

    @property
    def length_v(self) -> float:
        return float(sum(self.spans_v))

    @property
    def angle_deg(self) -> float:
        return math.degrees(math.atan2(self.u[1], self.u[0]))

    @property
    def ok(self) -> bool:
        return all(c.status != "NG" for c in self.checks)


def _frame(corners) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float], float, float]:
    """4点 → (始めの角, 長い辺の向き u, v（u から左回り）, 長い辺の長さ, 短い辺の長さ)."""
    pts = [tuple(map(float, p)) for p in corners][:4]
    if len(pts) < 4:
        raise ValueError("内部足場の範囲は長方形の4点で指定してください")
    area = sum(pts[i][0] * pts[(i + 1) % 4][1] - pts[(i + 1) % 4][0] * pts[i][1] for i in range(4))
    if area < 0:
        pts.reverse()                                   # 左回りにそろえる
    # 4つの角が直角でないと（台形・平行四辺形）、長い辺から張った格子が範囲の外へはみ出す（台形で壁の向こうまで出ていた）
    for i in range(4):
        a, b, c = pts[i - 1], pts[i], pts[(i + 1) % 4]
        v1, v2 = (a[0] - b[0], a[1] - b[1]), (c[0] - b[0], c[1] - b[1])
        n1, n2 = math.hypot(*v1), math.hypot(*v2)
        if n1 < 1e-6 or n2 < 1e-6:
            raise ValueError("内部足場の範囲の4点に重なった点があります")
        cos = (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)
        if abs(cos) > math.sin(math.radians(RIGHT_ANGLE_TOL_DEG)):
            ang = math.degrees(math.acos(max(-1.0, min(1.0, cos))))
            raise ValueError(f"内部足場の範囲は長方形で指定してください（角が {ang:.0f}°。台形・平行四辺形は格子がはみ出す）")
    sides = [(i, math.hypot(pts[(i + 1) % 4][0] - pts[i][0], pts[(i + 1) % 4][1] - pts[i][1])) for i in range(4)]
    # 長さの同じ辺（長方形の向かい合う辺）は先の辺を取る（計算の誤差で後の辺にしない。始めの角を呼ぶ側が決められる）
    la = max(s[1] for s in sides)
    i0 = next(i for i, s in sides if s >= la - 0.5)
    p0, p1 = pts[i0], pts[(i0 + 1) % 4]
    u = ((p1[0] - p0[0]) / la, (p1[1] - p0[1]) / la)
    v = (-u[1], u[0])
    lb = sides[(i0 + 1) % 4][1]
    return p0, u, v, la, lb


def _fit_spans(coins: list[int], length: float, slack: float = FIT_SLACK_MM) -> list[int]:
    """長さ以下のスパン列: 壁際の余り slack 以内でスパンの本数がいちばん少ない（長いスパン）もの、次に長いもの."""
    from .plan_solver import achievable_sums

    if length < min(coins):
        return []
    lo = max(min(coins), int(length - slack))
    table = achievable_sums(coins, lo, int(length))
    if not table:
        table = achievable_sums(coins, min(coins), int(length))
    best = min(table, key=lambda s: (len(table[s]), -s))
    return sorted(table[best], reverse=True)


def solve_stage(item: dict, master, capacities: Optional[dict] = None) -> StageResult:
    """内部ステージ足場を解いて検証する."""
    from .elevation_solver import solve_elevation

    name = str(item.get("name") or "内部ステージ足場")
    p0, u, v, la, lb = _frame(item["corners_mm"])
    coins = master.span_lengths()
    # EVシャフトは壁とのすき間を 30cm 以下にする（外周の手すりを省ける）ので、壁際の余りを小さく取る
    shaft_use = str(item.get("use", "")) in ("EVシャフト", "シャフト")
    slack = 2 * (SHAFT_WALL_GAP_MAX_MM - CLEAR_MM) if shaft_use else FIT_SLACK_MM
    # 短手（足場の幅）は 1219 まで（利用者の指定 2026-10-29: 足場の幅は1200までだよ1219）。枠組は建枠の幅で割る
    widths_v = (master.frame_widths() if master.is_frame and master.frame_widths()
                else [c for c in coins if c <= STAGE_WIDTH_MAX_MM]) or coins
    form = None
    if str(item.get("use", "")) in ("支保工", "型枠支保工"):
        # 型枠支保工は型枠の計算（せき板・根太・大引）と支柱1本の軸力で支柱の間隔を決める（利用者の指定 2026-10-29:
        # 型枠の計算をしないとスパン決めれないよ、1800飛ばせないと思う）
        tie0 = str(item.get("tie", "") or "")
        lo = SHORING_MIN_SPAN.get(str(getattr(master, "series_id", "")), 0)
        if "先行手摺ブレス" in tie0 and "強力斜材" in tie0:
            lo = max(lo, SHORING_MIN_SPAN_STRONG45)
        if lo:
            coins = [c for c in coins if c >= lo] or coins
            widths_v = [c for c in widths_v if c >= lo] or widths_v
        form = _shoring_form_spans(item, master, capacities, coins, widths_v)
        if form["spans"] is not None:
            umax, vmax = form["spans"]
            coins = [c for c in coins if c <= umax] or coins
            widths_v = [c for c in widths_v if c <= vmax] or widths_v
    su = _fit_spans(coins, la - 2 * CLEAR_MM, slack)
    sv = _fit_spans(widths_v, lb - 2 * CLEAR_MM, slack)
    if not su or not sv:
        raise ValueError(f"{name}: 範囲（{la:.0f}×{lb:.0f}）が狭くて支柱が立ちません")
    # 割り付けた格子を範囲の中央に寄せる
    off_u = (la - sum(su)) / 2.0
    off_v = (lb - sum(sv)) / 2.0
    origin = (p0[0] + u[0] * off_u + v[0] * off_v, p0[1] + u[1] * off_u + v[1] * off_v)
    deck_req = float(item.get("deck_mm", 0.0) or 0.0)
    if deck_req < 1000.0:
        raise ValueError(f"{name}: 作業床の高さ（deck_mm）を 1000 以上で指定してください")
    guard = 2 * int(master.koma_pitch) + int(getattr(master, "koma_top_gap", 0) or 0)
    try:
        elev, low_err = solve_elevation(int(round(deck_req)) + guard, master=master), None
    except ValueError as ex:            # 系列の最小の高さを下回る（支保工は天井から積み方を選び直すので後で判断）
        elev, low_err = None, ex
    shoring = str(item.get("use", "")) in ("支保工", "型枠支保工")
    ceil_mm = item.get("ceiling_mm")
    depth = float(item.get("form_depth_mm", FORM_DEPTH_MM) or FORM_DEPTH_MM)
    base_up = 0
    if shoring and ceil_mm:
        # 支保工は支柱の天端を大引の下に合わせる: 大引受けジャッキの繰出しが UHEAD_EXT_TARGET_MM に近い支柱の積み方
        # 大引受けジャッキだけで届かない（コマ 450 の刻みの間に落ちる）ときは、足元のジャッキも繰り出して上げる
        # （天井 4200 で積み方が見つからず、支柱が天井を突き抜ける既定の積み方に戻っていた）
        from .elevation_solver import JACK_MAX_EXTENSION

        want = float(ceil_mm) - depth
        best = None
        for req in range(max(1000, int(want) - 1200), int(want) + 1, 25):
            try:
                e = solve_elevation(req, master=master)
            except ValueError:
                continue                # 系列の最小の高さを下回る（単管は 2030 未満が組めない）
            extra = want - (e.jack_extension + sum(e.posts))
            if extra < 0:
                continue
            up = int(min(max(0.0, extra - UHEAD_EXT_TARGET_MM), max(0, JACK_MAX_EXTENSION - e.jack_extension)))
            ext = extra - up
            if ext <= UHEAD_EXT_MAX_MM and (best is None or abs(ext - UHEAD_EXT_TARGET_MM) < best[0]):
                best = (abs(ext - UHEAD_EXT_TARGET_MM), e, up)
        if best is not None:
            elev, base_up = best[1], best[2]
    if elev is None:
        raise ValueError(f"{name}: {low_err}")
    # 作業床は指定にいちばん近い段（コマの位置で決まるので少し上下する。実機 2026-10-24: 4000 の指定で 4025 を捨てて
    # 2225 になった）
    hs = [int(h) + base_up for h in elev.level_heights]
    deck = min(hs, key=lambda h: (abs(h - deck_req), h)) if hs else int(deck_req)
    root = int(elev.first_ledger_height) + base_up
    koma = int(master.koma_pitch or 0)
    if shoring and koma >= 300 and abs(deck - deck_req) > koma / 2:
        # 支保工は天井から支柱の積み方を選び直すので、層の段が指定の作業床から離れることがある。くさびはコマごとに
        # 布材を掛けられるので、指定にいちばん近いコマの高さを作業床の段にする（1800 の指定が 2465 になっていた）
        # コマは層の段と同じ並び（根がらみはコマから半分ずれることがあるので、層の段から数える）
        k = round((deck_req - deck) / koma)
        cand = deck + k * koma
        top0 = int(elev.jack_extension + base_up + sum(elev.posts))
        while cand + GUARD_MM > top0 and cand - koma > root + koma / 2:
            cand -= koma                    # 作業床の手すりが支柱の天端（大引の下）を超えない
        while cand <= root + koma / 2:
            cand += koma
        deck = int(cand)
        hs = sorted(set(hs) | {deck})
    levels = [root] + [h for h in hs if h <= deck]
    live = float(item.get("live_kn_m2", LIVE_DEFAULT_KN_M2) or LIVE_DEFAULT_KN_M2)
    res = StageResult(name, origin, u, v, su, sv, levels, deck, float(item.get("base_mm", 0.0) or 0.0),
                      list(elev.posts), int(elev.jack_extension) + base_up, live)
    res.top_mm = int(elev.jack_extension + base_up + sum(elev.posts))
    if shoring:
        # 作業床より上の段と、間隔が TIE_PITCH_MAX_MM を超える所に足す段（くさびはコマごとに布材を付けられる）
        add = [h for h in hs if deck < h < res.top_mm]
        lv = sorted(levels + add + [res.top_mm])
        koma = int(master.koma_pitch) or 450
        for a, b in zip(lv, lv[1:]):
            n = math.ceil((b - a) / TIE_PITCH_MAX_MM) - 1
            for i in range(1, n + 1):
                # コマは作業床の段と同じ並び（根がらみから数えるとコマから半分ずれることがある）
                pos = a + (b - a) * i / (n + 1)
                add.append(int(deck + round((pos - deck) / koma) * koma))
        res.upper_levels = sorted(set(add) - set(levels))
    res.ceiling_mm = float(ceil_mm) if ceil_mm else None
    res.form = form
    res.series_id = str(getattr(master, "series_id", "") or "")
    if shoring:
        res.use = "支保工"
        res.slab_mm = float(item.get("slab_mm", 200.0) or 200.0)
        res.live_kn_m2 = SHORING_LIVE_KN_M2
        res.design_kn_m2 = RC_KN_M3 * res.slab_mm / 1000.0 + FORM_KN_M2 + SHORING_LIVE_KN_M2
        ties = shoring_ties(capacities)
        tie = str(item.get("tie", "") or ties[0])
        res.tie = tie if tie in ties else ties[0]
        if res.ceiling_mm:
            res.uhead_ext_mm = int(round(res.ceiling_mm - depth - res.top_mm))
    res.wall_gap_mm = max(off_u, off_v)
    if str(item.get("use", "")) in ("EVシャフト", "シャフト"):
        res.use = "EVシャフト"
        res.floors_mm = sorted(float(f) for f in (item.get("floors_mm") or []) if 0 < float(f) < deck + 1)
        # 作業床は各層（層の高さごと）に全面に張り、各層にハッチ付布板で昇降する（利用者の指定 2026-10-29: エレベーター
        # シャフトは階段ではなくハッチつきアンチ／各層に作業床＋ハッチ）。各階の床の高さは壁つなぎの段に使う
        res.deck_levels = sorted(set(levels[1:]) - {deck})
        fh0 = int(master.floor_height or 1800)
        first = min(levels[1:]) if levels[1:] else deck
        low = first - fh0
        if first > fh0 + STAIR_FIRST_TOL_MM and low > levels[0] + 100:
            # 最初の段が高くハッチの梯子（層の高さ1つ分）がピットまで届かないので、1層下にいちばん下の踊り場を足す
            # （梯子はそこまで、ピットの床から踊り場へは踏台）
            res.levels = sorted(set(res.levels) | {low})
            res.deck_levels = sorted(set(res.deck_levels) | {low})
            levels = sorted(set(levels) | {low})
        res.guard = res.wall_gap_mm > SHAFT_WALL_GAP_MAX_MM
    # 昇降は階段（利用者の指定 2026-10-29: ハシゴじゃなくて階段を使う）。隅の1スパンに、層の高さの段どうしを階段枠でつなぐ
    # 階段の上（"stair"）は足元が建物の段で階段枠が据わらないので、指定が無ければ建物の階段から作業床の端へ出入りする
    # EVシャフトはハッチ付布板（梯子内蔵）で昇降する（利用者の指定 2026-10-29: エレベーターシャフトは階段ではなく
    # ハッチつきアンチにして）
    shaft = str(item.get("use", "")) in ("EVシャフト", "シャフト")
    access = str(item.get("access") or ("建物の階段" if item.get("stair") else ("ハッチ" if shaft else "階段")))
    res.access = access
    res.open_end = bool(item.get("open_end"))
    res.end_post_kn = float(item.get("end_post_kn", 0.0) or 0.0)
    if access == "ハッチ":
        # 層ごとの段に1枚ずつ（地面から最初の段を含む）。上下で位置をずらす
        res.stair_fh = int(master.floor_height or 1800)
        res.hatch_levels = sorted(set(levels[1:]))
    if access == "階段":
        fh = int(master.floor_height or 1800)
        res.stair_fh = fh
        # 本体の階段室と同じく、地面から最初の段までを1台目（足元は敷板の上）、あとは層ごとに1台
        lands = sorted(set(levels[1:]))
        res.stair_flights = list(zip([0] + lands[:-1], lands))
    if item.get("stair"):
        _stair_feet(res, master, dict(item["stair"]), off_u, off_v)
    _quantity(res, master)
    _checks(res, master, capacities)
    if res.top_mm >= SCAFFOLD_CHIEF_MM and res.use != "支保工":
        res.notes.append(f"支柱の高さ {res.top_mm}mm（5m 以上）なので足場の組立て等作業主任者を選任する（安衛則565条・566条）")
    if res.stair_feet:
        _stair_checks(res)
    if res.use == "支保工":
        _shoring(res, master, capacities)
    return res


def _stair_feet(r: StageResult, master, st: dict, off_u: float, off_v: float) -> None:
    """階段の上の支柱: 段の高さ z の脚は、下端を作業床の段（コマ）にそろう高さまで上げ、支柱を短くしてジャッキで受ける.

    stair: {"axis": "u"（長手）か "v", "from_mm": 範囲の始めの辺から1段目の蹴上げまで, "tread_mm", "riser_mm", "steps"}。
    踏面は始めの辺から遠い方へ上がる（"down": true なら下がる＝範囲の始めの側が高い）。
    """
    from .elevation_solver import JACK_MAX_EXTENSION, JACK_MIN_EXTENSION, _compose_table

    axis = str(st.get("axis", "u"))
    tread = float(st.get("tread_mm", 250) or 250)
    riser = float(st.get("riser_mm", 180) or 180)
    steps = int(st.get("steps", 0) or 0)
    start = float(st.get("from_mm", 0) or 0)
    down = bool(st.get("down", False))
    spans, off = (r.spans_u, off_u) if axis == "u" else (r.spans_v, off_v)
    xs, acc = [off], off
    for sp in spans:
        acc += sp
        xs.append(acc)
    koma = int(master.koma_pitch) or 450
    hard = master.jack_hard_max_mm()
    rated = max(JACK_MAX_EXTENSION, min(hard, 432))
    # 枠組は建枠・調整枠の高さ、くさび・単管は支柱の長さ
    lengths = sorted(set(master.frame_heights() if master.is_frame else master.post_lengths()), reverse=True)
    if master.system_type not in (FRAME, TUBE):
        # くさびはコマの倍数の支柱だけ（675・1125 などの半端な支柱を挟むとコマがずれて布材が掛からない）
        lengths = [v for v in lengths if v % koma == 0] or lengths
    table = _compose_table(r.top_mm + max(lengths), lengths)
    # 調整カラー（アルバトロス 60・150・300。支柱の下に継いで高さを足す）。ジャッキと敷板の前に使う（1脚に1個）
    collars = [0] + sorted({int(p.nominal_dim) for p in master.by_category("調整カラー") if p.nominal_dim > 0})
    for i, x in enumerate(xs):
        k = 0 if x < start else min(steps, int((x - start) // tread) + 1)
        z = (steps - k if down else k) * riser
        edges = [start + j * tread for j in range(steps + 1)]
        edge = min((abs(x - e) for e in edges), default=1e9)
        col = 0
        if z == 0:
            ext, shim, stack = r.jack_mm, 0, list(r.posts)
        elif master.system_type == TUBE:
            # 単管はクランプでどこでも継げるので、ジャッキはそのままにして足りる長さ以上の最少の本数（上に出る分は手すり柱）
            ext, shim = r.jack_mm, 0
            need0 = int(round(r.top_mm - z - ext))
            stack = next((table[t] for t in range(max(need0, 0), need0 + max(lengths) + 1) if t in table), None)
        else:
            # 支柱（建枠）の組み合わせで天端がそろうジャッキの繰出しを探す（くさびはコマ 450 の倍数の支柱なので段も
            # そろう。枠組は建枠・調整枠の高さの組み合わせ）。敷板なし・実務上限 270 以内を先に、次に短い繰出し
            stack, ext, shim = None, JACK_MIN_EXTENSION, 0
            best = None
            for sh in range(0, SHIM_BOARDS_MAX + 4):
                for c in collars:
                    for e in range(JACK_MIN_EXTENSION, rated + 1):
                        t = int(round(r.top_mm - z - e - sh * SHIM_BOARD_MM - c))
                        if t in table and table[t]:
                            # 敷板が少なく、実務上限 270 以内、調整カラー無し、継ぎの少ない積み方、短い繰出しの順
                            key = (sh, e > JACK_MAX_EXTENSION, c > 0, len(table[t]), e)
                            if best is None or key < best[0]:
                                best = (key, e, sh, table[t], c)
                if best is not None and best[0][0] == sh:
                    break
            if best is not None:
                _, ext, shim, stack, col = best
            else:
                ext = min(rated, max(JACK_MIN_EXTENSION, int(r.top_mm - z) % max(koma, 1)))
        need = int(round(r.top_mm - z - ext - shim * SHIM_BOARD_MM - col))
        # 根がらみ: 支柱の下端から NEGARAMI_MAX_MM 以内に段（布材）が無い列は、その支柱の最初のコマに足す
        bottom = z + shim * SHIM_BOARD_MM + ext + col
        above = [h for h in r.levels if h > bottom + 100]
        neg = 0
        if not master.is_frame and (not above or above[0] > bottom + NEGARAMI_MAX_MM):
            neg = int(r.levels[0] + math.ceil((bottom + 100 - r.levels[0]) / koma) * koma)
        r.stair_feet.append({"axis": axis, "index": i, "x_mm": round(x), "z_mm": z, "jack_mm": int(round(ext)),
                             "shim": shim, "posts": stack, "post_mm": need, "edge_mm": round(edge), "negarami_mm": neg,
                             "collar_mm": col})


def _stair_checks(r: StageResult) -> None:
    from .elevation_solver import JACK_MAX_EXTENSION

    feet = r.stair_feet
    out = r.checks
    zs = sorted({f["z_mm"] for f in feet})
    jacks = [f["jack_mm"] for f in feet]
    over = [f for f in feet if f["shim"] > SHIM_BOARDS_MAX or f["posts"] is None]
    shims = [f for f in feet if 0 < f["shim"] <= SHIM_BOARDS_MAX]
    long_ = [f for f in feet if f["jack_mm"] > JACK_MAX_EXTENSION]
    st = "NG" if over else ("WARN" if shims or long_ else "OK")
    msg = (f"階段の上の支柱の列 {len(feet)}（段の高さ {'・'.join(f'{z:.0f}' for z in zs)}）: 支柱を段ごとに短くし、ジャッキの繰出し "
           f"{min(jacks)}〜{max(jacks)}mm で作業床の段にそろえる")
    if long_:
        msg += f"。繰出しが {JACK_MAX_EXTENSION}mm を超える列 {len(long_)}（許容繰出しの大きいロングジャッキを使う）"
    cols = [f for f in feet if f.get("collar_mm")]
    if cols:
        msg += (f"。調整カラー（{'・'.join(str(c) for c in sorted({f['collar_mm'] for f in cols}))}）を継ぐ列 {len(cols)}"
                "（斜めに並ぶので傾斜方向に単管で頭つなぎ。スギコ カタログ p027）")
    if shims:
        msg += f"。敷板 {max(f['shim'] for f in shims)}枚で上げる列 {len(shims)}（{SHIM_BOARDS_MAX}枚まで）"
    if over:
        msg += (f"。{len(over)}列はジャッキ＋敷板 {SHIM_BOARDS_MAX}枚で受けきれない（敷角を重ねない。支柱の位置を踏面の"
                "中ほどにずらすか、段ごとに建地を立てて調整する）")
    out.append(StageCheck("階段の上の支柱", st, msg + "（ジャッキは段差を埋める道具ではない。報告 地足場と内部足場）"))
    # 作業床の段がその列の支柱の下端（段＋敷板＋ジャッキ）より低いと、その列に布材が掛からず床を受けられない
    low = [f for f in feet if r.deck_mm < f["z_mm"] + f["shim"] * SHIM_BOARD_MM + f["jack_mm"] + f.get("collar_mm", 0) + 100]
    if low:
        out.append(StageCheck("作業床と踊り場", "NG",
                              f"{len(low)}列（段の高さ {'・'.join(str(int(f['z_mm'])) for f in low)}）で作業床 {r.deck_mm}mm が"
                              "支柱の下端より低く、布材が掛からない。作業床を上げるか、範囲を踊り場の手前で止める（踊り場は床の上で作業）"))
    near = [f for f in feet if f["edge_mm"] < PLATE_HALF_MM]
    if near:
        out.append(StageCheck("踏面の端", "WARN",
                              f"{len(near)}列の支柱が段鼻・蹴上げから {PLATE_HALF_MM}mm 以内（ジャッキの底板が踏面に乗りきらない）。"
                              "踏面に敷板を渡して受けるか、スパンをずらす"))
    r.notes.append("階段の上の支柱は段ごとに下端の高さが違うので、根がらみは段ごとにその支柱の最初のコマで取り、"
                   "脚の滑り止め（踏面に敷板を釘止め・根がらみを2方向）を付ける")


def _form_checks(r: StageResult) -> None:
    """型枠（せき板・根太・大引）の曲げとたわみを、実際の支柱の間隔（長手・短手の最大）で検定して書く."""
    from .formwork import DEFLECTION_MAX_MM, NEDA_PITCH_MM, check

    fm = r.form or {}
    if not fm:
        return
    res = check(fm["q"], fm["q_dead"], max(r.spans_u), max(r.spans_v), fm["neda"], fm["obiki"])
    ok = all(c.ok for c in res)
    parts = "、".join(f"{c.part}（{c.member}・スパン {c.span_mm:.0f}）σ{c.sigma:.0f}/{c.fb:.0f}N/mm²・"
                     f"δ{c.deflection_mm:.1f}/{DEFLECTION_MAX_MM:.0f}mm" for c in res)
    lim = fm.get("spans")
    r.checks.append(StageCheck("型枠（せき板・根太・大引）", "OK" if ok else "NG",
                               f"{parts}。根太 @{NEDA_PITCH_MM:.0f}、単純梁（曲げは設計荷重、たわみは固定荷重）"
                               + (f"。支柱の間隔は {lim[0]}×{lim[1]} まで（型枠の部材と支柱の軸力から）" if lim else
                                  "。どの定尺の間隔でも通らない: 根太・大引を強い部材にするか支柱の間隔を詰める")))


def _shoring_form_spans(item: dict, master, caps: Optional[dict], coins: list[int], widths_v: list[int]) -> dict:
    """型枠支保工の支柱の間隔の上限: せき板・根太・大引（formwork）と支柱1本の軸力がみな通る、いちばん広い定尺の組."""
    from .formwork import DEFAULT_NEDA, DEFAULT_OBIKI, NEDA, OBIKI, max_spans

    slab = float(item.get("slab_mm", 200.0) or 200.0)
    q_dead = RC_KN_M3 * slab / 1000.0 + FORM_KN_M2
    q = q_dead + SHORING_LIVE_KN_M2
    fm = dict(item.get("form") or {})
    neda = str(fm.get("neda") or DEFAULT_NEDA)
    obiki = str(fm.get("obiki") or DEFAULT_OBIKI)
    neda = neda if neda in NEDA else DEFAULT_NEDA
    obiki = obiki if obiki in OBIKI else DEFAULT_OBIKI
    ties = shoring_ties(caps)
    tie = str(item.get("tie", "") or ties[0])
    allow = _cap(caps, "支保工許容支持力", tie if tie in ties else ties[0]) or \
        _cap(caps, "支柱許容圧縮耐力") or 1e9
    h_m = float(item.get("ceiling_mm") or 4000.0) / 1000.0

    def post_ok(su: int, sv: int) -> bool:
        return (su / 1000.0) * (sv / 1000.0) * q + POST_SELF_KN_PER_M * h_m <= allow

    spans = max_spans(q, q_dead, sorted(coins, reverse=True), sorted(widths_v, reverse=True), post_ok, neda, obiki)
    return {"neda": neda, "obiki": obiki, "q": q, "q_dead": q_dead, "spans": spans}


def _shoring_spacing_hint(r: StageResult, master, caps: Optional[dict], q: float, h_m: float) -> str:
    """支保工の軸力が許容を超えたときの案内: 今のつなぎ方で収まる支柱の間隔（定尺の組み合わせ）と、強いつなぎ方."""
    allow = _cap(caps, "支保工許容支持力", r.tie) or 0.0
    coins = sorted(master.span_lengths(), reverse=True)
    fits = [(a, b) for a in coins for b in coins if b <= a
            and (a / 1000.0) * (b / 1000.0) * q + POST_SELF_KN_PER_M * h_m <= allow]
    msg = ""
    if fits:
        a, b = max(fits, key=lambda ab: ab[0] * ab[1])
        msg = f"。支柱の間隔を {a}×{b} 以下に詰める"
    stronger = [t for t in shoring_ties(caps) if (_cap(caps, "支保工許容支持力", t) or 0.0) > allow]
    if stronger:
        msg += f"{'か、' if msg else '。'}つなぎ方を {'・'.join(stronger)} にする"
    return msg or "。支柱の間隔を詰める"


def _shoring(r: StageResult, master, caps: Optional[dict]) -> None:
    """型枠支保工として使うときの部材と検定（手引 14章・参考資料2）."""
    nu, nv = len(r.spans_u), len(r.spans_v)
    n_posts = (nu + 1) * (nv + 1)
    # 頂部: 大引受けジャッキ（鋼製の受け金物で大引を固定）、大引は長手の支柱の列ごと、根太・せき板は型枠大工
    r.quantity.append(("大引受けジャッキ", 0, n_posts, "支保工の頂部（大引を受けて固定する）"))
    from .formwork import NEDA, OBIKI

    fm = r.form or {}
    ob = OBIKI[fm["obiki"]].name if fm.get("obiki") in OBIKI else "大引"
    ne = NEDA[fm["neda"]].name if fm.get("neda") in NEDA else "根太"
    r.quantity.append(("大引", int(r.length_u), nv + 1, f"支保工の大引（{ob}・長手の支柱の列ごと。継ぎは支柱の上）"))
    if fm:
        from .formwork import NEDA_PITCH_MM

        n_neda = int(math.floor(r.length_u / NEDA_PITCH_MM)) + 1
        r.quantity.append(("根太", int(r.length_v), n_neda, f"支保工の根太（{ne}・@{NEDA_PITCH_MM:.0f}・大引の上に短手の向き）"))
    su, sv = max(r.spans_u) / 1000.0, max(r.spans_v) / 1000.0
    h_m = r.top_mm / 1000.0
    q = r.design_kn_m2
    out = r.checks
    # 足場としての支柱の軸力（作業床の積載だけ）は支保工の軸力に置き換える
    out[:] = [c for c in out if c.item != "支柱の軸力"]
    _form_checks(r)
    out.append(StageCheck("支保工の設計荷重", "OK",
                          f"固定 {RC_KN_M3 * r.slab_mm / 1000:.2f}（鉄筋コンクリート 2400kg/m³×{r.slab_mm:.0f}mm）＋型枠 {FORM_KN_M2:.2f}"
                          f"＋積載 {SHORING_LIVE_KN_M2:.2f}（150kg/m²）＝{q:.2f}kN/m²（安衛則240条・計画届作成の手引 p261）"))
    n_kn = _trib_m2(r) * q + POST_SELF_KN_PER_M * h_m
    # 支柱の下の床（下の階のスラブ）が受ける力。打設の荷重がそのまま下の階へ降りる
    r.notes.append(f"支柱の下の床（下の階のスラブ）は支柱1本 {n_kn:.1f}kN（{q:.1f}kN/m² 相当）を受ける。"
                   "下の階のスラブの材齢・強度で受けられるか確かめ、受けられなければ下の階の支保工を残すか（盛り替え）、"
                   "敷板・敷角で分散する")
    if "強力斜材" in r.tie:
        # アルバトロス強力斜材の使用条件（スギコ カタログ p062 注意事項）
        r.notes.append("強力斜材の支保工（45.0kN・49.1kN仕様）: ジャッキ型ベース金具の繰出しは 270mm 以下、斜材は基本 H900・最下部は"
                       " H675、布材と強力斜材・先行手摺と強力斜材は高さ 900mm 以下に設置、最下層は根がらみプレート付支柱、支柱の"
                       "最下端と最上端は梁間・桁行とも根がらみ・頭つなぎ（最上段が先行手摺ブレスなら桁行に単管で頭つなぎ）。"
                       "45.0kN仕様の支柱間隔は 914〜1829、49.1kN仕様は 610〜1829（スギコ カタログ p061〜062）")
        if r.jack_mm > 270:
            out.append(StageCheck("強力斜材の使用条件", "NG",
                                  f"ジャッキの繰出し {r.jack_mm}mm が 270mm を超える（強力斜材の支保工は 270 以下。p062）。"
                                  "支柱の積み方か作業床・天井の高さを見直す"))
        if "先行手摺ブレス" in r.tie and min(r.spans_u + r.spans_v) < 914:
            out.append(StageCheck("強力斜材の使用条件", "NG",
                                  f"45.0kN仕様の支柱間隔は 914〜1829（{min(r.spans_u + r.spans_v)} の升目がある。p061）。"
                                  "49.1kN仕様（強力斜材＋強力斜材×強力斜材＋強力斜材）にするか間隔を広げる"))
    allow = _cap(caps, "支保工許容支持力", r.tie)
    if allow is None:
        scaf = _cap(caps, "支柱許容圧縮耐力")
        if scaf is not None and n_kn <= scaf:
            out.append(StageCheck("支保工の支柱の軸力", "OK",
                                  f"{_post_label(r)}1本 {n_kn:.2f}kN ≦ 足場としての許容 {scaf:.1f}kN（支保工の承認値は"
                                  "これより大きいので足りる。手引 p143）"))
        else:
            out.append(StageCheck("支保工の支柱の軸力", "WARN",
                                  f"{_post_label(r)}1本 {n_kn:.2f}kN。この機種の支保工の許容支持力（承認値・つなぎ方別）を"
                                  "メーカーに確かめる（組み合わされた支保工は指定の最大使用荷重以下。安衛則240条3項2号・手引 p143）"))
    else:
        st = "OK" if n_kn <= allow else "NG"
        out.append(StageCheck("支保工の支柱の軸力", st,
                              f"{_post_label(r)}1本 {n_kn:.2f}kN {'≦' if st == 'OK' else '＞'} 許容 {allow:.1f}kN（{r.tie}）"
                              + ("" if st == "OK" else _shoring_spacing_hint(r, master, caps, q, h_m))
                              + "（組み合わされた支保工はメーカー指定の最大使用荷重以下。安衛則240条3項2号・手引 p143）"))
    ratio = SHORING_H_RATIO_FRAME if master.system_type == FRAME else SHORING_H_RATIO
    r.h_ratio = ratio
    area = r.length_u * r.length_v / 1e6
    hk = ratio * q * area
    have = min(2 * math.ceil(len(sp) / BRACE_EVERY_SPANS) for sp in (r.spans_u, r.spans_v))
    strong = _strong_brace_caps(r, caps)
    if strong is not None:
        # 強力斜材（くさびで固定）は1構面あたりの許容水平耐力がカタログにある（p061）。桁行（長手）・梁間（短手）で別に数える
        need_uv = (math.ceil(hk / strong[0]), math.ceil(hk / strong[1]))
        need = max(need_uv)
        how = (f"強力斜材の構面（許容水平耐力 桁行 {strong[0]:.1f}kN・梁間 {strong[1]:.1f}kN。カタログ p061）で受けると"
               f"各層 桁行 {need_uv[0]}・梁間 {need_uv[1]}構面以上、外周の構面は各方向 {have}")
    else:
        need = math.ceil(hk * math.sqrt(2.0) / BRACE_CLAMP_KN)
        need_uv = (need, need)
        how = (f"筋かい（45°・自在クランプ {BRACE_CLAMP_KN}kN。FD＝H/(n·cos45°)）で受けると各層・各方向 {need}本以上、"
               f"外周の筋かいは {have}本")
    out.append(StageCheck("支保工の水平荷重", "OK" if have >= need else "WARN",
                          f"設計荷重の {ratio * 100:.1f}%＝{hk:.1f}kN（{area:.0f}m²）を上端に見込む。" + how
                          + ("" if have >= need else (f"。内側の通りにも筋かいを足すか（各層・各方向あと {need - have}本）、" if need_uv[0] == need_uv[1] else
                             f"。内側の通りにも構面を足すか（各層 桁行あと {max(0, need_uv[0] - have)}・梁間あと "
                             f"{max(0, need_uv[1] - have)}）、")
                             + "打設済みの柱・壁に水平力を預ける形を構造計算書で示す")
                          + "（安衛則240条3項4号・手引 p263）"))
    r.inner_braces = max(0, need - have)
    # 交さ筋かいを入れられる升目（外周の筋かいの升目を除く）が足りないと、組数を満たせない
    room = min((len(r.spans_v) + 1) * len(r.spans_u), (len(r.spans_u) + 1) * len(r.spans_v)) - have
    if need - have > room:
        out.append(StageCheck("支保工の筋かいの入る升目", "NG",
                              f"各層・各方向に交さ筋かい {need - have}組が要るが、入れられる升目は {room}。支柱の間隔を詰めて升目を"
                              "増やすか、打設済みの柱・壁に水平力を預ける形を構造計算書で示す"))
    if have < need:
        # 足りない分を内側の通りに交さ筋かいで（各層・各方向。長さは長い方のスパン）
        layers = max(1, len(r.levels) + len(r.upper_levels) - 1)
        for spans, dir_, nd in ((r.spans_u, "長手", need_uv[0]), (r.spans_v, "短手", need_uv[1])):
            if nd <= have:
                continue
            what = "構面の強力斜材（H900 を1層に2段）" if strong is not None else "交さ筋かい"
            r.quantity.append(("強力斜材" if strong is not None else "筋交", int(max(spans)), (nd - have) * 2 * layers,
                               f"支保工の水平荷重を受ける内側の{what}（{dir_}・{layers}層×{nd - have}組）"))
    if r.uhead_ext_mm is not None:
        e = r.uhead_ext_mm
        if e < 0:
            st, msg = "NG", f"支柱の天端が大引の下端より {-e}mm 高い。短い支柱に替える"
        elif e > UHEAD_EXT_MAX_MM:
            st, msg = "NG", f"大引受けジャッキの繰出し {e}mm が {UHEAD_EXT_MAX_MM}mm を超える。支柱を足すか長い支柱に替える"
        else:
            st, msg = "OK", f"大引受けジャッキの繰出し {e}mm（{UHEAD_EXT_MAX_MM}mm 以下）"
        out.append(StageCheck("大引受けジャッキ", st, msg + f"（スラブ下端 {r.ceiling_mm:.0f}mm から型枠の厚さを引いた位置まで）"))
    # 根がらみから支柱の天端まで（作業床より上の段も入れる）。天端の上は大引受けジャッキ
    lv = sorted(r.levels + r.upper_levels + [r.top_mm])
    pitch = max((b - a for a, b in zip(lv, lv[1:])), default=0)
    out.append(StageCheck("水平つなぎ", "OK" if pitch <= TIE_PITCH_MAX_MM else "NG",
                          f"根がらみから支柱の天端まで布材の段の間隔 最大 {pitch}mm（{TIE_PITCH_MAX_MM}mm 以内ごとに直交2方向。"
                          "手引 p141・p268）"))
    if r.upper_levels:
        nu, nv = len(r.spans_u), len(r.spans_v)
        k = len(r.upper_levels)
        for s, cnt in sorted({sp: r.spans_u.count(sp) for sp in r.spans_u}.items()):
            r.quantity.append(("布材", int(s), cnt * (nv + 1) * k, "支保工の水平つなぎ（作業床の段のほか・長手）"))
        for s, cnt in sorted({sp: r.spans_v.count(sp) for sp in r.spans_v}.items()):
            r.quantity.append(("布材", int(s), cnt * (nu + 1) * k, "支保工の水平つなぎ（作業床の段のほか・短手）"))
    need_notify = r.top_mm >= SHORING_NOTIFY_MM
    out.append(StageCheck("設置届", "WARN" if need_notify else "OK",
                          (f"支柱高さ {r.top_mm}mm（3.5m 以上）なので型枠支保工の設置届（安衛法88条・様式20号）。"
                           "配置図・直交2方向の組立図・構造計算書を添付" if need_notify else
                           f"支柱高さ {r.top_mm}mm（3.5m 未満で届出不要）。組立図と構造計算書による組立は要る")))
    r.notes.append("敷板・敷角で沈下を防ぎ、根がらみで滑動を防ぐ。敷板・敷角は2段以上はさまない（安衛則242条・手引 p145・p268）")
    r.notes.append("大引は大引受けジャッキ（鋼製の受け金物）で固定し、継ぎは支柱の上で。根太・せき板は型枠の割付による")
    r.notes.append("型枠支保工の組立て等作業主任者を選任して指揮させる（高さに関係なく。安衛則246条・247条）。コンクリートの打設は"
                   "その日の作業前に支保工を点検し、偏らないよう打ち、異常があれば作業を止める（安衛則244条）")


def _strong_brace_caps(r: StageResult, caps: Optional[dict]) -> Optional[tuple[float, float]]:
    """強力斜材の支保工の構面の許容水平耐力（桁行, 梁間）。つなぎ方「桁行×梁間」の各側に 先行手摺ブレス があれば
    先行手摺ブレス＋H900斜材、無ければ H900斜材 の値（capacity.csv の 支保工許容水平耐力）。強力斜材でなければ None."""
    if r.use != "支保工" or "強力斜材" not in (r.tie or ""):
        return None
    vals = []
    for side in (r.tie.split("×") + [r.tie])[:2]:
        key = "先行手摺ブレス＋強力斜材" if "先行手摺ブレス" in side else "強力斜材"
        v = _cap(caps, "支保工許容水平耐力", key)
        if v is None:
            return None
        vals.append(v)
    return vals[0], vals[1]


def _quantity(r: StageResult, master) -> None:
    nu, nv = len(r.spans_u), len(r.spans_v)
    n_posts = (nu + 1) * (nv + 1)
    q = r.quantity
    # 階段の上の列は段ごとに支柱の積み方が違う（列ごとに直角方向の本数だけ）
    per_row = (nv + 1) if (r.stair_feet and r.stair_feet[0]["axis"] == "u") else (nu + 1)
    counts: dict[int, int] = {}
    stair_rows = [f for f in r.stair_feet if f["posts"]]
    for p in r.posts:
        counts[int(p)] = counts.get(int(p), 0) + n_posts - per_row * len(stair_rows)
    for f in stair_rows:
        for p in f["posts"]:
            counts[int(p)] = counts.get(int(p), 0) + per_row
    if master.is_frame:
        # 枠組: 長手の各通りに短手のスパンを渡る建枠を層ごとに立て、長手のスパンは交差筋かい（両面）でつなぐ
        for p in sorted(set(r.posts), reverse=True):
            k = r.posts.count(p) * (nu + 1) * nv
            q.append(("建枠", int(p), k, f"内部ステージの建枠（高さ{p}・幅{'/'.join(str(v) for v in sorted(set(r.spans_v)))}）"))
    else:
        for p, k in sorted(counts.items(), reverse=True):
            if k:
                q.append(("支柱", p, k, "内部ステージの支柱" + ("（階段の上は段ごとの長さ）" if stair_rows else "")))
    q.append(("ジャッキ", 0, n_posts, "内部ステージのジャッキベース"))
    n_shim = sum(f["shim"] for f in r.stair_feet) * per_row
    if n_shim:
        q.append(("敷板", 0, n_shim, "階段の上の支柱の高さ合わせ（1脚 2枚まで）"))
    for c in sorted({f.get("collar_mm", 0) for f in r.stair_feet} - {0}):
        q.append(("調整カラー", c, sum(1 for f in r.stair_feet if f.get("collar_mm") == c) * per_row,
                  "階段の上の支柱の高さ合わせ（支柱の下に継ぐ）"))
    # 段ごとの根がらみ: その列の直角方向（列の中）と、足元の低い隣の列へ1スパンずつ
    feet = r.stair_feet
    cross = r.spans_v if (feet and feet[0]["axis"] == "u") else r.spans_u
    along = r.spans_u if (feet and feet[0]["axis"] == "u") else r.spans_v
    neg: dict[int, int] = {}
    for k, f in enumerate(feet):
        if not f["negarami_mm"]:
            continue
        for sp in cross:
            neg[int(sp)] = neg.get(int(sp), 0) + 1
        for nb, sp in ((k - 1, along[k - 1] if k > 0 else None), (k + 1, along[k] if k < len(along) else None)):
            if sp is not None and 0 <= nb < len(feet) and feet[nb]["z_mm"] < f["z_mm"]:
                neg[int(sp)] = neg.get(int(sp), 0) + per_row
    for sp, k in sorted(neg.items()):
        q.append(("布材", sp, k, "階段の上の段ごとの根がらみ"))
    n_lv = len(r.levels)                       # 根がらみ＋各段
    if master.is_frame:
        n_fl = max(1, len(r.posts))           # 建枠の段数
        for s in sorted(set(r.spans_u)):
            q.append(("筋交", int(s), r.spans_u.count(s) * (nv + 1) * n_fl,
                      "内部ステージの交差筋かい（長手のスパンを各通り・各段）"))
    else:
        for s in sorted(set(r.spans_u)):
            k = r.spans_u.count(s) * (nv + 1) * n_lv
            q.append(("布材", int(s), k, "内部ステージの布材（長手）"))
        for s in sorted(set(r.spans_v)):
            k = r.spans_v.count(s) * (nu + 1) * n_lv
            q.append(("布材", int(s), k, "内部ステージの布材（短手）"))
    # 最上段の全面の踏板: 長手のスパンに掛け、短手のスパンを踏板の幅で埋める
    widths = sorted({int(w) for w in getattr(master, "deck_widths", (500, 240)) or (500, 240)}, reverse=True)
    decks: dict[tuple[int, int], int] = {}
    gaps: dict[tuple[int, int], int] = {}      # (長手のスパン, すき間の幅) → 升目の数
    for s_u in r.spans_u:
        for s_v in r.spans_v:
            rest = float(s_v) - 30.0
            for w in widths:
                k = int(rest // w)
                if k:
                    decks[(int(s_u), w)] = decks.get((int(s_u), w), 0) + k
                    rest -= k * w
            if rest > DECK_GAP_MAX_MM:
                # 布板で埋めきれないすき間はすき間板でふさぐ（ステージは全面の作業床。すき間 3cm 以下）
                key = (int(s_u), int(round(rest)))
                gaps[key] = gaps.get(key, 0) + 1
    n_deck = 1 + len(r.deck_levels)
    if r.access == "ハッチ" and r.hatch_levels:
        # 作業床の段のハッチは幅500の布板1枚と入れ替える
        n_rep = len({h for h in r.hatch_levels if h > LOW_LANDING_STEP_MM} & set(r.deck_levels + [r.deck_mm]))
        key = (int(r.spans_u[0]), max(widths))
        if n_rep and key in decks:
            decks[key] = decks[key] - n_rep / n_deck
    # 階段の隅の1スパンは、階段が上がって来る作業床の段で床を張らない（開口部手摺で囲う）
    open_lv = len({b for _a, b in r.stair_flights} & set(r.deck_levels + [r.deck_mm]))
    if open_lv:
        # 階段の升目は階段の通る幅（階段枠 450 を2列で折り返し＋すき間 100、狭ければ1列）を抜いて残りに張る
        def fill(width: float) -> dict[int, int]:
            got, rest = {}, width - 30.0
            for w in widths:
                k = int(rest // w)
                if k:
                    got[w] = k
                    rest -= k * w
            return got
        sv0 = float(r.spans_v[0])
        lane = STAIR_LANE_MM * 2 + 100 if sv0 >= STAIR_LANE_MM * 2 + 100 else STAIR_LANE_MM + 100
        full, left = fill(sv0), fill(sv0 - lane)
        for w in widths:
            diff = full.get(w, 0) - left.get(w, 0)
            if diff:
                key = (int(r.spans_u[0]), w)
                decks[key] = decks.get(key, 0) - diff * open_lv / n_deck
    for (s_u, g), k in sorted(gaps.items()):
        # 系列にすき間板の品があれば品番と幅を書き、入れても 3cm を超えて残らないか確かめる（アルバトロスの
        # フック付すきま埋め板は幅175。カタログ p045）
        gp = next((p for p in master.by_category("すき間板") if p.nominal_dim == s_u), None) if master else None
        gw = int(re.search(r"幅(\d+)", gp.note).group(1)) if gp is not None and re.search(r"幅(\d+)", gp.note) else 0
        what = f"布板のすき間 {g}mm をふさぐ（ステージは全面の作業床・すき間 3cm 以下）"
        if gp is not None:
            left = g - gw
            what += (f"。{gp.model_no}（幅{gw}）" + (f"を入れて残り {left}mm" if 0 <= left <= DECK_GAP_MAX_MM else
                     f"1枚では {left}mm 残るので2枚か布板の幅を組み替える" if left > DECK_GAP_MAX_MM else
                     f"は {-left}mm 入らないので布板の幅を組み替える"))
        q.append(("すき間板", s_u, k * n_deck, what + (f"×{n_deck}段" if n_deck > 1 else "")))
    for (s_u, w), k in sorted(decks.items()):
        n = int(round(k * n_deck))
        if n > 0:
            q.append(("踏板", s_u, n, f"内部ステージの全面の作業床（幅{w}）"
                      + (f"×{n_deck}段（{'各層' if r.use == 'EVシャフト' else '各段'}）" if n_deck > 1 else "")
                      + ("・階段の開口を除く" if open_lv else "")
                      + ("・ハッチの分を除く" if r.access == "ハッチ" else "")))
    # 外周の手すり・中桟（2本）と幅木（EVシャフトは壁が近いので無し）
    per = {}
    for s in r.spans_u:
        per[s] = per.get(s, 0) + 2
    for s in r.spans_v:
        per[s] = per.get(s, 0) + (1 if r.open_end else 2)
    tail = "（終わりの短辺は出入口で除く）" if r.open_end else ""
    for s, k in sorted(per.items()) if r.guard else ():
        q.append(("布材", int(s), 2 * k, "内部ステージの外周の手すり・中桟" + tail))
        q.append(("幅木", int(s), k, "内部ステージの外周の幅木" + tail))
    if r.use == "EVシャフト":
        q.append(("壁つなぎ", 0, 4 * max(1, len(r.floors_mm)), "EVシャフトの四方の壁へ（各階）"))
    # 外周の構面の筋かい（各辺 5スパン以下ごと・各段）
    n_br = 0
    n_bands = n_lv + len(r.upper_levels) - 1          # 支保工は作業床より上の水平つなぎの段まで
    for spans in (r.spans_u, r.spans_u, r.spans_v, r.spans_v):
        n_br += math.ceil(len(spans) / BRACE_EVERY_SPANS) * n_bands
    if r.use == "支保工" and "強力斜材" in (r.tie or "") and master.by_category("強力斜材"):
        # 強力斜材の支保工は外周の構面も強力斜材（H900 を1層に2段。p061 の図）
        q.append(("強力斜材", int(max(r.spans_u)), n_br * 2, "支保工の外周の構面の強力斜材（H900 を1層に2段）"))
    else:
        q.append(("筋交", int(max(r.spans_u)), n_br * 2, "内部ステージの外周の筋かい（交さ2方向）"))
    if r.stair_flights:
        nf = len(r.stair_flights)
        stair = next(iter(master.by_category("階段")), None)
        q.append(("階段", int(stair.nominal_dim) if stair else 0, nf,
                  f"内部ステージの昇降の階段（隅の1スパンに折り返し・{nf}台＝層ごと）"))
        if master.by_category("階段手摺"):
            q.append(("階段手摺", 0, 2 * nf, "階段1台に両側2本"))
        if master.by_category("階段開口部手摺"):
            q.append(("階段開口部手摺", 0, nf, "階段の出入口（上の段）に1組"))
        if master.by_category("階段開口部幅木"):
            q.append(("階段開口部幅木", 0, nf, "階段の出入口（上の段）に1組"))
    elif r.access == "ハッチ":
        # いちばん下の踊り場（ピットから踏台）はハッチ不要（1つ上のハッチの梯子がそこまで届く）
        nh = len([h for h in r.hatch_levels if h > LOW_LANDING_STEP_MM])
        hatch = next(iter(master.by_category("踊り場")), None)
        name = f"ハッチ付布板（梯子内蔵 {hatch.model_no}）" if hatch else "ハッチ付布板（梯子内蔵）"
        q.append(("踊り場", int(hatch.nominal_dim) if hatch else int(r.spans_u[0]), nh,
                  f"{name}を各層の昇降口に {nh}枚（上下で位置をずらす）"))
        deck_set = set(r.deck_levels + [r.deck_mm])
        extra = [h for h in r.hatch_levels if h not in deck_set]
        if extra:
            w0 = max(widths)
            q.append(("踏板", int(r.spans_u[0]), len(extra),
                      f"作業床の無い段のハッチの脇の踊り場（幅{w0}を1枚ずつ・{len(extra)}段）"))
    elif r.access == "建物の階段":
        if master.by_category("階段開口部手摺"):
            q.append(("階段開口部手摺", 0, 1, "建物の階段からの出入口（作業床の端）に1組"))
    elif r.access == "なし":
        pass                            # 仮設通路の終わりの島など、ほかから渡る（昇降を持たない）
    else:
        q.append(("はしご", 0, n_deck, "内部ステージの昇降（はしご）" + ("・作業床の段ごと" if n_deck > 1 else "")
                  + ("。壁が近いので内側に立て、作業床ははしご口（ハッチ付きの踏板）で抜ける" if not r.guard else "")))


def _post_label(r: StageResult) -> str:
    n2 = (len(r.spans_u) >= 2) + (len(r.spans_v) >= 2)
    return ("角の支柱", "端の支柱", "内側の支柱")[n2]


def _access_text(r: StageResult) -> str:
    if r.access == "なし":
        return "昇降はほかの足場・通路から渡る（この足場には持たない）"
    if r.access == "ハッチ":
        return f"昇降はハッチ付布板（梯子内蔵）{len(r.hatch_levels)}枚（各層・上下で位置をずらす）"
    if r.access == "建物の階段":
        return "昇降は建物の階段から（上の踊り場から作業床の端の出入口へ。出入口に開口部手摺）"
    if r.stair_flights:
        return f"昇降は隅の1スパンの階段 {len(r.stair_flights)}台（折り返し）"
    return "昇降は作業床の段ごとのはしご" if r.deck_levels else "昇降のはしご1箇所"


def _hatch_access_check(r: StageResult) -> None:
    """ハッチ付布板の梯子は層の高さ1つ分。地面（ピットの床）から最初の段がそれより高いと梯子が届かない."""
    if r.access != "ハッチ" or not r.hatch_levels:
        return
    first = r.hatch_levels[0]
    gaps = [b - a for a, b in zip(r.hatch_levels, r.hatch_levels[1:])]
    if first <= LOW_LANDING_STEP_MM and all(g <= r.stair_fh + 10 for g in gaps[1:]):
        r.checks.append(StageCheck("昇降（ハッチ）", "OK",
                                   f"ハッチ付布板（梯子内蔵）を各層 {len(r.hatch_levels) - 1}枚、上下で位置をずらす。ピットの床から"
                                   f"いちばん下の踊り場 {first}mm へは踏台で上がる"))
    elif first <= r.stair_fh + STAIR_FIRST_TOL_MM and all(g <= r.stair_fh + 10 for g in gaps):
        r.checks.append(StageCheck("昇降（ハッチ）", "OK",
                                   f"ハッチ付布板（梯子内蔵）を各層 {len(r.hatch_levels)}枚、上下で位置をずらす。最初の段 {first}mm"))
    else:
        r.checks.append(StageCheck("昇降（ハッチ）", "WARN",
                                   f"ピットの床から最初の段まで {first}mm で、ハッチの梯子（層の高さ {r.stair_fh}mm）が届かない。"
                                   "最下段は移動はしご（上端を 60cm 以上出して固定）か踏台で上がる"))


def _landing_access_check(r: StageResult) -> None:
    """階段の上: 建物の上の踊り場（段数×蹴上げ）から作業床へ出入りできるか. 段差が大きければ昇降を足す."""
    if r.access != "建物の階段" or not r.stair_feet:
        return
    top = max(f["z_mm"] for f in r.stair_feet)
    gap = r.deck_mm - top
    if abs(gap) <= LANDING_STEP_MAX_MM:
        r.checks.append(StageCheck("昇降（建物の階段）", "OK",
                                   f"上の踊り場 {top:.0f}mm から作業床 {r.deck_mm}mm へ段差 {gap:+.0f}mm で出入り（出入口に開口部手摺）"))
    else:
        r.checks.append(StageCheck("昇降（建物の階段）", "WARN",
                                   f"上の踊り場 {top:.0f}mm と作業床 {r.deck_mm}mm の段差 {gap:+.0f}mm が大きい。"
                                   "踊り場から作業床へ階段枠を1台足すか、作業床の高さを踊り場に近づける"))


def _stair_access_check(r: StageResult) -> None:
    """階段で作業床まで上がれるか: 階段枠は層の高さ（ND 1800）の段どうしに掛かる. 1台目は地面（敷板）から最初の段まで
    なので、最初の段が地面から層の高さ ±STAIR_FIRST_TOL_MM に入らないと階段枠が合わない."""
    if not r.stair_fh or not r.stair_flights:
        return
    fh = r.stair_fh
    first = r.stair_flights[0][1]
    nf = len(r.stair_flights)
    if abs(first - fh) <= STAIR_FIRST_TOL_MM:
        r.checks.append(StageCheck("昇降の階段", "OK",
                                   f"地面から作業床 {r.deck_mm}mm まで階段 {nf}台（隅の1スパンに折り返し。1台目は地面から "
                                   f"{first}mm の段まで、敷板の上に据える。出入口に開口部手摺・幅木）"))
        return
    if r.use == "EVシャフト":
        # シャフトは最上段が最上階で決まるので作業床の高さは動かせない。最下段の段差で調整する
        r.checks.append(StageCheck("昇降の階段", "WARN",
                                   f"ピットの床から最初の段まで {first}mm で、階段枠の高さ {fh}mm に合わない。"
                                   f"最下段は踏台・ハーフ階段か、ピットに架台を組んで {first - fh:+d}mm を調整する"))
        return
    k = max(1, round(r.deck_mm / fh))
    good = [n * fh + d for n in (k - 1, k, k + 1) if n >= 1 for d in (0,)]
    r.checks.append(StageCheck("昇降の階段", "WARN",
                               f"地面から最初の段まで {first}mm で、階段枠の高さ {fh}mm に合わない（±{STAIR_FIRST_TOL_MM}mm を超える）。"
                               f"作業床を {'・'.join(str(g) for g in good)}mm 前後にするか、1台目の下を踏台・ハーフ階段で調整する"))


def _trib_m2(r: StageResult) -> float:
    """いちばん受け持ちの大きい支柱の受け持ち面積（m²）. 内側の支柱は隣り合うスパンの半分ずつで su×sv、
    スパンが1つしかない向きは端の支柱なので半分（EVシャフトの1×1スパンは角の支柱4本で su×sv/4）."""
    su, sv = max(r.spans_u) / 1000.0, max(r.spans_v) / 1000.0
    return (su if len(r.spans_u) >= 2 else su / 2.0) * (sv if len(r.spans_v) >= 2 else sv / 2.0)


def _cap(caps: Optional[dict], item: str, key: str = "0") -> Optional[float]:
    if not caps:
        return None
    cv = caps.get((item, key))
    return float(cv.value) if cv is not None else None


def _checks(r: StageResult, master, caps: Optional[dict]) -> None:
    out = r.checks
    su, sv = max(r.spans_u) / 1000.0, max(r.spans_v) / 1000.0
    h_m = (r.deck_mm + GUARD_MM) / 1000.0
    # 1. 支柱の軸力（内側の支柱。受け持ち＝隣り合うスパンの半分ずつ）
    trib = _trib_m2(r)
    # 作業床が何段もあるとき（EVシャフトの各階）は床の自重は全段、積載は同時に2層まで（日建 ND の使用基準）
    n_deck = 1 + len(r.deck_levels)
    n_kn = trib * (r.live_kn_m2 * min(2, n_deck) + DECK_DEAD_KN_M2 * n_deck) + POST_SELF_KN_PER_M * h_m
    allow = _cap(caps, "支柱許容圧縮耐力")
    if allow is None:
        out.append(StageCheck("支柱の軸力", "WARN", f"{_post_label(r)}1本 {n_kn:.2f}kN（許容耐力が系列の資料に無いので確認）"))
    else:
        st = "OK" if n_kn <= allow else "NG"
        out.append(StageCheck("支柱の軸力", st, f"{_post_label(r)}1本 {n_kn:.2f}kN ≦ 許容 {allow:.1f}kN"
                              if st == "OK" else f"{_post_label(r)}1本 {n_kn:.2f}kN ＞ 許容 {allow:.1f}kN。スパンを詰めるか積載を下げる"))
    # 1'. 出入口の辺の支柱（仮設通路のフックを受ける布材の両端）: 自分の受け持ち（長手の終わりのスパンの半分×短手の
    # 半分ずつ）に通路の反力を足す（利用者の指定 2026-10-29 の仮設通路。島を単独で検定すると通路の重さが入らない）
    if r.open_end and r.end_post_kn > 0:
        e_trib = (r.spans_u[-1] / 1000.0 / 2.0) * (sv if len(r.spans_v) >= 2 else sv / 2.0)
        e_kn = e_trib * (r.live_kn_m2 + DECK_DEAD_KN_M2) + POST_SELF_KN_PER_M * h_m + r.end_post_kn
        body = f"通路を受ける支柱1本 {e_kn:.2f}kN（うち通路の反力 {r.end_post_kn:.2f}kN）"
        if allow is None:
            out.append(StageCheck("通路を受ける支柱", "WARN", body + "（許容耐力が系列の資料に無いので確認）"))
        else:
            ok = e_kn <= allow
            out.append(StageCheck("通路を受ける支柱", "OK" if ok else "NG",
                                  body + (f" ≦ 許容 {allow:.1f}kN" if ok else f" ＞ 許容 {allow:.1f}kN。島のスパンを詰めるか支柱を足す")))
    # 2. 1スパンあたりの積載と作業床の許容積載
    bay = su * sv * r.live_kn_m2
    deck_allow = _cap(caps, "作業床許容積載荷重", "スパン")
    if deck_allow is None:
        out.append(StageCheck("作業床の積載", "WARN", f"1スパン {bay:.2f}kN（{bay * 102:.0f}kg）。作業床の許容積載を確認"))
    else:
        st = "OK" if bay <= deck_allow else "WARN"
        msg = (f"1スパン {bay:.2f}kN（{bay * 102:.0f}kg）≦ 許容 {deck_allow:.2f}kN" if st == "OK" else
               f"積載 {r.live_kn_m2:.1f}kN/m² だと1スパン {bay:.2f}kN（{bay * 102:.0f}kg）で許容 {deck_allow:.2f}kN"
               f"（{deck_allow * 102:.0f}kg）を超える。1スパン {deck_allow * 102:.0f}kg 以下を掲示し、資材を分散して置く")
        out.append(StageCheck("作業床の積載", st, msg))
    # 3. 高さと短辺の比（転倒・横揺れ）。EVシャフトは各階で四方の壁に壁つなぎ
    short = min(r.length_u, r.length_v) / 1000.0
    ratio = h_m / max(short, 1e-6)
    if r.use == "EVシャフト":
        vmax = SHAFT_TIE_V_MAX_MM["frame" if master.system_type == FRAME else "wedge"]
        lv = [0.0] + list(r.floors_mm) + [float(r.deck_mm)]
        gap = max(b - a for a, b in zip(lv, lv[1:]))
        out.append(StageCheck("壁つなぎ", "OK" if gap <= vmax else "WARN",
                              f"高さ {h_m:.2f}m／短辺 {short:.2f}m＝{ratio:.1f}。各階で四方の壁に壁つなぎ（壁つなぎ用インサート）、"
                              f"垂直の間隔 最大 {gap:.0f}mm" + ("" if gap <= vmax else f"（{vmax}mm を超えるので中間にも取る）")
                              + "（安衛則570条1項5号）"))
    else:
        # 転倒安定度（仮設工業会『足場・型枠支保工設計指針』の棚足場: 無積載・上端に自重の 2.5% の水平荷重で
        # FS＝MS/MO＝(W·b/2)/(0.025W·h)≧2.0）。比 4 は目安で、FS より厳しい側（報告 地足場と内部足場 2026-10-28）
        fs = (short / 2.0) / (STAGE_H_RATIO * h_m) if h_m > 0 else 99.0
        st = "OK" if ratio <= HB_LIMIT and fs >= STAGE_FS_MIN else ("NG" if fs < STAGE_FS_MIN else "WARN")
        out.append(StageCheck("高さと短辺の比", st,
                              f"高さ {h_m:.2f}m／短辺 {short:.2f}m＝{ratio:.1f}、転倒安定度 {fs:.1f}（2.0 以上。水平荷重は自重の 2.5%）"
                              + ("（比 4 以下）" if ratio <= HB_LIMIT else
                                 "。比が目安の 4 を超えるので壁・柱から控え（壁つなぎ）を取る")))
    # 4. 墜落防止・昇降（作業床 2m 以上: 安衛則563条・526条）
    if r.use == "EVシャフト":
        gap_ok = r.wall_gap_mm <= SHAFT_WALL_GAP_MAX_MM
        out.append(StageCheck("墜落防止・昇降", "OK" if gap_ok else "WARN",
                              f"作業床 {1 + len(r.deck_levels)}段（{'・'.join(str(h) for h in r.deck_levels + [r.deck_mm])}mm）。"
                              f"作業床の端と壁の隙間 {r.wall_gap_mm:.0f}mm"
                              + ("（30cm 以下なので外周の手すりは省く）" if gap_ok else
                                 "（30cm を超えるので外周に手すり・中桟・幅木）")
                              + "。" + _access_text(r)))
        r.notes.append("乗場の開口は各階で手すり・養生枠で囲い（安衛則519条）、「開口部 立入禁止」を表示する。足場の解体後も"
                       "養生枠でふさぎ、エレベーター業者の入場後は業者の養生に引き継ぐ")
        r.notes.append("シャフトの中は上下の同時作業をしない（落下物）。資材の荷揚げは作業床の端で受け、開口から身を乗り出さない")
    elif r.deck_mm >= 2000:
        out.append(StageCheck("墜落防止・昇降", "OK", f"作業床 {r.deck_mm}mm: 外周に手すり H{GUARD_MM}＋中桟＋幅木、"
                              + _access_text(r) + "（作業床の隙間 3cm 以下・開口部は手すりで囲う）"))
    else:
        out.append(StageCheck("墜落防止・昇降", "OK", f"作業床 {r.deck_mm}mm（2m 未満）: 外周の手すり・{_access_text(r)}は計上済み"))
    _stair_access_check(r)
    _landing_access_check(r)
    _hatch_access_check(r)
    # 5. 天井（上の階の床の下端）との取り合い（実機 2026-10-25: 階高 3m の部屋に既定の 4000 で置き、手すりと支柱が
    #    上の階の床を突き抜けた）
    ceil = getattr(r, "ceiling_mm", None)
    if ceil and r.use == "支保工":
        # 支保工は支柱が大引の下まで伸びるので頭上の空きは見ず、作業床の手すりが大引に当たらないかだけ見る
        under = ceil - FORM_DEPTH_MM
        rail = r.deck_mm + GUARD_MM
        if rail > under - 50:
            out.append(StageCheck("天井との取り合い", "NG",
                                  f"作業床の手すり {rail}mm が大引の下端（約 {under:.0f}）に当たる。作業床を 1 段下げる"))
        return
    if ceil:
        top = float(getattr(r, "top_mm", 0) or 0)
        head = ceil - r.deck_mm
        if top > ceil - 30.0:
            out.append(StageCheck("天井との取り合い", "NG",
                                  f"支柱・手すりの天端 {top:.0f} が天井（上の床の下端 {ceil:.0f}）に当たる。作業床を "
                                  f"{ceil - 1800:.0f} 前後（天井から 1.8m 下）に下げる"))
        elif head < 1500 or head > 2100:
            out.append(StageCheck("天井との取り合い", "WARN",
                                  f"作業床から天井まで {head:.0f}mm。天井の作業は 1.6〜1.8m 前後が楽（頭上 {head:.0f}）"))
        else:
            out.append(StageCheck("天井との取り合い", "OK", f"作業床から天井（上の床の下端 {ceil:.0f}）まで {head:.0f}mm"))
    if r.deck_mm < 1800:
        r.notes.append("作業床の高さが低いので、ステージの上の天井作業の姿勢（頭上の空き）を確かめてください")


def stage_report(r: StageResult) -> str:
    lines = [f"# {r.name}（内部ステージ足場）", "",
             f"- 範囲（支柱の芯）: {r.length_u:.0f} × {r.length_v:.0f} mm（スパン 長手 {'+'.join(map(str, r.spans_u))}／"
             f"短手 {'+'.join(map(str, r.spans_v))}）",
             f"- 作業床の高さ: {r.deck_mm} mm（段 {len(r.levels) - 1}・支柱 {'+'.join(map(str, r.posts))}・ジャッキ {r.jack_mm}）",
             f"- 積載: {r.live_kn_m2:.1f} kN/m²"]
    if r.use == "EVシャフト":
        lines.append(f"- 用途: EVシャフト（各階の床 {'・'.join(f'{f:.0f}' for f in r.floors_mm)}mm／作業床の段 "
                     f"{'・'.join(str(h) for h in r.deck_levels + [r.deck_mm])}mm）")
    if r.use == "支保工":
        lines.append(f"- 用途: 型枠支保工（スラブ厚 {r.slab_mm:.0f}mm・設計荷重 {r.design_kn_m2:.2f} kN/m²・支柱高さ {r.top_mm}mm）")
    lines += ["", "## 検証", ""]
    lines += [f"- {c.item}: {c.status} — {c.message}" for c in r.checks]
    lines += ["", "## 数量", "", "| 分類 | 呼び寸法 | 数 | 用途 |", "|---|---|---|---|"]
    lines += [f"| {c} | {d or ''} | {n} | {why} |" for c, d, n, why in r.quantity]
    if r.stair_feet:
        lines += ["", "## 階段の上の支柱（列ごと）", "",
                  "| 列 | 位置 | 段の高さ | 敷板 | ジャッキ | 調整カラー | 支柱 | 根がらみ | 踏面の端まで |",
                  "|---|---|---|---|---|---|---|---|---|"]
        lines += [f"| {f['index'] + 1} | {f['x_mm']} | {f['z_mm']:.0f} | {f['shim']} | {f['jack_mm']} | "
                  f"{f.get('collar_mm') or ''} | {'+'.join(map(str, f['posts'])) if f['posts'] else '組めない'} | "
                  f"{f['negarami_mm'] or '共通'} | {f['edge_mm']} |" for f in r.stair_feet]
    if r.notes:
        lines += ["", "## 注意", ""] + [f"- {n}" for n in r.notes]
    if r.use == "支保工" and r.top_mm >= SHORING_NOTIFY_MM:
        lines += [""] + shoring_notification_lines(r)
    return "\n".join(lines) + "\n"


def shoring_notification_lines(r: StageResult) -> list[str]:
    """型枠支保工の設置届（安衛則88条・別表第七 十の項・様式第20号）に書く内容の下書き."""
    tie_lv = sorted(r.levels + r.upper_levels)
    brace = sum(n for c, _, n, _ in r.quantity if c == "筋交")
    strong = sum(n for c, _, n, _ in r.quantity if c == "強力斜材")
    brace_txt = f"筋かい {brace}本" if not strong else (f"強力斜材 {strong}本" + (f"・筋かい {brace}本" if brace else ""))
    return ["## 設置届（様式第20号）の記入の下書き（型枠支保工）", "",
            "| 欄 | 記入 |", "|---|---|",
            "| 機械等の種類 | 型枠支保工（支柱の高さ 3.5m 以上） |",
            f"| 設置の場所 | {r.name} |",
            f"| 構造・型式 | くさび緊結式のシステム支保工"
            + (f"（{SHORING_APPROVAL[r.series_id]}）" if r.series_id in SHORING_APPROVAL else "（メーカーの承認品）")
            + f"・つなぎ方 {r.tie} |",
            f"| 計画の概要 | 支柱の高さ {r.top_mm}mm（大引受けジャッキの繰出し {r.uhead_ext_mm or 0}mm を除く）、"
            f"支柱の間隔 長手 {max(r.spans_u)}mm・短手 {max(r.spans_v)}mm、範囲 {r.length_u:.0f}×{r.length_v:.0f}mm、"
            f"水平つなぎ {'・'.join(map(str, tie_lv))}mm の段に直交2方向、{brace_txt}、"
            f"受けるスラブ厚 {r.slab_mm:.0f}mm |",
            f"| 設計荷重 | {r.design_kn_m2:.2f}kN/m²（鉄筋コンクリート＋型枠＋積載 1.47）、水平荷重 設計荷重の "
            f"{r.h_ratio * 100:g}% |",
            "| 添付 | 配置図、組立図（平面と直交2方向の立面）、構造計算書（この報告の検証）、支柱・大引受けジャッキの"
            "承認の写し |",
            "| 提出 | 設置の工事を始める日の30日前まで（安衛法88条1項）・所轄の労働基準監督署長 |"]


def stage_params(r: StageResult, line_mode: bool = False, master=None) -> dict:
    """部品 ashiba_stage のパラメータ（原点は外周の支柱の始めの角、faceAng は長手の向き）.

    master を渡すと、本体の足場と同じ部材の作り（支柱の径・コマの間隔・足場の種類）で描く（利用者の指定 2026-10-29:
    支保工も今作っている足場部材でやる）."""
    member = {}
    if master is not None:
        cat = "建枠" if master.is_frame else "支柱"
        dia = next((p.diameter for p in master.by_category(cat) if p.diameter > 0), 0.0)
        member = {"postDia": round(float(dia) / 1000.0, 4), "komaP": float(master.koma_pitch or 450) / 1000.0,
                  "sysKind": 1 if master.system_type == TUBE else (2 if master.is_frame else 0)}
        widths = sorted({int(w) for w in getattr(master, "deck_widths", (500, 240)) or (500, 240)}, reverse=True)
        member["dkWs"] = ",".join(map(str, widths))
    return {**member, "jackExt": r.jack_mm / 1000.0,
            "footJk": ",".join(str(int(f["jack_mm"])) for f in r.stair_feet),
            # 昇降の階段（下の段,上の段 を続けて。2026-10-29 はしごをやめた）
            "stFl": ",".join(f"{int(a + r.base_mm)},{int(b + r.base_mm)}" for a, b in r.stair_flights),
            "ladOn": r.access == "はしご",
            # ハッチ付布板の段（EVシャフト。2026-10-29 階段からハッチに）
            "hatchZ": ",".join(str(int(h + r.base_mm)) for h in r.hatch_levels),"faceAng": r.angle_deg, "spanU": ",".join(map(str, r.spans_u)), "spanV": ",".join(map(str, r.spans_v)),
            "lvList": ",".join(str(int(h + r.base_mm)) for h in sorted(r.levels + r.upper_levels)),
            "deckH": (r.deck_mm + r.base_mm) / 1000.0,
            "deckList": ",".join(str(int(h + r.base_mm)) for h in r.deck_levels), "guardOn": bool(r.guard), "gOpenE": bool(r.open_end),
            "postTop": ((r.top_mm + r.base_mm) / 1000.0) if r.use == "支保工" else 0.0,
            "uheadExt": (max(0, r.uhead_ext_mm or 0) / 1000.0) if r.use == "支保工" else 0.0,
            "inBrN": int(r.inner_braces),
            # 階段の上: 支柱の列ごとの足元（段の高さ＋敷板）
            "footAxis": 1 if (r.stair_feet and r.stair_feet[0]["axis"] == "v") else 0,
            "footZ": ",".join(str(int(f["z_mm"] + f["shim"] * SHIM_BOARD_MM)) for f in r.stair_feet),
            "footNeg": ",".join(str(int(f["negarami_mm"] + r.base_mm) if f["negarami_mm"] else 0) for f in r.stair_feet),
            "zBase": r.base_mm / 1000.0, "stName": r.name, "lineMode": bool(line_mode)}
