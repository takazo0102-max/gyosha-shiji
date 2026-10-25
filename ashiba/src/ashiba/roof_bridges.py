"""屋上への渡り（足場の最上段の床から屋上へ渡る桟橋。部品 ashiba_bridge）.

利用者の指定（2026-10-24）「屋上への渡りもGDL作成して 平面に表記するようにして」。階段で最上段まで上がり、
そこから屋上（パラペットを越えて）へ渡る。既定は階段室の隣のスパン（階段の降り口の先）に1箇所。
条件ファイル:
  roof_bridge: false                       # 自動で置かない
  roof_bridges: [{"face": "南面", "position_mm": 7300, "width_mm": 600, "parapet_mm": 600}]   # 位置を指定
  roof_parapet_mm: 600                     # パラペットの高さ（屋上の床から。既定 0）
最上段の床と屋上の床の差が ROOF_MAX_STEP_MM を超える面には置かず、案内を出す。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

BRIDGE_W_MM = 600.0          # 渡りの幅（手すりの芯々）
ROOF_LANDING_MM = 600.0      # 屋上側の掛かり（躯体の外面・パラペットの先の平らな床）
ROOF_MAX_STEP_MM = 1800.0    # 最上段の床と屋上の床の差がこれを超えたら渡りは置かない（1層以上の差）
# 渡りの形（安衛則552条 架設通路: 勾配 30°以下、15°を超えるものは踏桟。それより急なら踏段（階段））
DECK_START_MM = 300.0        # 足場の床に掛ける長さ（内側建地列から外へ。足場の床の通路を半分残す）
DECK_START_MAX_MM = 500.0    # 段が足りないときに足場の床へ延ばす上限（610 の床で通路 110 は残す）
FLAT_STEP_MM = 30.0          # これ以下の高低差は平らな踏板（床のすき間・段差の扱い）
RAMP_PLAIN_DEG = 15.0        # 踏桟なしの斜路の上限
RAMP_MAX_DEG = 30.0          # 斜路の上限（これより急なら踏段）
STEP_RISE_MM = 200.0         # 踏段のけあげの上限
STEP_TREAD_MM = 200.0        # 踏段の踏面の下限
PARAPET_CLEAR_MM = 50.0      # パラペットの天端と渡りの床のあき
PARAPET_TOP_MM = 300.0       # パラペットの天端を越える平らな区間（躯体の外面の 50 手前から）


@dataclass
class RoofBridge:
    edge_index: int
    x_mm: float              # 面の始点の支柱から、渡りの始めの位置
    width_mm: float
    z_from_mm: float         # 最上段の床（足場の立つ高さから）
    z_to_mm: float           # 屋上の床（足場の立つ高さから）
    length_mm: float         # 内側建地列から躯体側へ
    parapet_mm: float = 0.0
    manual: bool = False
    # 渡りの床の折れ点（内側建地列からの奥行き mm、足場の立つ高さからの床の上面 mm）と、区間ごとの形
    # （0 平らな踏板、1 斜路（踏桟なし）、2 斜路（踏桟つき）、3 踏段）。bridge_profile
    profile: list = field(default_factory=list)
    kinds: list = field(default_factory=list)


def _rise(y0: float, z0: float, z1: float, run_max: float, notes: list, ahead: bool) -> tuple[list, list]:
    """高低差 z0→z1 の区間 → (折れ点, [形]).

    ahead=False: y0 で z1 に着くよう手前へ（足場の床の上と離れの隙間。長さ run_max まで）。斜路が入れば使える長さ
    いっぱいにゆるく、入らなければ踏段。ahead=True: y0 から先へ（屋上の上。15°の斜路が 1.2m 以内ならそれ、次に
    30°の斜路（踏桟）、それより長ければ踏段）。
    """
    dz = abs(z1 - z0)
    run15 = dz / math.tan(math.radians(RAMP_PLAIN_DEG))
    run30 = dz / math.tan(math.radians(RAMP_MAX_DEG))
    run = None
    if not ahead and run30 <= run_max + 1e-6:
        run = run_max
    elif ahead and run15 <= 1200.0:
        run = run15
    elif ahead and run30 <= 1200.0:
        run = run30
    if run is not None:
        kind = 1 if math.degrees(math.atan2(dz, run)) <= RAMP_PLAIN_DEG + 1e-6 else 2
        return ([(y0 + run, z1)] if ahead else [(y0 - run, z0), (y0, z1)]), [kind]
    n_rise = max(2, math.ceil(dz / STEP_RISE_MM))
    run = (n_rise - 1) * STEP_TREAD_MM
    if not ahead and run > run_max + 1e-6:
        notes.append(f"踏段の踏面が {run_max / (n_rise - 1):.0f}mm しか取れません（{STEP_TREAD_MM:.0f} 以上が要る）。"
                     "足場の最上段の床の高さを屋上に近づけるか、踏み台（可搬式の昇降ステップ）を使ってください")
        run = run_max
    return ([(y0 + run, z1)] if ahead else [(y0 - run, z0), (y0, z1)]), [3]


def bridge_profile(z_from: float, z_to: float, edge_mm: float, parapet_mm: float,
                   deck_mm: float) -> tuple[list, list, list[str]]:
    """渡りの床の折れ点と区間の形 → ([(y, z)], [形], 案内). y は内側建地列から躯体側へ mm（躯体の外面＝edge_mm）.

    熟練者の組み方（安衛則552条・563条）: 高低差は躯体の外面の手前（足場の床の上と離れの隙間）か、屋上の上で
    取り、床は折れ点のあいだで平ら・斜路（30°以下、15°超は踏桟）・踏段のどれか。屋上が高ければ外面までに上がり
    きり（段・側桁が屋上のスラブに食い込まない）、屋上が低ければ外面まで床の高さのまま渡って屋上の上で下りる。
    パラペットは天端の 50 上を平らに越え、屋上の上で下りる。屋上の上は ROOF_LANDING_MM の平らな床。
    """
    notes: list[str] = []
    y_s = -DECK_START_MM
    y_far = -min(DECK_START_MAX_MM, max(DECK_START_MM, deck_mm - 110.0))
    top = z_to + parapet_mm + PARAPET_CLEAR_MM if parapet_mm > 0 else z_to
    pts: list = [(y_s, z_from)]
    kinds: list = []
    if top - z_from > FLAT_STEP_MM:
        # 外面の手前で上がりきる（パラペットがあれば外面の 50 手前で天端の 50 上に）
        y_e = edge_mm - (PARAPET_CLEAR_MM if parapet_mm > 0 else 0.0)
        tmp: list = []
        p, k = _rise(y_e, z_from, top, y_e - y_s, tmp, False)
        if k == [3]:
            p, k = _rise(y_e, z_from, top, y_e - y_far, notes, False)
        if p[0][0] < y_s - 1.0:
            pts = [p[0]]
        elif p[0][0] > y_s + 1.0:
            pts.append(p[0])
            kinds.append(0)
        pts.append(p[1])
        kinds += k
    else:
        # 高低差 30 以下（またはパラペットの天端が床より低い）: 床の高さのまま外面まで渡す。屋上の床へは平らに掛ける
        pts.append((edge_mm, z_from if parapet_mm > 0 or z_from - z_to > FLAT_STEP_MM else z_to))
        kinds.append(0)
    if parapet_mm > 0:
        pts.append((edge_mm + PARAPET_TOP_MM - PARAPET_CLEAR_MM, pts[-1][1]))
        kinds.append(0)
    # 屋上の上で下りる（屋上が低い・パラペットを越えた）
    if pts[-1][1] - z_to > FLAT_STEP_MM:
        p, k = _rise(pts[-1][0], pts[-1][1], z_to, 0.0, notes, True)
        pts += p
        kinds += k
    pts.append((pts[-1][0] + ROOF_LANDING_MM, z_to if abs(pts[-1][1] - z_to) > FLAT_STEP_MM else pts[-1][1]))
    kinds.append(0)
    # 続く平らな区間はまとめる
    out_p, out_k = [pts[0]], []
    for (y, z), k in zip(pts[1:], kinds):
        if out_k and k == 0 and out_k[-1] == 0 and abs(out_p[-1][1] - z) < 1e-6 and abs(out_p[-2][1] - z) < 1e-6:
            out_p[-1] = (y, z)
            continue
        out_p.append((y, z))
        out_k.append(k)
    return [(round(y, 1), round(z, 1)) for y, z in out_p], out_k, notes


def profile_words(b: "RoofBridge") -> str:
    """渡りの形の要約（「斜路 22° 踏桟」「踏段 2段」）."""
    words = []
    for (y0, z0), (y1, z1), k in zip(b.profile, b.profile[1:], b.kinds):
        if k in (1, 2):
            ang = math.degrees(math.atan2(abs(z1 - z0), max(1.0, y1 - y0)))
            words.append(f"斜路{ang:.0f}°" + ("・踏桟" if k == 2 else ""))
        elif k == 3:
            words.append(f"踏段{max(2, math.ceil(abs(z1 - z0) / STEP_RISE_MM))}段（けあげ"
                         f"{abs(z1 - z0) / max(2, math.ceil(abs(z1 - z0) / STEP_RISE_MM)):.0f}）")
    return "・".join(words)


def _face_index(model, face) -> int | None:
    names = dict(zip(model.plan.face_names(), (e.edge_index for e in model.plan.edges)))
    if isinstance(face, int) or str(face).isdigit():
        return int(face)
    key = str(face).replace("面", "")
    return next((ei for n, ei in names.items() if n == face or n.replace("面", "") == key), None)


def roof_bridges(model, stair_plan, spec: dict) -> tuple[list[RoofBridge], list[str]]:
    """渡りを置く所 → ([RoofBridge], 案内)."""
    notes: list[str] = []
    out: list[RoofBridge] = []
    if spec.get("roof_bridge") is False:
        return out, notes
    eaves = getattr(model, "eaves_by_face", None) or {}
    default_eaves = float(spec.get("eaves_height_mm") or 0.0)
    para0 = float(spec.get("roof_parapet_mm", 0) or 0)
    edges = {e.edge_index: e for e in model.plan.edges}

    def make(ei: int, x: float, w: float, para: float, manual: bool) -> None:
        ep = edges.get(ei)
        if ep is None:
            notes.append(f"屋上への渡り: 面（辺{ei}）に足場がありません")
            return
        lv = list(model.elevation_of(ei).level_heights)
        if not lv:
            return
        z_to = float(eaves.get(ei, default_eaves))
        # 屋上の床にいちばん近い段から渡す（最上段は屋根より1段上のことがある。実機 2026-10-24: 下り1775 になった）
        z_from = float(min(lv, key=lambda h: (abs(float(h) - z_to), -float(h))))
        name = model.face_name(ei)
        if abs(z_to - z_from) > ROOF_MAX_STEP_MM:
            notes.append(f"屋上への渡り: {name}は最上段の床（{z_from:.0f}）と屋上（{z_to:.0f}）の差が"
                         f"{ROOF_MAX_STEP_MM:.0f} を超えるので置いていません（足場の高さ・屋上の高さを確かめてください）")
            return
        length = float(sum(ep.spans))
        x = max(0.0, min(float(x), length - w))
        prof, kinds, pnotes = bridge_profile(z_from, z_to, float(ep.standoff), para,
                                             float(model.row_spacing_of(ei)) or 600.0)
        notes.extend(f"屋上への渡り（{name}）: {t}" for t in pnotes)
        out.append(RoofBridge(ei, x, w, z_from, z_to, prof[-1][0], para, manual, prof, kinds))

    manual = spec.get("roof_bridges") or []
    for b in manual:
        ei = _face_index(model, b.get("face", b.get("edge_index")))
        if ei is None:
            notes.append(f"屋上への渡り: 面「{b.get('face')}」が分かりません")
            continue
        make(ei, float(b.get("position_mm", 0.0)), float(b.get("width_mm", BRIDGE_W_MM)),
             float(b.get("parapet_mm", para0) or 0), True)
    if manual:
        return out, notes
    towers = list(getattr(stair_plan, "towers", None) or [])
    if not towers:
        return out, notes
    t = towers[0]
    ep = edges.get(t.edge_index)
    if ep is None:
        return out, notes
    # 階段室の終点の側の隣のスパン（入らなければ始点の側）
    length = float(sum(ep.spans))
    x = float(t.end_mm) if float(t.end_mm) + BRIDGE_W_MM <= length - 1.0 else float(t.start_mm) - BRIDGE_W_MM
    make(t.edge_index, max(0.0, x), BRIDGE_W_MM, para0, False)
    return out, notes


def bridge_note(bridges: list[RoofBridge], model) -> str:
    parts = [f"{model.face_name(b.edge_index)} {b.x_mm:.0f}〜（幅{b.width_mm:.0f}・長さ{b.length_mm:.0f}"
             + (f"・上り{b.z_to_mm - b.z_from_mm:.0f}" if b.z_to_mm - b.z_from_mm > 1 else
                f"・下り{b.z_from_mm - b.z_to_mm:.0f}" if b.z_from_mm - b.z_to_mm > 1 else "")
             + (f"・パラペット{b.parapet_mm:.0f}越え" if b.parapet_mm > 0 else "")
             + (f"・{profile_words(b)}" if profile_words(b) else "") + "）" for b in bridges]
    return "屋上への渡り: " + "、".join(parts)
