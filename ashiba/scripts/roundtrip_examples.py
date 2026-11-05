"""全サンプルを解いて plan.json から実機に再配置し、GDLパラメータの読み戻しを照合する.

place_from_plan_json.py を examples/*.json の全部に対して回す。文字列パラメータの
255文字切れ（壁つなぎが多い面で上層が消えていた）のような「配置は成功するのに
図が欠ける」事故は、この照合でしか見つからない。GDLやパラメータを変えたら回す。

使い方:
  python3 scripts/roundtrip_examples.py            # 全サンプル
  python3 scripts/roundtrip_examples.py waku_composite rect_30x20
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def run(example: Path) -> tuple[bool, str]:
    out = ROOT / "out" / f"reg_{example.stem}"
    cli = subprocess.run(
        [PY, "-m", "ashiba.cli", str(example), "--out", str(out)],
        cwd=ROOT, capture_output=True, text=True,
        env={**__import__("os").environ, "PYTHONPATH": str(ROOT / "src")},
    )
    if cli.returncode != 0:
        return False, "CLI失敗: " + (cli.stderr or cli.stdout).strip().splitlines()[-1]
    plans = sorted(out.glob("*_plan.json"))
    if not plans:
        return False, "plan.json が出力されていません"
    rt = subprocess.run(
        [PY, str(ROOT / "scripts" / "place_from_plan_json.py"), str(plans[0])],
        cwd=ROOT, capture_output=True, text=True,
    )
    text = rt.stdout + rt.stderr
    ok = "全パラメータ一致" in text and rt.returncode == 0
    if ok:
        return True, "全パラメータ一致"
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return False, " / ".join(lines[-4:])[:300]


def main() -> int:
    names = sys.argv[1:]
    examples = (
        [ROOT / "examples" / f"{n}.json" for n in names]
        if names else sorted((ROOT / "examples").glob("*.json"))
    )
    failed = 0
    for ex in examples:
        ok, msg = run(ex)
        failed += 0 if ok else 1
        print(f"{'OK ' if ok else 'NG '} {ex.stem}: {msg}")
    print(f"\n{len(examples) - failed}/{len(examples)} 一致")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
