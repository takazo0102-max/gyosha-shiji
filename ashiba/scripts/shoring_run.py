"""支保工足場（パレットのボタン「支保工足場」）: スラブの型枠の支保工を、パイプサポートの代わりに内部足場（内部ステージ足場の
用途 支保工）で組む（利用者の指定 2026-10-31: しほこう足場を内部足場から作成して 図面化までしてちょ）.

  python3 scripts/shoring_run.py           # 選んだスラブ（何も選んでいなければ全部）を支保工足場に
  python3 scripts/shoring_run.py --pipe    # パイプサポートに戻す

スラブを ashiba_out/支保工足場.json に控え、「型枠」（form_run.py）で置き直す。控えたスラブは、せき板・根太は型枠の部品で、
その下を梁・壁で区切った長方形ごとに部品 ashiba_stage（支柱・布材・ジャッキ・大引受けジャッキ・大引・筋かい・作業床）で受ける
（src/ashiba/shoring_stage.py）。図面は「型枠計画図」（伏図・断面図・計算書・部材等明細書・計画届に支保工足場として出る）.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))


def main(argv=None) -> int:
    import form_run

    argv = list(sys.argv[1:] if argv is None else argv)
    return form_run.main((["--pipe"] if "--pipe" in argv else ["--shoring"]) + [a for a in argv if a != "--pipe"])


if __name__ == "__main__":
    sys.exit(main())
