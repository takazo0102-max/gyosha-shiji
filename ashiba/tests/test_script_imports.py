"""scripts/ どうしの読み込み（関数の中も）で、読む名前が相手のスクリプトにあるか.

2026-11-01 に床の開口養生を scripts/opening_run.py で作ったとき、足場の「開口」の同じ名前のスクリプトを上書きし、
昇降機（hoist_run.py の関数の中の from opening_run import OUT_DIR, building_of, guide_line）が押すと必ず落ちていた。
関数の中の読み込みは動かすまで分からないので、ここで名前を突き合わせる（2026-11-05 の全部のコマンドの試験で見つけた）.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SRC = Path(__file__).resolve().parents[1] / "src" / "ashiba"


def top_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            for t in (node.targets if isinstance(node, ast.Assign) else [node.target]):
                for n in ast.walk(t):
                    if isinstance(n, ast.Name):
                        names.add(n.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                names.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, (ast.If, ast.Try)):
            for sub in ast.walk(node):
                if isinstance(sub, (ast.FunctionDef, ast.ClassDef)):
                    names.add(sub.name)
                elif isinstance(sub, ast.Assign):
                    for t in sub.targets:
                        if isinstance(t, ast.Name):
                            names.add(t.id)
                elif isinstance(sub, (ast.Import, ast.ImportFrom)):
                    for a in sub.names:
                        names.add((a.asname or a.name).split(".")[0])
    return names


class TestScriptImports(unittest.TestCase):
    def test_names_exist(self):
        mods = {p.stem: p for p in SCRIPTS.glob("*.py")}
        mods.update({f"ashiba.{p.stem}": p for p in SRC.glob("*.py")})
        cache: dict[str, set] = {}
        bad = []
        for p in sorted(SCRIPTS.glob("*.py")):
            for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom) and node.module in mods and node.level == 0:
                    have = cache.setdefault(node.module, top_names(mods[node.module]))
                    for a in node.names:
                        if a.name != "*" and a.name not in have:
                            bad.append(f"{p.name}: from {node.module} import {a.name}")
        self.assertEqual(bad, [])

    def test_palette_scripts_exist_and_differ(self):
        """パレットの操作のスクリプトはあり、足場の「開口」と床の「開口養生」は別のスクリプト."""
        import sys

        sys.path.insert(0, str(SRC.parent))
        from ashiba.palette import ACTIONS

        for a in ACTIONS:
            self.assertTrue((SCRIPTS / a.script).exists(), a.title)
        by = {a.title: a.script for a in ACTIONS}
        self.assertNotEqual(by["開口"], by["開口養生"])


if __name__ == "__main__":
    unittest.main()
