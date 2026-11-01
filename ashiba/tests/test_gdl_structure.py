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
    # 予約語（2026-11-01、仮囲いでパネルの上端を top と名付けて、部品のパラメータが1つも変えられなくなった。del top の top）
    "top",
    # 2026-11-01、乗入れ構台で水平つなぎの段数を nTr と名付けて、部品のパラメータが1つも読めなくなった（座標変換の数を
    # 返す関数 NTR）。値の個数を返す NSP も
    "ntr", "nsp",
    # 2026-11-01、仮設建物の階段の幅のパラメータを stW と名付けて GSM に変換できなかった（文字の幅 STW）
    "stw",
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

    def test_parameter_names(self):
        """パラメータの名前も組み込み名は不可（2026-11-01、仮設建物の階段の幅を stW と名付けて、GSM の変換が「GDL keyword」で
        失敗した。文字の幅の関数 STW）."""
        bad = []
        for p in sorted(HSF.glob("*/paramlist.xml")):
            for n in re.findall(r'Name="([^"]+)"', p.read_text(encoding="utf-8-sig")):
                if n.lower() in GDL_BUILTINS:
                    bad.append(f"{p.parent.name}: {n}")
        self.assertEqual(bad, [])

    def test_detects_fra(self):
        self.assertTrue(builtin_shadows("\tfra = atn(1)\n"))
        self.assertEqual(builtin_shadows("\tfrAng = atn(1)\nif a = 1 then b = 2\n"), [])
        self.assertTrue(builtin_shadows("top = lift + pnH\n"))


# ループの中の座標変換（add・rot・mul）と del の釣り合い。1回ずれると回るたびに積み重なって部材が散らばる
# （2026-10-31、山留めの部品で add＋addz に del 1 で、切梁上の足場のブラケットが根切りの外へ点々と散った）
TRANSFORM = re.compile(r"^(add|addx|addy|addz|rot|rotx|roty|rotz|mul|mulx|muly|mulz|xform)\b")
# if の中で開いて別の if で閉じる・del の数を式で書くものは数えられない
COND_DEL_PARTS = {"ashiba_hoist", "ashiba_line", "ashiba_member", "ashiba_stage"}


def loop_transform_leaks(text: str) -> list[str]:
    out, stack = [], []                  # [種類, 行, 変換の増減, then の増減]
    for n, ln in _logical_lines(text):
        low = ln.lower()
        if not low:
            continue
        if re.match(r"^if\b.*\bthen$", low):
            stack.append(["if", n, 0, None])
            continue
        if low == "else" and stack and stack[-1][0] == "if":
            stack[-1][3], stack[-1][2] = stack[-1][2], 0
            continue
        if low == "endif" and stack and stack[-1][0] == "if":
            _k, s, d, t = stack.pop()
            if t is not None and t != d:
                out.append(f"{s}行目の if と else で座標変換の数が違う（{t:+d} と {d:+d}）")
            if stack:
                stack[-1][2] += d
            continue
        if re.match(r"^(for|while)\b", low):
            stack.append([low.split()[0], n, 0, None])
            continue
        if re.match(r"^(next|endwhile)\b", low):
            if stack:
                k, s, d, _t = stack.pop()
                if d:
                    out.append(f"{s}行目の {k} の中で座標変換が {d:+d}（del の数が合わない）")
            continue
        single = re.match(r"^if\b.*?\bthen\s+(\S.*)$", low)
        body = single.group(1) if single else low
        m = re.match(r"^del\s+(\d+)\s*$", body)
        if stack:
            stack[-1][2] += -int(m.group(1)) if m else (1 if TRANSFORM.match(body) else 0)
    return out


class TestLoopTransforms(unittest.TestCase):
    def test_every_3d_script(self):
        for p in sorted(HSF.glob("*/scripts/3d.gdl")):
            if p.parent.parent.name in COND_DEL_PARTS:
                continue
            with self.subTest(script=p.parent.parent.name):
                self.assertEqual(loop_transform_leaks(p.read_text(encoding="utf-8-sig")), [])

    def test_detects_add_addz_del_1(self):
        self.assertTrue(loop_transform_leaks("for i = 1 to 2\n\tadd 1, 0, 0\n\taddz 1\n\tblock 1, 1, 1\n\tdel 1\nnext i\n"))
        self.assertEqual(loop_transform_leaks("for i = 1 to 2\n\tif a then\n\t\tadd 1, 0, 0\n\telse\n\t\taddx 2\n"
                                              "\tendif\n\tblock 1, 1, 1\n\tdel 1\nnext i\n"), [])


def array_scalar_clashes(scripts: list[str]) -> list[str]:
    """dim で配列にした名前を、大文字小文字だけ違う名前で数（スカラー）として代入していないか（GDL は大文字小文字を区別しない）."""
    arrays, scalars = {}, {}
    for text in scripts:
        for raw in text.splitlines():
            line = _strip(raw)
            for m in re.finditer(r"\bdim\s+([A-Za-z_]\w*)\s*\[", line, re.I):
                arrays.setdefault(m.group(1).lower(), set()).add(m.group(1))
            m = re.match(r"\s*([A-Za-z_]\w*)\s*=", line)
            if m:
                scalars.setdefault(m.group(1).lower(), set()).add(m.group(1))
    return [f"{sorted(arrays[k])} と {sorted(scalars[k])}" for k in arrays if k in scalars and scalars[k] - arrays[k]]


class TestNoArrayScalarClash(unittest.TestCase):
    """2026-11-01、移動式クレーン（ashiba_crane）で作業半径の配列 wr と車輪の半径 wR を同じ名前にして、部品のパラメータが
    1つも読めず置いても設定に失敗した."""

    def test_every_part(self):
        """スクリプトごとに、その前に動くマスタースクリプト（1d.gdl）と合わせて見る（別のスクリプトの変数は別物）."""
        for d in sorted(p for p in HSF.iterdir() if (p / "scripts").is_dir()):
            master = d / "scripts" / "1d.gdl"
            head = [master.read_text(encoding="utf-8-sig")] if master.exists() else []
            for f in sorted((d / "scripts").glob("*.gdl")):
                with self.subTest(part=d.name, script=f.name):
                    body = [] if f == master else [f.read_text(encoding="utf-8-sig")]
                    self.assertEqual(array_scalar_clashes(head + body), [])

    def test_detects_case_only_difference(self):
        self.assertTrue(array_scalar_clashes(["dim wr[]\nwR = 0.6\n"]))
        self.assertEqual(array_scalar_clashes(["dim wr[]\nwr[1] = 0.6\n"]), [])


class TestNoDecimalStr(unittest.TestCase):
    """2026-11-01、移動式クレーン（ashiba_crane）の 2D で str(x, 1, 1)（長さが小数の桁に足りない）を使ったら、平面図に
    この部品の 2D が1本も出なかった（GetElementPreviewImage の 2D は描けていて気付きにくい）。小数を出すなら長さに余裕を
    （str(x, 4, 1) は詳細図で使っている）、整数は str(数, 1, 0)."""

    def test_every_script(self):
        bad = []
        for f in sorted(HSF.glob("*/scripts/*.gdl")):
            for i, raw in enumerate(f.read_text(encoding="utf-8-sig").splitlines(), 1):
                line = _strip(raw)
                for m in re.finditer(r"\bstr\s*\([^\"]*?,\s*(\d+)\s*,\s*(\d+)\s*\)", line, re.I):
                    if int(m.group(2)) > 0 and int(m.group(1)) <= int(m.group(2)) + 1:
                        bad.append(f"{f.parent.parent.name}/{f.name}:{i}")
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()


class TestMaterialDefinedOnce(unittest.TestCase):
    """同じ名前の define material をスクリプトの2か所に書くと（別々の if の中でも）、Archicad はその 3D を丸ごと
    描かない。2026-10-25、拡幅ブラケット（ashiba_kbrk）の隅の支柱の分岐に金色をもう一度定義して、ブラケットが
    実機の 3D から全部消えた（GetElementPreviewImage が白紙）."""

    def test_every_script(self):
        bad = []
        for f in sorted(HSF.glob("*/scripts/*.gdl")):
            names = re.findall(r'define\s+material\s+"([^"]+)"', f.read_text(encoding="utf-8-sig"), re.I)
            dup = sorted({n for n in names if names.count(n) > 1})
            if dup:
                bad.append(f"{f.parent.parent.name}/{f.name}: {', '.join(dup)}")
        self.assertEqual(bad, [])


class TestLineLength(unittest.TestCase):
    """GDL の1行が長すぎると部品が壊れる（2026-11-01、仮設建物の型の一覧を 12種類の長い名前にして 761 バイトになり、部品の
    パラメータが1つも変えられなくなった。動いている部品の一番長い行は 522 バイト）."""

    def test_every_script(self):
        bad = []
        for f in sorted(HSF.glob("*/scripts/*.gdl")):
            for i, raw in enumerate(f.read_text(encoding="utf-8-sig").splitlines(), 1):
                if len(raw.encode("utf-8")) > 522:
                    bad.append(f"{f.parent.parent.name}/{f.name}:{i}（{len(raw.encode('utf-8'))} バイト）")
        self.assertEqual(bad, [])
