"""付帯設備どうし・開口部との衝突検査.

開口部（梁枠より下は支柱を抜いた通路で、床も無い）と同じ区間に階段室・
荷受けステージ・ブラケット区間・昇降機が来ると、それぞれの検証は通っても
実際には組めない。各モジュールは自分の入力しか見ないので、ここで突き合わせる。
ステージの張出ブラケットとブラケット区間が同じ区間に重なる二重張出しも同様。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .model import ScaffoldModel


@dataclass
class ConflictIssue:
    kind: str        # "階段室×開口部" など
    severity: str    # "NG" / "WARN"
    message: str
    basis: str


def _overlap(a0: float, a1: float, b0: float, b1: float) -> bool:
    return min(a1, b1) - max(a0, b0) > 1e-6


def _rng(start: float, end: float) -> str:
    return f"{start:.0f}〜{end:.0f}mm"


def _asagao_conflicts(model: ScaffoldModel, hoists, stages) -> list[ConflictIssue]:
    import math

    from .model import ASAGAO_KIND_SAFE_WING

    a = model.config.asagao
    heights = model.asagao_heights()
    out: list[ConflictIssue] = []
    if a is None or not heights or not (hoists or stages):
        return out
    label = "セーフウイング" if a.kind == ASAGAO_KIND_SAFE_WING else "朝顔"
    rise = a.projection_mm * math.tan(math.radians(a.angle_deg))   # 先端の上がり
    lv = model.elevation.level_heights
    pitch = (lv[1] - lv[0]) if len(lv) >= 2 else 1800.0
    hs = "・".join(f"{h:.0f}" for h in heights)
    basis = "安衛則563条・537条（落下物防護）"

    from .platforms import hoist_cut_ranges

    for i, h in enumerate(hoists):
        cut = hoist_cut_ranges(model, h.edge_index, [h])
        rng = "・".join(_rng(s0, s1) for s0, s1 in cut) or f"{h.position_mm:.0f}mm付近"
        out.append(ConflictIssue(
            f"昇降機×{label}", "WARN",
            f"{model.face_name(h.edge_index)}の昇降機{i + 1}（始点から{h.position_mm:.0f}mm）のマスト・搬器は"
            f"{label}{len(heights)}段（高さ{hs}mm）を貫きます。該当スパン（{rng}）の{label}は"
            f"切り欠き、その開口は昇降機メーカー仕様の防護で塞いでください"
            f"（{label}の数量は切り欠き前の全スパンで計上しています）",
            basis,
        ))
    for i, st in enumerate(stages):
        for level in (st.levels or [1]):
            if not (1 <= level <= len(lv)):
                continue
            z = lv[level - 1]
            # ステージは床の下に張出ブラケット・方杖（ほぼ1層分）、上に手すり
            hit = [h for h in heights if _overlap(h, h + rise, z - pitch, z + 900)]
            if not hit:
                continue
            out.append(ConflictIssue(
                f"ステージ×{label}", "WARN",
                f"{model.face_name(st.edge_index)}の荷受けステージ{i + 1}（第{level}層・高さ{z:.0f}mm）が"
                f"{label}（高さ{'・'.join(f'{x:.0f}' for x in hit)}mm、先端の上がり{rise:.0f}mm）と"
                f"同じ高さ帯にあり、張出しが重なります。ステージの層を変えるか、"
                f"{label}の設置高さ（asagao.heights_mm）をずらしてください",
                basis,
            ))
    return out


def check_conflicts(
    model: ScaffoldModel,
    openings=None,
    stair_plan=None,
    platforms=None,
    brackets: Optional[list] = None,
) -> list[ConflictIssue]:
    """同じ辺・同じ区間に来た付帯設備と開口部の衝突を挙げる."""
    out: list[ConflictIssue] = []
    vm = model.master.vertical_member_name
    n_levels = model.elevation.n_levels
    ops = list(openings.openings) if openings is not None else []
    towers = list(stair_plan.towers) if stair_plan is not None else []
    stages = list(platforms.stages) if platforms is not None else []
    hoists = list(platforms.hoists) if platforms is not None else []
    sections = list(brackets or [])

    for o in ops:
        o_rng = _rng(o.start_mm, o.end_mm)
        # 階段室: 梁枠より下は床も支柱も無く、段板を組めない
        for t in towers:
            if t.edge_index == o.edge_index and _overlap(
                t.start_mm, t.end_mm, o.start_mm, o.end_mm
            ):
                out.append(ConflictIssue(
                    "階段室×開口部", "NG",
                    f"{model.face_name(o.edge_index)}の階段室（{_rng(t.start_mm, t.end_mm)}）が"
                    f"開口部（{o_rng}）と重なっています。梁枠より下は{vm}を抜いた"
                    "通路で床が無く、階段室を組めません。階段位置か開口部をずらしてください",
                    "安衛則526条・563条（昇降設備・作業床）",
                ))
        # 荷受けステージ: 梁枠上は積載低減の区間で、集中荷重は受けられない
        for i, st in enumerate(stages):
            if st.edge_index == o.edge_index and _overlap(
                st.start_mm, st.end_mm(model), o.start_mm, o.end_mm
            ):
                out.append(ConflictIssue(
                    "ステージ×開口部", "NG",
                    f"{model.face_name(o.edge_index)}の荷受けステージ{i + 1}"
                    f"（{_rng(st.start_mm, st.end_mm(model))}）が開口部（{o_rng}）の"
                    "区間にあります。梁枠上は積載荷重を低減する区間で、荷受けステージの"
                    "集中荷重は受けられません。ステージを開口部の外に移してください",
                    "安衛則562条（最大積載荷重）・仮設工業会 梁枠使用基準",
                ))
        # ブラケット区間: 梁枠より下の層は取り付ける支柱が無い。梁枠上は偏心確認
        for i, b in enumerate(sections):
            if b.edge_index != o.edge_index or not _overlap(
                b.start_mm, b.end_mm, o.start_mm, o.end_mm
            ):
                continue
            levels = list(b.levels) if b.levels else list(range(1, n_levels + 1))
            below = [lv for lv in levels if lv < o.level]
            if below:
                out.append(ConflictIssue(
                    "ブラケット区間×開口部", "NG",
                    f"{model.face_name(o.edge_index)}のブラケット区間{i + 1}"
                    f"（{_rng(b.start_mm, b.end_mm)}・第{'・'.join(map(str, below))}層）が"
                    f"開口部（{o_rng}）の梁枠より下にかかっています。その層は{vm}を"
                    "抜いているので、ブラケットを取り付けられません。区間か層を見直してください",
                    "安衛則570条（足場の構造）",
                ))
            else:
                out.append(ConflictIssue(
                    "ブラケット区間×開口部", "WARN",
                    f"{model.face_name(o.edge_index)}のブラケット区間{i + 1}"
                    f"（{_rng(b.start_mm, b.end_mm)}）が開口部（{o_rng}）の梁枠上に"
                    "かかっています。梁枠上の積載を低減し、ブラケットの偏心荷重を"
                    f"梁枠両端の{vm}で確認してください",
                    "仮設工業会 梁枠使用基準",
                ))
        # 昇降機: マスト控えを取る支柱が梁枠より下に無い
        for i, h in enumerate(hoists):
            if h.edge_index == o.edge_index and (
                o.start_mm - 1e-6 <= h.position_mm <= o.end_mm + 1e-6
            ):
                on_beam = [lv for lv in h.landings(model) if lv >= o.level]
                out.append(ConflictIssue(
                    "昇降機×開口部", "WARN",
                    f"{model.face_name(o.edge_index)}の昇降機{i + 1}（始点から{h.position_mm:.0f}mm）が"
                    f"開口部（{o_rng}）の区間にあります。梁枠より下には控えを取る{vm}が"
                    f"無いので、マスト控えは梁枠両端の{vm}か躯体に取ってください"
                    + (f"。乗り込み口 第{'・'.join(map(str, on_beam))}層は梁枠上なので"
                       "積載を低減してください" if on_beam else ""),
                    "安衛則570条（壁つなぎ）・仮設工業会 梁枠使用基準",
                ))

    # 階段室 × 昇降機・荷受けステージ。階段室のスパンは段板と開口・床で埋まるので、
    # 同じスパンに乗り込み口（搬器から渡る床）やステージの間口は取れない。
    # 実機の小型面で自動配置の階段室と昇降機が同じスパンに描かれていた
    from .platforms import hoist_cut_ranges
    for t in towers:
        for i, h in enumerate(hoists):
            if h.edge_index != t.edge_index:
                continue
            for s0, e0 in hoist_cut_ranges(model, h.edge_index, [h]):
                if _overlap(t.start_mm, t.end_mm, s0, e0):
                    out.append(ConflictIssue(
                        "階段室×昇降機", "NG",
                        f"{model.face_name(t.edge_index)}の階段室（{_rng(t.start_mm, t.end_mm)}）と"
                        f"昇降機{i + 1}の搬器が掛かるスパン（{_rng(s0, e0)}）が重なっています。"
                        "階段室のスパンは段板と開口・床で埋まり、乗り込み口の床が取れません。"
                        "階段位置か昇降機の位置をずらしてください",
                        "安衛則526条・563条（昇降設備・作業床）",
                    ))
                    break
        for i, st in enumerate(stages):
            if st.edge_index == t.edge_index and _overlap(
                t.start_mm, t.end_mm, st.start_mm, st.end_mm(model)
            ):
                out.append(ConflictIssue(
                    "階段室×ステージ", "NG",
                    f"{model.face_name(t.edge_index)}の階段室（{_rng(t.start_mm, t.end_mm)}）と"
                    f"荷受けステージ{i + 1}（{_rng(st.start_mm, st.end_mm(model))}）が重なっています。"
                    "ステージの間口は荷を通すため外側の手すりを外す区間で、階段室の"
                    "段板・開口と両立しません。区間を分けてください",
                    "安衛則563条（作業床）・仮設工業会 張出しブラケット使用基準",
                ))

    # 朝顔（セーフウイング）× 昇降機・荷受けステージ。朝顔は面の全長に渡って外へ2m出る
    # 板なので、マストや搬器が通る位置は切り欠くしかない。ステージが朝顔と同じ高さ帯に
    # あると張出しが二重になる。3Dでは互いを貫いて描かれるだけで、検証は素通りしていた
    out += _asagao_conflicts(model, hoists, stages)

    # ステージの張出ブラケット × ブラケット区間（同じ区間の二重張出し）
    for i, st in enumerate(stages):
        st_levels = set(st.levels) if st.levels else {1}
        for j, b in enumerate(sections):
            if b.edge_index != st.edge_index or not _overlap(
                st.start_mm, st.end_mm(model), b.start_mm, b.end_mm
            ):
                continue
            b_levels = set(b.levels) if b.levels else set(range(1, n_levels + 1))
            hit = sorted(st_levels & b_levels)
            if not hit:
                continue
            out.append(ConflictIssue(
                "ステージ×ブラケット区間", "NG",
                f"{model.face_name(st.edge_index)}の荷受けステージ{i + 1}"
                f"（{_rng(st.start_mm, st.end_mm(model))}）とブラケット区間{j + 1}"
                f"（{_rng(b.start_mm, b.end_mm)}）が第{'・'.join(map(str, hit))}層で"
                "重なっています。ステージは専用の張出ブラケットで組むので、同じ区間に"
                "ブラケット区間を重ねると張出しが二重になります。区間か層を分けてください",
                "仮設工業会 張出しブラケット使用基準",
            ))
    return out
