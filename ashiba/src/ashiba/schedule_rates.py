"""工程表の歩掛かり（1班1日の量）. 調べたメモは research_notes/工程表 歩掛かり/歩掛かり.md（2026-11-04）.

出典（頁は PDF の通し番号）:
- K: 国土交通省「公共建築工事標準単価積算基準」令和8年改定 https://www.mlit.go.jp/gobuild/content/001733127.pdf
- S: 島根県「令和8年度 建設工事積算基準 第17章 作業日当り標準作業量」（国交省の施工パッケージ・標準歩掛に沿った工程検討用）
  https://www.pref.shimane.lg.jp/infra/kouji/kouji_info/sekisan/kouji_kijyun/kouji_kijyun.data/R08_kensetukoujisekisankijunn_17.pdf
- M: 農林水産省「土地改良事業等請負工事標準歩掛 15.仮設工」令和7年度
  https://www.maff.go.jp/j/nousin/sekkei/sekisan_kijun/sekisan_kijun_old/attach/pdf/sekisan_kijun_R7-8.pdf
- MS: 農林水産省「積算参考歩掛 13.仮設工」令和7年度
  https://www.maff.go.jp/j/nousin/sekkei/sekisan_kijun/sekisan_kijun_old/attach/pdf/sekisan_kijun_R7-10.pdf
K の足場・ネット・仮囲いの歩掛り（人／掛m²・人／m）は、表の注の割り振り（掛け 65％・払い 35％、敷鉄板は 50％ずつ）で組立と解体に分け、
1人1日の量＝1 ÷（歩掛り × 割合）。班の人数は【目安】（M の編成の例と現場の一般的な班）。
くさび緊結式足場（次世代足場）の歩掛りは公開資料に無く、手すり先行の枠組本足場 900枠（K 表A1-1-10）を当てる【目安】.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rate:
    per_day: float            # 1班1日の量（数量の単位）
    unit: str
    crews: int = 1            # 既定の班の数
    crew: str = ""            # 1班の編成
    source: str = ""
    guess: bool = False       # 出典で確かめていない値
    days: int = 0             # 数量によらない日数（据付など）
    pitch: float = 0.0        # 親杭の間隔 m
    tail: int = 0             # 後ろの作業の終わりから延ばす稼働日（足場の最上部の手すり）


def _per(prsn_rate: float, share: float, people: int) -> float:
    """K の歩掛り（人／数量）と割合・班の人数 → 1班1日の量."""
    return round(people / (prsn_rate * share), 1)


# 足場の高さの区分（K 表A1-1-10 手すり先行 枠組本足場 900枠: とび工 人／掛m²）
SCAFFOLD_K = ((12.0, 0.044), (22.0, 0.049), (1e9, 0.054))


def scaffold_rate(height_m: float, up: bool = True, people: int = 5) -> Rate:
    k = next(v for h, v in SCAFFOLD_K if height_m < h)
    share = 0.65 if up else 0.35
    band = "12m未満" if height_m < 12 else "22m未満" if height_m < 22 else "22m以上"
    return Rate(_per(k, share, people), "掛m²", 1, f"とび工 {people}人【目安】",
                f"K 表A1-1-10（PDF12）手すり先行 枠組本足場 900枠 {band} {k}人／掛m² の{'掛け 65' if up else '払い 35'}％。"
                "くさび緊結式の表は公開資料に無く代用【目安】", True, tail=3 if up else 0)


RATES = {
    "足場組立": scaffold_rate(15.0, True),
    "足場解体": scaffold_rate(15.0, False),
    "養生シート": Rate(_per(0.022, 0.65, 2), "掛m²", 1, "とび工 2人【目安】", "K 表A1-1-27（PDF19）養生シート 0.022人／掛m² の掛け 65％"),
    "仮囲い": Rate(_per(0.24, 0.65, 4), "m", 1, "普通作業員 4人【目安】", "K 表A1-1-1（PDF10）鋼板 H3.0 0.24人／m の設置 65％"),
    "仮囲い撤去": Rate(_per(0.24, 0.35, 4), "m", 1, "普通作業員 4人【目安】", "K 表A1-1-1（PDF10）鋼板 H3.0 0.24人／m の撤去 35％"),
    "敷鉄板": Rate(9.4, "枚", 1, "普通作業員 2人・4.9t クレーン付きトラック",
                 "K 表A1-1-3（PDF10）1524×6096 0.046人・クレーン 0.023日／m² の設置・撤去 50％ずつ → 87m²／日"),
    "親杭": Rate(23.0, "本", 1, "世話役1・とび工2・普通作業員1（M 表4.1）・クローラクレーン＋バイブロ",
               "M 表5.1（PDF61）H300 バイブロ打込み 12m以下 23本／日。建築で多いアースオーガの建込みの表は見つからない【目安】",
               pitch=1.2),
    "親杭引抜": Rate(50.0, "本", 1, "世話役1・とび工2・普通作業員1", "M 表5.7（PDF66）H形鋼の引抜き 12m以下 50本／日"),
    "掘削": Rate(180.0, "m³", 1, "バックホウ 1台", "S Ⅰ-17-①-17（PDF18）床掘り 標準（障害あり）180m³／日"),
    "埋戻し": Rate(53.0, "m³", 1, "バックホウ 1台", "S Ⅰ-17-①-18（PDF19）埋戻し 最大埋戻幅 1〜4m 53m³／日"),
    "構台架設": Rate(109.0, "m²", 1, "とび工・25t ラフター",
                 "M ⑬ 表4.16（PDF50）仮桟橋 上部工 13t／日＋覆工板 109m²／日（建築の構台の表は無く仮桟橋で代用）【目安】", True),
    "構台撤去": Rate(185.0, "m²", 1, "とび工・25t ラフター", "M ⑬ 表4.16（PDF50）上部工 17t／日＋覆工板 185m²／日（撤去）【目安】", True),
    "型枠": Rate(_per(0.17, 1.0, 8), "m²", 1, "型わく工・普通作業員 8人【目安】",
               "K 表A1-6-5（PDF40）普通合板 ラーメン地上軸部 型わく工 0.15＋普通作業員 0.02人／m²（加工〜解体、支保を含む）"),
    "仮設建物": Rate(6.0, "棟", 1, "とび工 3人・ユニック", "ユニットハウスの設置の歩掛りは公開資料に無い（K は共通仮設費率）【目安】", True),
    "仮設電気": Rate(0.0, "", 1, "電工 1・普通作業員 1", "MS（PDF36）低圧引込 50kW未満 電工 2.54・普通作業員 2.20人／か所 → 3日", days=3),
    "タワークレーン組立": Rate(0.0, "", 1, "専門の組立班・移動式クレーン", "組立・解体の日数は公開資料に無い【目安】", True, days=10),
    "タワークレーン解体": Rate(0.0, "", 1, "専門の解体班・移動式クレーン", "組立・解体の日数は公開資料に無い【目安】", True, days=8),
}
# 構台の上部工の t／日（覆工板の m²／日と足す）
DECK_T = {"構台架設": 13.0, "構台撤去": 17.0}


def rate_text(r: Rate, crews: int | None = None) -> str:
    n = crews or r.crews
    head = f"{r.days}日" if r.days else f"{r.per_day:g}{r.unit}／班日 × {n}班"
    return f"{head}（{r.crew}）{r.source}" + ("【目安】" if r.guess and "【目安】" not in r.source else "")
