"""レイアウトの表題欄を埋める（Phase 9-4）: 入力の工事名・届出の情報を Archicad のプロジェクト情報へ.

マスターレイアウトの表題欄はプロジェクト情報のオートテキスト（プロジェクト名・敷地住所・連絡先 会社…）を
映すので、プロジェクト情報に入れれば全レイアウトの表題欄に出る。マスターレイアウトは API で開けない
（ChangeWindow が "Failed to activate the view"）ため、表題欄そのものには触らない。

プロジェクト情報はプロジェクト全体の値（建物本体の図面も同じ表題欄を使う）なので、
**空の項目と、前回このツールが書いた値のままの項目だけ**を書き換える。利用者が入れた値は残して案内だけ出す。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

RECORD = "project_info.json"

# プロジェクト情報の項目 → 入力のどこから取るか（先に書いたものを優先）
FIELD_SOURCES: tuple[tuple[str, str, tuple[tuple[str, ...], ...]], ...] = (
    ("PROJECTNAME", "プロジェクト名", (("notification", "site_name"), ("project_name",))),
    ("SITEFULLADDRESS", "敷地 住所", (("notification", "site_address"),)),
    ("CONTACTCOMPANY", "連絡先 会社", (("notification", "contractor"),)),
    ("CONTACT_FULLNAME", "連絡先 氏名", (("notification", "planner_name"),)),
)


def _get(spec: dict, path: tuple[str, ...]):
    cur = spec
    for k in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def wanted_fields(spec: dict) -> dict[str, str]:
    """入力から、表題欄に出したいプロジェクト情報（空の値は入れない）."""
    out = {}
    for fid, _label, paths in FIELD_SOURCES:
        for p in paths:
            v = _get(spec, p)
            if v is not None and str(v).strip():
                out[fid] = str(v).strip()
                break
    return out


def plan_updates(current: dict[str, str], wanted: dict[str, str],
                 last_written: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """書き換える項目と、利用者の値なので残す項目の案内.

    current: いまのプロジェクト情報（id → 値）、last_written: 前回このツールが書いた値。
    """
    labels = {fid: label for fid, label, _ in FIELD_SOURCES}
    updates: dict[str, str] = {}
    kept: list[str] = []
    for fid, value in wanted.items():
        if fid not in current:
            continue                      # この Archicad には無い項目
        now = str(current.get(fid) or "")
        if now == value:
            continue
        if now == "" or now == last_written.get(fid):
            updates[fid] = value
        else:
            kept.append(f"表題欄の「{labels.get(fid, fid)}」は「{now}」が入っているので変えていません"
                        f"（ツールの値: {value}）")
    return updates, kept


def load_record(out_dir) -> dict[str, str]:
    try:
        data = json.loads((Path(out_dir) / RECORD).read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_record(out_dir, written: dict[str, str], previous: Optional[dict[str, str]] = None) -> None:
    rec = dict(previous or {})
    rec.update(written)
    (Path(out_dir) / RECORD).write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fill_title_block(client, spec: dict, out_dir) -> tuple[dict[str, str], list[str]]:
    """プロジェクト情報に工事名などを入れる。戻り値は (書いた項目, 案内)."""
    fields = client.tapir("GetProjectInfoFields", {}).get("fields", [])
    current = {f.get("projectInfoId"): f.get("projectInfoValue") or "" for f in fields}
    last = load_record(out_dir)
    updates, notes = plan_updates(current, wanted_fields(spec), last)
    written: dict[str, str] = {}
    for fid, value in updates.items():
        try:
            client.tapir("SetProjectInfoField", {"projectInfoId": fid, "projectInfoValue": value})
            written[fid] = value
        except Exception as e:          # 1項目の失敗で配置全体を止めない
            notes.append(f"表題欄の {fid} を書けませんでした: {e}")
    if written:
        save_record(out_dir, written, last)
    return written, notes
