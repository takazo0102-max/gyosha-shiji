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

from dataclasses import dataclass

BRIDGE_W_MM = 600.0          # 渡りの幅（手すりの芯々）
ROOF_LANDING_MM = 600.0      # 屋上側の掛かり（離れの先）
ROOF_MAX_STEP_MM = 1800.0    # 最上段の床と屋上の床の差がこれを超えたら渡りは置かない（1層以上の差）


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
        out.append(RoofBridge(ei, x, w, z_from, z_to, float(ep.standoff) + ROOF_LANDING_MM, para, manual))

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
             + (f"・パラペット{b.parapet_mm:.0f}越え" if b.parapet_mm > 0 else "") + "）" for b in bridges]
    return "屋上への渡り: " + "、".join(parts)
