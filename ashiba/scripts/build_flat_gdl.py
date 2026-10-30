"""HSFソースから単一ファイル参照版 .gdl を生成する.

参照版を手で書くと必ずHSF側とズレる（実際、立面モードと壁つなぎ表示が
入らないまま放置されていた）。生成物にしてズレようがなくしてある。
tests/test_flat_gdl_sync.py が「生成し直した内容と一致するか」を検査する。

使い方:
  python3 scripts/build_flat_gdl.py            # 全パーツを書き出し
  python3 scripts/build_flat_gdl.py --check    # 差分があれば非ゼロ終了
"""

from __future__ import annotations

import sys
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HSF_DIR = ROOT / "gdl" / "hsf"

# 参照版を出すパーツと、その概要（オブジェクト全体の設計意図はHSFの
# どのスクリプトにも属さないのでここに置く）
PARTS = {
    "ashiba_line": {
        "title": "足場ライン オブジェクト（くさび緊結式・1辺=1オブジェクト）",
        "notes": [
            "アーキテクチャ決定（開発指示書2.1）:",
            "  部材1本ごとにオブジェクトを置かず、1つの辺を1つのGDLオブジェクトとし",
            "  内部で支柱・布材・踏板・手すり・幅木・ブレスをパラメトリック生成する。",
            "  Python側は割付を解いてこのオブジェクトを辺の数だけ置くのみ。",
        ],
    },
    "ashiba_detail": {
        "title": "詳細図 2Dシンボル（設置届 添付図・detailTypeで5種を切替）",
        "notes": [
            "方式③: 詳細図は3Dモデルからの投影ではなく2Dシンボルとして描く。",
            "投影に頼ると縮尺1/10〜1/20で必要な納まりの線が出ない。",
        ],
    },
    "ashiba_spec": {
        "title": "足場条件（ツールバーが読む入力条件）",
        "notes": [
            "スラブの近くに置き、設定ダイアログ（基本／高さ・離れ／安全・表示）で条件を入れる。",
            "ツールバーはこの部品のパラメータを読み、デスクトップの JSON より優先する。",
            "パラメータと入力 JSON の対応は src/ashiba/spec_object.py の FIELDS が正。",
        ],
    },
    "ashiba_tie": {
        "title": "壁つなぎ（1本＝1部品）",
        "notes": [
            "足場ラインから分けた部材（利用者の指定 2026-10-20）。ツールバーが壁つなぎの位置ごとに置く。",
            "原点＝内側建地の芯、faceAng で面の向き、+Y が躯体側。平面は ▽ 記号、3Dはクランプ＋本体＋アンカープレート。",
        ],
    },
    "ashiba_net": {
        "title": "水平ネット（躯体と足場の隙間・1面1層に1部品）",
        "notes": [
            "足場条件の「水平ネットの層」で指定した層に、面ごとに置く。平面は網目の格子、3Dは面とロープ。",
        ],
    },
    "ashiba_netbk": {
        "title": "ネットブラケット（内側建地に付けて水平ネットを受ける）",
        "notes": [
            "水平ネットを張る層の、内側建地の位置ごとに置く。腕は躯体側へ（離れ−50）。",
        ],
    },
    "ashiba_sheet": {
        "title": "養生シート（メッシュシート・防音シート。足場の外側の構面・1面に1部品）",
        "notes": [
            "足場条件の「養生材」がなし以外なら、面ごとに置く。地面から支柱の天端まで、出隅は角の外まで回す。",
            "3Dは透ける膜と1枚の幅（1.8m）ごとの継ぎ目、平面は外側の破線と目盛り。",
        ],
    },
    "ashiba_member": {
        "title": "足場の部材（1本＝1部品。足場ラインを部材に分解したとき）",
        "notes": [
            "パレットの「部材に分解」で、足場ラインの支柱・ジャッキ・布材・腕木・手すり・踏板・幅木・ブレースを1本ずつの部品にする。",
            "kind で種類（1支柱 2布材 3踏板 4幅木 5先行手すり 6ブレース 7ジャッキ）、faceAng で向き、zH で下端の高さ。",
            "形は足場ラインの同じ部材と同じ。parentId に分解元の足場ラインの要素ID（「分解を戻す」で使う）。",
        ],
    },
    "ashiba_xsec": {
        "title": "足場断面図 2Dシンボル（2Dで書くときの断面の形・1面に1部品）",
        "notes": [
            "利用者の指定（2026-10-23）: 断面図は3Dの切断ではなく、2Dで書くときの形に（案1）。",
            "支柱は2本線、面に沿う布材・手すり・中桟は切り口の丸、踏板は切り口の矩形に×、腕木・壁つなぎ・朝顔は線。",
            "値は xsec.py が面ごとに入れ、平面の下の行に置いて、切り抜いてレイアウト「足場断面図 A-A」などへ 1/50 で貼る。",
        ],
    },
    "ashiba_stage": {
        "title": "内部ステージ足場（室内に格子に支柱を立て、最上段に全面の作業床・1つの範囲に1部品）",
        "notes": [
            "利用者の指定（2026-10-24）: 内部足場の内部ステージ足場の機能追加して検証して。",
            "原点＝外周の支柱の始めの角、faceAng で長手の向き。支柱の格子・各段の布材（両方向）・全面の作業床・外周の手すり・幅木・筋かい・はしご。",
        ],
    },
    "ashiba_bridge": {
        "title": "屋上への渡り（足場の最上段の床から屋上へ・1箇所に1部品）",
        "notes": [
            "利用者の指定（2026-10-24）: 屋上への渡りもGDL作成して 平面に表記するようにして。",
            "原点＝足場の内側建地列、faceAng で面の向き。床（踏板・斜路の踏桟・段差は踏段、パラペットは天端の上を越える）と両側の手すり・中桟・幅木。平面は外形・手すり・矢印・名前。",
        ],
    },
    "ashiba_kbrk": {
        "title": "拡幅・張出ブラケット（日建 NDBK03H 拡幅305・NDBK06H 張出610・1基に1部品）",
        "notes": [
            "利用者の指定（2026-10-25）: これだよ拡張ブラケット 作り直して／拡張ブラケットGDL作って 配置してみて（カタログ Vol.10 p014）。",
            "原点＝ブラケットを付ける支柱の芯、faceAng で腕の向き、zArm で腕の高さ。緊結部（腕と方杖の下）・背の縦材・腕・方杖・先端の管とホゾ φ36.4、拡幅時は補強単管とスーパークランプ S2C。",
        ],
    },
    "ashiba_hoist": {
        "title": "昇降機（工事用エレベーター・ロングスパン・荷揚げ機・1基に1部品）",
        "notes": [
            "利用者の指定（2026-10-27）: 昇降機の機種表にする・フロアーゲートを描いて数える・機種ごとの形を3Dで描く・昇降機は別オブジェクトで配置できるように。",
            "機種（hoModel）を選ぶと data/hoist_models.csv の荷台・マスト・壁つなぎ間隔で描く（寸法表は scripts/gen_hoist_gdl.py が書き出す）。原点＝足場の外側建地の列の上の昇降機の中心、faceAng で面の向き。",
        ],
    },
    "ashiba_hstage": {
        "title": "昇降機の荷取りステージ（乗り込む所1か所に1部品）",
        "notes": [
            "利用者の指定（2026-10-28）: ブラケットも詳細にして／ステージは高さの調整があるので別オブジェクトにして。",
            "原点＝昇降機の部品と同じ（足場の外側建地の列の上の昇降機の中心）、faceAng で面の向き、zSt で床の高さ（上下に調整でき、次の配置でも残す）。stMode 0＝荷取用金具＋梁枠＋ころばし＋足場板、1＝クランプ式の内側ブラケット＋敷板＋足場板。フロアーゲートは床先に立てる。",
        ],
    },
    "ashiba_box": {
        "title": "足場の箱（超簡易モード。四角い足場を伸び縮みして形を決める）",
        "notes": [
            "利用者の指定（2026-10-30）: 超簡易モードになってない いきなり足場が現れた／箱を作って自分で伸び縮みするような感じ → 一周の箱・ボタンで本体にする。",
            "原点＝内側の建地の列の角。右の辺・上の辺の中ほどのつまみで長手・短手を伸び縮み（定尺の組み合わせに吸着してスパンを書き直す）、3D の天端のつまみで作業床の段数。パレットの「箱を足場に」でそのスパンと段数の足場一式に置き直す。",
        ],
    },
    "ashiba_side": {
        "title": "足場の辺（足場の箱を1辺ずつに分けたもの。辺ごとに厚み・段数を変え、消してコの字・L字にもできる）",
        "notes": [
            "利用者の指定（2026-10-31）: 箱は1辺ずつ別々にしてちょ。",
            "原点＝内側の建地の列の始点、+X＝辺の向き、足場は −Y の側（建物は +Y）。終わりの端のつまみで長さ（定尺に吸着）、中ほどのつまみで厚み、3D の天端のつまみで段数。パレットの「箱を足場に」で、つながった辺を一周・コの字・L字・1本の足場一式に置き直す。",
        ],
    },
    "ashiba_walkway": {
        "title": "仮設通路（アルミ製の伸縮通路 日工セック ライトブリッジ・1本に1部品）",
        "notes": [
            "利用者の指定（2026-10-29）: https://www.nikkosec.co.jp/page-73/ 次足場はこういうのにも対応できるようにしたい。",
            "原点＝始めの島の布材の上の通路の芯、faceAng で通路の向き、wkL で長さ、zDeck・zEnd で両端の床の高さ（差があれば傾ける）。床幅 660・外枠 766・全幅 915、手すり 966・中桟 484・幅木 125、2段の伸縮と両端のフック。両端の島は部品 ashiba_stage。",
        ],
    },
    "ashiba_cstep": {
        "title": "コーナーステップ（くさびの隅の隙間を塞ぐ踏板・1つの隅に1部品）",
        "notes": [
            "利用者の指定（2026-10-23）: くさびの隅が寸法（フィート）で繋がらないところは無理に繋がず、コーナーステップで納める。",
            "原点＝隙間を持つ面の最後の支柱（内側建地列）、faceAng で面の向き。平面は枠と×と「CS 隙間」、3Dは各層の踏板と外側の手すり・中桟・幅木。",
        ],
    },
    "ashiba_mvo": {
        "title": "仮設足場 モデル表示オプション（ライブラリグローバル）",
        "notes": [
            "足場ラインが LIBRARYGLOBAL(\"ashiba_mvo_<版>\", ...) で読む表示設定。",
            "平面の単線／詳細、寸法・注記の有無、3Dの立体／線表示を、部品を触らずに",
            "モデル表示オプションの組合せで切り替える（bim-arekore の足場MVO と同じ仕組み）。",
        ],
    },
}

SCRIPT_SECTIONS = [
    ("1d.gdl", "マスタースクリプト"),
    ("2d.gdl", "2Dスクリプト"),
    ("3d.gdl", "3Dスクリプト"),
    ("ui.gdl", "UIスクリプト"),
    ("vl.gdl", "パラメータスクリプト"),
]

TYPE_JA = {
    "Length": "長さ",
    "String": "文字列",
    "Boolean": "ブール",
    "Integer": "整数",
    "RealNum": "実数",
    "Angle": "角度",
    "Material": "表面材",
}


def _rule(char: str = "=") -> str:
    return "! " + char * 58


def _width(s: str) -> int:
    """等幅フォントでの表示幅。日本語は2桁ぶんなので len() では揃わない."""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def _pad(s: str, width: int) -> str:
    return s + " " * max(0, width - _width(s))


def parameter_lines(part_dir: Path) -> list[str]:
    """paramlist.xml → コメント行。Archicad標準の固定パラメータ(A/B/ZZYZX)は除く."""
    root = ET.parse(part_dir / "paramlist.xml").getroot()
    params = root.find("Parameters")
    if params is None:
        raise SystemExit(f"Parameters セクションがありません: {part_dir}")
    rows = []
    for el in params:
        if el.find("Fix") is not None:
            continue
        desc = (el.findtext("Description") or "").strip().strip('"')
        value = (el.findtext("Value") or "").strip()
        rows.append((el.get("Name", ""), TYPE_JA.get(el.tag, el.tag), desc, value))
    if not rows:
        return []
    w_name = max(_width(r[0]) for r in rows)
    w_type = max(_width(r[1]) for r in rows)
    w_desc = max(_width(r[2]) for r in rows)
    return [
        f"!   {_pad(n, w_name)}  {_pad(t, w_type)}  {_pad(d, w_desc)}  既定 {v}"
        for n, t, d, v in rows
    ]


def build_flat_gdl(part: str) -> str:
    meta = PARTS[part]
    part_dir = HSF_DIR / part
    out = [
        _rule(),
        f"! {meta['title']} 単一ファイル参照版",
        _rule("-"),
        f"! このファイルは gdl/hsf/{part}/ から自動生成しています。",
        "! 直接編集しないでください。HSF側を直してから再生成します:",
        "!   python3 scripts/build_flat_gdl.py",
        "!",
        "! 通しで読む・差分を見るための参照用で、そのままでは動きません",
        f"! （実際に読み込むのは gdl/{part}.gsm）。各セクションはArchicadの",
        "! 対応するスクリプト欄にそのまま貼れます。",
        _rule("-"),
    ]
    out += ["! " + n for n in meta["notes"]]
    param_lines = parameter_lines(part_dir)
    if param_lines:
        out += [_rule("-"), "! パラメータリスト:"] + param_lines
    out += [_rule(), ""]

    for filename, label in SCRIPT_SECTIONS:
        src = part_dir / "scripts" / filename
        if not src.exists():
            continue
        body = src.read_text(encoding="utf-8-sig").rstrip("\n")
        out += [_rule(), f"! ==== {label} ====", _rule(), body, ""]
    return "\n".join(out) + "\n"


def main() -> None:
    check = "--check" in sys.argv
    stale = []
    for part in PARTS:
        if not (HSF_DIR / part).is_dir():
            continue
        path = ROOT / "gdl" / f"{part}.gdl"
        text = build_flat_gdl(part)
        current = path.read_text(encoding="utf-8-sig") if path.exists() else None
        if current == text:
            print(f"変更なし: {path.relative_to(ROOT)}")
            continue
        if check:
            stale.append(str(path.relative_to(ROOT)))
            continue
        # 他のGDLソースに合わせてBOM付きUTF-8で出す
        path.write_text(text, encoding="utf-8-sig")
        print(f"生成: {path.relative_to(ROOT)}")
    if stale:
        raise SystemExit(
            "HSFと参照版がズレています: " + ", ".join(stale)
            + "\n  python3 scripts/build_flat_gdl.py で再生成してください"
        )


if __name__ == "__main__":
    main()
