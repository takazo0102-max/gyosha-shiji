"""足場の断面・レイアウトの残骸を工事名ごとに数える（途中で止まった実行・スモークの後始末用）.

ツールバーは断面を「<工事名> <面> 足場立面」、レイアウトを「<工事名> 足場立面図／足場平面図／足場詳細図」
（面ごとなら「<工事名> 足場立面図 <面>」）で作る。名前から工事名を取り出して数え、足場条件の部品が
置かれていない工事名（＝今は使っていない）を残骸の候補として示す。
"""

from __future__ import annotations

from dataclasses import dataclass, field

SECTION_SUFFIX = " 足場立面"
LAYOUT_KINDS = (" 足場立面図", " 足場平面図", " 足場詳細図")


def prefix_of_layout(name: str) -> str | None:
    for k in LAYOUT_KINDS:
        i = name.find(k)
        if i > 0:
            return name[:i]
    return None


def prefix_of_section(name: str) -> str | None:
    if not name.endswith(SECTION_SUFFIX):
        return None
    head = name[: -len(SECTION_SUFFIX)]
    if " " not in head:
        return None
    return head.rsplit(" ", 1)[0]            # 最後の語が面名（南面・東面(辺0) など）


@dataclass
class PrefixUse:
    prefix: str
    sections: list[str] = field(default_factory=list)
    layouts: list[str] = field(default_factory=list)
    in_use: bool = False


def group(section_names, layout_names, active_prefixes) -> list[PrefixUse]:
    """工事名ごとの断面・レイアウト。active_prefixes（足場条件の部品の工事名など）は使用中."""
    out: dict[str, PrefixUse] = {}
    for n in section_names:
        p = prefix_of_section(n)
        if p:
            out.setdefault(p, PrefixUse(p)).sections.append(n)
    for n in layout_names:
        p = prefix_of_layout(n)
        if p:
            out.setdefault(p, PrefixUse(p)).layouts.append(n)
    act = set(active_prefixes)
    for u in out.values():
        u.in_use = u.prefix in act
    return sorted(out.values(), key=lambda u: (u.in_use is False, u.prefix))


def lines(uses: list[PrefixUse]) -> list[str]:
    if not uses:
        return ["足場の断面・レイアウトはありません"]
    out = []
    for u in uses:
        mark = "使用中" if u.in_use else "残骸の候補"
        out.append(f"{mark}: 「{u.prefix}」 断面{len(u.sections)}・レイアウト{len(u.layouts)}")
    if any(not u.in_use for u in uses):
        out.append("残骸の候補は python3 scripts/leftover_report.py --remove \"<工事名>\" で消せます"
                   "（レイアウトと、控えに GUID のある断面。控えの無い断面はプロジェクトマップで手で消す）")
    return out
