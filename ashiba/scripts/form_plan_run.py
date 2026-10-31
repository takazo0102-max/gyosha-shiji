"""型枠支保工計画図を作る（利用者の指定 2026-10-31: 型枠しほこう計画図作成できる？ → 伏図・断面図と詳細図・構造計算書・計画届の要否と様式）.

  python3 scripts/form_plan_run.py        # ashiba_out/型枠_計画.json（form_run.py が書く）から

ashiba_out に 型枠支保工計画図.html・.pdf（A3 横）と 型枠支保工_計算書.xlsx を書く。先に「型枠」（form_run.py）で型枠を置いておく.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))


def main(argv=None) -> int:
    import run_from_archicad as R
    from ashiba.form_drawings import build_html, build_xlsx, notice_info, to_pdf

    src = R.OUT_DIR / "型枠_計画.json"
    if not src.exists():
        print("型枠支保工計画図: 先に「型枠」で型枠を置いてください（ashiba_out/型枠_計画.json がありません）")
        return 1
    plan = json.loads(src.read_text(encoding="utf-8"))
    html_path = R.OUT_DIR / "型枠支保工計画図.html"
    html_path.write_text(build_html(plan), encoding="utf-8")
    pdf_path = R.OUT_DIR / "型枠支保工計画図.pdf"
    ok = to_pdf(html_path, pdf_path)
    xlsx = R.OUT_DIR / "型枠支保工_計算書.xlsx"
    build_xlsx(plan, xlsx)
    ni = notice_info(plan)
    print(f"型枠支保工計画図: {pdf_path if ok else html_path}")
    print(f"  計算書: {xlsx}")
    print(f"  計画届: {'要る' if ni['required'] else '要らない'}（支柱の高さの最大 {ni['max']:.0f}・{ni['where']}。3.5m 以上で要る）")
    if not ok:
        print("  注意: Chrome が無いので PDF にできませんでした。HTML をブラウザで開いて印刷してください")
    return 0


if __name__ == "__main__":
    sys.exit(main())
