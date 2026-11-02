"""総合仮設計画図の右の欄（凡例・道路占用・届出・事前に確かめる項目）と道路占用の出幅の上限（利用者の指定 2026-11-02:
各図面を参考にして、図面かボタンを追加してちょ）.

施工図の手引き（建築施工図研究会 平成16年。利用者が渡した PDF）の総合仮設計画図にならう: 平面図は Archicad の平面図
（足場・仮囲い・ゲート・仮設建物・揚重機・通路・敷鉄板など ashiba が置いた物が全部映る）をレイアウトに切り抜いて置き、
右の欄に線種の凡例（手引き p14 の仮設計画図の使い分け）、道路占用の許可基準、主な届出、事前に確かめる項目を書く。

道路占用の許可基準は、東京都北多摩北部建設事務所「道路占用許可申請手続き（工事用足場・仮囲い・落下物防護用施設）」p.3
（https://www.kensetsu.metro.tokyo.lg.jp/documents/d/kensetsu/p_ashiba）の値。道路管理者ごとに違うので、ほかの区市町村・
国道は管理者に確かめる（帳票にそう書く）.
"""

from __future__ import annotations

import html
from dataclasses import dataclass

ESC = html.escape
SERIES = "総合仮設"
SUBSET = "総合仮設"
ROAD_SOURCE = "東京都北多摩北部建設事務所「道路占用許可申請手続き」p.3"
# 道路占用（足場・仮囲い）の許可基準
WALK_MAX_MM = 1000.0          # 歩道上: 路端から 1m 以下
WALK_RATIO = 1.0 / 3.0        # 　かつ有効幅員の 1/3 以下（ガードレール・植樹帯があればその内側から 1/3 以下・最大 1m）
WALK_LEFT_MM = 1500.0         # 　占用物件を除いた幅員 1.5m（最低でも 1m）
WALK_LEFT_MIN_MM = 1000.0
ROAD_MAX_MM = 1000.0          # 車道上: 路端から 1m 以下
ROAD_RATIO = 1.0 / 8.0        # 　かつ道路幅員の 1/8 以下
OVERHANG_WALK_MM, OVERHANG_ROAD_MM = 3000.0, 4500.0   # 掛け出し足場の路面からの高さ（歩道・車道）
ASAGAO_WALK_MM, ASAGAO_ROAD_MM = 4000.0, 5000.0       # 落下物防護用施設（朝顔）の高さ（歩道・車道）

# 線種の凡例（手引き p14「図面作成における線種の使い分け」の仮設計画図の欄）: (名前, 太さ mm, 破線の並び（空は実線）)
LINE_LEGEND = (
    ("建物外周・強調する部位", 0.35, ""),
    ("揚重機（位置が変わるときは破線）", 0.35, ""),
    ("仮設建物・足場", 0.20, "2 1"),
    ("仮囲い", 0.35, "2 1"),
    ("通り芯", 0.20, "4 1 0.6 1"),
    ("道路・敷地境界線", 0.20, "4 1 0.6 1 0.6 1"),
    ("埋設物・架空線・ストックヤード", 0.10, "4 1 0.6 1 0.6 1"),
)
# 主な届出（手引き p29 の官庁提出用申請図の表を、今の様式の名前で）: (出し先, 中身)
OFFICES = (
    ("道路管理者（国・都道府県・市区町村）", "道路占用許可（足場・仮囲い・朝顔）、沿道掘削（道路法44条。沿道区域で安定角 45° の線より深く掘る）、"
                                      "自費工事（歩道の切下げ・ガードレール・街路樹の移設）、着手届・完了届"),
    ("警察署", "道路使用許可（生コン打設・荷下ろし）、通行の制限の解除（一方通行・重量・車幅・時間）、交通標識の移設"),
    ("公共企業（水道・下水・電気・ガス・通信）", "敷地周りの埋設物の調査、撤去・迂回・移設・防護の願い"),
    ("労働基準監督署", "建設工事計画届（様式第21号）、足場・型枠支保工などの設置届（様式第20号）、クレーン設置届・設置報告書"),
)
# 事前に確かめる項目（手引き p21 のチェックシートを要約）: (項目, 確かめること…)
CHECKS = (
    ("敷地境界杭", "境界杭が正しいか（設計図書と比べる）", "工事で動くおそれと、動いたときの復旧（引照点）"),
    ("周辺道路", "幅員・構造・種類（道路管理者）", "歩道・ガードレール・街路樹（仮囲い・ゲートの位置）",
     "横断歩道・信号・交通標識・電柱・公共桝", "通行規制（一方通行・重量）とゲートの幅・搬入車両", "敷地と道路の高低差（歩道の切下げ）"),
    ("道路の埋設管", "埋設管の種類と本数・径・深さ・境界からの離れ（沿道掘削の届出）"),
    ("電気・給排水", "架空線とクレーンの荷取り", "仮設電気の容量と引き込み位置（受電の形）", "給水の分岐と量水器", "排水の接続位置と勾配"),
    ("近隣建物", "構造と規模、地下階・杭（掘削の影響）", "境界との離れ・庇の出（外部足場・養生）"),
    ("埋設物", "敷地内の配管（水道・ガス）", "既存の躯体・杭の障害物（図面・試掘）"),
    ("作業環境", "通行量と時間帯（通勤・通学路）", "近くの学校・病院", "水質・振動の影響", "商店街・町内の行事", "電波障害",
     "工事協定（作業時間）"),
    ("その他", "条例・行政指導", "道路占用の使用許可", "河川の水位（湧水）"),
)


@dataclass
class RoadLimit:
    max_out_mm: float           # 出幅の上限 mm
    rule: str                   # 決めた基準
    notes: list


def road_limit(width_mm: float, sidewalk: bool = True, guard_inner_mm: float | None = None) -> RoadLimit:
    """足場・仮囲いを道路へ出せる幅の上限. width_mm は歩道なら有効幅員、車道（歩道の無い道路）なら道路幅員.
    guard_inner_mm はガードレール・植樹帯があるとき、その内側（路端側）までの幅."""
    notes = []
    if sidewalk:
        base = guard_inner_mm if guard_inner_mm else width_mm
        lim = min(WALK_MAX_MM, base * WALK_RATIO)
        if width_mm - lim < WALK_LEFT_MM:
            lim2 = max(0.0, width_mm - WALK_LEFT_MM)
            notes.append(f"残りの幅 {width_mm - lim:,.0f} が {WALK_LEFT_MM:,.0f} に足りない → 出幅を {lim2:,.0f} に"
                         f"（やむを得なければ残り {WALK_LEFT_MIN_MM:,.0f} まで。管理者と協議）")
            lim = lim2
        notes.append(f"掛け出し足場は路面から {OVERHANG_WALK_MM / 1000:g}m 以上、朝顔は {ASAGAO_WALK_MM / 1000:g}m 以上")
        rule = (f"歩道上: 路端から {WALK_MAX_MM / 1000:g}m 以下かつ{'ガードレール等の内側から' if guard_inner_mm else '有効幅員の'} 1/3 以下")
    else:
        lim = min(ROAD_MAX_MM, width_mm * ROAD_RATIO)
        notes.append(f"掛け出し足場は路面から {OVERHANG_ROAD_MM / 1000:g}m 以上、朝顔は {ASAGAO_ROAD_MM / 1000:g}m 以上")
        rule = f"車道上: 路端から {ROAD_MAX_MM / 1000:g}m 以下かつ道路幅員の 1/8 以下"
    notes.append("出入口の扉は道路側へ外開きにしない。路上に占用した足場にウインチ・リフトを付けない。消火栓・マンホールの位置を平面図に")
    return RoadLimit(max(0.0, lim), rule, notes)


def _wrap(text: str, n: int) -> list[str]:
    return [text[i:i + n] for i in range(0, len(text), n)] or [""]


def panel_svg(x0: float, y0: float, w: float, road: RoadLimit | None = None, road_desc: str = "") -> tuple[str, float]:
    """右の欄の SVG（紙の mm。左上 x0, y0 から下へ）→ (SVG, 下の端の y)."""
    out = []
    y = y0
    t = lambda x, yy, s, cls="ts", extra="": out.append(f'<text x="{x:.2f}" y="{yy:.2f}" class="{cls}"{extra}>{ESC(s)}</text>')
    n = max(20, int(w / 2.3))
    t(x0, y + 4, "凡例（線種）", "h2")
    y += 9
    for name, wt, dash in LINE_LEGEND:
        da = f' stroke-dasharray="{dash}"' if dash else ""
        out.append(f'<line x1="{x0:.2f}" y1="{y - 1:.2f}" x2="{x0 + 16:.2f}" y2="{y - 1:.2f}" stroke="#000" stroke-width="{wt}"{da}/>')
        t(x0 + 19, y, name)
        y += 4.0
    y += 3
    t(x0, y + 4, "道路占用の許可基準", "h2")
    y += 9
    rows = [f"歩道上: 路端から 1m 以下かつ有効幅員の 1/3 以下（ガードレール・植樹帯はその内側から 1/3・最大 1m）。残りの幅 1.5m"
            "（最低 1m）。掛け出し足場は路面から 3m 以上",
            "車道上: 路端から 1m 以下かつ道路幅員の 1/8 以下。掛け出し足場は 4.5m 以上",
            "朝顔（落下物防護用施設）: 歩道上 4m 以上・車道上 5m 以上",
            "扉は道路側へ外開きにしない。占用した足場にウインチ・リフトを付けない",
            f"出典: {ROAD_SOURCE}。管理者ごとに違うので確かめる"]
    if road is not None:
        rows.insert(0, f"この現場{('（' + road_desc + '）') if road_desc else ''}: 出幅の上限 {road.max_out_mm:,.0f}mm（{road.rule}）")
    for r in rows:
        for k, ln in enumerate(_wrap(r, n)):
            t(x0 + 2, y, ("・" if k == 0 else "　") + ln)
            y += 3.0
        y += 0.8
    y += 3
    t(x0, y + 4, "主な届出", "h2")
    y += 9
    for who, what in OFFICES:
        t(x0 + 2, y, who, "ts", ' font-weight="bold"')
        y += 3.2
        for ln in _wrap(what, n - 2):
            t(x0 + 4, y, ln)
            y += 3.0
        y += 0.8
    y += 3
    t(x0, y + 4, "事前に確かめる項目", "h2")
    y += 9
    for group in CHECKS:
        t(x0 + 2, y, group[0], "ts", ' font-weight="bold"')
        y += 3.2
        for item in group[1:]:
            for k, ln in enumerate(_wrap(item, n - 4)):
                t(x0 + 4, y, ("□ " if k == 0 else "　 ") + ln)
                y += 3.0
        y += 0.6
    return "".join(out), y


def build_html(project: str = "", road: RoadLimit | None = None, road_desc: str = "") -> str:
    """凡例・道路占用・届出・確認の A3 横（2段組み。平面図そのものは Archicad のレイアウト）."""
    from .form_drawings import CSS, MARGIN, PAGE_W, _page

    col = (PAGE_W - 2 * MARGIN - 20.0) / 2
    left, _y = panel_svg(MARGIN + 6, MARGIN + 12, col, road, road_desc)
    body = left
    return ("<!doctype html><html><head><meta charset='utf-8'><title>総合仮設計画図</title><style>" + CSS
            + "</style></head><body>" + _page(body, "総合仮設計画図 凡例・確認", project, "―", 1, 1, SERIES) + "</body></html>")
