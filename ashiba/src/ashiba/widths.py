"""足場の幅を始めに選ぶ（利用者の指定 2026-10-22: 足場の幅が始めに選べるようにして、インチとセンチで）.

「配置」の始めに、幅がまだ決まっていない建物（足場条件の部品の「幅」が0・入力に scaffold_width_mm が無い）なら
幅の一覧を出す。センチ（メートル系: 60・90・120cm）とインチ（インチ系: 2・3・4フィート＝24・36・48インチ）の
両方を並べ、選んだ幅の系（モジュール）に合わせる。系が変わるなら系列もその系の既定にする（信和A／日建ND1800）。
選んだ幅は足場条件の部品（無ければ条件ファイル）に書くので、次からは聞かない。
枠組（建枠の幅で決まる）・単管抱き足場・単管のブラケット足場（足場板1列）は幅を選ばない。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class WidthChoice:
    label: str
    module: str        # "metric" / "inch"
    width_mm: int


WIDTH_CHOICES: tuple[WidthChoice, ...] = (
    WidthChoice("60cm（600mm）", "metric", 600),
    WidthChoice("90cm（900mm）", "metric", 900),
    WidthChoice("120cm（1200mm）", "metric", 1200),
    WidthChoice("2フィート＝24インチ（610mm）", "inch", 610),
    WidthChoice("3フィート＝36インチ（914mm）", "inch", 914),
    WidthChoice("4フィート＝48インチ（1219mm）", "inch", 1219),
)


def find_choice(text) -> Optional[WidthChoice]:
    """一覧の見出し、または幅の mm（"914"）・cm（"90cm"）・インチ（"36in" "36インチ"）・フィート（"3ft"）."""
    t = str(text or "").strip().replace(" ", "").lower()
    if not t:
        return None
    for c in WIDTH_CHOICES:
        if t == c.label.lower():
            return c
    import re

    m = re.fullmatch(r"([\d.]+)(mm|cm|in|インチ|ft|フィート)?", t)
    if not m:
        return None
    v, unit = float(m.group(1)), m.group(2) or "mm"
    mm = {"mm": v, "cm": v * 10, "in": v * 25.4, "インチ": v * 25.4, "ft": v * 304.8, "フィート": v * 304.8}[unit]
    return min(WIDTH_CHOICES, key=lambda c: abs(c.width_mm - mm)) if mm > 0 else None


def needs_width_choice(spec: dict) -> bool:
    """幅を聞く建物か（幅がまだ無く、幅で建地列の間隔が決まる形式）."""
    if spec.get("scaffold_width_mm") or spec.get("deck_widths"):
        return False
    form = str(spec.get("scaffold_form") or "本足場")
    if form in ("抱き足場", "単管抱き足場"):
        return False
    if form == "ブラケット足場" and str(spec.get("bracket_post") or "支柱") == "単管":
        return False
    return str(spec.get("series_id") or "") != "waku"


def ordered_choices(spec: dict) -> list[WidthChoice]:
    """いまの系（モジュール）の幅を先に並べる."""
    cur = _module_of(spec)
    return [c for c in WIDTH_CHOICES if c.module == cur] + [c for c in WIDTH_CHOICES if c.module != cur]


def _module_of(spec: dict) -> str:
    from .master import normalize_module, series_module

    sid = str(spec.get("series_id") or "")
    if sid:
        try:
            return series_module(sid)
        except Exception:
            pass
    try:
        return normalize_module(spec.get("module") or "metric")
    except Exception:
        return "metric"


def apply_width_choice(spec: dict, choice: WidthChoice) -> tuple[dict, list[str]]:
    """選んだ幅を入力に入れる → (新しい入力, 変えた項目の説明). 系が変われば module を替え、合わない系列は外す."""
    from .master import series_module

    out = dict(spec)
    notes = [f"足場の幅 {choice.label}"]
    out["scaffold_width_mm"] = int(choice.width_mm)
    if _module_of(spec) != choice.module:
        out["module"] = choice.module
        sid = str(spec.get("series_id") or "")
        if sid and sid != "tankan":
            try:
                if series_module(sid) != choice.module:
                    out.pop("series_id", None)
                    notes.append(f"系列 {sid} は{'メートル' if choice.module == 'inch' else 'インチ'}系なので、"
                                 f"{'インチ' if choice.module == 'inch' else 'メートル'}系の既定の系列にします")
            except Exception:
                out.pop("series_id", None)
        notes.append(f"モジュール {'インチ' if choice.module == 'inch' else 'メートル'}")
    return out, notes
