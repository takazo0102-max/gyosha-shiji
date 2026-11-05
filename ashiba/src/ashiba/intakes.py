"""取り入れ口（資材の取り込み口）. 揚重機で吊った資材を足場越しに躯体へ取り込む開口.

利用者の指定（2026-10-24）「取り入れ口を作る仕組みを考えて作成して」。
- 取り入れ口のスパン・層は、外側の固定の手すり・中桟と幅木を外し（部材編集と同じ扱い。3D・平面・数量）、
  代わりに取り外しのできる可動手すり（単管2本＝手すり・中桟を自在クランプで留め、取り込むときだけ外す）を付ける
- 外部のシートは取り入れ口の範囲を巻き上げ式（取り込むときだけ開ける）にする
- 図: 平面は外側建地列の外に範囲の破線と「取り入れ口（3〜5層）」、3D（立面・断面）は可動手すりを外側にずらして描く

入力: intakes: [{"face": "南面", "start_mm": 7316, "span_count": 1, "levels": "3-5"}]（位置は面の始点の支柱から、
levels は作業床の層。省くと全部の層）。パレットの「取り入れ口」は平面の線で書く。
"""

from __future__ import annotations

from dataclasses import dataclass

from .member_edits import MemberEdit


@dataclass
class Intake:
    edge_index: int
    span_from: int        # 1 始まり（含む）
    span_to: int
    level_from: int       # 作業床の層 1 始まり（含む）
    level_to: int


def _levels(v, n: int) -> tuple[int, int]:
    if v in (None, "", "全部", "全て", "すべて", "all"):
        return 1, n
    if isinstance(v, (list, tuple)):
        a, b = int(v[0]), int(v[-1])
    else:
        t = str(v).replace("〜", "-").replace("~", "-")
        a, _s, b = t.partition("-")
        a, b = int(a), int(b or a)
    a, b = sorted((a, b))
    return max(1, a), min(n, b)


def parse_intakes(items, model, resolve_face) -> tuple[list[Intake], list[str]]:
    """入力の intakes → [Intake]・読めなかった項目の説明."""
    out: list[Intake] = []
    errors: list[str] = []
    by_edge = {e.edge_index: e for e in model.plan.edges}
    for i, it in enumerate(items or []):
        lbl = f"intakes[{i}]"
        try:
            ei = resolve_face(str(it["face"]), model) if "face" in it else int(it["edge_index"])
        except Exception as ex:      # noqa: BLE001 — 面名の誤りはそのまま返す
            errors.append(f"{lbl}: {ex}")
            continue
        ep = by_edge.get(int(ei))
        if ep is None:
            errors.append(f"{lbl}: その面に足場がありません")
            continue
        posts = [0.0]
        for sp in ep.spans:
            posts.append(posts[-1] + float(sp))
        x = float(it.get("start_mm", 0.0))
        s0 = min(range(len(ep.spans)), key=lambda k: abs(posts[k] - x)) + 1
        n = int(it.get("span_count", 1) or 1)
        s1 = min(len(ep.spans), s0 + n - 1)
        try:
            l0, l1 = _levels(it.get("levels"), model.elevation_of(ep.edge_index).n_levels)
        except ValueError:
            errors.append(f"{lbl}.levels: 「{it.get('levels')}」は層の番号（例 3-5）で書いてください")
            continue
        out.append(Intake(ep.edge_index, s0, s1, l0, l1))
    return out, errors


def intake_edits(intakes: list[Intake]) -> list[MemberEdit]:
    """取り入れ口の升目: 外側の固定の手すり・中桟と幅木を外す（部材編集。auto＝墜落の要確認は可動手すりの注記で出す）."""
    return [MemberEdit(t.edge_index, t.span_from, t.span_to, t.level_from, t.level_to, ("外側手すり", "幅木"),
                       reason="取り入れ口", auto=True) for t in intakes]


def intake_list(model, ep) -> str:
    """足場ラインの intkList: 「始め,終わり,層始め,層終わり」（mm・層番号）の繰り返し."""
    posts = [0.0]
    for sp in ep.spans:
        posts.append(posts[-1] + float(sp))
    parts = []
    for t in getattr(model, "intakes", None) or []:
        if t.edge_index != ep.edge_index:
            continue
        parts += [f"{posts[t.span_from - 1]:.0f}", f"{posts[t.span_to]:.0f}", str(t.level_from), str(t.level_to)]
    return ",".join(parts)


def mine(model) -> list[Intake]:
    """この模型の数量で数える取り入れ口（面ごとに高さが違うときは、その面の組だけ。二重に手配しない）."""
    return [t for t in getattr(model, "intakes", None) or []
            if model.edge_subset is None or t.edge_index in model.edge_subset]


def intake_cells(model) -> int:
    return sum((t.span_to - t.span_from + 1) * (t.level_to - t.level_from + 1) for t in mine(model))


def _rng(a: int, b: int) -> str:
    return f"{a}" if a == b else f"{a}〜{b}"


def intake_note(model) -> str:
    items = []
    for t in mine(model):
        items.append(f"{model.face_name(t.edge_index)} {_rng(t.span_from, t.span_to)}スパン目・"
                     f"{_rng(t.level_from, t.level_to)}層")
    n = intake_cells(model)
    return (f"取り入れ口（{'、'.join(items)}）は外側の固定の手すり・中桟と幅木を外し、可動手すり（単管2本を自在クランプ"
            f"で留め、取り込むときだけ外す）{n}組とクランプ {n * 4}個、シートは巻き上げ式で開ける。取り込み中は"
            "立入禁止・合図者を置き、作業後はすぐ可動手すりを戻すこと")
