"""拡幅・縮幅（途中の作業床から足場の幅を 305 変える）.

利用者の指定 2026-10-25「両方作って 610→914と914→1219」「拡張が全ての足場になってしまうから直すのところで線を
引いた範囲限定にする」。日建 ND1800 の拡幅ブラケット NDBK03H（出 305・方杖は1コマ 450 下・先端ホゾ φ36.4。
カタログ Vol.10 p014）と、ND1900 カタログ p015 の「拡幅・縮幅例」の組み方:

- 幅を変える作業床（level 段目）のコマで、下の足場の外側の支柱にブラケットを掛ける。拡幅は外へ、縮幅は内（躯体側）へ。
- 先端のホゾに新しい外側の支柱を立てて天端まで。元の外側の支柱はその床の上に NDP09N（900）を継ぎ足し、つなぎ材
  NDT03（305）で新しい支柱と繋ぐ。
- 幅を変えるのは全高で1回だけ。幅を変えた層の上下は前踏み側の全スパンに壁つなぎ、拡幅部の支柱の許容荷重
  （ND1800 は 8.8kN/本）を確かめる。

幅を変える範囲はパレットの「幅の変更」で平面に引いた線（width_change.faces の「南面[a-b]」。面の始点の支柱から mm、
支柱に寄せる）。範囲の無い指定は全部の面。

足場ラインは、範囲のスパンで縦に、幅を変える床の 100 下で横に区切る（segments と同じ区切り）。範囲の下は元の幅、
上は新しい幅（rowW・作業床の組・出隅の升目の辺）。範囲の外は元のまま。

範囲の端（面の途中）: 元の外側の支柱を天端まで通し（始まりの端は継ぎ足しの支柱で、終わりの端は後の区間の支柱が
そのまま）、新しい外側の支柱（終わりの端はブラケットの部品が描く）との間を各層の手すり・中桟の高さでつなぎ材 NDT03
で塞ぐ。拡幅の終わりの端は、新しい幅の床を受ける腕木（布材）をブラケットの部品が足す。

出隅の升目:
- 両方の面が隅まで幅を変える: 角は新しい幅の升目。拡幅は元の升目の外に地面から支柱を1本立て、幅を変える床までの
  各層で元の角の支柱へ単管で繋ぐ。縮幅は元の升目の対角に単管を渡し、その上に角の支柱を立てる。
- 片方の面だけ隅まで幅を変える: 角の升目はその面の向きだけ新しい幅の長方形。元の角の支柱にブラケットを掛け、
  先端に角の支柱を立てる（幅を変えない面の足場ラインも幅を変える床で上下に分け、上の升目の辺を新しい幅にする）。
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
    # 幅を変える面と範囲 {辺番号: (始め, 終わり) mm（この組の面の始点の支柱から）か None（面全体）}。None＝全部の面
    ranges: Optional[dict] = None

    @property
    def mode(self) -> str:
        return "拡幅" if self.to_mm > self.from_mm else "縮幅"

    @property
    def label(self) -> str:
        return f"{self.mode} {self.from_mm}→{self.to_mm}（{self.level}段目の床から）"


def labels_for(width_mm: int) -> list[str]:
    """いまの足場の幅から選べる幅の変え方（「拡幅 610→914」など）."""
    w = int(width_mm)
    return ([f"拡幅 {a}→{b}" for a, b in WIDTH_PAIRS if a == w]
            + [f"縮幅 {b}→{a}" for a, b in WIDTH_PAIRS if b == w])


def parse_spec(value) -> Optional[dict]:
    """width_change の値 → {"to_mm", "level", "faces"}（無し・「なし」は None）.

    {"to_mm": 914, "level": 4, "faces": ["南面[1829-9145]"]} のほか、ラベル（「拡幅 610→914」）と段（level）も読む。
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
        return None       # 段だけ（幅の欄が「なし」）
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
    faces = v.get("faces")
    if faces is not None and not isinstance(faces, (list, tuple, str)):
        errs.append(f"width_change.faces: 面名（「南面」「南面[1829-9145]」）の並びで指定してください（{faces!r}）")
    return errs


def _ranges_from(faces, model) -> Optional[dict]:
    """faces（「南面」「南面[a-b]」の並び）→ {辺番号: (始め, 終わり) か None}. 同じ面の区間は外側までまとめる."""
    from .face_forms import split_key

    if faces is None:
        return None
    if isinstance(faces, str):
        faces = [t for t in faces.replace("；", ";").replace("、", ";").split(";") if t.strip()]
    names = dict(zip(model.plan.face_names(), (e.edge_index for e in model.plan.edges)))
    out: dict = {}
    for key in faces:
        face, a, b = split_key(str(key))
        if face not in names:
            continue
        ei = names[face]
        if a is None:
            out[ei] = None
            continue
        x0 = float((getattr(model, "face_offsets", {}) or {}).get(ei, (0.0, 0.0))[0])
        a, b = a - x0, b - x0
        if ei in out:
            if out[ei] is None:
                continue
            a, b = min(a, out[ei][0]), max(b, out[ei][1])
        out[ei] = (a, b)
    return out


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
                      f"幅の変更をやり直すか、足場の幅を {int(v['from_mm'])} にしてください）"]
    if tuple(sorted((w1, w2))) not in WIDTH_PAIRS:
        pairs = "・".join(f"{a}↔{b}" for a, b in WIDTH_PAIRS)
        return None, [f"幅を変えられるのは拡幅ブラケット 305 の1回分（{pairs}）だけです（{w1}→{w2} は幅を変えずに計画しました）"]
    if not any(p.nominal_dim == WIDTH_STEP_MM and "拡幅" in p.note for p in m.by_category("ブラケット")):
        return None, [f"系列 {m.series_id} に拡幅ブラケット 305 がありません（幅を変えずに計画しました）"]
    row2, decks = m.width_setup(w2)
    if int(row2) != w2 or not decks:
        return None, [f"系列 {m.series_id} に幅 {w2} の腕木・作業床がありません（幅を変えずに計画しました）"]
    ranges = _ranges_from(v.get("faces"), model)
    wc = WidthChange(from_mm=w1, to_mm=w2, level=int(v.get("level") or 0), to_decks=tuple(decks), ranges=ranges)
    notes = []
    short = [model.face_name(e.edge_index) for e in model.plan.edges
             if (ranges is None or e.edge_index in ranges)
             and len(model.elevation_of(e.edge_index).level_heights) < wc.level]
    if short:
        notes.append(f"{'・'.join(short)}は作業床が {wc.level} 段に届かないので幅を変えません")
    return wc, notes


# ---- 範囲 ----


def posts_x(ep) -> list[float]:
    """面の支柱の位置（面の始点の支柱から mm。0, スパン, …, 面の長さ）."""
    xs, x = [0.0], 0.0
    for s in ep.spans:
        x += float(s)
        xs.append(x)
    return xs


def span_range(model, ep) -> Optional[tuple[int, int]]:
    """この面で幅を変えるスパン (始め, 終わり)（1 始まり・両端を含む）. 幅を変えなければ None.

    線の区間は、いちばん近い支柱に寄せる（線がかかるスパン）。"""
    wc = getattr(model, "width_change", None)
    if wc is None or len(model.elevation_of(ep.edge_index).level_heights) < wc.level:
        return None
    n = len(ep.spans)
    if wc.ranges is None:
        return (1, n)
    if ep.edge_index not in wc.ranges:
        return None
    r = wc.ranges[ep.edge_index]
    if r is None:
        return (1, n)
    xs = posts_x(ep)
    i0 = min(range(len(xs)), key=lambda i: abs(xs[i] - r[0]))
    i1 = min(range(len(xs)), key=lambda i: abs(xs[i] - r[1]))
    if i1 <= i0:
        return None
    return (i0 + 1, i1)


def applies_face(model, edge_index: int) -> bool:
    """この面のどこかで幅を変えるか."""
    ep = next((e for e in model.plan.edges if e.edge_index == edge_index), None)
    return ep is not None and span_range(model, ep) is not None


def faces(model) -> list:
    """幅を変える面（model.plan.edges の要素）."""
    return [ep for ep in model.plan.edges if span_range(model, ep) is not None]


def _reaches(model, ep, end: str) -> bool:
    sr = span_range(model, ep)
    return bool(sr) and (sr[0] == 1 if end == "s" else sr[1] == len(ep.spans))


def _neighbor(model, ep, step: int):
    n = len(model.plan.outline.edges)
    ei = (ep.edge_index + step) % n
    return next((e for e in model.plan.edges if e.edge_index == ei), None)


def start_corner(model, ep) -> Optional[str]:
    """始点の出隅の升目が幅を変える床から上でどう変わるか.

    "both"＝両方の面が隅まで幅を変える、"self"＝この面だけ、"prev"＝前の面だけ、None＝変わらない（出隅でない）."""
    wc = getattr(model, "width_change", None)
    if wc is None or model.corner_kind_start(ep.edge_index) != "出隅":
        return None
    prev = _neighbor(model, ep, -1)
    me = _reaches(model, ep, "s")
    pv = prev is not None and _reaches(model, prev, "e")
    if me and pv:
        return "both"
    if me:
        return "self"
    if pv and len(model.elevation_of(ep.edge_index).level_heights) >= wc.level:
        return "prev"
    return None


def end_corner_changes(model, ep) -> bool:
    """終点の出隅の升目（次の面が描く）の、この面の向きの辺（次の面の建地列間隔）が新しい幅になるか."""
    nxt = _neighbor(model, ep, 1)
    return nxt is not None and start_corner(model, nxt) in ("both", "self")


def change_height_mm(model, edge_index: int) -> float:
    """幅を変える床の高さ（足場の立つ面から mm）."""
    wc = model.width_change
    return float(model.elevation_of(edge_index).level_heights[wc.level - 1])


def upper_levels(model, edge_index: int) -> int:
    """新しい幅の作業床の段数."""
    return len(model.elevation_of(edge_index).level_heights) - model.width_change.level + 1


def touched(model, ep) -> bool:
    """この面の足場ラインを区切るか（幅を変える範囲がある、または始点の隅の升目だけ変わる）."""
    return span_range(model, ep) is not None or start_corner(model, ep) == "prev"


# ---- 足場ラインの部品 ----


def line_pieces(model, ep) -> list[dict]:
    """この面の足場ラインの部品の上書き（先頭は面の部品そのもの、残りは足して置く部品）. 変えなければ [].

    範囲の前・範囲・範囲の後でスパンを縦に区切り、範囲（と、前の面だけ幅を変える隅の升目を持つ区間）は幅を変える床で
    横にも区切る。"""
    if getattr(model, "width_change", None) is None or not touched(model, ep):
        return []
    k = model.width_change.level
    n = len(ep.spans)
    sr = span_range(model, ep)
    corner = start_corner(model, ep)
    groups = []
    if sr:
        sa, sb = sr
        if sa > 1:
            groups.append(("pre", 1, sa - 1))
        groups.append(("R", sa, sb))
        if sb < n:
            groups.append(("post", sb + 1, n))
    else:
        groups.append(("pre", 1, n))
    out = []
    for kind, a, b in groups:
        seg = {"segSpanA": a if a > 1 else 0, "segSpanB": b if b < n else 0, "segGroup": f"幅の変更{ep.edge_index}"}
        split = kind == "R" or (kind == "pre" and a == 1 and corner == "prev")
        if not split:
            out.append({**seg, "segLevA": 0, "segLevB": 0})
            continue
        out.append({**seg, "segLevA": 0, "segLevB": k - 1})
        out.append({**seg, **upper_params(model, ep, wide=(kind == "R"))})
    return out


def lower_params(model, ep) -> dict:
    """面の部品（置いた足場ライン）の上書き: 幅を変える面は区切った最初の部品."""
    pcs = line_pieces(model, ep)
    return pcs[0] if pcs else {}


def upper_params(model, ep, wide: bool = True) -> dict:
    """幅を変える床から上の部品の上書き. wide＝範囲（建地列の間隔・作業床を新しい幅に）、False＝前の面だけ幅を変える
    隅の升目を持つ区間（隅の升目の辺だけ新しい幅）."""
    wc = model.width_change
    n = len(model.plan.outline.edges)
    ds = list(wc.to_decks)
    w2 = wc.to_mm / 1000.0
    prev = _neighbor(model, ep, -1)
    c_s = (w2 if prev is not None and _reaches(model, prev, "e") and model.corner_kind_start(ep.edge_index) == "出隅"
           else model.row_spacing_of((ep.edge_index - 1) % n) / 1000.0)
    c_e = w2 if end_corner_changes(model, ep) else model.row_spacing_of((ep.edge_index + 1) % n) / 1000.0
    out = {
        "segLevA": wc.level, "segLevB": 0,
        "cornerSW": c_s, "cornerEW": c_e,
        # 敷板・ジャッキは下の部品が持つ
        "sillT": 0.0, "sillList": "",
        # 平面の上の部品の注記（2d.gdl の 970）
        "segNote": f"{wc.mode} {wc.from_mm}→{wc.to_mm}" if wide else f"{wc.mode}の隅の升目",
    }
    if wide:
        out.update({"rowW": w2, "deckW1": ds[0] / 1000.0, "deckW2": (ds[1] if len(ds) > 1 else 0) / 1000.0})
    return out


# ---- ブラケットと範囲の端 ----


def _rail_heights(model, ep) -> list[float]:
    """幅を変えた層の手すり・中桟の高さ（足場の立つ面から mm）。範囲の端を塞ぐつなぎ材の高さ."""
    lv = list(model.elevation_of(ep.edge_index).level_heights)[model.width_change.level - 1:]
    out = []
    for h in lv:
        out += [float(h) + float(model.midrail_height_mm), float(h) + float(model.guard_rail_height_mm)]
    top = float(model.own_height(ep.edge_index))
    return [z for z in out if z < top - 10.0]


def bracket_specs(model, ep) -> list[dict]:
    """この面のブラケット（面の座標 mm。y は躯体側が＋）と、それぞれの継ぎ足し・つなぎ材・先端の支柱.

    dir: "face"＝面に直角（拡幅は外・縮幅は躯体側）、"prev"＝前の面に直角（隅の升目の前の面の向き）。
    z: 腕の高さ（足場の立つ面から）、ext: 元の支柱の継ぎ足しの長さ、ties: つなぎ材の高さ（腕から上 mm）、
    tip: 先端に立てる支柱の長さ（範囲の終わりの端）、ud: 先端まで延ばす腕木の高さ（腕から上 mm。拡幅の範囲の終わりの端）、
    end: 範囲の端なら "s"／"e"."""
    wc = getattr(model, "width_change", None)
    if wc is None:
        return []
    out: list[dict] = []
    w1 = float(wc.from_mm)
    top = float(model.own_height(ep.edge_index))
    sr = span_range(model, ep)
    if sr:
        sa, sb = sr
        n = len(ep.spans)
        zk = change_height_mm(model, ep.edge_index)
        xs = posts_x(ep)
        rails = [z - zk for z in _rail_heights(model, ep)]
        floors = [float(h) - zk for h in list(model.elevation_of(ep.edge_index).level_heights)[wc.level - 1:]]
        for i in range(sa - 1, sb + 1):
            b = {"x": xs[i], "y": -w1, "dir": "face", "z": zk, "ext": float(EXT_POST_MM),
                 "ties": [float(TIE_ABOVE_MM)], "tip": 0.0, "ud": [], "end": ""}
            if i == sa - 1 and sa > 1:
                # 範囲の始まりの端: 元の支柱を天端まで（前の区間の外側の布材・手すりが掛かる）
                b.update({"ext": top - zk, "ties": rails, "end": "s"})
            elif i == sb and sb < n:
                # 範囲の終わりの端: 元の支柱は後の区間がそのまま。先端の支柱をこの部品で天端まで
                b.update({"ext": 0.0, "ties": rails, "tip": top - zk, "end": "e",
                          "ud": floors if wc.mode == "拡幅" else []})
            out.append(b)
    corner = start_corner(model, ep)
    if corner in ("self", "prev"):
        n_out = len(model.plan.outline.edges)
        w1p = float(model.row_spacing_of((ep.edge_index - 1) % n_out))
        out.append({"x": -w1p, "y": -w1, "dir": "face" if corner == "self" else "prev",
                    "z": change_height_mm(model, ep.edge_index), "ext": float(EXT_POST_MM),
                    "ties": [float(TIE_ABOVE_MM)], "tip": 0.0, "ud": [], "end": ""})
    return out


def corner_point(model, ep) -> Optional[dict]:
    """両方の面が隅まで幅を変える出隅の升目の角の支柱の納まり（面の座標 mm）. None＝この面は持たない."""
    if start_corner(model, ep) != "both":
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


def range_ends(model, ep) -> list[tuple[float, str]]:
    """面の途中の範囲の端 [(位置 mm, "s"|"e")]（つなぎ材で塞ぐ・妻側のシートを張る）."""
    sr = span_range(model, ep)
    if not sr:
        return []
    xs = posts_x(ep)
    out = []
    if sr[0] > 1:
        out.append((xs[sr[0] - 1], "s"))
    if sr[1] < len(ep.spans):
        out.append((xs[sr[1]], "e"))
    return out


def outer_row_at(model, ep, x: float) -> float:
    """面の始点から x mm の外側の建地列の、躯体側の建地列からのいちばん外の位置 mm（拡幅した範囲は新しい幅）.

    敷地境界までの離れ（site_boundary.face_clearances）を、幅を広げた上の層でも測るため."""
    row = float(model.post_row_spacing_mm)
    wc = getattr(model, "width_change", None)
    if wc is None or wc.to_mm <= wc.from_mm:
        return row
    sr = span_range(model, ep)
    if not sr:
        return row
    xs = posts_x(ep)
    return float(wc.to_mm) if xs[sr[0] - 1] - 1.0 <= x <= xs[sr[1]] + 1.0 else row

