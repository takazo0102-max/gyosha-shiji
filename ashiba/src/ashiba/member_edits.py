"""範囲を指定した部材の編集（外す・置き換える）.

参考: smartCON Planner の「一般部材編集」（升目・列・行を選んで部材を消す・別の部材に替える）。
足場の自動割付のあとで「この面の3〜5スパン目の2〜4層は踏板を外す（設備の搬入口）」
「東面の手すりは全部 布材に替える」のような現場ごとの直しを、入力の member_edits で持つ。

- 外す: 数量表から引き、3D・平面（足場ラインの editList）でも描かない。
- 置換: 数量表で別の品番に付け替える（同じ数）。図は変えない（形の近い部材どうしの置き換え用）。

升目は（面, スパン番号, 層）。スパン番号は面の始点から 1, 2, …、層は作業床の層 1, 2, …（1層目＝最下段の
作業床）。筋かいは「その層の床の下の構面」、手すり・幅木は「その層の床の上」に付くものとして扱う。

開口部（梁枠より下）の升目はもともと部材が無いので引かない。足場の中の階段室の区間は、床の扱いが
層ごとに違う（階段が上がってくる側だけ開く）ので、踏板の編集は効かせない（注記する）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .model import GUARD_RAIL_ADVANCE, ScaffoldModel

# 部材の種類 → GDL の editList に入れるビット（足場ライン 3d.gdl・1d.gdl と同じ）
PART_BITS = {"踏板": 1, "外側手すり": 2, "幅木": 4, "筋かい": 8, "内側手すり": 16, "外側踏板": 32, "内側踏板": 64}
# 踏板（両方）は外側・内側の踏板の両方。上の層だけ床を狭める（内側の踏板を外す）ときは片側だけ指定する
PART_ALIASES = {
    "踏板": "踏板", "床": "踏板", "アンチ": "踏板", "布板": "踏板", "作業床": "踏板",
    "外側手すり": "外側手すり", "手すり": "外側手すり", "先行手すり": "外側手すり", "先行手摺": "外側手すり",
    "外手すり": "外側手すり",
    "幅木": "幅木",
    "筋かい": "筋かい", "筋交": "筋かい", "筋違": "筋かい", "ブレス": "筋かい", "斜材": "筋かい",
    "交差筋交": "筋かい", "交差筋違": "筋かい",
    "内側手すり": "内側手すり", "躯体側手すり": "内側手すり", "内手すり": "内側手すり",
    "外側踏板": "外側踏板", "外踏板": "外側踏板", "外側の踏板": "外側踏板", "外側の床": "外側踏板",
    "内側踏板": "内側踏板", "内踏板": "内側踏板", "内側の踏板": "内側踏板", "内側の床": "内側踏板",
}
ACTIONS = {"外す": "外す", "削除": "外す", "消す": "外す", "remove": "外す",
           "置換": "置換", "置き換え": "置換", "替える": "置換", "replace": "置換"}
ALL_WORDS = ("全部", "全て", "すべて", "all", "*")


@dataclass
class MemberEdit:
    edge_index: int
    span_from: int          # 1 始まり（含む）
    span_to: int
    level_from: int         # 作業床の層 1 始まり（含む）
    level_to: int
    parts: tuple            # PART_BITS のキー
    action: str = "外す"    # "外す" / "置換"
    to: str = ""            # 置換先の品番
    reason: str = ""
    # ツールが自分で入れた編集（入隅のつなぎで床を渡る升目の手すり・幅木など）。墜落の危険の要確認は出さない
    auto: bool = False

    @property
    def code(self) -> int:
        c = 0
        for p in self.parts:
            c |= PART_BITS[p]
        return c


@dataclass
class EditEffect:
    """編集が数量に効いた結果（注記・帳票用）."""
    edit: MemberEdit
    removed: dict = field(default_factory=dict)     # (品番, 分類) → 引いた数
    added: dict = field(default_factory=dict)       # (品番, 分類) → 足した数（置換先）
    skipped_cells: int = 0                          # 開口部・階段室で効かせなかった升目


def _range(v, n: int, what: str, errors: list) -> Optional[tuple[int, int]]:
    """"3-5"・[3, 5]・3・"全部"・None → (3, 5)。1〜n に収める."""
    if v is None or (isinstance(v, str) and v.strip().lower() in ALL_WORDS):
        return 1, n
    try:
        if isinstance(v, (list, tuple)):
            a, b = (int(v[0]), int(v[-1])) if v else (1, n)
        elif isinstance(v, (int, float)):
            a = b = int(v)
        else:
            s = str(v).replace("〜", "-").replace("～", "-").replace("~", "-").replace("ー", "-").strip()
            if "-" in s:
                x, y = s.split("-", 1)
                a, b = int(x), int(y)
            else:
                a = b = int(s)
    except (TypeError, ValueError):
        errors.append(f"{what}: 「{v}」は読めません（例: 3、\"3-5\"、[3, 5]、\"全部\"）")
        return None
    if a > b:
        a, b = b, a
    if b < 1 or a > n:
        errors.append(f"{what}: {a}〜{b} は範囲外です（1〜{n}）")
        return None
    return max(1, a), min(n, b)


def parse_member_edits(items, model: ScaffoldModel, resolve_face=None) -> tuple[list[MemberEdit], list[str]]:
    """入力の member_edits → MemberEdit の一覧と、読めなかった項目の説明."""
    edits: list[MemberEdit] = []
    errors: list[str] = []
    by_edge = {e.edge_index: e for e in model.plan.edges}
    for i, it in enumerate(items or []):
        lbl = f"member_edits[{i}]"
        if not isinstance(it, dict):
            errors.append(f"{lbl}: オブジェクトで指定してください")
            continue
        ei = it.get("edge_index")
        if it.get("face") is not None:
            try:
                ei = resolve_face(str(it["face"]), model) if resolve_face else None
            except Exception as ex:      # noqa: BLE001 — 面名の誤りはそのまま利用者に返す
                errors.append(f"{lbl}: {ex}")
                continue
        if ei is None or int(ei) not in by_edge:
            errors.append(f"{lbl}: 面（face）か辺番号（edge_index）を足場のある面で指定してください")
            continue
        ep = by_edge[int(ei)]
        n_lv = model.elevation_of(ep.edge_index).n_levels
        sr = _range(it.get("spans"), len(ep.spans), f"{lbl}.spans", errors)
        lr = _range(it.get("levels"), n_lv, f"{lbl}.levels", errors)
        if sr is None or lr is None:
            continue
        raw = it.get("parts", it.get("part"))
        raw = [raw] if isinstance(raw, str) else list(raw or [])
        parts = []
        for p in raw:
            key = PART_ALIASES.get(str(p).strip())
            if key is None:
                errors.append(f"{lbl}.parts: 「{p}」は分かりません（{'・'.join(PART_BITS)}）")
            elif key not in parts:
                parts.append(key)
        if not parts:
            if not raw:
                errors.append(f"{lbl}: parts（{'・'.join(PART_BITS)}）を指定してください")
            continue
        act = ACTIONS.get(str(it.get("action", "外す")).strip())
        if act is None:
            errors.append(f"{lbl}.action: 「{it.get('action')}」は分かりません（外す／置換）")
            continue
        to = str(it.get("to") or "").strip()
        if act == "置換":
            if not to:
                errors.append(f"{lbl}: 置換には置き換える品番（to）が要ります")
                continue
            if model.master.get(to) is None:
                errors.append(f"{lbl}.to: 品番 {to} が系列 {model.master.series_id} のマスタにありません")
                continue
        edits.append(MemberEdit(ep.edge_index, sr[0], sr[1], lr[0], lr[1], tuple(parts), act, to,
                                str(it.get("reason") or "")))
    return edits, errors


def inner_corner_edits(model: ScaffoldModel) -> list[MemberEdit]:
    """入隅でつないだ隅（model.inner_corner_joins）: 隅から始まる面の最初のスパンは外側の手すり・幅木を付けない.

    隅で終わる面の床から、その升目を通って歩いて渡る（inner_corners。利用者の指摘 2026-10-24: 入りすみが重なっている）。
    """
    out = []
    by_edge = {e.edge_index: e for e in model.plan.edges}
    for a, b, _gap in getattr(model, "inner_corner_joins", None) or []:
        if b not in by_edge:
            continue
        n_lv = min(model.elevation_of(a).n_levels, model.elevation_of(b).n_levels)
        if n_lv >= 1:
            out.append(MemberEdit(b, 1, 1, 1, n_lv, ("外側手すり", "幅木"), reason="入隅のつなぎ（床を渡る）",
                                  auto=True))
    return out


def tier_passage_edits(model: ScaffoldModel, passages) -> list[MemberEdit]:
    """セットバックの上段が本体に繋がる升目（setback_junctions の _tier_passage「面, 始め, 終わり, 屋根の高さ」。位置は元の
    面の始点の支柱から mm）: 途中の屋根より上の層で本体の内側の手すりを付けない（上段の床から本体の床へ回れる）.

    利用者の指摘 2026-10-25: セットバックの足場が本体と回らないようになっている布材を配置しないようにして。
    """
    out = []
    by_edge = {e.edge_index: e for e in model.plan.edges}
    for ei, a, b, z0 in passages or []:
        ep = by_edge.get(int(ei))
        if ep is None or (model.edge_subset is not None and int(ei) not in model.edge_subset):
            continue
        off = float((getattr(model, "face_offsets", {}) or {}).get(int(ei), (0.0, 0.0))[0])
        posts = [0.0]
        for sp in ep.spans:
            posts.append(posts[-1] + float(sp))
        k = next((i for i in range(len(ep.spans)) if abs(posts[i] - (float(a) - off)) < 2.0
                  and abs(posts[i + 1] - (float(b) - off)) < 2.0), None)
        if k is None:
            continue
        lv = list(model.elevation_of(int(ei)).level_heights)
        l0 = next((i + 1 for i, h in enumerate(lv) if float(h) >= float(z0) - 1.0), None)
        if l0 is None:
            continue
        out.append(MemberEdit(int(ei), k + 1, k + 1, l0, len(lv), ("内側手すり",), reason="上段への通り（セットバック）",
                              auto=True))
    return out


def edit_list(model: ScaffoldModel, ep, edits) -> str:
    """足場ラインへ渡す editList「スパン始,スパン終,層始,層終,ビット」の繰り返し（外すものだけ）."""
    out = []
    for e in edits or []:
        if e.edge_index == ep.edge_index and e.action == "外す":
            out += [e.span_from, e.span_to, e.level_from, e.level_to, e.code]
    return ",".join(str(v) for v in out)


def _span_x(ep) -> list[float]:
    xs, x = [], 0.0
    for s in ep.spans:
        xs.append(x)
        x += s
    return xs


def cell_blocked(model: ScaffoldModel, ep, span_i: int, level: int, openings=None) -> bool:
    """開口部（梁枠より下）の升目か（もともと部材が無い）。span_i は 0 始まり、level は 1 始まり."""
    if openings is None:
        return False
    ev = model.elevation_of(ep.edge_index)
    if not ev.level_heights:
        return False
    x = _span_x(ep)[span_i]
    sp = ep.spans[span_i]
    z = ev.level_heights[level - 1]
    for o in openings.openings:
        if o.edge_index != ep.edge_index:
            continue
        idx = min(max(o.level, 1), len(ev.level_heights)) - 1
        beam_h = ev.level_heights[idx]
        if x >= o.start_mm - 1e-6 and x + sp <= o.end_mm + 1e-6 and z < beam_h - 1e-6:
            return True
    return False


def in_inside_stair(model: ScaffoldModel, ep, span_i: int, stair_plan=None) -> bool:
    """足場の中の階段室の区間のスパンか（外付けは本体の床を切らないので対象外）."""
    if stair_plan is None or getattr(stair_plan, "outside", False):
        return False
    x = _span_x(ep)[span_i]
    sp = ep.spans[span_i]
    for t in getattr(stair_plan, "towers", []) or []:
        if t.edge_index == ep.edge_index and x >= t.start_mm - 1e-6 and x + sp <= t.start_mm + t.length_mm + 1e-6:
            return True
    return False


def cell_parts(model: ScaffoldModel, ep, span_i: int, level: int, part: str, rules=None) -> list:
    """1升目にある、その種類の部材 [(Part, 数)]（数量拾いと同じ規則）."""
    from .quantity import QuantityRules

    rules = rules or QuantityRules()
    m = model.master
    s = ep.spans[span_i]
    rows = 1 if model.config.scaffold_form == "一側足場" else rules.rows
    n_lv = model.elevation_of(ep.edge_index).n_levels
    out = []
    if part in ("踏板", "外側踏板", "内側踏板"):
        widths = list(model.config.deck_widths if m.is_frame else model.deck_widths_in_use)
        # 外側の踏板は1枚目（足場ラインの deckW1）、内側は2枚目（deckW2）
        if part == "外側踏板":
            widths = widths[:1]
        elif part == "内側踏板":
            widths = widths[1:2]
        for w in widths:
            out.append((m.deck_parts(w, s), 1))
    elif part == "幅木":
        if model.config.has_toe_board:
            out.append((m.find("幅木", s), 1))
    elif part == "外側手すり":
        if m.is_frame:
            # 枠組の中間層の手すりは1つ上の建枠が兼ねる。布材の手すり・中桟は最上層だけ
            if level == n_lv:
                out.append((m.find("布材", s), rules.rails_per_level_outer))
        elif model.config.guard_rail_type == GUARD_RAIL_ADVANCE:
            out.append((m.find("先行手摺", s), 1))
        else:
            out.append((m.find("布材", s), rules.rails_per_level_outer))
    elif part == "内側手すり":
        if not m.is_frame and model.config.inner_guard_rail and rows >= 2:
            out.append((m.find("布材", s), 2))
    elif part == "筋かい":
        if m.is_frame:
            out.append((next((p for p in m.by_category("筋交") if p.nominal_dim == s), None),
                        max(1, rules.frame_braces_per_bay)))
        else:
            brace = next(iter(m.by_category("筋交")), None)
            ev_s = max(1, rules.brace_every_spans)
            ev_l = max(1, rules.brace_every_levels)
            # 3D と同じ升目（ev_s スパン・ev_l 層ごと）で、規格スパンの構面だけ
            if brace is not None and span_i % ev_s == 0 and (level - 1) % ev_l == 0 and s == brace.nominal_dim:
                out.append((brace, rules.braces_per_location))
    return [(p, n) for p, n in out if p is not None and n > 0]


def _expand(parts) -> list[str]:
    """踏板（両方）→ 外側踏板・内側踏板（片側の指定と重なっても二重に引かない）."""
    out: list[str] = []
    for p in parts:
        for q in (("外側踏板", "内側踏板") if p == "踏板" else (p,)):
            if q not in out:
                out.append(q)
    return out


def edit_effects(model: ScaffoldModel, edits, rules=None, openings=None, stair_plan=None) -> list[EditEffect]:
    """編集ごとに、引く・足す数を求める（升目の重なりは後の編集を優先せず、同じ部材を二重に引かない）."""
    by_edge = {e.edge_index: e for e in model.plan.edges}
    done: set = set()       # (辺, スパン, 層, 種類) — 二重に引かない
    effects = []
    for ed in edits or []:
        ep = by_edge.get(ed.edge_index)
        if ep is None:
            continue          # 面の組で数えるとき、この組に無い面の編集
        n_lv = model.elevation_of(ep.edge_index).n_levels
        eff = EditEffect(ed)
        for si in range(ed.span_from - 1, min(ed.span_to, len(ep.spans))):
            for lv in range(ed.level_from, min(ed.level_to, n_lv) + 1):
                if cell_blocked(model, ep, si, lv, openings):
                    eff.skipped_cells += 1
                    continue
                for part in _expand(ed.parts):
                    if part in ("外側踏板", "内側踏板") and in_inside_stair(model, ep, si, stair_plan):
                        eff.skipped_cells += 1
                        continue
                    key = (ed.edge_index, si, lv, part)
                    if key in done:
                        continue
                    done.add(key)
                    for p, n in cell_parts(model, ep, si, lv, part, rules):
                        k = (p.model_no, p.category)
                        eff.removed[k] = eff.removed.get(k, 0) + n
                        if ed.action == "置換":
                            tp = model.master.get(ed.to)
                            tk = (tp.model_no, tp.category)
                            eff.added[tk] = eff.added.get(tk, 0) + n
        effects.append(eff)
    return effects


def apply_member_edits(result, model: ScaffoldModel, rules=None, openings=None, stair_plan=None):
    """数量の結果に編集を効かせる（行の数を引く・置換先の行を足す。重量・台数も直す）."""
    import math

    from .quantity import BomLine, QuantityRules

    edits = getattr(model, "member_edits", None) or []
    if not edits:
        return result
    rules = rules or QuantityRules()
    effects = edit_effects(model, edits, rules, openings, stair_plan)
    lines = {(l.part.model_no, l.part.category): l for l in result.lines}
    order = list(result.lines)
    names = {e.edge_index: n for e, n in zip(model.plan.edges, model.plan.face_names())}
    for eff in effects:
        ed = eff.edit
        short = 0
        for k, n in eff.removed.items():
            line = lines.get(k)
            have = line.qty if line else 0
            take = min(have, n)
            short += n - take
            if line:
                line.qty -= take
        for k, n in eff.added.items():
            line = lines.get(k)
            if line is None:
                line = BomLine(part=model.master.get(k[0]), qty=0, note="部材編集で置換")
                lines[k] = line
                order.append(line)
            line.qty += n
        where = (f"{names.get(ed.edge_index, f'辺{ed.edge_index}')} {ed.span_from}〜{ed.span_to}スパン目・"
                 f"{ed.level_from}〜{ed.level_to}層")
        what = "・".join(ed.parts)
        moved = "・".join(f"{k[0]} {n}" for k, n in eff.removed.items()) or "該当なし"
        if ed.action == "外す":
            msg = f"部材編集: {where}の{what}を外しました（{moved}）"
        else:
            msg = f"部材編集: {where}の{what}を {ed.to} に置き換えました（{moved}）"
        if ed.reason:
            msg += f"。理由: {ed.reason}"
        if eff.skipped_cells:
            msg += f"。開口部・足場の中の階段室の升目{eff.skipped_cells}は対象外"
        if short:
            msg += f"。数量表に無い分{short}本は引けませんでした"
        result.notes.append(msg)
        if ed.action == "外す" and not ed.auto and any(p in ("外側手すり", "内側手すり", "幅木") for p in ed.parts):
            msg2 = (f"{where}の手すり・幅木を外しています。作業床が残る升目は墜落の危険があるので、"
                    "立入禁止の措置か別の防護を確認してください")
            result.notes.append(msg2)
            result.warnings.append(msg2)
            result.warning_kinds[msg2] = "現場対応"
    result.lines = [l for l in order if l.qty > 0]
    result.total_weight_kg = round(sum(l.subtotal_weight for l in result.lines), 1)
    result.truck_count = (math.ceil(result.total_weight_kg / rules.truck_payload_kg)
                          if result.total_weight_kg else 0)
    return result


def drawn_deltas(model: ScaffoldModel, ep, edits, stair_plan=None, openings=None) -> dict[str, int]:
    """足場ラインの図示本数（qty*）から引く数。1d.gdl の editList の処理と同じ式（テストで突き合わせる）."""
    n_lv = model.elevation_of(ep.edge_index).n_levels
    adv = model.config.guard_rail_type == GUARD_RAIL_ADVANCE and not model.master.is_frame
    rows = 1 if model.config.scaffold_form == "一側足場" else 2
    inner = 2 if (model.config.inner_guard_rail and not model.master.is_frame and rows >= 2) else 0
    out = {"qtyDeck": 0, "qtyToe": 0, "qtyAdv": 0, "qtyNuno": 0}
    # 踏板が1枚敷き（deckW2 が無い）なら外側の踏板だけで升目の床が無くなる
    one_deck = len(model.config.deck_widths if model.master.is_frame else model.deck_widths_in_use) < 2
    seen: set = set()
    for ed in edits or []:
        if ed.edge_index != ep.edge_index or ed.action != "外す":
            continue
        for si in range(ed.span_from - 1, min(ed.span_to, len(ep.spans))):
            for lv in range(ed.level_from, min(ed.level_to, n_lv) + 1):
                if cell_blocked(model, ep, si, lv, openings):
                    continue
                for part in _expand(ed.parts):
                    key = (si, lv, part)
                    if key in seen:
                        continue
                    seen.add(key)
                    if part in ("外側踏板", "内側踏板"):
                        # 図示本数は升目で1（床がある升目）。外側・内側の両方を外した升目だけ引く（1d.gdl と同じ）
                        other = "内側踏板" if part == "外側踏板" else "外側踏板"
                        gone = (part == "外側踏板") if one_deck else (si, lv, other) in seen
                        if gone and not in_inside_stair(model, ep, si, stair_plan):
                            out["qtyDeck"] += 1
                    elif part == "幅木" and not adv:
                        out["qtyToe"] += 1
                    elif part == "外側手すり":
                        if adv:
                            out["qtyAdv"] += 1
                        elif not model.master.is_frame:
                            out["qtyNuno"] += 2
                    elif part == "内側手すり":
                        out["qtyNuno"] += inner
    return out


# ---- 足場条件の部品（設定ダイアログ）に書く1行の形 ----
# 「南面 2-3 2-3 踏板・幅木」「東面 1 全部 手すり→NDT09S」「北面 全部 4 筋かい #搬入路」。区切りは ; か改行。
# 並びは 面・スパン・層・部材（→置換先の品番）、# の後ろは理由。層を省くと全部の層。
def parse_edit_text(text: str) -> tuple[list[dict], list[str]]:
    items: list[dict] = []
    errors: list[str] = []
    raw = str(text or "").replace("；", ";").replace("\n", ";")
    for chunk in raw.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        reason = ""
        if "#" in chunk or "＃" in chunk:
            chunk, _, reason = chunk.replace("＃", "#").partition("#")
            chunk = chunk.strip()
        toks = chunk.replace("　", " ").split()
        if len(toks) < 3:
            errors.append(f"「{chunk}」: 面・スパン・（層）・部材 の順に空白で区切って書いてください（例 南面 2-3 2-3 踏板）")
            continue
        face, spans = toks[0], toks[1]
        if len(toks) >= 4:
            levels, part_tok = toks[2], toks[3]
        else:
            levels, part_tok = "全部", toks[2]
        to = ""
        for arrow in ("→", "->", "＞", ">"):
            if arrow in part_tok:
                part_tok, to = part_tok.split(arrow, 1)
                break
        parts = [p for p in part_tok.replace("、", "・").replace(",", "・").split("・") if p]
        item = ({"edge_index": int(face[1:])} if face.startswith("辺") and face[1:].isdigit()
                else {"face": face})
        item.update({"spans": spans, "levels": levels, "parts": parts})
        if to:
            item["action"] = "置換"
            item["to"] = to.strip()
        if reason.strip():
            item["reason"] = reason.strip()
        items.append(item)
    return items, errors


def format_edit_items(items) -> list[str]:
    """member_edits（入力 JSON）→ 部品に書く1行ずつ（parse_edit_text の逆）."""
    out = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        face = it.get("face") if it.get("face") is not None else f"辺{it.get('edge_index')}"

        def rng(v):
            if v is None:
                return "全部"
            if isinstance(v, (list, tuple)):
                return f"{v[0]}-{v[-1]}" if len(v) > 1 else str(v[0])
            return str(v)

        parts = it.get("parts", it.get("part"))
        parts = [parts] if isinstance(parts, str) else list(parts or [])
        s = f"{face} {rng(it.get('spans'))} {rng(it.get('levels'))} {'・'.join(str(p) for p in parts)}"
        if ACTIONS.get(str(it.get("action", "外す"))) == "置換" and it.get("to"):
            s += f"→{it['to']}"
        if it.get("reason"):
            s += f" #{it['reason']}"
        out.append(s)
    return out
