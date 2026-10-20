"""GDL スクリプトの if/endif・for/next・while/endwhile の釣り合い.

GDL は構文が崩れると Archicad で黙って何も描かない（3D が白紙）。2026-10-21、先行手すりの書き換えで
endif が1つ余り、足場ラインの 3D が全部消えた（実機のプレビューで発見）。コンパイラ（LP_XMLConverter）は
これを通すので、ここで数えて止める。
"""

import re
import unittest
from pathlib import Path

HSF = Path(__file__).resolve().parents[1] / "gdl" / "hsf"


def _strip(line: str) -> str:
    out, q = [], False
    for ch in line:
        if ch == '"':
            q = not q
        if ch == "!" and not q:
            break
        out.append(ch)
    return "".join(out).strip()


def balance(text: str) -> list[str]:
    errs, stack = [], []
    for n, raw in enumerate(text.splitlines(), 1):
        ln = _strip(raw)
        low = ln.lower()
        if not low:
            continue
        if re.match(r"^if\b.*\bthen$", low):
            stack.append(("if", n))
        elif re.match(r"^for\b", low):
            stack.append(("for", n))
        elif re.match(r"^while\b.*\bdo$", low):
            stack.append(("while", n))
        elif low == "endif":
            if not stack or stack[-1][0] != "if":
                errs.append(f"{n}行目: 対応する if の無い endif（開いているのは {stack[-1] if stack else 'なし'}）")
            else:
                stack.pop()
        elif re.match(r"^next\b", low):
            if not stack or stack[-1][0] != "for":
                errs.append(f"{n}行目: 対応する for の無い next（開いているのは {stack[-1] if stack else 'なし'}）")
            else:
                stack.pop()
        elif low == "endwhile":
            if not stack or stack[-1][0] != "while":
                errs.append(f"{n}行目: 対応する while の無い endwhile")
            else:
                stack.pop()
    errs += [f"{n}行目の {k} が閉じていない" for k, n in stack]
    return errs


class TestGdlBlocksBalance(unittest.TestCase):
    def test_every_script(self):
        scripts = sorted(HSF.glob("*/scripts/*.gdl"))
        self.assertTrue(scripts)
        for p in scripts:
            with self.subTest(script=f"{p.parent.parent.name}/{p.name}"):
                self.assertEqual(balance(p.read_text(encoding="utf-8-sig")), [])

    def test_detects_a_stray_endif(self):
        self.assertTrue(balance("if a then\n\tb = 1\nendif\nendif\n"))
        self.assertEqual(balance("if a then b = 1\nfor i = 1 to 2\nnext i\n"), [])


if __name__ == "__main__":
    unittest.main()
