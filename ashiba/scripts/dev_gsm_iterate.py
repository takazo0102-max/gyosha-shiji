"""GDL開発イテレーション: HSFソースを版名でクローン→GSMコンパイル→
埋め込みライブラリ注入→テスト配置→プレビュー画像で検証.

埋め込みライブラリは同名上書き不可のため、イテレーションごとに
部品名を <part>_v<N> に変えて新GUIDで追加する（検証後に要素は削除）。

使い方:
  python3 scripts/dev_gsm_iterate.py <version> [--part ashiba_line] [--keep]
  python3 scripts/dev_gsm_iterate.py 1 --part ashiba_detail --params detailType=base

detailType はASCIIキー（base/tie/asagao/corner/beam）。日本語を渡すとGDL側の
比較が一致せず「detailType 未知」になる。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ashiba.tapir_adapter import ArchicadClient  # noqa: E402

# LP_XMLConverter（GRAPHISOFT LibDev Toolkit 同梱）の場所。
# 開発者の実機パスを直書きすると、他の環境では意味不明な失敗になる。
# 環境変数 → よくある場所の順で探す
LPX_ENV = "ASHIBA_LP_XMLCONVERTER"
LPX_GLOBS = (
    "~/Downloads/LibDev Toolkit*/Tool/OSX/MakeGDLLib_X86/"
    "LP_XMLConverter.app/Contents/MacOS/LP_XMLConverter",
    "/Applications/LibDev Toolkit*/Tool/OSX/MakeGDLLib_X86/"
    "LP_XMLConverter.app/Contents/MacOS/LP_XMLConverter",
    "~/Applications/LibDev Toolkit*/Tool/OSX/MakeGDLLib_X86/"
    "LP_XMLConverter.app/Contents/MacOS/LP_XMLConverter",
)


def find_lp_xmlconverter() -> str:
    """LP_XMLConverter を探す。見つからなければ何をすればよいかを言う."""
    import glob

    env = os.environ.get(LPX_ENV)
    if env:
        if Path(env).exists():
            return env
        raise SystemExit(
            f"{LPX_ENV} に指定されたパスがありません: {env}"
        )
    for pattern in LPX_GLOBS:
        hits = sorted(glob.glob(str(Path(pattern).expanduser())))
        if hits:
            return hits[-1]      # 版が複数あれば新しい方
    raise SystemExit(
        "LP_XMLConverter が見つかりません。GRAPHISOFT の LibDev Toolkit を"
        "インストールし、見つからない場合は場所を環境変数で指定してください:\n"
        f"  export {LPX_ENV}='/path/to/LP_XMLConverter'"
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
    # EVシャフトの内部足場（各階の床・外周の手すり無し。利用者の指定 2026-10-28）
    "ashiba_stage": {
        "images": ("3D", "2D"),
        "params": {"spanU": "1829", "spanV": "1219", "lvList": "440,1565,3365,5165,6965,8765",
                   "deckH": 8.765, "deckList": "1565,5165", "guardOn": False, "stName": "EV1",
                   "lvList": "440,1565,3365,5165,6965,8765", "deckList": "1565,3365,5165,6965",
                   "hatchZ": "1565,3365,5165,6965,8765", "ladOn": False},
    },
    # 階段の上（利用者の指定 2026-10-28）。--profile ashiba_stage_stair で使う
    "ashiba_stage_stair": {
        "images": ("3D",),
        "params": {"spanU": "1829,1829,1829", "spanV": "1829", "lvList": "225,900,2700,4500", "deckH": 4.5,
                   "footAxis": 0, "footZ": "0,1080,2410,2880", "footNeg": "0,1575,2925,3375", "stName": "階段室",
                   "postDia": 0.0427, "jackExt": 0.055, "footJk": "55,100,190,100", "ladOn": False},
    },
    # 型枠支保工（利用者の指定 2026-10-28）。--profile ashiba_stage_shoring で使う
    "ashiba_stage_shoring": {
        "images": ("3D", "2D"),
        "params": {"spanU": "1829,1829,1829,1524", "spanV": "1219,1219,1219", "lvList": "200,1325,3125", "deckH": 1.325,
                   "postTop": 4.08, "uheadExt": 0.145, "stName": "2F床 支保工",
                   "postDia": 0.0427, "komaP": 0.45, "sysKind": 0, "jackExt": 0.03, "dkWs": "500,240",
                   "stFl": "0,1325", "inBrN": 7},
    },
    # 外付けのロングスパンの前養生（利用者の指定 2026-10-29: 妻側は足場1スパン、正面に補強）。--profile ashiba_hoist_guard
    "ashiba_hoist_guard": {
        "images": ("3D", "2D"),
        "params": {"hoModel": "KSE-990", "hoReach": 9.955, "hoInside": False, "sideSpan": 1.219,
                   "sbL0": -4.5725, "sbL1": -2.7435, "sbR0": 2.7435, "sbR1": 4.5725, "sideLvP": 1.8, "rowSp": 0.914},
    },
    "ashiba_detail": {
        "images": ("2D",),
        # detailType はASCIIキー（日本語を渡すとGDL側の比較が一致しない）
        "params": {"detailType": "base", "jackOut": 0.2},
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
        [find_lp_xmlconverter(), "hsf2libpart", str(hsf_dst), str(gsm)],
        capture_output=True, text=True,
    )
    out = (res.stdout + res.stderr).replace("\n", " ")
    if not gsm.exists():
        raise SystemExit(f"GSMコンパイル失敗: {out}")
    return name, gsm


def build_current_gsm(part: str, work_dir: Path) -> tuple[str, Path]:
    """HSFの現在の内容からGSMを作る。部品名とGUIDは内容のハッシュから決める.

    版番号を手で振ると、更新を忘れたまま古い埋め込み部品を検証してしまう
    （実機E2Eが数ヶ月前のGSMを検証し続けていた）。内容が変わったときだけ
    名前が変わるので、埋め込みライブラリに無駄に溜まることもない。
    """
    import hashlib

    hsf_src = HSF_DIR / part
    if not hsf_src.is_dir():
        raise SystemExit(f"HSFソースがありません: {hsf_src}")
    h = hashlib.sha256()
    for f in sorted(hsf_src.rglob("*")):
        if f.is_file():
            h.update(f.relative_to(hsf_src).as_posix().encode())
            h.update(f.read_bytes())
    digest = h.hexdigest()[:8]

    name = f"{part}_{digest}"
    hsf_dst = work_dir / name
    if hsf_dst.exists():
        shutil.rmtree(hsf_dst)
    shutil.copytree(hsf_src, hsf_dst)
    lpd = hsf_dst / "libpartdata.xml"
    text = lpd.read_text(encoding="utf-8")
    old_guid = text.split("<MainGUID>")[1].split("</MainGUID>")[0]
    new_guid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"ashiba/{name}")).upper()
    lpd.write_text(text.replace(old_guid, new_guid), encoding="utf-8")

    gsm = work_dir / f"{name}.gsm"
    if gsm.exists():
        gsm.unlink()
    res = subprocess.run(
        [find_lp_xmlconverter(), "hsf2libpart", str(hsf_dst), str(gsm)],
        capture_output=True, text=True,
    )
    if not gsm.exists():
        raise SystemExit(
            f"GSMコンパイル失敗: {(res.stdout + res.stderr)}".replace("\n", " ")
        )
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
        # 整数パラメータ（warnPen・nRows等）にfloatを送ると型不一致で弾かれる
        try:
            out[k] = int(v)
        except ValueError:
            try:
                out[k] = float(v)
            except ValueError:
                out[k] = v
    return out


def main() -> None:
    # 第1引数は版番号。部品名を渡す間違いが多いので、使い方を出して止める
    if len(sys.argv) > 1 and not sys.argv[1].lstrip("-").isdigit():
        raise SystemExit(
            f"第1引数は版番号（数字）です: {sys.argv[1]!r}\n"
            "  python3 scripts/dev_gsm_iterate.py <版番号> "
            "[--part ashiba_line|ashiba_detail] [--params k=v ...] [--keep]"
        )
    version = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    keep = "--keep" in sys.argv
    part = "ashiba_line"
    if "--part" in sys.argv:
        part = sys.argv[sys.argv.index("--part") + 1]
    script3d = None
    if "--script3d" in sys.argv:
        script3d = Path(sys.argv[sys.argv.index("--script3d") + 1])
    profile = PART_PROFILES.get(part, {"images": ("2D",), "params": {}})
    if "--profile" in sys.argv:
        profile = PART_PROFILES[sys.argv[sys.argv.index("--profile") + 1]]
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
