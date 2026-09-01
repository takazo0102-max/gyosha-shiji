"""GDL開発イテレーション: HSFソースを版名でクローン→GSMコンパイル→
埋め込みライブラリ注入→テスト配置→プレビュー画像で検証.

埋め込みライブラリは同名上書き不可のため、イテレーションごとに
部品名を <part>_v<N> に変えて新GUIDで追加する（検証後に要素は削除）。

使い方:
  python3 scripts/dev_gsm_iterate.py <version> [--part ashiba_line] [--keep]
  python3 scripts/dev_gsm_iterate.py 1 --part ashiba_detail --params detailType=脚部
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ashiba.tapir_adapter import ArchicadClient  # noqa: E402

LPX = (
    "/Users/takazou/Downloads/LibDev Toolkit 27 (3001)/Tool/OSX/"
    "MakeGDLLib_X86/LP_XMLConverter.app/Contents/MacOS/LP_XMLConverter"
)
HSF_DIR = ROOT / "gdl" / "hsf"

# 部品ごとの検証パラメータと確認するプレビュー種別
PART_PROFILES = {
    "ashiba_line": {
        "images": ("3D", "2D"),
        "params": {
            "spanList": "1800,1800,1800,1800,900",
            "postList": "3600,3600,3600,1800,450",
            "jackOut": 0.1,
            "standoff": 0.3,
        },
    },
    "ashiba_detail": {
        "images": ("2D",),
        "params": {"detailType": "脚部", "jackOut": 0.2},
    },
}


def build_versioned_gsm(
    version: int, work_dir: Path, part: str = "ashiba_line", script3d: Path | None = None
) -> tuple[str, Path]:
    name = f"{part}_v{version}"
    hsf_src = HSF_DIR / part
    if not hsf_src.is_dir():
        raise SystemExit(f"HSFソースがありません: {hsf_src}")
    hsf_dst = work_dir / name
    if hsf_dst.exists():
        shutil.rmtree(hsf_dst)
    shutil.copytree(hsf_src, hsf_dst)
    if script3d is not None:
        shutil.copyfile(script3d, hsf_dst / "scripts" / "3d.gdl")
    # 新GUIDに差し替え（同一GUIDの重複部品を避ける）
    lpd = hsf_dst / "libpartdata.xml"
    text = lpd.read_text(encoding="utf-8")
    old_guid = text.split("<MainGUID>")[1].split("</MainGUID>")[0]
    lpd.write_text(text.replace(old_guid, str(uuid.uuid4()).upper()), encoding="utf-8")
    gsm = work_dir / f"{name}.gsm"
    if gsm.exists():
        gsm.unlink()
    res = subprocess.run(
        [LPX, "hsf2libpart", str(hsf_dst), str(gsm)],
        capture_output=True, text=True,
    )
    out = (res.stdout + res.stderr).replace("\n", " ")
    if not gsm.exists():
        raise SystemExit(f"GSMコンパイル失敗: {out}")
    return name, gsm


def parse_params(argv: list[str]) -> dict:
    """--params k=v k=v ... を辞書に（数値に見える値はfloatにする）."""
    if "--params" not in argv:
        return {}
    out = {}
    for tok in argv[argv.index("--params") + 1:]:
        if tok.startswith("--") or "=" not in tok:
            break
        k, v = tok.split("=", 1)
        try:
            out[k] = float(v)
        except ValueError:
            out[k] = v
    return out


def main() -> None:
    version = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    keep = "--keep" in sys.argv
    part = "ashiba_line"
    if "--part" in sys.argv:
        part = sys.argv[sys.argv.index("--part") + 1]
    script3d = None
    if "--script3d" in sys.argv:
        script3d = Path(sys.argv[sys.argv.index("--script3d") + 1])
    profile = PART_PROFILES.get(part, {"images": ("2D",), "params": {}})
    params = dict(profile["params"])
    params.update(parse_params(sys.argv))
    suffix = params.get("detailType", "")

    work_dir = ROOT / "out" / "gsm_dev"
    work_dir.mkdir(parents=True, exist_ok=True)

    name, gsm = build_versioned_gsm(version, work_dir, part, script3d)
    print(f"コンパイル完了: {gsm.name}")

    c = ArchicadClient()
    c.add_file_to_embedded_library(str(gsm), gsm.name)
    print("埋め込みライブラリへ追加")

    elem = c.create_object(name, 50000, 50000)
    print(f"テスト配置: {elem['elementId']['guid']}")

    # 検証はプレビュー画像で行う。
    # 注意: Get3DBoundingBoxes はオブジェクトに対して
    # 「2D記号の外形×高さパラメータ」のフォールバック値を返すことがあり
    # 3D生成の検証には使えない（実機で確認済みの落とし穴）。
    if params:
        c.set_gdl_parameters(elem, params)
    import base64
    for img_type in profile["images"]:
        resp = c.tapir(
            "GetElementPreviewImage",
            {"elementId": elem["elementId"], "imageType": img_type,
             "width": 900, "height": 900},
        )
        img = base64.b64decode(resp["previewImage"])
        tag = f"_{suffix}" if suffix else ""
        p = work_dir / f"{name}{tag}_{img_type}.png"
        p.write_bytes(img)
        print(f"プレビュー保存 ({len(img)}B): {p}")

    if not keep:
        c.delete_elements([elem])
        print("テスト要素を削除（--keep で残せます）")


if __name__ == "__main__":
    main()
