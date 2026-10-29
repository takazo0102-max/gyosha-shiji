"""部材マスタ（part_master.csv）の読み込みと系列ロック.

- 呼び寸法(nominal)と実寸法(actual)を厳密に分ける。割付計算は呼び寸法、描画は実寸法。
- 系列(series_id)混在は絶対禁止。SeriesLockError で即座にブロックする。
"""

from __future__ import annotations

import re

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

DEFAULT_MASTER_PATH = Path(__file__).resolve().parents[2] / "data" / "part_master.csv"

# 足場の方式。くさび式（支柱＋布材）と枠組式（建枠）は構造が根本的に違うため、
# 立面の解き方も数量ルールも分岐する。
WEDGE = "くさび"
FRAME = "枠組"
# 単管（φ48.6 の鋼管をクランプで組む）。緊結部（コマ）が無く、布・腕木・ブラケットは建地の好きな高さにクランプで
# 留める。立面の解き方はくさびと同じ（コマピッチの代わりに細かい刻み）、部材の拾いにクランプ・ジョイントが加わる
TUBE = "単管"

# ジャッキの機械的な上限。枠組はジャッキ型ベース金具の最大使用高さ350mm（構造規格）、
# くさびはマスタに上限の記載が無いときの既定
FRAME_JACK_MAX_MM = 350
DEFAULT_JACK_MAX_MM = 450

# スパンのモジュール。メートル（1800/1500/1200/900/600）かインチ（1829/1524/1219/914/610）。
# 系列ロックの上に「インチで組みたい」という指定を受けるための区分（足場計画.gsm の
# インチ／メートル切替と同じ発想）。インチ系列は日建ND1800/ND1900と枠組
MODULE_METRIC = "metric"
MODULE_INCH = "inch"
MODULE_ALIASES = {"metric": MODULE_METRIC, "メートル": MODULE_METRIC, "m": MODULE_METRIC, "mm": MODULE_METRIC,
                  "inch": MODULE_INCH, "インチ": MODULE_INCH, "in": MODULE_INCH}
DEFAULT_SERIES_BY_MODULE = {MODULE_METRIC: "shinwa_A", MODULE_INCH: "nikken_nd1800"}


def normalize_module(value) -> str:
    """入力のモジュール表記（inch／インチ／metric／メートル）を正規化。不明なら ValueError."""
    key = str(value).strip().lower() if value is not None else ""
    for k, v in MODULE_ALIASES.items():
        if key == k.lower():
            return v
    raise ValueError(f"モジュールは inch（インチ）か metric（メートル）です（'{value}'）")


def series_module(series_id: str) -> str:
    return SERIES_CONST[series_id]["module"]


# 足場の種類（足場条件の部品で選ぶ表示名）→ 系列。利用者の指定（2026-10-20）: 配置のとき足場の種類を選べるように
SERIES_LABELS = {
    "nikken_nd1800": "日建 NDシステム1800（くさび）",
    "nikken_nd1900": "日建 NDシステム1900（くさび）",
    "nikken_strong": "日建 NDシステム ストロング（くさび・高耐力）",
    "nikken_millennium": "日建 ミレニューム（くさび・次世代）",
    "waku": "日建 枠組（建枠）",
    "albatross": "スギコ アルバトロス（くさび・先行手摺ブレス）",
    "shinwa_A": "信和 Aタイプ（くさび・メートル）",
    "shinwa_B": "信和 Bタイプ（くさび・メートル）",
    "tankan": "単管・クランプ（単管ブラケット足場・単管抱き足場）",
}


def series_from_label(value) -> str:
    """表示名でも系列IDでも受けて系列IDを返す（分からなければそのまま）."""
    v = str(value or "").strip()
    for sid, label in SERIES_LABELS.items():
        if v in (label, sid):
            return sid
    return v


def series_ids_for_module(module: str) -> list[str]:
    return [sid for sid, c in SERIES_CONST.items() if c["module"] == module]

# 系列ごとのコマピッチ・階高・既定踏板幅 [mm]
# 踏板幅は系列で実寸が違う（A:400/250、B:405/240）。既定値を決め打ちにすると
# 系列を切り替えたときにマスタ引き当てが静かに失敗するので、ここから引く。
SERIES_CONST = {
    "shinwa_A": {"system_type": WEDGE, "koma_pitch": 450, "floor_height": 1800,
                 "hozo": 125, "module": "metric",
                 "deck_widths": (400, 250), "next_gen_deck_widths": (500, 250)},
    "shinwa_B": {"system_type": WEDGE, "koma_pitch": 475, "floor_height": 1900,
                 "hozo": 125, "module": "metric",
                 "deck_widths": (405, 240), "next_gen_deck_widths": (500, 240)},
    # 日建リース NDシステム1800（ダーウィン）: コマ450・階高1800、スパンはインチ
    # （1829/1524/1219/914/610）。品番・重量・耐力は仮設資材カタログVol.10
    # （data/NIKKEN_CATALOG_NOTES.md に抜き書き）
    # コマの位置（カタログの支柱図）: 上端から koma_top_gap 下に1つ、そこから koma_pitch で下へ。
    # nega_koma_lengths の支柱は下端から koma_nega にも根がらみ用のコマがある（ND1800 p003: NDP27N は 170・395・845…）
    "nikken_nd1800": {"system_type": WEDGE, "koma_pitch": 450, "floor_height": 1800,
                      "koma_top_gap": 55, "koma_nega": 170, "nega_koma_lengths": (2700, 1125, 900, 675, 450),
                      "hozo": 125, "module": "inch",
                      "deck_widths": (500, 240), "next_gen_deck_widths": (500, 240)},
    # 日建リース NDシステム1900: コマ475・階高1900（支柱3800/2850/1900/1425/950/475）。
    # つなぎ材・布板・ブラケット・梁枠はND1800と共通、支柱・先行手すり・階段が専用
    "nikken_nd1900": {"system_type": WEDGE, "koma_pitch": 475, "floor_height": 1900,
                      "koma_top_gap": 55, "koma_nega": 120, "nega_koma_lengths": (2750,),
                      "hozo": 125, "module": "inch",
                      "deck_widths": (500, 240), "next_gen_deck_widths": (500, 240)},
    # 日建リース NDシステム ストロング: 支柱だけ専用（φ42.7・φ48.6 の異形断面 STK500 t2.7、NSジョイントで連結）。
    # つなぎ材・先行手すり・布板などは ND1800 と共通。支柱の許容支持力 13.7〜19.3kN/本（ND1800 は 11〜17）
    "nikken_strong": {"system_type": WEDGE, "koma_pitch": 450, "floor_height": 1800,
                      "koma_top_gap": 55, "koma_nega": 170, "nega_koma_lengths": (2700,),
                      "hozo": 55, "module": "inch",
                      "deck_widths": (500, 240), "next_gen_deck_widths": (500, 240)},
    # 日建リース ミレニューム（次世代足場のパイオニア）: 支柱 φ48.6・コマ450・階高1800、先行手すり筋交い（2段手すり機能）。
    # 布板（アップロック式鋼製布板）・幅木・壁つなぎなどは ND と共通。支柱の許容支持力 11.0kN/本（補剛材ありで19.6）
    "nikken_millennium": {"system_type": WEDGE, "koma_pitch": 450, "floor_height": 1800,
                          "koma_top_gap": 30, "koma_nega": 120, "nega_koma_lengths": (2700,),
                          "hozo": 125, "module": "inch",
                          "deck_widths": (500, 240), "next_gen_deck_widths": (500, 240)},
    # スギコ（アルインコ製）アルバトロス: 支柱 φ48.6・コマ（フランジ）450・階高1800、スパンはインチ（布材 1829〜153）、
    # 先行手摺ブレス。支柱の継ぎは連結ピン（上下 130。ほぞ 130）。品番・重量はスギコ カタログvol.7 p025〜051
    # （data/SUGIKO_CATALOG_NOTES.md）。利用者の指定 2026-10-29「アルバロスの材料も対応できるようにして」。
    # 最上段のフランジの位置は図に寸法が無く、3600 支柱の図の縮尺から上端の下 約50 と読んだ。根がらみプレート付支柱
    # （2700・1350・900・675・225。p027 の図・p062「最下層には根がらみプレート付支柱」）は下端から 約130 にもプレートがある
    # （図の縮尺: コマの間隔 46px に対して 13px。±10 の読み）
    "albatross": {"system_type": WEDGE, "koma_pitch": 450, "floor_height": 1800,
                  "koma_top_gap": 50, "koma_nega": 130, "nega_koma_lengths": (2700, 1350, 900, 675),
                  "hozo": 130, "module": "inch",
                  "deck_widths": (500, 240), "next_gen_deck_widths": (500, 240)},
    # 単管（φ48.6×2.4・日建 カタログVol.10p372 の単管パイプ、p377 直線ジョイント、p378 兼用クランプ、p078 ジャッキベース）。
    # クランプは建地のどこにでも留まるので、koma_pitch は高さの刻み（50）。スパンはメートル（建地間隔 1.85m 以下）
    "tankan": {"system_type": TUBE, "koma_pitch": 50, "floor_height": 1800,
               "hozo": 0, "module": "metric",
               "deck_widths": (240, 240), "next_gen_deck_widths": (240, 240)},
    # 枠組: 建枠を積む。層高＝建枠高さ、コマピッチの概念はない
    "waku": {"system_type": FRAME, "koma_pitch": 0, "floor_height": 1700,
             "hozo": 0, "module": "inch",
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

    def adjustable_range(self) -> Optional[tuple[int, int]]:
        """伸縮品の可変範囲（note の「NNN〜MMM」）。定尺品は None."""
        m = re.search(r"(\d+)\s*〜\s*(\d+)", self.note)
        if not m:
            return None
        lo, hi = int(m.group(1)), int(m.group(2))
        return (lo, hi) if lo < hi else None

    def max_extension_mm(self) -> Optional[int]:
        """ジャッキの繰出し上限（note の「繰出し最大NNN」）。書いていなければ None."""
        m = re.search(r"繰出し最大\s*(\d+)", self.note)
        return int(m.group(1)) if m else None

    def covers(self, width: int) -> bool:
        """この部材で呼び幅 width をまかなえるか（定尺は一致、伸縮は範囲内）."""
        rng = self.adjustable_range()
        if rng is None:
            return self.nominal_dim == width
        return rng[0] <= width <= rng[1]


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
    def koma_top_gap(self) -> int:
        """支柱の上端から最上のコマまで（ND1800・ストロング 55、ミレニューム 30。カタログの無い系列は 0）."""
        return int(SERIES_CONST[self.series_id].get("koma_top_gap", 0))

    def post_koma_offsets(self, length: int) -> list[int]:
        """支柱1本の下端からのコマの高さ（mm、昇順。カタログの支柱図）.

        上端から koma_top_gap 下を起点に koma_pitch で下へ並べ、根がらみ用のコマのある支柱
        （nega_koma_lengths）は下端から koma_nega と、そこから上の半ピッチのコマを足す
        （ND1800 の NDP27N: 170・395・845…2645、NDP36N: 395・845…3545）。
        """
        pitch = self.koma_pitch
        if pitch <= 0 or length <= 0:
            return []
        c = SERIES_CONST[self.series_id]
        out = set()
        z = length - self.koma_top_gap
        while z >= 100:
            out.add(z)
            z -= pitch
        nega = int(c.get("koma_nega", 0) or 0)
        if nega and length in tuple(c.get("nega_koma_lengths", ())):
            out.add(nega)
            # 根がらみのコマのすぐ上（ND1800 の NDP11N は 170 の上に 395 がある）
            if not any(nega < v <= nega + pitch * 0.75 for v in out) and pitch - self.koma_top_gap < length:
                out.add(pitch - self.koma_top_gap)
        return sorted(out)

    @property
    def system_type(self) -> str:
        """足場の方式（くさび / 枠組）. 立面の解き方と数量ルールが変わる."""
        return SERIES_CONST[self.series_id]["system_type"]

    @property
    def is_frame(self) -> bool:
        return self.system_type == FRAME

    @property
    def is_tube(self) -> bool:
        """単管（クランプで組む。コマが無い）."""
        return self.system_type == TUBE

    @property
    def module(self) -> str:
        """スパンのモジュール（metric／inch）."""
        return series_module(self.series_id)

    @property
    def system_name(self) -> str:
        """帳票に書く足場の種類。届出書に別方式の名前を書かないための一元管理."""
        if self.is_tube:
            return "単管足場"
        return "枠組足場" if self.is_frame else "くさび緊結式足場"

    @property
    def deck_category(self) -> str:
        """作業床の分類名。枠組は「布板」、くさびは「踏板」と呼び分ける.

        分類名を決め打ちすると、枠組の計画でステージや区間指定の作業床が
        「マスタにありません」になる（実際の部材はあるのに拾えない）。
        """
        return "布板" if self.is_frame else "踏板"

    @property
    def vertical_member_name(self) -> str:
        """鉛直部材の呼び名。枠組は「建枠」、くさびは「支柱」.

        開口部（梁枠）で抜く部材や補強の対象を帳票に書くときに使う。
        決め打ちで「支柱」と書くと、枠組の届出・数量で別部材の名前になる。
        """
        return "建枠" if self.is_frame else "支柱"

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

    def width_setup(self, width_mm: int, gap_mm: int = 20) -> tuple[int, tuple[int, ...]]:
        """足場の幅（600・900 など）→ (建地列の間隔＝腕木の呼び寸法, 作業床の幅の組).

        利用者の指定（2026-10-20）: 幅を 900・600 から選べるようにする。腕木は呼び寸法が幅に
        いちばん近い布材（日建は 610・914、信和は 600・900）。作業床は系列にある幅を2枚までで、
        建地列の間隔＋70（床は支柱芯より少し外まで掛かる）に収まるいちばん広い組（同じなら枚数の少ない方）。
        """
        # 枠組は建枠の幅（1219・914・610）から選び、布板（アンチ）はその建枠に載る組（利用者の指定 2026-10-23:
        # 幅を変えるとアンチも変更、614枠はアンチ1列）。建枠は布板が載る最小の幅を model が選ぶ（frame_width_for）
        rows = (sorted(w for w in self.frame_widths() if w > 0) if self.is_frame else
                sorted({p.nominal_dim for p in self.by_category("布材") if p.nominal_dim > 0}))
        row = min(rows, key=lambda v: (abs(v - width_mm), v)) if rows else int(width_mm)
        avail = sorted(self.deck_widths_available(), reverse=True)
        if self.is_tube and avail:
            # 単管は足場板（幅240）を建地列の間に収まるだけ並べる（幅900で3枚、1200で4枚。以前は2枚までで、
            # 幅900・1200の単管本足場の床が半分しか無かった）
            w = max(avail)
            n = max(1, int((row + 70 + gap_mm) // (w + gap_mm)))
            return row, (w,) * n
        best: tuple[int, ...] = ()
        best_key = None
        for i, a in enumerate(avail):
            for combo in [(a,)] + [(a, b) for b in avail[i:]]:
                total = sum(combo) + gap_mm * (len(combo) - 1)
                if total > row + 70:
                    continue
                key = (total, -len(combo), min(combo))   # 同じなら細い板（150 など）を混ぜない組
                if best_key is None or key > best_key:
                    best, best_key = combo, key
        return row, best

    def deck_widths_available(self) -> set[int]:
        """この系列のマスタにある作業床の幅（noteの「幅NNN」）.

        無い幅を指定しても解けてしまい、数量表で床が丸ごと欠けるだけになる。
        入力時点で弾くために使う。
        """
        out: set[int] = set()
        for p in self.by_category(self.deck_category):
            # 狭小地用の板（アルバトロスの 150幅鋼製板）は本体の床の組に入れない（610 に 500＋150 を敷いていた。カタログ
            # p025「足場の幅610の場合は500幅の布板」）。屋上への渡りなど狭い所は roof_bridges が幅を直接拾う
            if "狭小地" in p.note:
                continue
            for token in p.note.split():
                if token.startswith("幅"):
                    try:
                        out.add(int(token[1:]))
                    except ValueError:
                        pass
        return out

    def by_category(self, category: str) -> list[Part]:
        return [p for p in self.parts if p.category == category]

    def get(self, model_no: str) -> Optional[Part]:
        """品番 → 部材（この系列のマスタに無ければ None）."""
        return next((p for p in self.parts if p.model_no == model_no), None)

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

    def jack_hard_max_mm(self) -> int:
        """この系列でジャッキを繰り出せる上限（mm）.

        枠組はジャッキ型ベース金具の最大使用高さ350mm（構造規格）。くさびはマスタの
        ジャッキの「繰出し最大NNN」の最大（ロングがあればその値）、書いていなければ450。
        敷地の高低差を解くときの機械的な上限に使う（実務上限270とは別）。
        """
        if self.is_frame:
            return FRAME_JACK_MAX_MM
        limits = [p.max_extension_mm() for p in self.by_category("ジャッキ")
                  if "アンダーベース" not in p.note and p.max_extension_mm() is not None]
        return max(limits) if limits else DEFAULT_JACK_MAX_MM

    def bracket_for(self, width: int, outward: bool) -> Optional[Part]:
        """区間指定のブラケット（呼び幅・向き）に当てる部材.

        呼び寸法が一致する定尺品を優先し、無ければ伸縮範囲（note の「360〜475」）に
        幅が入る伸縮品のうち最短のものを返す。完全一致だけにしていると、
        枠組の張出（日建 TWL750 は 500〜750）や ND の伸縮ブラケットが
        「マスタにありません」になり、実際にはある部材を別途手配させていた。
        """
        cands = [
            p for p in self.by_category("ブラケット")
            if ("張出" in p.note) == outward
        ]
        exact = next((p for p in cands if p.nominal_dim == width), None)
        if exact is not None:
            return exact
        covering = [p for p in cands if p.covers(width)]
        return min(covering, key=lambda p: p.nominal_dim) if covering else None

    def find(self, category: str, nominal_dim: int, note_contains: str = "") -> Optional[Part]:
        for p in self.by_category(category):
            if p.nominal_dim == nominal_dim and note_contains in p.note:
                return p
        return self._tube_cover(self.by_category(category), nominal_dim, note_contains)

    def deck_parts(self, width: int, nominal_dim: int) -> Optional[Part]:
        """指定幅・長さの作業床（くさび=踏板 / 枠組=布板）."""
        cands = [p for p in self.by_category(self.deck_category)
                 if f"幅{width}" in p.note and "センター" not in p.note]
        for p in cands:
            if p.nominal_dim == nominal_dim:
                return p
        return self._tube_cover(cands, nominal_dim)

    def _tube_cover(self, parts: list, nominal_dim: int, note_contains: str = "") -> Optional[Part]:
        """単管・足場板は切って使わず、長い品をクランプで留める（重ねる）。呼びが無ければそれ以上でいちばん短い品."""
        if not self.is_tube or nominal_dim <= 0:
            return None
        longer = [p for p in parts if p.nominal_dim >= nominal_dim and note_contains in p.note]
        return min(longer, key=lambda p: p.nominal_dim) if longer else None

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
    TUBE: ("支柱", "布材", "踏板", "ジャッキ", "壁つなぎ", "クランプ"),
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
