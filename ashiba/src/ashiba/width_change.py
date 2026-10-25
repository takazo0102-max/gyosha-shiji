"""拡幅・縮幅（途中の作業床から足場の幅を 305 変える）.

利用者の指定 2026-10-25「両方作って 610→914と914→1219」。日建 ND1800 の拡幅ブラケット NDBK03H（出 305・方杖は
1コマ 450 下・先端ホゾ φ36.4。カタログ Vol.10 p014）と、ND1900 カタログ p015 の「拡幅・縮幅例」の組み方:

- 幅を変える作業床（level 段目）のコマで、下の足場の外側の支柱にブラケットを掛ける。拡幅は外へ、縮幅は内（躯体側）へ。
- 先端のホゾに新しい外側の支柱を立てて天端まで。元の外側の支柱はその床の上に NDP09N（900）を継ぎ足し、つなぎ材
  NDT03（305）で新しい支柱と繋ぐ。
- 幅を変えるのは全高で1回だけ。幅を変えた層の上下は前踏み側の全スパンに壁つなぎ、拡幅部の支柱の許容荷重
  （ND1800 は 8.8kN/本）を確かめる。

足場ラインは、幅を変える床の 100 下で上下2本に分ける（segments と同じ区切り）。下は segLevB＝level−1 の元の幅、
上は segLevA＝level の新しい幅（rowW・作業床の組・出隅の升目の辺）。

出隅の升目の外側の角の支柱（新しい幅の角）は、ブラケットの先に来ない:
- 拡幅: 角は元の升目の外。地面から天端まで支柱を1本立て、幅を変える床までの各層で元の角の支柱へ単管で繋ぐ。
- 縮幅: 角は元の升目の中（升目の対角線の上）。幅を変える床のコマで、元の升目の内側の角の支柱から外側の角の支柱へ
  対角に単管を渡し、その上に角の支柱を立てる。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

WIDTH_STEP_MM = 305                 # 拡幅ブラケット NDBK03H の出（芯々）
WIDTH_PAIRS = ((610, 914), (914, 1219))
EXT_POST_MM = 900                   # 元の外側の支柱に継ぎ足す支柱（NDP09N）
TIE_ABOVE_MM = 900                  # つなぎ材 NDT03 の高さ（ブラケットの床から2コマ上。継ぎ足した NDP09N の上のコマ）
MODES = ("拡幅", "縮幅")


@dataclass(frozen=True)
class WidthChange:
    from_mm: int                    # 下の足場の建地列の間隔（腕木の呼び寸法）
    to_mm: int                      # 上の足場の建地列の間隔
    level: int                      # 幅を変える作業床（1 始まり。この床から上が to_mm）
    to_decks: tuple                 # 上の足場の作業床の組（master.width_setup）
    edges: Optional[frozenset] = None   # 幅を変える面（None＝全部）

    @property
    def mode(self) -> str:
        return "拡幅" if self.to_mm > self.from_mm else "縮幅"

    @property
    def label(self) -> str:
        return f"{self.mode} {self.from_mm}→{self.to_mm}（{self.level}段目の床から）"


def parse_spec(value) -> Optional[dict]:
    """width_change の値 → {"to_mm", "level", "faces"}（無し・「なし」は None）.

    {"to_mm": 914, "level": 4, "faces": ["南面"]} のほか、配置の窓の文字（「拡幅 610→914」）と段（level）も読む。
    """
    if not value or value in ("なし", "無し"):
        return None
    if isinstance(value, str):
        value = {"label": value}
    if not isinstance(value, dict):
        return None
    out = dict(value)
    lab = str(out.get("label") or "")
    if lab and "to_mm" not in out:
        nums = [int(t) for t in lab.replace("→", " ").replace("->", " ").split() if t.isdigit()]
        if len(nums) >= 2:
            out["from_mm"], out["to_mm"] = nums[0], nums[1]
        if lab.startswith("なし"):
            return None
    if "to_mm" not in out:
        return None       # 段だけ（部品の「幅を変える床」だけ入っていて幅の欄が「なし」）
    return out


def check(value, n_levels: int) -> list[str]:
    """入力の誤り（cli の検証）。値の形と段の範囲だけ（系列・幅の組は build で見る）."""
    v = parse_spec(value)
    if v is None:
        return []
    errs = []
    to = v.get("to_mm")
    if not isinstance(to, (int, float)) or isinstance(to, bool):
        errs.append(f"width_change.to_mm: 上の足場の幅（914・1219・610）を mm で指定してください（{to!r}）")
    lv = v.get("level")
    if not isinstance(lv, (int, float)) or isinstance(lv, bool) or int(lv) != lv or lv < 2:
        errs.append(f"width_change.level: 幅を変える作業床の段を 2 以上の整数で指定してください（{lv!r}）")
    elif n_levels and lv > n_levels:
        errs.append(f"width_change.level: {int(lv)}段目は足場の作業床（{n_levels}段）より上です")
    return errs


def build(spec: dict, model) -> tuple[Optional[WidthChange], list[str]]:
    """spec の width_change → WidthChange と注意（使えないときは None と理由）."""
    v = parse_spec(spec.get("width_change"))
    if v is None:
        return None, []
    m = model.master
    if m.is_frame or m.is_tube or model.config.scaffold_form != "本足場":
        return None, ["幅を変える（拡幅・縮幅）のは、くさび式の本足場だけです（この足場では幅を変えずに計画しました）"]
    w1 = int(model.post_row_spacing_mm)
    w2 = int(round(float(v.get("to_mm") or 0)))
    if v.get("from_mm") and int(v["from_mm"]) != w1:
        return None, [f"拡幅・縮幅の元の幅 {int(v['from_mm'])} が足場の幅 {w1} と違います（幅を変えずに計画しました。"
                      f"足場の幅を {int(v['from_mm'])} にしてください）"]
    if tuple(sorted((w1, w2))) not in WIDTH_PAIRS:
        pairs = "・".join(f"{a}↔{b}" for a, b in WIDTH_PAIRS)
        return None, [f"幅を変えられるのは拡幅ブラケット 305 の1回分（{pairs}）だけです（{w1}→{w2} は幅を変えずに計画しました）"]
    if m.find("ブラケット", WIDTH_STEP_MM) is None and not any(
            p.nominal_dim == WIDTH_STEP_MM and "拡幅" in p.note for p in m.by_category("ブラケット")):
        return None, [f"系列 {m.series_id} に拡幅ブラケット 305 がありません（幅を変えずに計画しました）"]
    row2, decks = m.width_setup(w2)
    if int(row2) != w2 or not decks:
        return None, [f"系列 {m.series_id} に幅 {w2} の腕木・作業床がありません（幅を変えずに計画しました）"]
    edges = None
    faces = v.get("faces")
    if faces:
        names = dict(zip(model.plan.face_names(), (e.edge_index for e in model.plan.edges)))
        edges = frozenset(names[f] for f in faces if f in names)
    wc = WidthChange(from_mm=w1, to_mm=w2, level=int(v.get("level") or 0), to_decks=tuple(decks), edges=edges)
    notes = []
    short = [n for n, e in zip(model.plan.face_names(), model.plan.edges)
             if applies_face(model, e.edge_index, wc) is False and (edges is None or e.edge_index in edges)]
    if short:
        notes.append(f"{'・'.join(short)}は作業床が {wc.level} 段に届かないので幅を変えません")
    return wc, notes


def applies_face(model, edge_index: int, wc: Optional[WidthChange] = None) -> bool:
    """この面で幅を変えるか（面の作業床が level 段以上ある）."""
    wc = wc or getattr(model, "width_change", None)
    if wc is None:
        return False
    if wc.edges is not None and edge_index not in wc.edges:
        return False
    return len(model.elevation_of(edge_index).level_heights) >= wc.level


def faces(model) -> list:
    """幅を変える面（model.plan.edges の要素）."""
    return [ep for ep in model.plan.edges if applies_face(model, ep.edge_index)]


def change_height_mm(model, edge_index: int) -> float:
    """幅を変える床の高さ（足場の立つ面から mm）."""
    wc = model.width_change
    return float(model.elevation_of(edge_index).level_heights[wc.level - 1])


def upper_levels(model, edge_index: int) -> int:
    """新しい幅の作業床の段数."""
    return len(model.elevation_of(edge_index).level_heights) - model.width_change.level + 1


def corner_changes(model, ep) -> bool:
    """この面の始点の出隅の升目も新しい幅にするか（隣の面も幅を変える）."""
    n = len(model.plan.outline.edges)
    prev = (ep.edge_index - 1) % n
    return (model.corner_kind_start(ep.edge_index) == "出隅"
            and any(e.edge_index == prev for e in faces(model)))


def lower_params(model, ep) -> dict:
    """下の足場ライン（元の幅）の上書き: 幅を変える床の下の段まで."""
    if not applies_face(model, ep.edge_index):
        return {}
    return {"segLevA": 0, "segLevB": model.width_change.level - 1}


def upper_params(model, ep) -> dict:
    """上の足場ライン（新しい幅）の上書き: 幅を変える床から天端まで、建地列の間隔・作業床・出隅の升目の辺."""
    wc = model.width_change
    n = len(model.plan.outline.edges)
    ds = list(wc.to_decks)
    w2 = wc.to_mm / 1000.0

    def side(ei):
        return w2 if applies_face(model, ei) else model.row_spacing_of(ei) / 1000.0

    return {
        "segLevA": wc.level, "segLevB": 0,
        "rowW": w2,
        "deckW1": ds[0] / 1000.0,
        "deckW2": (ds[1] if len(ds) > 1 else 0) / 1000.0,
        "cornerSW": side((ep.edge_index - 1) % n),
        "cornerEW": side((ep.edge_index + 1) % n),
        # 敷板・ジャッキは下の部品が持つ
        "sillT": 0.0, "sillList": "",
        # 平面の上の部品の注記（2d.gdl の 970）
        "segNote": f"{wc.mode} {wc.from_mm}→{wc.to_mm}",
    }


def bracket_points(model, ep) -> list[tuple[float, float]]:
    """ブラケットを掛ける下の足場の外側の支柱（面の座標 (x, y) mm。y は躯体側が＋）."""
    w1 = float(model.width_change.from_mm)
    xs, x = [0.0], 0.0
    for s in ep.spans:
        x += float(s)
        xs.append(x)
    return [(xv, -w1) for xv in xs]


def corner_point(model, ep) -> Optional[dict]:
    """始点の出隅の升目の角の支柱の納まり（面の座標 mm）. None＝この面は角を持たない."""
    if not corner_changes(model, ep):
        return None
    wc = model.width_change
    w1, w2 = float(wc.from_mm), float(wc.to_mm)
    n = len(model.plan.outline.edges)
    w1p = float(model.row_spacing_of((ep.edge_index - 1) % n))
    old = (-w1p, -w1)
    new = (-(w1p + (w2 - w1)), -w2)
    return {"old": old, "new": new, "inner": (0.0, 0.0), "mode": wc.mode,
            "diag_mm": math.hypot(new[0] - old[0], new[1] - old[1]),
            "beam_mm": math.hypot(old[0], old[1])}
