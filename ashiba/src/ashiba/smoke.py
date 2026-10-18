"""実機スモーク（scripts/smoke_archicad.py）の中身のうち、Archicad に触らない部分.

検証する入力の一覧、置き場所（利用者のモデルから離れた所に1件ずつ）、照合（置いた本数・
部品が書き戻す図示本数・断面とレイアウト・CLI と同じ判定か）を純粋関数で持つ。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# 利用者のモデル（原点付近〜数百m）から離して置く。1件ごとに x を 100m ずらす
ORIGIN_MM = (2_000_000.0, 2_000_000.0)
PITCH_MM = 100_000.0
PREFIX = "スモーク"
RECT_30x20 = [[0, 0], [30000, 0], [30000, 20000], [0, 20000]]


@dataclass
class Case:
    name: str
    spec: dict


@dataclass
class Check:
    case: str
    item: str
    ok: bool
    detail: str = ""


@dataclass
class CaseReport:
    case: str
    checks: list[Check] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and all(c.ok for c in self.checks)

    def add(self, item: str, ok: bool, detail: str = "") -> None:
        self.checks.append(Check(self.case, item, bool(ok), detail))


def cases(examples_dir: Path) -> list[Case]:
    """小型入力（examples/dev/*.json）＋ 30×20m のメートル・インチ."""
    out = []
    for p in sorted(Path(examples_dir).glob("*.json")):
        out.append(Case(p.stem, json.loads(p.read_text(encoding="utf-8"))))
    base = {"outline_mm": RECT_30x20, "eaves_height_mm": 15400, "building_height_mm": 16000}
    out.append(Case("rect_metric", dict(base, module="metric")))
    out.append(Case("rect_inch", dict(base, module="inch")))
    return out


def select(all_cases: list[Case], only: list[str]) -> list[Case]:
    if not only:
        return all_cases
    hit = [c for c in all_cases if c.name in only]
    unknown = sorted(set(only) - {c.name for c in hit})
    if unknown:
        raise SystemExit(f"知らない入力: {', '.join(unknown)}（{', '.join(c.name for c in all_cases)}）")
    return hit


def placed_spec(case: Case, index: int) -> tuple[dict, list[list[float]]]:
    """その件を置く入力（工事名に接頭辞、外形を置き場所へ平行移動）と外形."""
    dx = ORIGIN_MM[0] + PITCH_MM * index
    dy = ORIGIN_MM[1]
    outline = [[float(x) + dx, float(y) + dy] for x, y in case.spec["outline_mm"]]
    spec = dict(case.spec)
    spec["outline_mm"] = outline
    spec["project_name"] = f"{PREFIX} {case.name}"
    # 敷地の点は外形と同じだけ動かす（入力にあれば）
    if spec.get("ground_points_mm"):
        spec["ground_points_mm"] = [[p[0] + dx, p[1] + dy, *p[2:]] for p in spec["ground_points_mm"]]
    return spec, outline


def count_mismatches(expected: dict[str, int], got: dict) -> list[str]:
    """部品が書き戻した図示本数（qty*）と Python の式の食い違い。部品側に無い名前は飛ばす."""
    bad = []
    for k, v in expected.items():
        if k not in got:
            continue
        try:
            g = int(round(float(got[k])))
        except (TypeError, ValueError):
            bad.append(f"{k}=?")
            continue
        if g != int(v):
            bad.append(f"{k} 部品{g}≠式{int(v)}")
    return bad


def all_zero(got: dict, names) -> bool:
    """図示本数がすべて 0（1D スクリプトが途中で止まり、書き戻しが走っていない）."""
    vals = [got.get(k) for k in names if k in got]
    return bool(vals) and all(not v for v in vals)


def summary_lines(reports: list[CaseReport], verbose: bool = False) -> list[str]:
    out = []
    for r in reports:
        mark = "OK " if r.ok else "NG "
        out.append(f"{mark}{r.case}")
        if r.error:
            out.append(f"    エラー: {r.error}")
        for c in r.checks:
            if not c.ok:
                out.append(f"    × {c.item}: {c.detail}")
            elif verbose:
                out.append(f"    ○ {c.item}" + (f": {c.detail}" if c.detail else ""))
    n_ng = sum(1 for r in reports if not r.ok)
    out.append(f"{len(reports)}件中 {len(reports) - n_ng}件 OK" + (f"・{n_ng}件 NG" if n_ng else ""))
    return out
