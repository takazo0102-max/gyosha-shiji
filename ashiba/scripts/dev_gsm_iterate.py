"""GDL開発イテレーション: HSFソースを版名でクローン→GSMコンパイル→
埋め込みライブラリ注入→テスト配置→3Dバウンディングボックス検証.

埋め込みライブラリは同名上書き不可のため、イテレーションごとに
部品名を ashiba_line_v<N> に変えて新GUIDで追加する（検証後に要素は削除）。

使い方: python3 scripts/dev_gsm_iterate.py <version> [--keep]
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
HSF_SRC = ROOT / "gdl" / "hsf" / "ashiba_line"


def build_versioned_gsm(
    version: int, work_dir: Path, script3d: Path | None = None
) -> tuple[str, Path]:
    name = f"ashiba_line_v{version}"
    hsf_dst = work_dir / name
    if hsf_dst.exists():
        shutil.rmtree(hsf_dst)
    shutil.copytree(HSF_SRC, hsf_dst)
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


def main() -> None:
    version = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    keep = "--keep" in sys.argv
    script3d = None
    if "--script3d" in sys.argv:
        script3d = Path(sys.argv[sys.argv.index("--script3d") + 1])
    work_dir = ROOT / "out" / "gsm_dev"
    work_dir.mkdir(parents=True, exist_ok=True)

    name, gsm = build_versioned_gsm(version, work_dir, script3d)
    print(f"コンパイル完了: {gsm.name}")

    c = ArchicadClient()
    c.add_file_to_embedded_library(str(gsm), gsm.name)
    print("埋め込みライブラリへ追加")

    elem = c.create_object(name, 50000, 50000)
    guid = elem["elementId"]["guid"]
    print(f"テスト配置: {guid}")

    # 検証は3Dプレビュー画像で行う。
    # 注意: Get3DBoundingBoxes はオブジェクトに対して
    # 「2D記号の外形×高さパラメータ」のフォールバック値を返すことがあり
    # 3D生成の検証には使えない（実機で確認済みの落とし穴）。
    c.set_gdl_parameters(
        elem,
        {
            "spanList": "1800,1800,1800,1800,900",
            "postList": "3600,3600,3600,1800,450",
            "jackOut": 0.1,
            "standoff": 0.3,
        },
    )
    import base64
    for img_type in ("3D", "2D"):
        resp = c.tapir(
            "GetElementPreviewImage",
            {"elementId": elem["elementId"], "imageType": img_type,
             "width": 700, "height": 700},
        )
        img = base64.b64decode(resp["previewImage"])
        p = work_dir / f"{name}_{img_type}.png"
        p.write_bytes(img)
        print(f"プレビュー保存 ({len(img)}B): {p}")

    if not keep:
        c.delete_elements([elem])
        print("テスト要素を削除（--keep で残せます）")


if __name__ == "__main__":
    main()
