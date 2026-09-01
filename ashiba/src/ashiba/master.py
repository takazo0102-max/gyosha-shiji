"""部材マスタ（part_master.csv）の読み込みと系列ロック.

- 呼び寸法(nominal)と実寸法(actual)を厳密に分ける。割付計算は呼び寸法、描画は実寸法。
- 系列(series_id)混在は絶対禁止。SeriesLockError で即座にブロックする。
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

DEFAULT_MASTER_PATH = Path(__file__).resolve().parents[2] / "data" / "part_master.csv"

# 系列ごとのコマピッチ・階高 [mm]
SERIES_CONST = {
    "shinwa_A": {"koma_pitch": 450, "floor_height": 1800, "hozo": 125},
    "shinwa_B": {"koma_pitch": 475, "floor_height": 1900, "hozo": 125},
    "inch": {"koma_pitch": 0, "floor_height": 1700, "hozo": 0},
}


class SeriesLockError(Exception):
    """系列ロック違反（規格混在）"""


@dataclass(frozen=True)
class Part:
    series_id: str
    category: str
    model_no: str
    nominal_dim: int  # 呼び寸法 [mm] 割付計算に使う
    actual_dim: int   # 実寸法 [mm] 描画・干渉に使う
    diameter: float   # [mm] 0なら管材でない
    weight_kg: float
    note: str = ""


@dataclass
class PartMaster:
    """1プロジェクト＝1系列にロックされた部材マスタ."""

    series_id: str
    parts: list[Part] = field(default_factory=list)

    @property
    def koma_pitch(self) -> int:
        return SERIES_CONST[self.series_id]["koma_pitch"]

    @property
    def floor_height(self) -> int:
        return SERIES_CONST[self.series_id]["floor_height"]

    @property
    def hozo(self) -> int:
        return SERIES_CONST[self.series_id]["hozo"]

    def by_category(self, category: str) -> list[Part]:
        return [p for p in self.parts if p.category == category]

    def post_lengths(self, include_negarami: bool = False) -> list[int]:
        """支柱の呼び寸法一覧（降順）。根がらみ用は既定で除外."""
        out = []
        for p in self.by_category("支柱"):
            if not include_negarami and "根がらみ" in p.note:
                continue
            if "屋根足場" in p.note:
                continue
            out.append(p.nominal_dim)
        return sorted(set(out), reverse=True)

    def negarami_post_lengths(self) -> list[int]:
        return sorted(
            {p.nominal_dim for p in self.by_category("支柱") if "根がらみ" in p.note},
            reverse=True,
        )

    def span_lengths(self, min_span: int = 600) -> list[int]:
        """スパン割に使える布材呼び寸法（降順）。端数は真物のみで構成し切断調整は存在しない."""
        return sorted(
            {p.nominal_dim for p in self.by_category("布材") if p.nominal_dim >= min_span},
            reverse=True,
        )

    def find(self, category: str, nominal_dim: int, note_contains: str = "") -> Optional[Part]:
        for p in self.by_category(category):
            if p.nominal_dim == nominal_dim and note_contains in p.note:
                return p
        return None

    def deck_parts(self, width: int, nominal_dim: int) -> Optional[Part]:
        """指定幅・長さの踏板."""
        for p in self.by_category("踏板"):
            if p.nominal_dim == nominal_dim and f"幅{width}" in p.note and "センター" not in p.note:
                return p
        return None

    def assert_series(self, part: Part) -> None:
        if part.series_id != self.series_id:
            raise SeriesLockError(
                f"系列混在は禁止です: プロジェクトは {self.series_id} にロック済み、"
                f"{part.model_no} は {part.series_id} の部材です"
            )


def load_master(series_id: str, csv_path: Optional[Path] = None) -> PartMaster:
    """CSVから指定系列のみ読み込む（系列ロック）."""
    path = Path(csv_path) if csv_path else DEFAULT_MASTER_PATH
    if series_id not in SERIES_CONST:
        raise SeriesLockError(f"未知の系列IDです: {series_id}")
    master = PartMaster(series_id=series_id)
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["series_id"] != series_id:
                continue
            master.parts.append(
                Part(
                    series_id=row["series_id"],
                    category=row["category"],
                    model_no=row["model_no"],
                    nominal_dim=int(row["nominal_dim"]),
                    actual_dim=int(row["actual_dim"]),
                    diameter=float(row["diameter"]),
                    weight_kg=float(row["weight_kg"]),
                    note=row.get("note", "") or "",
                )
            )
    if not master.parts:
        raise SeriesLockError(f"系列 {series_id} の部材がマスタにありません: {path}")
    return master
