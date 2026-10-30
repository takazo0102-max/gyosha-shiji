"""埋め込みライブラリに溜まる版付き部品の整理（Phase 13-3）.

ツールバーは部品（ashiba_line など）を「<名前>_<版8桁>」で埋め込みライブラリに入れる。埋め込んだ部品は
Tapir から上書き・削除できないので、GSM を直すたびに新しい版が足され、古い版はライブラリに残る
（置いた足場は次の実行で新しい版に置き換わる）。長く使うプロジェクトでは古い版が溜まるので、
どの版が使われているかを数え、使われていない古い版を手で消す手順を案内する。

埋め込みライブラリの中身は1つのファイルにまとまっていて、外から一覧できない（2026-10-18 確認）。
数えられるのは「置いた部品が使っている版」だけなので、ライブラリにしか無い版は手順の側で拾う。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

BASES = ("ashiba_line", "ashiba_detail", "ashiba_mvo", "ashiba_spec", "ashiba_tie", "ashiba_net", "ashiba_netbk", "ashiba_sheet", "ashiba_member", "ashiba_xsec", "ashiba_cstep", "ashiba_bridge", "ashiba_stage", "ashiba_walkway", "ashiba_box", "ashiba_side")
_VERSIONED = re.compile(r"^(?P<base>ashiba_[a-z]+)(?:_(?P<ver>[0-9a-f]{8}))?$")


def split_name(name: str) -> tuple[str, str] | None:
    """'ashiba_line_67740d9e' → ('ashiba_line', '67740d9e')。版の無い名前は ('ashiba_line', '')."""
    m = _VERSIONED.match(str(name or "").strip())
    if not m or m.group("base") not in BASES:
        return None
    return m.group("base"), m.group("ver") or ""


def current_versions(gdl_dir: Path) -> dict[str, str]:
    """いまの配布GSMの版（gdl/<名前>.gsm.hash）."""
    out = {}
    for base in BASES:
        p = Path(gdl_dir) / f"{base}.gsm.hash"
        if p.exists():
            out[base] = p.read_text(encoding="utf-8").strip()[:8]
    return out


@dataclass
class VersionReport:
    current: dict[str, str]
    in_use: dict[str, dict[str, int]] = field(default_factory=dict)   # 部品 → 版 → 置いた数

    def old_in_use(self) -> list[tuple[str, str, int]]:
        """今の版ではないのに置かれている部品（次のツールバー実行で置き換わる）."""
        return [(b, v, n) for b, vs in sorted(self.in_use.items()) for v, n in sorted(vs.items())
                if v != self.current.get(b)]

    def lines(self) -> list[str]:
        out = []
        for base in BASES:
            cur = self.current.get(base, "?")
            used = self.in_use.get(base, {})
            used_txt = "・".join(f"{v or '版なし'} {n}個" for v, n in sorted(used.items())) or "置いていない"
            out.append(f"{base}: 今の版 {cur}／置いてある版 {used_txt}")
        old = self.old_in_use()
        placed = [(b, v, n) for b, v, n in old if b != "ashiba_spec"]
        if placed:
            out.append("今の版でない足場部品が置かれています（ツールバーをもう一度実行すると今の版に置き換わります）: "
                       + "・".join(f"{b}_{v} {n}個" for b, v, n in placed))
        spec = [(b, v, n) for b, v, n in old if b == "ashiba_spec"]
        if spec:
            # 足場条件の部品は条件が入っているので、ツールバーは読むだけで置き換えない
            out.append("足場条件の部品は古い版のままです（" + "・".join(f"{b}_{v}" for b, v, _ in spec) + "）。"
                       "条件はそのまま読めます。新しい項目を設定画面に出したいときは、条件を控えてから部品を消し、"
                       "ツールバーを実行して置き直させてください")
        return out


def count_versions(names: Iterable[str], current: dict[str, str]) -> VersionReport:
    rep = VersionReport(current=dict(current))
    for name in names:
        sp = split_name(name)
        if sp is None:
            continue
        base, ver = sp
        rep.in_use.setdefault(base, {})
        rep.in_use[base][ver] = rep.in_use[base].get(ver, 0) + 1
    return rep


CLEANUP_STEPS = (
    "古い版の消し方（Archicad の画面で行う。API では消せない。Archicad 30 の画面で確認 2026-10-18）:",
    "  1. ツールバー（または パレットの「足場2_配置」）を一度実行し、置いてある足場を今の版に置き換える",
    "  2. ファイル → ライブラリとオブジェクト → ライブラリマネージャー を開き、「埋め込みライブラリ」タブ →「ashiba」フォルダ",
    "  3. ashiba_line_／ashiba_detail_／ashiba_mvo_／ashiba_spec_ のうち、末尾の8桁が上の「今の版」とも",
    "     「置いてある版」とも違う部品を選び、下の削除ボタン（赤い ✕）で消す（置いてある版は消さない）",
    "  4. OK で閉じる（「キャンセル」なら何も変わらない）",
    "  ※「ashiba」フォルダごとは消さない。置いてある版まで消え、足場は「見つからない部品」になり、",
    "    足場条件の部品は値が読めなくなる（2026-10-18 実機）。消してしまったら、ツールバーを実行すれば",
    "    今の版が入り直して足場は置き換わる。足場条件の部品は置き直されるので、条件を設定ダイアログで入れ直す",
)
