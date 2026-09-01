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

# 足場の方式。くさび式（支柱＋布材）と枠組式（建枠）は構造が根本的に違うため、
# 立面の解き方も数量ルールも分岐する。
WEDGE = "くさび"
FRAME = "枠組"

# 系列ごとのコマピッチ・階高・既定踏板幅 [mm]
# 踏板幅は系列で実寸が違う（A:400/250、B:405/240）。既定値を決め打ちにすると
# 系列を切り替えたときにマスタ引き当てが静かに失敗するので、ここから引く。
SERIES_CONST = {
    "shinwa_A": {"system_type": WEDGE, "koma_pitch": 450, "floor_height": 1800,
                 "hozo": 125,
                 "deck_widths": (400, 250), "next_gen_deck_widths": (500, 250)},
    "shinwa_B": {"system_type": WEDGE, "koma_pitch": 475, "floor_height": 1900,
                 "hozo": 125,
                 "deck_widths": (405, 240), "next_gen_deck_widths": (500, 240)},
    "inch": {"system_type": WEDGE, "koma_pitch": 450, "floor_height": 1829,
             "hozo": 125,
             "deck_widths": (500, 240), "next_gen_deck_widths": (500, 240)},
    # 枠組: 建枠を積む。層高＝建枠高さ、コマピッチの概念はない
    "waku": {"system_type": FRAME, "koma_pitch": 0, "floor_height": 1700,
             "hozo": 0,
             "deck_widths": (500, 240), "next_gen_deck_widths": (500, 240)},
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

    @property
    def system_type(self) -> str:
        """足場の方式（くさび / 枠組）. 立面の解き方と数量ルールが変わる."""
        return SERIES_CONST[self.series_id]["system_type"]

    @property
    def is_frame(self) -> bool:
        return self.system_type == FRAME

    @property
    def system_name(self) -> str:
        """帳票に書く足場の種類。届出書に別方式の名前を書かないための一元管理."""
        return "枠組足場" if self.is_frame else "くさび緊結式足場"

    def frame_heights(self) -> list[int]:
        """建枠の高さ一覧（降順）. 枠組式のみ."""
        return sorted(
            {p.nominal_dim for p in self.by_category("建枠")}, reverse=True
        )

    def frame_widths(self) -> list[int]:
        """建枠の幅一覧（降順）. noteの「幅NNNN」から読む."""
        out = set()
        for p in self.by_category("建枠"):
            for token in p.note.split():
                if token.startswith("幅"):
                    try:
                        out.add(int(token[1:]))
                    except ValueError:
                        pass
        return sorted(out, reverse=True)

    def default_deck_widths(self, next_gen: bool = False) -> tuple[int, ...]:
        """この系列の既定踏板幅.

        次世代足場は専用系列を作らず「くさび派生（踏板幅500・階高1800/1900）」
        として扱う（仕様3.1）。
        """
        key = "next_gen_deck_widths" if next_gen else "deck_widths"
        return SERIES_CONST[self.series_id][key]

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
