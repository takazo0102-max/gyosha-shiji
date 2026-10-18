"""選択したスラブに対して置いた足場ライン・立面図・詳細図を撤去する（ツールバー割当用）.

条件を変えて何度も試すとき、run_from_archicad.py は同じ位置の前回分を置き換えるが、
外形や離れが変わると位置がずれて残る。スラブを選択してこれを実行すると、その建物の
ぶんだけ消す（他の建物の配置や他ツールの部品には触らない）。

使い方:
  スラブを選択 → python3 scripts/remove_from_archicad.py
  python3 scripts/remove_from_archicad.py --all     # プロジェクト内の足場部品を全部消す
"""
from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from ashiba.tapir_adapter import ArchicadClient, TapirError, get_selected_outline_mm, is_ashiba_part  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ashiba.elevation_sections import (  # noqa: E402
    ELEVATIONS_RECORD,
    load_record,
    remove_all_scaffold_elevations,
    remove_elevations,
)
from run_from_archicad import (  # noqa: E402
    DETAIL_OBJECT,
    DETAIL_OFFSET_MM,
    ELEVATION_OFFSET_MM,
    LINE_OBJECT,
    OUT_DIR,
    SPEC,
    load_spec_override,
)


def _remove_section_elevations(client, all_buildings: bool) -> None:
    """断面図方式の立面（断面要素・レイアウト）も消す。控え（elevation_sections.json）の GUID で消す."""
    import json

    from ashiba.elevation_sections import activate_floor_plan
    activate_floor_plan(client)      # 断面の削除は平面図が前面のときだけ通る
    rec = load_record(OUT_DIR)
    if all_buildings:
        n_s, n_l, left = remove_all_scaffold_elevations(client, rec.values())
        (OUT_DIR / ELEVATIONS_RECORD).write_text("{}\n", encoding="utf-8")
    else:
        # この建物の分: 条件ファイルの project_name（ツールバーと同じ接頭辞）で選ぶ
        spec = dict(SPEC)
        spec.update(load_spec_override())
        prefix = str(spec.get("project_name") or "足場")
        mine = {k: v for k, v in rec.items() if k.startswith(prefix + " ")}
        faces = [k[len(prefix) + 1:-len(" 足場立面")] for k in mine]
        n_s, n_l, left = remove_elevations(client, list(mine), [f"{prefix} 足場立面図 {f}" for f in faces]
                                           + [f"{prefix} 足場立面図", f"{prefix} 足場平面図", f"{prefix} 足場詳細図"], mine.values())
        rest = {k: v for k, v in rec.items() if k not in mine}
        (OUT_DIR / ELEVATIONS_RECORD).write_text(json.dumps(rest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if n_s or n_l:
        print(f"立面図（断面図ビューポイント）{n_s}面・レイアウト {n_l}枚を撤去しました")
    if left:
        print("控えの無い断面が残っています（プロジェクトマップで手で消してください）: " + "・".join(left))


def main() -> int:
    client = ArchicadClient()
    from ashiba.elevation_sections import activate_floor_plan
    activate_floor_plan(client)      # 部品は平面図のデータベースにある
    names = (LINE_OBJECT, DETAIL_OBJECT)
    if "--all" in sys.argv:
        els = client.tapir("GetElementsByType", {"elementType": "Object"}).get("elements", [])
        targets = [
            e for e, d in zip(els, client.get_details(els) if els else [])
            if is_ashiba_part((d.get("details", {}).get("libPart") or {}).get("name") or "", names)
        ]
    else:
        import os
        from ashiba.tapir_adapter import slab_outline_mm_by_guid
        guid = os.environ.get("ASHIBA_SLAB", "").strip()
        outline = slab_outline_mm_by_guid(client, guid) if guid else get_selected_outline_mm(client)
        targets = client.objects_for_slab(
            outline, names, elevation_offset_mm=ELEVATION_OFFSET_MM, detail_offset_mm=DETAIL_OFFSET_MM,
        )
    if targets:
        client.delete_elements(targets)
        print(f"足場部品 {len(targets)}個を撤去しました")
    else:
        print("撤去する足場部品はありません")
    # 平面の部材名ラベル（控えの GUID で。--all なら全建物の分）
    from ashiba.elevation_sections import building_key
    from ashiba.plan_labels import remove_plan_labels
    n_lab = remove_plan_labels(client, OUT_DIR, None if "--all" in sys.argv else building_key(outline))
    if n_lab:
        print(f"平面の部材名ラベル {n_lab}個を撤去しました")
    _remove_section_elevations(client, "--all" in sys.argv)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except TapirError as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(2)
