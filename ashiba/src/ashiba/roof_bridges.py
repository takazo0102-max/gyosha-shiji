"""屋上への渡り（足場の床から屋上へ。部品 ashiba_bridge）.

利用者の指定（2026-10-24）「屋上への渡りもGDL作成して 平面に表記するようにして」。階段で最上段まで上がり、
そこから屋上（パラペットを越えて）へ渡る。既定は階段室の隣のスパン（階段の降り口の先）に1箇所。

組み方（利用者の指定 2026-10-26。現場の写真: くさびの布材で屋上に支柱を立てた渡り、屋上に立てた階段）:
  渡りは足場の部材で組む。足場の1スパン（内側建地列の2本の支柱の間）から躯体側へ
  - くさび: 布材を出して屋上に支柱（ジャッキ付き）を立てる「支柱」、または張出ブラケットで浮かせる「ブラケット」。
    床はアンチ（布板）を内側建地列と屋上の支柱の布材に掛けて敷き、両脇の手すり・中桟も布材（幅木つき）
  - 枠組・単管: 単管と足場板。単管を建地（建枠の脚）にクランプで留めて屋上に単管の支柱（ベース付き）を立てるか、
    単管を跳ね出して浮かせ、足場板を敷く。手すり・中桟も単管
  - パラペットがあれば避ける: 渡りの床はパラペットの天端より上、屋上の支柱はパラペットの内側（内面から 150）
  - 渡りの床が屋上より高ければ、屋上側に踏段（昇降ステップ）で下りる。足場の床より高ければ足場側に踏み台
条件ファイル:
  roof_bridge: false                       # 自動で置かない
  roof_bridges: [{"face": "南面", "position_mm": 7300, "parapet_mm": 600, "parapet_t_mm": 150}]   # 位置を指定
  roof_parapet_mm: 600                     # パラペットの高さ（屋上の床から。既定 0）
  roof_parapet_t_mm: 150                   # パラペットの厚さ（既定 150）
最上段の床と屋上の床の差が ROOF_MAX_STEP_MM を超える面には置かず、案内を出す。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

BRIDGE_W_MM = 600.0          # 位置を指定するときの既定の幅（実際は置くスパンの幅）
ROOF_MAX_STEP_MM = 1800.0    # 足場の床と屋上の床の差がこれを超えたら渡りは置かない（1層以上の差）
PARAPET_CLEAR_MM = 50.0      # パラペットの天端と渡りの床（アンチ・足場板の下）のあき
PARAPET_T_MM = 150.0         # パラペットの厚さの既定
ROOF_POST_IN_MM = 150.0      # 屋上の支柱はパラペットの内面（なければ躯体の外面）からこれだけ内側
FLUSH_MM = 30.0              # 渡りの床と足場の床・屋上の床の段差がこれ以下なら段差なし（床のすき間の扱い）
POST_MIN_DROP_MM = 300.0     # 渡りの床が屋上よりこれ以上高ければ屋上に支柱を立てる（低ければ浮かせる）
STEP_RISE_MM = 230.0         # 踏段・踏み台のけあげの上限
STEP_TREAD_MM = 250.0        # 踏段の踏面
TUBE_OVERHANG_MM = 100.0     # 足場板の長さの余り（受けの単管はスパンの両端の 50 内側、そこから両端に 100 以上出す）


@dataclass
class RoofBridge:
    edge_index: int
    x_mm: float              # 面の始点の支柱から、渡りを掛けるスパンの始めの支柱
    width_mm: float          # スパンの幅（渡りの両脇の手すりの芯々）
    z_from_mm: float         # 渡りへ出る足場の床（足場の立つ高さから）
    z_to_mm: float           # 屋上の床（足場の立つ高さから）
    length_mm: float         # 内側建地列から躯体側へ（布材・ブラケット・単管の長さ）
    parapet_mm: float = 0.0
    manual: bool = False
    kind: str = "支柱"        # 支柱（屋上に支柱を立てる）／ブラケット（浮かせる）／単管支柱／単管跳ね出し
    z_deck_mm: float = 0.0   # 渡りの床（足場の立つ高さから）
    parapet_t_mm: float = 0.0
    standoff_mm: float = 0.0
    post_mm: float = 0.0     # 屋上の支柱の長さ（くさびの支柱・単管）
    jack_mm: float = 0.0     # 屋上の支柱のジャッキの繰出し（くさび）
    deck: list = field(default_factory=list)   # 床の幅の並び（アンチ 500・240、足場板 240）
    deck_len_mm: float = 0.0                   # 床材の長さ（アンチは布材と同じ呼び、足場板は規格の長さ）
    tube: bool = False       # 単管と足場板で組む（枠組・単管）
    bracket: str = ""        # ブラケットの品名（すき間を塞ぐ渡り）
    ext_mm: float = 0.0      # 渡りの手すりを受けるために継ぎ足す、掛けるスパンの内側の支柱2本の長さ（0 は不要）
    post_top_mm: float = 0.0 # 内側の支柱の天端（足場の立つ高さから）

    @property
    def step_up_mm(self) -> float:
        """足場の床から渡りの床へ上がる段差（踏み台）."""
        d = self.z_deck_mm - self.z_from_mm
        return d if d > FLUSH_MM else 0.0

    @property
    def drop_mm(self) -> float:
        """渡りの床から屋上へ下りる段差（踏段）."""
        d = self.z_deck_mm - self.z_to_mm
        return d if d > FLUSH_MM else 0.0

    def steps(self, rise_mm: float) -> int:
        return max(1, math.ceil(rise_mm / STEP_RISE_MM)) if rise_mm > FLUSH_MM else 0


def _face_index(model, face) -> int | None:
    names = dict(zip(model.plan.face_names(), (e.edge_index for e in model.plan.edges)))
    if isinstance(face, int) or str(face).isdigit():
        return int(face)
    key = str(face).replace("面", "")
    return next((ei for n, ei in names.items() if n == face or n.replace("面", "") == key), None)


def _deck_level(levels: list[float], roof: float, para: float, koma: float,
                tube: bool) -> tuple[float, float, str] | None:
    """(渡りへ出る足場の床, 渡りの床, 形). 形は "gap"（屋上とほぼ同じ高さ: 躯体の外面まですき間を塞ぐ）か
    "posts"（屋上より高い: 屋上に支柱を立てる）.

    パラペットが無く、足場の床が屋上の床の 230 下〜30 上なら、その床のまま躯体の外面まで渡す（すき間を塞ぐ。屋上へは
    段差なしか1段上がる）。それより高い床なら屋上に支柱を立てて渡し、屋上へ踏段で下りる。どの床も屋上より低ければ、
    足場の床の上のコマ（単管は任意の高さ）に渡りの床を上げ、足場側に踏み台を置く。パラペットがあれば渡りの床は
    天端の 50 上より上（パラペットを越える）。
    """
    if para <= 0:
        near = [h for h in levels if roof - STEP_RISE_MM <= h <= roof + FLUSH_MM]
        if near:
            return max(near), max(near), "gap"
        need = roof + PARAPET_CLEAR_MM
    else:
        need = roof + para + PARAPET_CLEAR_MM
    above = [h for h in levels if h >= need - 1.0]
    below = [h for h in levels if h < need - 1.0]
    flush = (min(above), min(above)) if above else None
    raised = None
    if below:
        zl = max(below)
        zb = zl + math.ceil((need - zl) / koma - 1e-9) * koma if (koma and not tube) else math.ceil(need / 10.0) * 10.0
        raised = (zl, zb)
    got = flush or raised
    if flush and raised and flush[1] - need > 900.0 and raised[1] - raised[0] <= 450.0 + 1.0:
        # 屋上へ大きく下りるより、足場側の小さな踏み台（1コマ以内）で上がる方がよい
        got = raised
    return (got[0], got[1], "posts") if got else None


def _deck_list(depth: float, unit: int, wall_clear: float = 30.0) -> list[int]:
    """奥行き depth に並べる床材の幅（くさび: アンチ 500 と 240 の組み合わせでいちばん埋まるもの、単管: 足場板 240）.
    床材の間は 10 あける."""
    room = depth - wall_clear
    if unit == 240:
        return [240] * max(1, int((room + 10) // 250))
    best: list[int] = [240]
    for n5 in range(int(room // 500) + 1):
        n24 = int((room - n5 * 510 + 10) // 250) if room - n5 * 510 + 10 >= 250 else 0
        ws = [500] * n5 + [240] * n24
        if ws and _filled(ws) <= room and _filled(ws) > _filled(best):
            best = ws
    return best


def _filled(ws: list[int]) -> float:
    return float(sum(ws) + 10 * max(0, len(ws) - 1))


def deck_gap_mm(depth: float, ws: list[int], wall_clear: float = 30.0) -> float:
    """床材を並べた残り（両端の受けとのすき間の合計）."""
    return depth - wall_clear - _filled(ws)


def _wedge_post(drop: float, master) -> tuple[float, float]:
    """屋上の支柱（長さ, ジャッキの繰出し）: 渡りの床・中桟・手すりがコマに来るよう、支柱の天端を手すりのコマ＋上端の
    コマの下がり（＋コマの倍数）にする。ジャッキの繰出しはコマの並びで決まる（30〜ジャッキの上限）."""
    koma = float(master.koma_pitch or 450.0)
    gap = float(master.koma_top_gap or 0.0)
    jmax = float(master.jack_hard_max_mm() or 270.0)
    lengths = sorted(L for L in master.post_lengths() if koma and L % koma == 0) or sorted(master.post_lengths())
    cands = []
    for L in lengths:
        for k in range(0, 4):
            j = drop + 2 * koma + gap + k * koma - L
            if 30.0 <= j <= jmax:
                cands.append((j, k, L))
    if cands:
        j, _k, L = min(cands)
        return float(L), float(j)
    return float(lengths[0]), max(30.0, drop + 2 * koma + gap - lengths[0])


def _tube_len(need: float, master) -> float:
    lens = sorted(p.nominal_dim for p in master.by_category("単管"))
    return float(next((L for L in lens if L >= need), lens[-1] if lens else math.ceil(need / 500.0) * 500.0))


def plan_bridge(model, ei: int, x: float, z_to: float, para: float, para_t: float, manual: bool,
                notes: list[str]) -> RoofBridge | None:
    """1箇所の渡りの組み方を決める（面 ei の位置 x を含むスパン）."""
    ep = next((e for e in model.plan.edges if e.edge_index == ei), None)
    if ep is None or not ep.spans:
        return None
    m = model.master
    tube = bool(m.is_tube or m.is_frame)
    name = model.face_name(ei)
    # 渡りを掛けるスパン（内側建地列の2本の支柱の間）
    acc, x0, w = 0.0, 0.0, float(ep.spans[0])
    for sp in ep.spans:
        x0, w = acc, float(sp)
        if x < acc + sp:
            break
        acc += float(sp)
    lv = [float(h) for h in model.elevation_of(ei).level_heights]
    if not lv:
        return None
    para_t = para_t if para > 0 else 0.0
    got = _deck_level(lv, z_to, para, float(m.koma_pitch or 0), tube)
    if got is None:
        return None
    zl, zb, mode = got
    if zb - z_to > ROOF_MAX_STEP_MM or z_to - zl > ROOF_MAX_STEP_MM:
        notes.append(f"屋上への渡り: {name}は足場の床（{zl:.0f}）と屋上（{z_to:.0f}）の差が"
                     f"{ROOF_MAX_STEP_MM:.0f} を超えるので置いていません（足場の高さ・屋上の高さを確かめてください）")
        return None
    so = float(ep.standoff)
    b = RoofBridge(ei, x0, w, zl, z_to, 0.0, para, manual, z_deck_mm=zb, parapet_t_mm=para_t, standoff_mm=so,
                   tube=tube)
    if mode == "gap":
        # 屋上とほぼ同じ高さ: 躯体の外面まで床を出してすき間を塞ぐ（床材は面に沿って2本のブラケット・単管に掛ける）
        if tube:
            b.kind = "単管跳ね出し"
            b.length_mm = so - FLUSH_MM
            b.deck = _deck_list(so, 240)
            b.deck_len_mm = plank_len(w + TUBE_OVERHANG_MM, m)
        else:
            br = sorted((p for p in m.by_category("ブラケット") if "張出" in p.note and "荷取り" not in p.note),
                        key=lambda p: p.nominal_dim)
            fit = [p for p in br if p.nominal_dim <= so + 10.0] or br[:1]
            b.kind = "ブラケット"
            b.length_mm = float(fit[-1].nominal_dim) if fit else so
            b.bracket = (f"{fit[-1].model_no} " + ("拡幅ブラケット" if "拡幅" in fit[-1].note else "張出ブラケット")
                         + f"{fit[-1].nominal_dim:.0f}") if fit else "ブラケット"
            b.deck = _deck_list(min(so, b.length_mm + FLUSH_MM), 240 if b.length_mm < 500 else 500)
            b.deck_len_mm = w
        if sum(b.deck) > so - 10.0:
            notes.append(f"屋上への渡り（{name}）: 離れ {so:.0f} に床材 {'＋'.join(map(str, b.deck))} が入りきりません"
                         "（躯体に当たらないか確かめてください）")
    else:
        drop = zb - z_to
        reach_need = so + para_t + ROOF_POST_IN_MM
        if tube:
            b.kind = "単管支柱"
            # 奥行きは足場板（幅 240）が並ぶ寸法に（すき間を残さない）
            b.length_mm = math.ceil((reach_need - 40.0) / 240.0) * 240.0 + 40.0
            # 足場板は横引き（面に沿って、両脇の単管に掛ける。利用者の指定 2026-10-26）
            b.deck = _deck_list(b.length_mm, 240)
            b.deck_len_mm = plank_len(w + TUBE_OVERHANG_MM, m)
            b.post_mm = _tube_len(drop + 1000.0, m)
        else:
            spans = sorted(m.span_lengths())
            b.kind = "支柱"
            # 奥行きはアンチがすき間なく並ぶ布材の長さ（安衛則563条: 床材のすき間 3cm 以下。残りは受けの両端で 90 まで＝ND の 610 の床と同じ）
            cands = [L for L in spans if L >= reach_need] or spans[-1:]
            b.length_mm = float(next((L for L in cands if deck_gap_mm(L, _deck_list(L, 500)) <= 90.0),
                                     min(cands, key=lambda L: deck_gap_mm(L, _deck_list(L, 500)))))
            # アンチも横引き（面に沿って、両脇の腕木の布材に掛ける。長さはスパンと同じ呼び）
            b.deck = _deck_list(b.length_mm, 500)
            b.deck_len_mm = w
            b.post_mm, b.jack_mm = _wedge_post(drop, m)
    row = float(model.row_spacing_of(ei)) or 600.0
    if b.step_up_mm and (b.steps(b.step_up_mm) - 1) * STEP_TREAD_MM > row - 100.0:
        notes.append(f"屋上への渡り（{name}）: 足場の床（{zl:.0f}）から渡りの床（{zb:.0f}）まで {b.step_up_mm:.0f} 上がります。"
                     "踏み台が足場の床に入りきらないので、足場の最上段の床をパラペット・屋上より上にするか、昇降用の"
                     "階段を別に設けてください")
    if mode == "gap" and z_to - zb > FLUSH_MM:
        notes.append(f"屋上への渡り（{name}）: 渡りの床から屋上へ {z_to - zb:.0f} 上がります（1段）")
    # 渡りの手すりは掛けるスパンの内側の支柱2本に留める。天端が足りなければ、その2本を継ぎ足す（くさびはコマの並びを
    # 崩さないコマの倍数の支柱、枠組・単管は建地に重ねてクランプで留める単管）
    top = float(model.elevation_of(ei).total_height)
    b.post_top_mm = top
    gap = 100.0 if tube else float(m.koma_top_gap or 0.0)
    need = zb + 900.0 + gap - top
    if need > 1.0:
        if tube:
            b.ext_mm = _tube_len(need + 300.0, m)
        else:
            koma = float(m.koma_pitch or 450.0)
            want = math.ceil(need / koma - 1e-9) * koma
            b.ext_mm = float(min((L for L in m.post_lengths() if L >= want and L % koma == 0),
                                 default=max(m.post_lengths())))
        post = "建地" if tube else "支柱"
        notes.append(f"屋上への渡り（{name}）: 渡りの手すり（{zb + 900:.0f}）が内側の{post}の天端（{top:.0f}）より上になるので、"
                     f"掛けるスパンの内側の{post}2本に{'単管' if tube else '支柱'}{b.ext_mm:.0f}を継ぎ足しています")
    return b


def planks(m) -> list:
    """足場板（単管は踏板の「足場板…」、枠組は渡り用の「足場板」）. 長さは実長（actual_dim）."""
    return sorted({p.model_no: p for p in m.parts if p.model_no.startswith("足場板")}.values(),
                  key=lambda p: p.actual_dim)


def plank_len(need: float, m) -> float:
    ps = planks(m)
    return float(next((p.actual_dim for p in ps if p.actual_dim >= need), ps[-1].actual_dim if ps else need))


def roof_bridges(model, stair_plan, spec: dict) -> tuple[list[RoofBridge], list[str]]:
    """渡りを置く所 → ([RoofBridge], 案内)."""
    notes: list[str] = []
    out: list[RoofBridge] = []
    if spec.get("roof_bridge") is False:
        return out, notes
    eaves = getattr(model, "eaves_by_face", None) or {}
    default_eaves = float(spec.get("eaves_height_mm") or 0.0)
    para0 = float(spec.get("roof_parapet_mm", 0) or 0)
    t0 = float(spec.get("roof_parapet_t_mm", PARAPET_T_MM) or PARAPET_T_MM)

    def make(ei: int, x: float, para: float, para_t: float, manual: bool) -> None:
        if not any(e.edge_index == ei for e in model.plan.edges):
            notes.append(f"屋上への渡り: 面（辺{ei}）に足場がありません")
            return
        b = plan_bridge(model, ei, x, float(eaves.get(ei, default_eaves)), para, para_t, manual, notes)
        if b is not None:
            out.append(b)

    manual = spec.get("roof_bridges") or []
    for item in manual:
        ei = _face_index(model, item.get("face", item.get("edge_index")))
        if ei is None:
            notes.append(f"屋上への渡り: 面「{item.get('face')}」が分かりません")
            continue
        make(ei, float(item.get("position_mm", 0.0)), float(item.get("parapet_mm", para0) or 0),
             float(item.get("parapet_t_mm", t0) or t0), True)
    if manual:
        return out, notes
    towers = list(getattr(stair_plan, "towers", None) or [])
    if not towers:
        return out, notes
    t = towers[0]
    ep = next((e for e in model.plan.edges if e.edge_index == t.edge_index), None)
    if ep is None:
        return out, notes
    # 階段室の終点の側の隣のスパン（入らなければ始点の側）
    length = float(sum(ep.spans))
    x = float(t.end_mm) + 1.0 if float(t.end_mm) + 600.0 <= length - 1.0 else float(t.start_mm) - 600.0
    make(t.edge_index, max(0.0, x), para0, t0, False)
    return out, notes


def bridge_words(b: RoofBridge) -> str:
    """渡りの組み方の要約（「布材914・屋上に支柱 1350＋ジャッキ・アンチ 500×3＋240」）."""
    if b.kind == "支柱":
        s = f"布材{b.length_mm:.0f}・屋上に支柱{b.post_mm:.0f}（ジャッキ{b.jack_mm:.0f}）"
    elif b.kind == "ブラケット":
        s = f"{b.bracket}で躯体の外面までのすき間を塞ぐ"
    elif b.kind == "単管支柱":
        s = f"単管{b.length_mm / 1000:.2f}m・屋上に単管の建地{b.post_mm / 1000:.1f}m（ベース）"
    else:
        s = f"単管を躯体の外面まで跳ね出してすき間を塞ぐ"
    if b.tube:
        s += f"・足場板{b.deck_len_mm / 1000:.1f}m×{len(b.deck)}枚"
    else:
        s += "・アンチ " + "＋".join(str(w) for w in b.deck)
    s += "・手すり・中桟" + ("（単管）" if b.tube else "（布材）") + "・幅木"
    if b.step_up_mm:
        s += f"・足場側に踏み台（{b.steps(b.step_up_mm)}段・{b.step_up_mm:.0f}上がる）"
    if b.drop_mm:
        s += f"・屋上へ踏段（{b.steps(b.drop_mm)}段・{b.drop_mm:.0f}下りる）"
    if b.parapet_mm > 0:
        s += f"・パラペット{b.parapet_mm:.0f}の上を越える"
    if b.ext_mm:
        s += f"・内側の{'建地' if b.tube else '支柱'}2本を{b.ext_mm:.0f}継ぎ足す"
    return s


def bridge_note(bridges: list[RoofBridge], model) -> str:
    parts = [f"{model.face_name(b.edge_index)} {b.x_mm:.0f}〜（幅{b.width_mm:.0f}・{bridge_words(b)}）" for b in bridges]
    return "屋上への渡り: " + "、".join(parts)
