"""配布用GSM（gdl/*.gsm）を現在のHSFから作り直す.

READMEは「gdl/ashiba_line.gsm をライブラリマネージャで読み込む」と案内して
いるので、ここが古いと利用者は最新のパラメータを持たない部品を読み込むことに
なる（配置時に「部品が古い」で止まる）。HSFを直したらこれを実行する。
由来のHSFハッシュを .gsm.hash に残し、ズレは tests/test_flat_gdl_sync.py が落とす。

使い方: python3 scripts/build_dist_gsm.py [--check]
"""

from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from dev_gsm_iterate import build_current_gsm  # noqa: E402

PARTS = ("ashiba_line", "ashiba_detail", "ashiba_mvo", "ashiba_spec", "ashiba_tie", "ashiba_net", "ashiba_netbk", "ashiba_sheet", "ashiba_member", "ashiba_xsec", "ashiba_cstep", "ashiba_bridge", "ashiba_stage", "ashiba_kbrk", "ashiba_hoist", "ashiba_hstage", "ashiba_walkway", "ashiba_box", "ashiba_side", "ashiba_cfill", "ashiba_wform", "ashiba_cform", "ashiba_bform", "ashiba_sform", "ashiba_yamadome", "ashiba_kakoi", "ashiba_crane", "ashiba_plate", "ashiba_kodai", "ashiba_route", "ashiba_house", "ashiba_opening", "ashiba_fence", "ashiba_lifeline", "ashiba_tube", "ashiba_machine", "ashiba_tower", "ashiba_ywall", "ashiba_shiho", "ashiba_steel")


def hsf_digest(part: str) -> str:
    src = ROOT / "gdl" / "hsf" / part
    h = hashlib.sha256()
    for f in sorted(src.rglob("*")):
        if f.is_file():
            h.update(f.relative_to(src).as_posix().encode())
            h.update(f.read_bytes())
    return h.hexdigest()[:8]


def main() -> None:
    check = "--check" in sys.argv
    stale = []
    for part in PARTS:
        stamp = ROOT / "gdl" / f"{part}.gsm.hash"
        want = hsf_digest(part)
        have = stamp.read_text(encoding="utf-8").strip() if stamp.exists() else ""
        if have == want:
            print(f"最新: gdl/{part}.gsm（{want}）")
            continue
        if check:
            stale.append(part)
            print(f"ズレ: gdl/{part}.gsm（{have or '未記録'} → {want}）")
            continue
        work = ROOT / "out" / "gsm_dist"
        work.mkdir(parents=True, exist_ok=True)
        _name, gsm = build_current_gsm(part, work)
        shutil.copyfile(gsm, ROOT / "gdl" / f"{part}.gsm")
        stamp.write_text(want + "\n", encoding="utf-8")
        print(f"生成: gdl/{part}.gsm（{want}）")
    if stale:
        raise SystemExit("HSFとズレています。--check なしで実行して再生成してください")


if __name__ == "__main__":
    main()
