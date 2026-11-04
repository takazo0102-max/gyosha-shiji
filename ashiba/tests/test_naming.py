"""置いたものの名前の番号と控えの片付け（src/ashiba/naming.py。利用者の指定 2026-11-05「使いやすいように」）."""

import unittest

from _path import SRC  # noqa: F401

from ashiba.naming import ordinal, prune_gone

G = "AAAAAAAA-0000-0000-0000-00000000000{}".format


class Fake:
    def __init__(self, alive, fail=False):
        self.alive, self.fail = set(alive), fail

    def tapir(self, cmd, params):
        assert cmd == "GetDetailsOfElements"
        if self.fail:
            raise RuntimeError("Archicad が応答しない")
        return {"detailsOfElements": [{"type": "Object"} if e["elementId"]["guid"] in self.alive else {"error": "なし"}
                                      for e in params["elements"]]}


class TestNaming(unittest.TestCase):
    def test_ordinal(self):
        rec = {"線a": G(1), "線b": G(2)}
        self.assertEqual(ordinal(rec, "線b", 0), 2)        # 同じ線は前の番号のまま
        self.assertEqual(ordinal(rec, "線c", 0), 3)        # 新しい線は控えの続き
        self.assertEqual(ordinal(rec, "線d", 1), 4)

    def test_prune_gone(self):
        """Archicad で消したものは控えから除く（消したクレーンが残り、次のクレーンが「クレーン2」になった）."""
        rec = {"線a": [G(1), G(2)], "線b": [G(3)], "線c": {"guid": G(4), "name": "柵3"}, "メモ": "x"}
        got = prune_gone(Fake({G(2), G(4)}), rec)
        self.assertEqual(list(got), ["線a", "線c", "メモ"])   # 1つでも残っていれば残す。GUID の無い値は触らない
        self.assertEqual(ordinal(got, "線z", 0), 4)
        self.assertEqual(prune_gone(Fake(set(), fail=True), rec), rec)   # 読めなければそのまま


if __name__ == "__main__":
    unittest.main()
