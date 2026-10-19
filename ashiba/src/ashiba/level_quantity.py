"""層ごと（作業床1層ごと）の数量（利用者の指定 2026-10-20: 1フロアごとに数量を拾えるように、支柱は分解して）.

- 支柱以外: 足場を k 層で切った計画の数量と k−1 層の数量の差を、k 層目の数量とする（布材・踏板・手すり・
  壁つなぎ・階段など、層ごとに増える部材がそのまま分かれる。ジャッキ・根がらみ等の足元は1層目に入る）。
- 支柱: 切った計画では天端の短い支柱が入れ替わり差が意味を持たないので、支柱を1本ずつに分解し、
  下端の高さが入る層に数える（2700 は1層目、その上の 3600 は2層目… のように積んだ順）。
  敷地の高低差の継ぎ足し・開口部の梁枠上の短い支柱など、位置ごとに違う分は1層目に寄せて注記する。
- 各層の合計は全体の数量表と一致する（テストで確かめる）。
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from .elevation_solver import truncate_elevation
from .model import ScaffoldModel


@dataclass
class LevelBand:
    index: int            # 1 始まり
    z_lo: float           # mm（足場の立つ面から）
    z_hi: float

    @property
    def label(self) -> str:
        return f"{self.index}層（{self.z_lo / 1000:.2f}〜{self.z_hi / 1000:.2f}m）"


@dataclass
class LevelRow:
    part: object
    per_level: list[int]

    @property
    def total(self) -> int:
        return sum(self.per_level)


@dataclass
class LevelTakeoff:
    bands: list[LevelBand]
    rows: list[LevelRow]
    notes: list[str] = field(default_factory=list)
    floors: list[str] = field(default_factory=list)    # 層ごとの建物のフロア名（フロアの情報があるとき）

    def by_floor(self) -> tuple[list[str], list[tuple[object, list[int]]]]:
        """フロアごとに層をまとめた数量 (フロア名の並び, [(部材, フロアごとの数)])。フロアが無ければ空."""
        if not self.floors:
            return [], []
        names: list[str] = []
        for f in self.floors:
            if f not in names:
                names.append(f)
        out = []
        for r in self.rows:
            vals = [0] * len(names)
            for i, v in enumerate(r.per_level):
                vals[names.index(self.floors[i])] += v
            out.append((r.part, vals))
        return names, out

    def level_weights(self) -> list[float]:
        return [round(sum(r.part.weight_kg * r.per_level[i] for r in self.rows), 1) for i in range(len(self.bands))]


def _truncated(model: ScaffoldModel, top_mm: float) -> ScaffoldModel:
    m = copy.copy(model)
    master = model.master
    m.elevation = truncate_elevation(model.elevation, top_mm, master)
    m.face_elevations = {i: truncate_elevation(ev, top_mm, master) for i, ev in model.face_elevations.items()}
    m.wall_ties = [t for t in model.wall_ties if t.height_mm <= top_mm + 1]
    return m


def _counts(q) -> dict:
    out: dict = {}
    parts: dict = {}
    for line in q.lines:
        key = (line.part.model_no, line.part.category)
        out[key] = out.get(key, 0) + line.qty
        parts[key] = line.part
    return out, parts


def floor_names(bands: list[LevelBand], stories, base_mm: float = 0.0) -> list[str]:
    """層（作業床の高さ）→ 建物のフロア名。床の高さ以下でいちばん高いフロア（無ければ最も低いフロア）.

    stories は [{"name": "2FL", "level_mm": 3000}, ...]（Archicad のフロア。足場の立つ高さ base を足して比べる）。
    """
    st = sorted(((float(s["level_mm"]), str(s["name"])) for s in stories or []), key=lambda v: v[0])
    if not st:
        return []
    out = []
    for b in bands:
        z = b.z_hi + base_mm
        hit = [name for lv, name in st if lv <= z + 1]
        out.append(hit[-1] if hit else st[0][1])
    return out


def take_off_by_level(model: ScaffoldModel, quantity, stories=None, **kw) -> LevelTakeoff:
    """層ごとの数量。quantity は全体の数量（take_off の結果）、kw は take_off に渡したもの.

    stories（建物のフロア）を渡すと、層ごとにフロア名を付け、フロアごとの合計も出せる（by_floor）。
    """
    from .quantity import _sub_model, face_height_groups, take_off

    levels = list(model.elevation.level_heights)
    n = len(levels)
    if n == 0:
        return LevelTakeoff([], [], ["作業床が無いため層ごとの数量は出しません"])
    bands = [LevelBand(k + 1, float(levels[k - 1]) if k else 0.0, float(levels[k])) for k in range(n)]

    full, parts = _counts(quantity)
    cum: list[dict] = []
    for k in range(1, n):
        c, p = _counts(take_off(_truncated(model, levels[k - 1]), **kw))
        parts.update(p)
        cum.append(c)
    cum.append(full)

    keys = list(full.keys())
    for c in cum:
        keys += [k for k in c if k not in keys]
    per: dict = {}
    for key in keys:
        prev = 0
        vals = []
        for c in cum:
            v = c.get(key, 0)
            vals.append(v - prev)
            prev = v
        per[key] = vals

    notes: list[str] = []
    master = model.master
    post_cat = "支柱"
    if not master.is_frame:
        rows_n = 1 if model.config.scaffold_form == "一側足場" else 2
        geo: dict = {}
        for ev, edges in face_height_groups(model):
            sub = _sub_model(model, ev, edges)
            positions = sub.plan.total_posts * rows_n + sub.outer_corner_posts()
            z = float(ev.jack_extension)
            for nominal in ev.posts:
                band = next((i for i, h in enumerate(levels) if z < h - 1), n - 1)
                geo.setdefault(nominal, [0] * n)[band] += positions
                z += nominal
        for key in [k for k in keys if k[1] == post_cat]:
            part = parts[key]
            want = full.get(key, 0)
            vals = list(geo.get(part.nominal_dim, [0] * n))
            diff = want - sum(vals)
            if diff:
                vals[0] += diff
                notes.append(f"{part.model_no}（{post_cat}{part.nominal_dim}）の {diff:+d}本は、敷地の継ぎ足し・"
                             "開口部の梁枠上など位置ごとに違う分として1層目に入れています")
            per[key] = vals

    # 朝顔は高さで決まる部材（1段目 4〜5m・2段目以降 10m ごと）。切った計画でも同じ段数で数えるので、
    # 差を取ると全部1層目に入る。段の高さの層へ段数で等分する
    heights = model.asagao_heights()
    if heights:
        stage_bands = [next((i for i, h in enumerate(levels) if z <= h + 1), n - 1) for z in heights]
        for key in [k for k in keys if k[1] == "朝顔"]:
            total = full.get(key, 0)
            vals = [0] * n
            each, rest = divmod(total, len(stage_bands))
            for j, b in enumerate(stage_bands):
                vals[b] += each + (1 if j < rest else 0)
            per[key] = vals

    neg = [k for k, v in per.items() if any(x < 0 for x in v)]
    if neg:
        notes.append("層を切ると数え方が変わる部材（" + "・".join(parts[k].model_no for k in neg)
                     + "）は、層によって負の数になります。合計は数量表と同じです")
    rows = [LevelRow(parts[k], per[k]) for k in keys if any(per[k])]
    return LevelTakeoff(bands, rows, notes, floor_names(bands, stories, float(model.base_height_mm)))
