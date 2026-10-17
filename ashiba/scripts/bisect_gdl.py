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
GOOD = "e9b039c4"     # 描けていた最後のコミット（3Dのスパン寸法文字）
VARIANTS = [
    ("current", {}),
    ("1d_from_good_no_vl", {"scripts/1d.gdl": "@" + GOOD, "scripts/vl.gdl": None,
                            "libpartdata.xml": [("\t<Script_VL SectVersion=\"20\" SectionFlags=\"0\" SubIdent=\"0\"/>\n", "")]}),
    ("2d_from_good", {"scripts/2d.gdl": "@" + GOOD}),
    ("paramlist_from_good_all_scripts_good", {"paramlist.xml": "@" + GOOD, "scripts/1d.gdl": "@" + GOOD, "scripts/2d.gdl": "@" + GOOD,
                                              "scripts/3d.gdl": "@" + GOOD, "scripts/vl.gdl": None,
                                              "libpartdata.xml": "@" + GOOD}),
    ("paramlist_from_good_scripts_current", {"paramlist.xml": "@" + GOOD}),
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


def is_blank(png: bytes) -> bool:
    """PNG がほぼ真っ白か（PIL が無くても判定できるよう、サイズと一様性を粗く見る）."""
    try:
        from PIL import Image  # type: ignore

        im = Image.open(io.BytesIO(png)).convert("L")
        hist = im.histogram()
        dark = sum(hist[:200])
        return dark < im.width * im.height * 0.0005
    except ImportError:
        return len(png) < 60000     # 2400x1500: 真っ白〜点だけで約20〜50KB、描けていれば70KB超


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
