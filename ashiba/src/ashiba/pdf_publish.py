"""足場のレイアウト（サブセット「仮設足場」）を PDF に発行する（Phase 9-5）.

Archicad の発行セット（既定「2 - レイアウト」＝レイアウトブックを映したもの）の中から、サブセット
「仮設足場」の項目だけを選んで PublishPublisherSet する。出力先は帳票と同じ ashiba_out の下の PDF/。
Archicad は出力先の下に「<プロジェクト名>/<サブセット>/<レイアウト>.pdf」のフォルダを作る。

実機（2026-10-18）: 項目は {"navigatorItemId": {"guid": …}} の形で渡す（{"guid": …} だと
"selectedNavigatorItemId is corrupt or missing"）。発行は3枚で約30秒。以前に20分以上止まったのは、
Archicad を長時間使い続けて図面の生成が詰まっていたとき（再起動後は通った）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .elevation_sections import SUBSET_NAME, walk_tree

DEFAULT_PUBLISHER_SET = "2 - レイアウト"


@dataclass
class PdfResult:
    files: list[Path] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def find_subset_item(tree: dict, subset: str = SUBSET_NAME) -> Optional[str]:
    """発行セットのツリーから、サブセットの項目の GUID（名前が一致する最初のもの）."""
    for it in walk_tree(tree):
        if it.get("name") == subset and it.get("type") != "LayoutItem":
            return it.get("guid")
    return None


def find_layout_items(tree: dict, prefix: str) -> list[str]:
    """この工事のレイアウト（名前が「<工事名> 足場…」）の GUID。サブセットには他の建物の分も入るので選ぶ."""
    return [it["guid"] for it in walk_tree(tree)
            if it.get("type") == "LayoutItem" and str(it.get("name", "")).startswith(f"{prefix} 足場")]


def publish_params(set_name: str, item_guids, out_dir: Path) -> dict:
    guids = [item_guids] if isinstance(item_guids, str) else list(item_guids)
    return {"publisherSetName": set_name,
            "selectedNavigatorItemIds": [{"navigatorItemId": {"guid": g}} for g in guids],
            "outputPath": str(out_dir)}


def publish_scaffold_pdf(client, out_dir: Path, set_name: str = DEFAULT_PUBLISHER_SET,
                         subset: str = SUBSET_NAME, prefix: str = "") -> PdfResult:
    """この工事の足場レイアウトを PDF に（prefix が無ければサブセットごと）。失敗は notes に書いて返す."""
    res = PdfResult()
    out_dir = Path(out_dir)
    try:
        r = client.tapir("GetNavigatorItemTree", {"navigatorMapId": "PublisherSets", "publisherSetName": set_name})
    except Exception as e:
        res.notes.append(f"発行セット「{set_name}」を読めません（{e}）。入力の pdf_publisher_set に"
                         "Archicad の発行セット名（レイアウトブックを映したもの）を書いてください")
        return res
    tree = r.get("navigatorItemTree") or r.get("navigatorTree") or r
    guid = find_layout_items(tree, prefix) if prefix else find_subset_item(tree, subset)
    if not guid:
        what = f"「{prefix} 足場…」のレイアウト" if prefix else f"サブセット「{subset}」"
        res.notes.append(f"発行セット「{set_name}」に{what}がありません"
                         "（発行セットがレイアウトブックを映していない可能性）")
        return res
    out_dir.mkdir(parents=True, exist_ok=True)
    started = time.time() - 1
    try:
        client.tapir("PublishPublisherSet", publish_params(set_name, guid, out_dir))
    except Exception as e:
        res.notes.append(f"PDF を発行できませんでした（{e}）")
        return res
    res.files = sorted(p for p in out_dir.rglob("*.pdf") if p.stat().st_mtime >= started)
    if not res.files:
        res.notes.append(f"発行は終わりましたが、{out_dir} に新しい PDF が見当たりません")
    elif prefix:
        # 同じ工事の前回の足場の PDF で今回出なかったもの（図面の名前が変わった・枚数が減った）を消す。
        # 残すと「A-A 1」など古い図が新しい図と並び、どれが今の計画か分からなかった
        gone = [q for d in {f.parent for f in res.files} for q in d.glob("*.pdf")
                if q.stat().st_mtime < started and f" {prefix} 足場" in q.name]
        for q in gone:
            try:
                q.unlink()
            except OSError:
                pass
        if gone:
            res.notes.append(f"前回の PDF {len(gone)}枚（今回は出ない図面）を消しました")
    return res
