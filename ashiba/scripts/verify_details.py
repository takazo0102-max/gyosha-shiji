"""詳細図5枚の実機検証: 1回のGSM注入で5種すべてを描画し、
埋め込み法規チェックが違反時に発火することまで確認する.

埋め込みライブラリは同名上書き不可なので、部品追加は1回だけ行い、
detailType パラメータを切り替えて5枚ぶん配置・プレビューする。

使い方: python3 scripts/verify_details.py <version> [--keep]
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ashiba.tapir_adapter import ArchicadClient, TapirError  # noqa: E402
from dev_gsm_iterate import build_current_gsm  # noqa: E402

# (ASCIIキー, 表示名, 適合パラメータ, 違反パラメータ)
# detailType は必ずASCII。日本語値は外部から渡すとGDL側の比較が一致しない（実機確認済み）
CASES = [
    ("base", "脚部", {"jackOut": 0.2}, {"jackOut": 0.35}),
    ("tie", "壁つなぎ", {"tieV": 3.6, "tieH": 5.4}, {"tieV": 5.4, "tieH": 6.0}),
    ("asagao", "朝顔",
     {"asagaoProj": 2.0, "asagaoAngle": 25.0},
     {"asagaoProj": 1.5, "asagaoAngle": 15.0}),
    ("corner", "コーナー", {"standoff": 0.3}, None),
    ("beam", "梁枠", {"beamSpan": 3.6}, {"beamSpan": 4.2}),
]


def preview(c: ArchicadClient, elem: dict, out: Path) -> int:
    resp = c.tapir(
        "GetElementPreviewImage",
        {"elementId": elem["elementId"], "imageType": "2D",
         "width": 1000, "height": 1000},
    )
    img = base64.b64decode(resp["previewImage"])
    out.write_bytes(img)
    return len(img)


def main() -> None:
    keep = "--keep" in sys.argv
    work = ROOT / "out" / "details"
    work.mkdir(parents=True, exist_ok=True)

    # 部品名はHSFの内容ハッシュ。版番号を手で振ると、更新を忘れたまま
    # 古い埋め込み部品を検証してしまう
    name, gsm = build_current_gsm("ashiba_detail", work)
    print(f"コンパイル: {gsm.name}")

    c = ArchicadClient()
    try:
        c.add_file_to_embedded_library(str(gsm), gsm.name)
        print("埋め込みライブラリへ追加（1回のみ）")
    except TapirError:
        print("同じ内容の部品が既にあるのでそれを使います")

    placed: list[dict] = []
    failures: list[str] = []
    sizes: dict[str, int] = {}
    x = 0
    for key, jp, ok_params, ng_params in CASES:
        for label, params in (("適合", ok_params), ("違反", ng_params)):
            if params is None:
                continue
            elem = c.create_object(name, x * 4000, 0)
            x += 1
            placed.append(elem)
            c.set_gdl_parameters(elem, {"detailType": key, **params})
            p = work / f"{jp}_{label}.png"
            size = preview(c, elem, p)
            sizes[f"{jp}_{label}"] = size
            if size <= 8000:  # 空白画像＝GDLエラー
                failures.append(f"{jp}({label}): 描画なし")
            print(f"  {jp:<6}{label}: {size:>6}B  {p.name}")

    # 5種が同じ絵になっていないこと（detailTypeが効かず全部同じ図になる事故の検出）
    ok_sizes = [sizes[f"{jp}_適合"] for _k, jp, _o, _n in CASES]
    if len(set(ok_sizes)) < len(ok_sizes):
        failures.append(f"詳細種別が切り替わっていない疑い（画像サイズが同一）: {ok_sizes}")
    # 違反ケースは警告が増える分、適合ケースと必ず異なる
    for _k, jp, _o, ng in CASES:
        if ng is None:
            continue
        if sizes[f"{jp}_違反"] == sizes[f"{jp}_適合"]:
            failures.append(f"{jp}: 違反時に警告が出ていない疑い")

    if not keep:
        c.delete_elements(placed)
        print(f"テスト要素 {len(placed)}個を削除")

    if failures:
        raise SystemExit("NG: " + " / ".join(failures))
    print(f"詳細図 {len(CASES)}種すべて描画OK（適合・違反 計{len(placed)}枚）")


if __name__ == "__main__":
    main()
