"""HSFソースから単一ファイル参照版 .gdl を生成する.

参照版を手で書くと必ずHSF側とズレる（実際、立面モードと壁つなぎ表示が
入らないまま放置されていた）。生成物にしてズレようがなくしてある。
tests/test_flat_gdl_sync.py が「生成し直した内容と一致するか」を検査する。

使い方:
  python3 scripts/build_flat_gdl.py            # 全パーツを書き出し
  python3 scripts/build_flat_gdl.py --check    # 差分があれば非ゼロ終了
"""

from __future__ import annotations

import sys
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HSF_DIR = ROOT / "gdl" / "hsf"

# 参照版を出すパーツと、その概要（オブジェクト全体の設計意図はHSFの
# どのスクリプトにも属さないのでここに置く）
PARTS = {
    "ashiba_line": {
        "title": "足場ライン オブジェクト（くさび緊結式・1辺=1オブジェクト）",
        "notes": [
            "アーキテクチャ決定（開発指示書2.1）:",
            "  部材1本ごとにオブジェクトを置かず、1つの辺を1つのGDLオブジェクトとし",
            "  内部で支柱・布材・踏板・手すり・幅木・ブレスをパラメトリック生成する。",
            "  Python側は割付を解いてこのオブジェクトを辺の数だけ置くのみ。",
        ],
    },
    "ashiba_detail": {
        "title": "詳細図 2Dシンボル（設置届 添付図・detailTypeで5種を切替）",
        "notes": [
            "方式③: 詳細図は3Dモデルからの投影ではなく2Dシンボルとして描く。",
            "投影に頼ると縮尺1/10〜1/20で必要な納まりの線が出ない。",
        ],
    },
}

SCRIPT_SECTIONS = [
    ("1d.gdl", "マスタースクリプト"),
    ("2d.gdl", "2Dスクリプト"),
    ("3d.gdl", "3Dスクリプト"),
]

TYPE_JA = {
    "Length": "長さ",
    "String": "文字列",
    "Boolean": "ブール",
    "Integer": "整数",
    "RealNum": "実数",
    "Angle": "角度",
}


def _rule(char: str = "=") -> str:
    return "! " + char * 58


def _width(s: str) -> int:
    """等幅フォントでの表示幅。日本語は2桁ぶんなので len() では揃わない."""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def _pad(s: str, width: int) -> str:
    return s + " " * max(0, width - _width(s))


def parameter_lines(part_dir: Path) -> list[str]:
    """paramlist.xml → コメント行。Archicad標準の固定パラメータ(A/B/ZZYZX)は除く."""
    root = ET.parse(part_dir / "paramlist.xml").getroot()
    params = root.find("Parameters")
    if params is None:
        raise SystemExit(f"Parameters セクションがありません: {part_dir}")
    rows = []
    for el in params:
        if el.find("Fix") is not None:
            continue
        desc = (el.findtext("Description") or "").strip().strip('"')
        value = (el.findtext("Value") or "").strip()
        rows.append((el.get("Name", ""), TYPE_JA.get(el.tag, el.tag), desc, value))
    if not rows:
        return []
    w_name = max(_width(r[0]) for r in rows)
    w_type = max(_width(r[1]) for r in rows)
    w_desc = max(_width(r[2]) for r in rows)
    return [
        f"!   {_pad(n, w_name)}  {_pad(t, w_type)}  {_pad(d, w_desc)}  既定 {v}"
        for n, t, d, v in rows
    ]


def build_flat_gdl(part: str) -> str:
    meta = PARTS[part]
    part_dir = HSF_DIR / part
    out = [
        _rule(),
        f"! {meta['title']} 単一ファイル参照版",
        _rule("-"),
        f"! このファイルは gdl/hsf/{part}/ から自動生成しています。",
        "! 直接編集しないでください。HSF側を直してから再生成します:",
        "!   python3 scripts/build_flat_gdl.py",
        "!",
        "! 通しで読む・差分を見るための参照用で、そのままでは動きません",
        f"! （実際に読み込むのは gdl/{part}.gsm）。各セクションはArchicadの",
        "! 対応するスクリプト欄にそのまま貼れます。",
        _rule("-"),
    ]
    out += ["! " + n for n in meta["notes"]]
    param_lines = parameter_lines(part_dir)
    if param_lines:
        out += [_rule("-"), "! パラメータリスト:"] + param_lines
    out += [_rule(), ""]

    for filename, label in SCRIPT_SECTIONS:
        src = part_dir / "scripts" / filename
        if not src.exists():
            continue
        body = src.read_text(encoding="utf-8-sig").rstrip("\n")
        out += [_rule(), f"! ==== {label} ====", _rule(), body, ""]
    return "\n".join(out) + "\n"


def main() -> None:
    check = "--check" in sys.argv
    stale = []
    for part in PARTS:
        if not (HSF_DIR / part).is_dir():
            continue
        path = ROOT / "gdl" / f"{part}.gdl"
        text = build_flat_gdl(part)
        current = path.read_text(encoding="utf-8-sig") if path.exists() else None
        if current == text:
            print(f"変更なし: {path.relative_to(ROOT)}")
            continue
        if check:
            stale.append(str(path.relative_to(ROOT)))
            continue
        # 他のGDLソースに合わせてBOM付きUTF-8で出す
        path.write_text(text, encoding="utf-8-sig")
        print(f"生成: {path.relative_to(ROOT)}")
    if stale:
        raise SystemExit(
            "HSFと参照版がズレています: " + ", ".join(stale)
            + "\n  python3 scripts/build_flat_gdl.py で再生成してください"
        )


if __name__ == "__main__":
    main()
