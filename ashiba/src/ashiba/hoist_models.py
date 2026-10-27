"""昇降機（工事用エレベーター・ロングスパン・荷揚げ機）の機種表とフロアーゲート.

利用者の指定（2026-10-27）: 建機サービス株式会社の図面（JWW/DXF 15製品）を渡され「昇降機の機種表にする」「フロアーゲート
を描いて数える」「機種ごとの形を3Dで描く」「昇降機は別オブジェクトで配置できるように」。数値は図面の文字から拾い、出典の
図面名と要確認の注記を data/hoist_models.csv に残す。

- frame_span_mm: ロングスパンの両端の枠組（建枠・支柱）の間隔。0 はマスト1本（片持ち）
- post_spacing_mm: マスト（ポスト・ガイドレール）の芯々。0 はマスト1本
- cage_len_mm・cage_depth_mm: 荷台の外々（面に沿った長さ×奥行）。平面・3D はこの大きさで描く
- gate: 乗り込み口のフロアーゲートの大きさ（"4.5"・"7.2" スパン。空は付けない＝荷揚げ専用）
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DATA = Path(__file__).resolve().parents[2] / "data" / "hoist_models.csv"

# フロアーゲート（建機サービス Floor-gate 4.5・7.2 スパン。単管 φ48.6×2.3t をクランプで建地に留める、リミット付ロック装置）
FLOOR_GATES = {
    "4.5": {"name": "フロアーゲート 4.5スパン", "span_mm": 4500.0, "opening_mm": 3930.0, "fold_mm": 570.0},
    "7.2": {"name": "フロアーゲート 7.2スパン", "span_mm": 7200.0, "opening_mm": 6630.0, "fold_mm": 681.0},
}


@dataclass(frozen=True)
class HoistModel:
    model_id: str
    name: str
    maker: str
    kind: str
    load_kg: float
    persons: int
    frame_span_mm: float
    post_spacing_mm: float
    cage_len_mm: float
    cage_depth_mm: float
    cage_in_len_mm: float
    cage_in_depth_mm: float
    max_lift_m: float
    tie_every_mm: float
    gate: str
    source: str
    note: str
    cage_h_mm: float = 0.0     # 荷台の内のりの高さ（三成研機の仕様表）。あれば荷台全体を囲う形（ジャバラ扉・金網・屋根枠）で描く

    @property
    def masts(self) -> int:
        """マストの本数（ロングスパンと、ポスト芯々のある工事用エレベーター＝HCE990GL のラック付き・ラック無しのポストは
        荷台の両端の2本。ほかの工事用エレベーター・荷揚げ機は1本）."""
        return 2 if self.post_spacing_mm > 0 and self.kind in ("ロングスパン", "工事用エレベーター") else 1

    @property
    def load_kn(self) -> float:
        return self.load_kg * 9.80665 / 1000.0


def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def load_hoist_models(path: Path = DATA) -> dict[str, HoistModel]:
    out: dict[str, HoistModel] = {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[r["model_id"]] = HoistModel(
                model_id=r["model_id"], name=r["name"], maker=r["maker"], kind=r["kind"],
                load_kg=_f(r["load_kg"]), persons=int(_f(r["persons"])),
                frame_span_mm=_f(r["frame_span_mm"]), post_spacing_mm=_f(r["post_spacing_mm"]),
                cage_len_mm=_f(r["cage_len_mm"]), cage_depth_mm=_f(r["cage_depth_mm"]),
                cage_in_len_mm=_f(r["cage_in_len_mm"]), cage_in_depth_mm=_f(r["cage_in_depth_mm"]),
                max_lift_m=_f(r["max_lift_m"]), tie_every_mm=_f(r["tie_every_mm"]) or 3600.0,
                gate=(r["gate"] or "").strip(), source=r["source"], note=r["note"],
                cage_h_mm=_f(r.get("cage_h_mm")))
    return out


def hoist_model(model_id: Optional[str]) -> Optional[HoistModel]:
    """機種名（model_id。大文字小文字・全角半角の「－」の違いは見ない）→ 機種. 無ければ None."""
    if not model_id:
        return None
    key = str(model_id).strip().upper().replace("－", "-").replace("ー", "-")
    for k, m in load_hoist_models().items():
        if k.upper() == key:
            return m
    return None


def model_ids() -> list[str]:
    return list(load_hoist_models())
