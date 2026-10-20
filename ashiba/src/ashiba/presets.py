"""足場条件の登録と呼び出し（参考: smartCON Planner の「足場条件の登録・呼び出し」）.

会社や現場の定番（足場の種類・幅・手すり方式・養生材・階段の付け方・ネットの層…）に名前を付けて
控え、別の建物の足場条件の部品へ呼び出す。建物ごとに違う値（工事名・現場名・軒高・建物高さ・
足場高さ・掛ける面・部材編集）は登録しない（呼び出しても今の建物の値のまま）。

控えは ashiba_out/条件の登録/<登録名>.json。部品のパラメータ（params）と、入力 JSON の形（spec）の
両方を書く（spec は条件ファイルへ写して使える）。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .spec_object import FIELDS, spec_from_params

PRESET_DIR_NAME = "条件の登録"
# 建物ごとに違う値。登録しない・呼び出しで上書きしない
BUILDING_FIELDS = frozenset({
    "projName", "siteName", "eavesH", "bldgH", "scaffH", "facesOnly",
    "memberEdit1", "memberEdit2", "memberEdit3", "memberEdit4", "presetName",
})
PRESET_FIELDS = tuple(f.gdl for f in FIELDS if f.gdl not in BUILDING_FIELDS)


def preset_dir(out_dir) -> Path:
    return Path(out_dir) / PRESET_DIR_NAME


def _stem(name: str) -> str:
    from .cli import safe_file_stem

    if not str(name or "").strip():
        raise ValueError("登録名を入れてください（足場条件の部品の「登録名」）")
    return safe_file_stem(str(name).strip())


def save_preset(name: str, params: dict, out_dir) -> Path:
    """部品のパラメータから登録する値だけを控える。同じ名前は上書き."""
    stem = _stem(name)
    keep = {k: params[k] for k in PRESET_FIELDS if k in params}
    if not keep:
        raise ValueError("足場条件の部品の値を読めません")
    d = preset_dir(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{stem}.json"
    body = {"name": str(name).strip(), "saved": datetime.now().isoformat(timespec="seconds"),
            "params": keep, "spec": spec_from_params(keep)}
    body["spec"].pop("_edit_errors", None)
    body["spec"].pop("member_edits", None)
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_preset(name: str, out_dir) -> dict:
    """登録した部品のパラメータ（登録する項目だけ）。無ければ FileNotFoundError（登録済みの名前を添える）."""
    stem = _stem(name)
    path = preset_dir(out_dir) / f"{stem}.json"
    if not path.exists():
        have = list_presets(out_dir)
        raise FileNotFoundError(f"登録「{name}」はありません（登録済み: {'・'.join(have) if have else 'なし'}）")
    body = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in (body.get("params") or {}).items() if k in PRESET_FIELDS}


def list_presets(out_dir) -> list[str]:
    d = preset_dir(out_dir)
    if not d.exists():
        return []
    out = []
    for p in sorted(d.glob("*.json")):
        try:
            out.append(str(json.loads(p.read_text(encoding="utf-8")).get("name") or p.stem))
        except (OSError, ValueError):
            continue
    return out


def apply_preset(params: dict, preset: dict) -> tuple[dict, list[str]]:
    """部品のパラメータに登録の値を重ねる（建物ごとの値は残す）。(新しい値, 変わった項目名)."""
    out = dict(params)
    changed = []
    for k, v in preset.items():
        if k in BUILDING_FIELDS:
            continue
        if out.get(k) != v:
            changed.append(k)
        out[k] = v
    return out, changed
