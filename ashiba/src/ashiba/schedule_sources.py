"""工程表の数量を ashiba_out の帳票から拾う（schedule.py が日数にする）.

帳票（各 *_run.py が書く Markdown）の表から読む。無い帳票の作業は工程表に出さない（条件で数量を入れれば出す）:
- 仮囲い.md: 安全鋼板などの「延べ ○m」の合計 → 仮囲いの延長 m
- 仮設建物.md: 建物の「連棟×段」→ ユニットの数（仮設トイレは別に数える）
- 敷鉄板.md・場内通路.md: 厚板鋼板の枚数
- 根切り*.md: 根切り・埋戻し・建設発生土 m³（いちばん新しい帳票）
- 構台.md: 覆工板の枚数（1×2m）→ 面積 m²、鋼材の重さ t
- *_plan.json: 足場の面ごとの長さ × 足場の高さ → 掛け面積 m²、層の数。工事名の <工事名>_plan.json、無ければ試験の計画
  （検証_・実機 で始まるもの）を除いたいちばん新しい配置（試験の建物の小さな計画を拾っていた 2026-11-04）
- 山留め足場.md: 腹起し上の足場の長さの合計 → 山留めの延長 m（腹起しは山留めの壁に沿う）
- 型枠_計画.json: 壁・柱・梁・スラブの数（型枠の面積は型枠_材料.csv の合板の枚数 × 1.62m²【目安】）
- タワークレーン.md・クレーン.md: 機種
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Quantities:
    hoarding_m: float = 0.0                 # 仮囲いの延長
    gates: int = 0
    house_units: int = 0                    # 仮設建物のユニット
    toilet_units: int = 0
    plates: int = 0                         # 敷鉄板（枚）
    guards: int = 0                         # 交通誘導員（ゲート。場内通路.md）
    excavation_m3: float = 0.0
    backfill_m3: float = 0.0
    soil_out_m3: float = 0.0
    retaining: bool = False                 # 山留めあり
    retaining_m: float = 0.0                # 山留めの延長（腹起し上の足場の長さ）
    deck_m2: float = 0.0                    # 構台の面積
    deck_t: float = 0.0
    scaffold_m2: float = 0.0                # 外部足場の掛け面積
    scaffold_h: float = 0.0                 # 足場の高さ m
    scaffold_tiers: int = 0
    scaffold_edges: int = 0                 # 足場の計画の面の数
    scaffold_len: float = 0.0               # 足場の計画の延べの長さ m
    form_m2: float = 0.0                    # 型枠の面積
    tower: str = ""                         # タワークレーンの機種
    cranes: list = field(default_factory=list)
    utility: bool = False                   # 仮設電気・給排水
    sources: dict = field(default_factory=dict)   # 数量 → 拾った帳票


_ROW = re.compile(r"^\|(.+)\|\s*$")


def md_rows(text: str) -> list[list[str]]:
    """Markdown の表の行（見出しの下の区切りの行は除く）."""
    out = []
    for line in text.splitlines():
        m = _ROW.match(line.strip())
        if not m:
            continue
        cells = [c.strip() for c in m.group(1).split("|")]
        if all(set(c) <= set("-: ") for c in cells):
            continue
        out.append(cells)
    return out


def _num(s: str) -> float:
    m = re.search(r"-?\d[\d,]*\.?\d*", s or "")
    return float(m.group(0).replace(",", "")) if m else 0.0


def _read(p: Path) -> str:
    """帳票を読む. 同じ名前の控え（.json）があって空なら、置いたものは消してあるので読まない（--remove は帳票を残す。
    消したタワークレーン・クレーンが工程表に出ていた 2026-11-04）."""
    rec = p.with_suffix(".json")
    if p.suffix == ".md" and rec.exists():
        try:
            if not json.loads(rec.read_text(encoding="utf-8")):
                return ""
        except (OSError, ValueError):
            pass
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return ""


TEST_PREFIXES = ("検証_", "実機 ", "実機_")         # 試験の建物の帳票（dev_cases.py・実機の試験）


def _latest(out: Path, pattern: str, skip: tuple = ()) -> Path | None:
    xs = sorted((p for p in out.glob(pattern) if not p.name.startswith(skip)), key=lambda p: p.stat().st_mtime, reverse=True)
    return xs[0] if xs else None


def plan_file(out: Path, name: str = "") -> Path | None:
    """足場の配置の計画: 工事名の <工事名>_plan.json、無ければ試験の計画を除いたいちばん新しいもの."""
    if name and (Path(out) / f"{name}_plan.json").exists():
        return Path(out) / f"{name}_plan.json"
    return _latest(Path(out), "*_plan.json", TEST_PREFIXES)


def collect(out: Path, name: str = "") -> Quantities:
    q = Quantities()
    out = Path(out)
    # 仮囲い
    t = _read(out / "仮囲い.md")
    for r in md_rows(t):
        if len(r) >= 3 and "延べ" in r[2]:
            m = re.search(r"延べ\s*([\d.]+)\s*m", r[2])
            if m:
                q.hoarding_m += float(m.group(1))
        if len(r) >= 2 and "ゲート" in r[0] and r[1].strip().isdigit():
            q.gates += int(r[1])
    if q.hoarding_m:
        q.sources["仮囲い"] = "仮囲い.md"
    # 仮設建物
    t = _read(out / "仮設建物.md")
    for r in md_rows(t):
        if len(r) >= 3 and re.fullmatch(r"\d+×\d+", r[2]):
            a, b = (int(x) for x in r[2].split("×"))
            if "トイレ" in r[1] or "トイレ" in r[0]:
                q.toilet_units += a * b
            else:
                q.house_units += a * b
    if q.house_units or q.toilet_units:
        q.sources["仮設建物"] = "仮設建物.md"
    # 敷鉄板（敷鉄板・場内通路）
    for name in ("敷鉄板.md", "場内通路.md"):
        for r in md_rows(_read(out / name)):
            if len(r) >= 2 and r[0].startswith("交通誘導員") and name == "場内通路.md":
                q.guards = max(q.guards, int(_num(r[1])))
            if len(r) >= 2 and r[0].startswith("厚板鋼板"):
                q.plates += int(_num(r[1]))
                q.sources["敷鉄板"] = q.sources.get("敷鉄板", "") + ("・" if q.sources.get("敷鉄板") else "") + name
    # 根切り
    p = _latest(out, "根切り*.md")
    if p:
        t = _read(p)
        for r in md_rows(t):
            if len(r) >= 2 and "m³" in r[1]:
                if r[0] == "根切り":
                    q.excavation_m3 = _num(r[1])
                elif r[0] == "埋戻し":
                    q.backfill_m3 = _num(r[1])
                elif r[0].startswith("建設発生土"):
                    q.soil_out_m3 = _num(r[1])
        q.retaining = "山留めあり" in t
        if q.excavation_m3:
            q.sources["根切り"] = p.name
    # 山留めの延長（腹起し上の足場は山留めの壁に沿って1辺に1つ）
    for m in re.finditer(r"^## 腹起し上の足場 .*?（長さ (\d+)mm）", _read(out / "山留め足場.md"), re.M):
        q.retaining_m += int(m.group(1)) / 1000.0
    if q.retaining_m:
        q.retaining = True
        q.sources["山留め"] = "山留め足場.md"
    # 構台
    t = _read(out / "構台.md")
    for r in md_rows(t):
        if len(r) >= 2 and r[0].startswith("覆工板"):
            m = re.search(r"(\d+(?:\.\d+)?)×(\d+(?:\.\d+)?)m", r[0])
            a = float(m.group(1)) * float(m.group(2)) if m else 2.0
            q.deck_m2 += a * _num(r[1])
        if len(r) >= 4 and r[3].endswith("kg"):
            q.deck_t += _num(r[3]) / 1000.0
    if q.deck_m2:
        q.sources["構台"] = "構台.md"
    # 外部足場（工事名の配置、無ければ試験の計画を除いたいちばん新しい配置）
    p = plan_file(out, name)
    if p:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            h = float(d.get("scaffold_height_mm") or 0) / 1000.0
            ln = sum(float(e.get("scaffold_length") or 0) for e in d.get("edges", [])) / 1000.0
            q.scaffold_h = h
            q.scaffold_m2 = round(ln * h, 1)
            q.scaffold_edges = len(d.get("edges", []))
            q.scaffold_len = round(ln, 1)
            q.scaffold_tiers = len((d.get("elevation") or {}).get("level_heights") or [])
            if q.scaffold_m2:
                q.sources["外部足場"] = p.name
        except (OSError, ValueError, TypeError):
            pass
    # 型枠（合板の枚数）
    p = out / "型枠_材料.csv"
    if p.exists():
        try:
            with p.open(encoding="utf-8-sig") as f:
                for row in csv.reader(f):
                    if row and any("合板" in c or "せき板" in c for c in row[:2]):
                        n = next((_num(c) for c in row[2:] if _num(c) > 0), 0.0)
                        q.form_m2 += n * 1.62          # 900×1800 の合板1枚【目安】
            if q.form_m2:
                q.sources["型枠"] = p.name
        except OSError:
            pass
    # 揚重
    for r in md_rows(_read(out / "タワークレーン.md")):
        if len(r) >= 2 and r[0] not in ("名前",) and "クレーン" in r[1] and not q.tower:
            q.tower = r[1]
    for r in md_rows(_read(out / "クレーン.md")):
        if len(r) >= 2 and "クレーン" in r[0] and r[1].strip().isdigit():
            q.cranes.append(r[0])
    q.utility = bool(_read(out / "仮設電気給排水.md"))
    return q
