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


def _logical_lines(text: str):
    """行末の \\ で続く行を1行につなぐ（「if ... and \\」の次の行に then がある複数行の if）。行番号は最初の行."""
    buf, start = "", 0
    for n, raw in enumerate(text.splitlines(), 1):
        ln = _strip(raw)
        if not buf:
            start = n
        if ln.endswith("\\"):
            buf += ln[:-1] + " "
            continue
        yield start, buf + ln
        buf = ""
    if buf:
        yield start, buf


def balance(text: str) -> list[str]:
    errs, stack = [], []
    for n, ln in _logical_lines(text):
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


# GDL の組み込み関数・定数の名前（変数名に使うと構文エラーで 3D が白紙になる。2026-10-21、朝顔のフレ止めで
# 角度を fra（端数の関数 FRA）と名付けて、足場ラインの 3D が全部消えた）
GDL_BUILTINS = {
    "abs", "ceil", "fra", "int", "round_int", "sgn", "sqr", "sqrt", "exp", "log", "sin", "cos", "tan", "atn",
    "acs", "asn", "pi", "rnd", "max", "min", "not", "mod", "str", "strlen", "strsub", "strstr", "split",
    "bittest", "bitset", "vardim1", "vardim2", "request", "ind", "and", "or", "exor",
}


def builtin_shadows(text: str) -> list[str]:
    out = []
    for n, raw in enumerate(text.splitlines(), 1):
        m = re.match(r"^\s*([A-Za-z_]\w*)\s*(\[[^\]]*\])?\s*=", _strip(raw))
        if m and m.group(1).lower() in GDL_BUILTINS:
            out.append(f"{n}行目: 変数名 {m.group(1)} は GDL の組み込み名")
        m = re.match(r"^\s*for\s+([A-Za-z_]\w*)\s*=", _strip(raw), re.I)
        if m and m.group(1).lower() in GDL_BUILTINS:
            out.append(f"{n}行目: ループ変数 {m.group(1)} は GDL の組み込み名")
    return out


class TestNoBuiltinNames(unittest.TestCase):
    def test_every_script(self):
        for p in sorted(HSF.glob("*/scripts/*.gdl")):
            with self.subTest(script=f"{p.parent.parent.name}/{p.name}"):
                self.assertEqual(builtin_shadows(p.read_text(encoding="utf-8-sig")), [])

    def test_detects_fra(self):
        self.assertTrue(builtin_shadows("\tfra = atn(1)\n"))
        self.assertEqual(builtin_shadows("\tfrAng = atn(1)\nif a = 1 then b = 2\n"), [])


if __name__ == "__main__":
    unittest.main()
