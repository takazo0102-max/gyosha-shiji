"""HSF の変種を実機でコンパイル・配置・プレビューして、どの変更で描けなくなったかを切り分ける.

GDL はエラーがあると黙って何も描かない（2Dが真っ白になる）。どのスクリプトのどの
ブロックが原因かは、ブロックを外した変種を順に試すのが確実。

使い方:
  python3 scripts/bisect_gdl.py                 # 既定の変種（下の VARIANTS）
  python3 scripts/bisect_gdl.py --part ashiba_line --view 2D
各変種について「描けた／真っ白」を出す。
"""

from __future__ import annotations

import base64
import io
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ashiba.cli import load_spec, solve_all  # noqa: E402
from ashiba.gdl_params import line_params  # noqa: E402
from ashiba.tapir_adapter import ArchicadClient, TapirError  # noqa: E402
from dev_gsm_iterate import HSF_DIR, find_lp_xmlconverter  # noqa: E402

# 変種: (名前, {相対パス: [(置換前, 置換後), ...]})。置換前が無ければその変種は飛ばす
GOOD = "c168d4b0"     # 描けていた最後のコミット（布材をつなぎ材の形に）
VARIANTS = [
    ("current_fine", {"scripts/3d.gdl": [("d3 = detail3d\n", "d3 = 1\n")]}),
    ("good_fine", {"scripts/3d.gdl": "@" + GOOD}),
    ("no_new_brace", {"scripts/3d.gdl": [("d3 = detail3d\n", "d3 = 1\n"), ('and eoB = 0 and serType <> "W" then', 'and eoB = 0 and serType = "ZZ" then')]}),
    ("no_deck_detail", {"scripts/3d.gdl": [("d3 = detail3d\n", "d3 = 1\n"), ("\tif isLite = 0 then\n\t\tfor hd870", "\tif isLite = 9 then\n\t\tfor hd870")]}),
    ("no_deck870", {"scripts/3d.gdl": [("d3 = detail3d\n", "d3 = 1\n"), ("\t\t\t\t\t\tgosub 870\n", "")]}),
    ("no_toe", {"scripts/3d.gdl": [("d3 = detail3d\n", "d3 = 1\n"), ("\t\t\t\t\tblock spans[ip] + 0.07, 0.008, 0.150\n\t\t\t\t\tblock spans[ip] + 0.07, 0.140, 0.004\n", "")]}),
    ("no_850", {"scripts/3d.gdl": [("d3 = detail3d\n", "d3 = 1\n"), ("\t\t\t\tgosub 850\n", "")]}),
]


def build_variant(part: str, name: str, patches: dict, work: Path) -> tuple[str, Path]:
    dst = work / f"{part}_{name}"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(HSF_DIR / part, dst)
    for rel, reps in patches.items():
        f = dst / rel
        if reps is None:
            f.unlink()
            continue
        if isinstance(reps, str) and reps.startswith("@"):
            # そのコミットのファイルに差し替える
            prefix = subprocess.run(["git", "rev-parse", "--show-prefix"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
            data = subprocess.run(["git", "show", f"{reps[1:]}:{prefix}gdl/hsf/{part}/{rel}"], capture_output=True, check=True, cwd=ROOT).stdout
            f.write_bytes(data)
            continue
        s = f.read_text(encoding="utf-8")
        for old, new in reps:
            if old not in s:
                raise LookupError(f"{name}: {rel} に置換前の文が無い: {old[:40]}")
            s = s.replace(old, new)
        f.write_text(s, encoding="utf-8")
    lpd = dst / "libpartdata.xml"
    t = lpd.read_text(encoding="utf-8")
    old_guid = t.split("<MainGUID>")[1].split("</MainGUID>")[0]
    lpd.write_text(t.replace(old_guid, str(uuid.uuid4()).upper()), encoding="utf-8")
    gsm = work / f"{part}_{name}.gsm"
    if gsm.exists():
        gsm.unlink()
    res = subprocess.run([find_lp_xmlconverter(), "hsf2libpart", str(dst), str(gsm)], capture_output=True, text=True)
    if not gsm.exists():
        raise SystemExit(f"{name}: コンパイル失敗: {(res.stdout + res.stderr)[:300]}")
    return f"{part}_{name}", gsm


def _dark_pixels(png: bytes, threshold: int = 200) -> tuple[int, int]:
    """PNG（8bit・RGB/RGBA/グレー・インターレース無し）の暗い画素の数と総画素数. 標準ライブラリだけで読む.

    以前は PIL が無いと「ファイルが 60KB 未満なら真っ白」と見ていて、寸法ツールで寸法を部品から外したら
    線の少ない平面が 57KB になり、描けているのに真っ白と判定した（2026-10-20 スモーク）。
    """
    import struct
    import zlib

    pos = 8
    width = height = 0
    ctype = 2
    data = b""
    while pos < len(png):
        n = struct.unpack(">I", png[pos:pos + 4])[0]
        kind = png[pos + 4:pos + 8]
        body = png[pos + 8:pos + 8 + n]
        if kind == b"IHDR":
            width, height, depth, ctype, _c, _f, inter = struct.unpack(">IIBBBBB", body)
            if depth != 8 or inter != 0 or ctype not in (0, 2, 4, 6):
                raise ValueError("対応していない PNG")
        elif kind == b"IDAT":
            data += body
        pos += 12 + n
    bpp = {0: 1, 2: 3, 4: 2, 6: 4}[ctype]
    raw = zlib.decompress(data)
    stride = width * bpp
    prev = bytearray(stride)
    dark = 0
    i = 0
    for _y in range(height):
        f = raw[i]
        line = bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0
            b = prev[x]
            c = prev[x - bpp] if x >= bpp else 0
            if f == 1:
                line[x] = (line[x] + a) & 255
            elif f == 2:
                line[x] = (line[x] + b) & 255
            elif f == 3:
                line[x] = (line[x] + ((a + b) >> 1)) & 255
            elif f == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        for x in range(0, stride, bpp):
            if line[x] < threshold:
                dark += 1
        prev = line
    return dark, width * height


def is_blank(png: bytes) -> bool:
    """PNG がほぼ真っ白か（暗い画素が 0.02% 未満）."""
    try:
        dark, total = _dark_pixels(png)
        return dark < total * 0.0002
    except (ValueError, KeyError, Exception):  # noqa: BLE001 — 読めない PNG は従来の大きさで見る
        return len(png) < 20000


def main() -> int:
    part = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--part=")), "ashiba_line")
    view = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--view=")), "2D")
    spec = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--spec=")), str(ROOT / "examples" / "dev" / "small_stage.json"))
    c = ArchicadClient()
    work = ROOT / "out" / "gsm_bisect"
    work.mkdir(parents=True, exist_ok=True)
    r = solve_all(load_spec(Path(spec)))
    ep = r.model.plan.edges[0]
    base = line_params(r.model, ep, stair_plan=r.stair_plan, openings=r.openings, platforms=r.platforms,
                       bracket_sections=r.brackets, terrain=r.terrain)
    out = ROOT / "out" / "view_check"
    out.mkdir(parents=True, exist_ok=True)
    for i, (name, patches) in enumerate(VARIANTS):
        try:
            pname, gsm = build_variant(part, name + "_" + uuid.uuid4().hex[:4], patches, work)
        except LookupError as e:
            print(f"- {name}: 飛ばす（{e}）")
            continue
        try:
            c.add_file_to_embedded_library(str(gsm), gsm.name)
        except TapirError:
            pass
        el = c.create_object(pname, 0, -70000 - 10000 * i)
        try:
            # その変種が持つパラメータだけ送る（無い名前を1つでも送ると全パラメータが落ちる）
            item = c.tapir("GetGDLParametersOfElements", {"elements": [el]})["gdlParametersOfElements"][0]
            have = {p["name"] for p in item.get("gdlParameters", item.get("parameters", []))}
            if not have:
                print(f"- {name}: パラメータを読めない（部品が壊れている可能性）: {str(item)[:200]}")
                continue
            c.set_gdl_parameters(el, {k: v for k, v in {**base, "viewMode": "plan"}.items() if k in have}, pname)
            resp = c.tapir("GetElementPreviewImage", {"elementId": el["elementId"], "imageType": view, "width": 2400, "height": 1500})
            png = base64.b64decode(resp["previewImage"])
            (out / f"bisect_{name}.png").write_bytes(png)
            print(f"- {name}: {'真っ白' if is_blank(png) else '描けた'}（{len(png)} bytes）")
        finally:
            c.delete_elements([el])
    return 0


if __name__ == "__main__":
    sys.exit(main())
