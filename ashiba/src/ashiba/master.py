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


class MasterDataError(Exception):
    """部材マスタCSVの読み取り失敗（列不足・型違い・文字コード違いなど）.

    マスタは利用者が差し替えられる外部データ。Excelから保存したCSVは
    BOM付きだったりShift_JISだったりするので、そこで落ちる理由が
    トレースバックだと直しようがない。
    """


MASTER_COLUMNS = ("series_id", "category", "model_no", "nominal_dim",
                  "actual_dim", "diameter", "weight_kg")


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

    @property
    def deck_category(self) -> str:
        """作業床の分類名。枠組は「布板」、くさびは「踏板」と呼び分ける.

        分類名を決め打ちすると、枠組の計画でステージや区間指定の作業床が
        「マスタにありません」になる（実際の部材はあるのに拾えない）。
        """
        return "布板" if self.is_frame else "踏板"

    def frame_heights(self) -> list[int]:
        """建枠の高さ一覧（降順）. 枠組式のみ."""
        return sorted(
            {p.nominal_dim for p in self.by_category("建枠")}, reverse=True
        )

    def frame_width_for(self, need_width: int) -> tuple[int, bool]:
        """布板幅の合計を載せられる最小の建枠幅と、足りているかを返す.

        「近い幅」で選ぶと布板より狭い建枠になり、実際には組めない。
        数量拾いと図面で別々に選ぶとズレるので、選定はここに集約する。
        """
        widths = self.frame_widths()
        fits = [w for w in widths if w >= need_width]
        if fits:
            return min(fits), True
        return (max(widths) if widths else 1219), False

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
        """指定幅・長さの作業床（くさび=踏板 / 枠組=布板）."""
        for p in self.by_category(self.deck_category):
            if p.nominal_dim == nominal_dim and f"幅{width}" in p.note and "センター" not in p.note:
                return p
        return None

    def assert_series(self, part: Part) -> None:
        if part.series_id != self.series_id:
            raise SeriesLockError(
                f"系列混在は禁止です: プロジェクトは {self.series_id} にロック済み、"
                f"{part.model_no} は {part.series_id} の部材です"
            )


def _read_master_text(path: Path) -> str:
    """マスタCSVを読む。ExcelのBOM付き・Shift_JIS保存もそのまま受ける."""
    try:
        raw = Path(path).read_bytes()
    except FileNotFoundError:
        raise MasterDataError(f"部材マスタが見つかりません: {path}") from None
    except OSError as e:
        raise MasterDataError(
            f"部材マスタを読めません: {path}（{e.strerror}）") from None
    if not raw.strip():
        raise MasterDataError(f"部材マスタが空です: {path}")
    for enc in ("utf-8-sig", "cp932"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise MasterDataError(
        f"部材マスタの文字コードを判別できません: {path}。"
        "UTF-8（BOM付き可）またはShift_JISで保存してください"
    )


def _num(row: dict, col: str, cast, path: Path, line: int):
    """数値列を読む。空欄・全角・単位付きは行と値を挙げて弾く."""
    value = (row.get(col) or "").strip()
    if not value:
        raise MasterDataError(
            f"部材マスタ {path} の{line}行目: 列「{col}」が空です"
            f"（型番 {row.get('model_no', '?')}）"
        )
    try:
        return cast(value)
    except ValueError:
        raise MasterDataError(
            f"部材マスタ {path} の{line}行目: 列「{col}」が数値ではありません"
            f"（{value!r}／型番 {row.get('model_no', '?')}）"
        ) from None


def load_master(series_id: str, csv_path: Optional[Path] = None) -> PartMaster:
    """CSVから指定系列のみ読み込む（系列ロック）."""
    path = Path(csv_path) if csv_path else DEFAULT_MASTER_PATH
    if series_id not in SERIES_CONST:
        raise SeriesLockError(f"未知の系列IDです: {series_id}")
    master = PartMaster(series_id=series_id)
    reader = csv.DictReader(_read_master_text(path).splitlines())
    missing = [c for c in MASTER_COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise MasterDataError(
            f"部材マスタに必要な列がありません: {path}"
            f"（不足: {'、'.join(missing)}／必要な列: {'、'.join(MASTER_COLUMNS)}）"
        )
    for i, row in enumerate(reader, start=2):   # 2行目からがデータ
        if (row.get("series_id") or "").strip() != series_id:
            continue
        master.parts.append(
            Part(
                series_id=row["series_id"],
                category=row["category"],
                model_no=row["model_no"],
                nominal_dim=_num(row, "nominal_dim", int, path, i),
                actual_dim=_num(row, "actual_dim", int, path, i),
                diameter=_num(row, "diameter", float, path, i),
                weight_kg=_num(row, "weight_kg", float, path, i),
                note=row.get("note", "") or "",
            )
        )
    if not master.parts:
        raise SeriesLockError(f"系列 {series_id} の部材がマスタにありません: {path}")
    _assert_complete(master, path)
    return master


# 割付・数量・構造のどれかが必ず引く分類。欠けていると解いている途中で
# 空の min() を取るような分かりにくい例外になる（実際 inch 系列がそうだった）
REQUIRED_CATEGORIES = {
    WEDGE: ("支柱", "布材", "踏板", "ジャッキ", "壁つなぎ"),
    FRAME: ("建枠", "布材", "布板", "ジャッキ", "壁つなぎ"),
}


def _assert_complete(master: PartMaster, path: Path) -> None:
    """系列に必須分類が揃っているか。足りなければ読み込み時点で落とす."""
    have = {p.category for p in master.parts}
    missing = [c for c in REQUIRED_CATEGORIES[master.system_type] if c not in have]
    if missing:
        raise SeriesLockError(
            f"系列 {master.series_id} は部材マスタが不完全です"
            f"（不足: {'、'.join(missing)}）。{path} を補完してください"
        )
