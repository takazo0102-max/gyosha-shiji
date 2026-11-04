"""仮設工事の金額の概算（利用者の指定 2026-11-04「仮設の金額を出せるようにしたい」）.

工程表（schedule_plan.build → schedule.schedule）の作業と数量から、項目ごとに 金額＝手間＋賃料・材料＋機械 を出す:
- 手間 ＝ 正味の作業日数（数量 ÷ 1班1日の量。工程表の線の長さは躯体を追って延びるので使わない）× 班の編成 × 労務単価
  ×（1＋専門工事業者の諸経費 47％）。労務単価は国交省 公共工事設計労務単価 R8.3（東京）
- 賃料 ＝ 単価 × 数量 × 存置の日数（組み立ての始め〜撤去の終わり。工程表の暦の日）。くさび緊結式足場は東京都の材工共の
  存置月数別の単価（手間を含むので手間を足さない）
- 機械 ＝ 日額 × 正味の作業日数（業者の公開価格【目安】）
- 共通仮設費率（公共建築工事共通費積算基準 R8 の式）は建物の直接工事費と工期を条件に入れたときだけ添える。ユニットハウス・
  仮設トイレは国の基準では率に含むので「率に含む」として別に足す（二重に数えない）

単価は research_notes/仮設の金額/単価.md（出典の URL・頁）。配布物の既定値に入れるのは国交省・東京都・業者の公開価格だけ
（県の単価表と金額入りの設計書は利用条件で二次利用を禁じているので入れない）。賃料が公開されていない項目（枠組足場以外の
シート・仮囲いの鋼板・覆工板・構台の鋼材・H形鋼・タワークレーン）は単価を空けて「単価なし」と出し、利用者が
ashiba_out/仮設単価.csv に自社や物価資料の値を入れると使う.
"""

from __future__ import annotations

import csv
import datetime as _dt
import math
from dataclasses import dataclass, field
from pathlib import Path

from .schedule import Task, days_of
from .schedule_rates import RATES
from .schedule_sources import Quantities

SRC_L = "国交省 公共工事設計労務単価 R8.3 東京（PDF p8〜12）"
SRC_K = "国交省 公共建築工事標準単価積算基準 R8"
SRC_C = "国交省 公共建築工事共通費積算基準 R8 別表-1（新営建築）"
SRC_TZ = "東京都 工事設計単価表 R8.11 建築資材（財務）印刷 p132"
SRC_SHINODA = "篠田重機（埼玉）公開価格 オペ付き https://www.shinoda-juki.com/about/price.html【目安】"
SRC_KENKIGO = "KenkiGo 公開価格 オペ無し https://kenki-go.com/pricing【目安】"
SRC_KAINOS = "カイノスレンタル 公開価格 22mm 5×20（日 200・最低10日・出入庫 各500・清掃 1,200）【目安】"
SRC_SOFIX = "ソフィックス 公開価格 ユニットハウス 3坪 月 16,500・基本 3,000【目安】"
SRC_P = "国交省 施工パッケージ R8 東京17区 No.382 覆工板設置・撤去（電線共同溝工の値）【目安】"

# 労務単価（円／人日、東京、R8.3 から）
LABOR = {"とび工": 33100, "普通作業員": 27000, "特殊作業員": 30700, "軽作業員": 18700, "運転手（特殊）": 31100,
         "鉄骨工": 29800, "型わく工": 33000, "土木一般世話役": 34400, "電工": 34300, "交通誘導警備員B": 18700}
OVERHEAD = 0.47                 # 専門工事業者の諸経費（労務費の 42〜52％、K 表3 S4 頁）の中ほど【目安】
# 1班の編成（schedule_rates の班の人数と同じ）
CREW = {"足場組立": {"とび工": 5}, "足場解体": {"とび工": 5}, "養生シート": {"とび工": 2},
        "仮囲い": {"普通作業員": 4}, "仮囲い撤去": {"普通作業員": 4}, "敷鉄板": {"普通作業員": 2},
        "親杭": {"土木一般世話役": 1, "とび工": 2, "普通作業員": 1}, "親杭引抜": {"土木一般世話役": 1, "とび工": 2, "普通作業員": 1},
        "掘削": {"運転手（特殊）": 1, "普通作業員": 1}, "埋戻し": {"運転手（特殊）": 1, "普通作業員": 1},
        "構台架設": {"土木一般世話役": 1, "とび工": 4}, "構台撤去": {"土木一般世話役": 1, "とび工": 4},
        "仮設建物": {"とび工": 3}, "仮設電気": {"電工": 1, "普通作業員": 1}}
# くさび緊結式足場（手すり先行）建地幅900・12m未満 材工共（円／掛m²）: 存置の月数（未満）→ 単価
KUSABI_900 = ((1, 1330), (2, 1540), (3, 1750), (6, 2170))
KUSABI_600 = ((1, 1170), (2, 1350), (3, 1530), (6, 1890))
KUSABI_STEP = 210               # 6か月を超える1か月ごと（東京 1〜3か月・福島の傾き）【目安】
# 出入口ゲート W6000×H5000 材工共（円／か所）: 存置の月数（未満）→ 単価
GATE = ((1, 147000), (2, 154000), (3, 161000), (4, 167000), (5, 174000), (6, 181000), (9, 201000), (12, 221000),
        (15, 240000), (18, 260000), (24, 301000))

# 単価表の既定（ashiba_out/仮設単価.csv の雛形）: 鍵 → (単価, 単位, 出典)。None は公開値が無い（利用者が入れる）
DEFAULTS: dict[str, tuple] = {
    "ラフター25t（日・オペ付き）": (70000, "円/日", SRC_SHINODA),
    "ラフター50t（日・オペ付き）": (125000, "円/日", SRC_SHINODA),
    "バックホウ0.45m3（日・オペ無し）": (22000, "円/日", SRC_KENKIGO),
    "クレーン付きトラック4.9t（日・オペ付き）": (None, "円/日", "公開値が見つからない"),
    "杭打機・バイブロ（日・オペ付き）": (None, "円/日", "公開値が見つからない（物価資料）"),
    "敷鉄板22mm 5×20 賃料（枚・日）": (200, "円/枚・日", SRC_KAINOS),
    "敷鉄板22mm 5×20 出入庫・清掃（枚）": (2200, "円/枚", SRC_KAINOS),
    "仮囲い 鋼板H3m 賃料（m・日）": (None, "円/m・日", "物価資料（公表単価表は非公表）"),
    "養生シート 賃料（掛m2・日）": (None, "円/掛m2・日", "物価資料（公表単価表は非公表）"),
    "覆工板 設置撤去（m2）": (2025.6, "円/m2", SRC_P),
    "覆工板 賃料（m2・日）": (None, "円/m2・日", "物価資料（非公表）"),
    "構台の鋼材 賃料（t・日）": (None, "円/t・日", "物価資料（非公表）"),
    "H形鋼（親杭）賃料（本・日）": (None, "円/本・日", "物価資料（非公表）"),
    "ユニットハウス 賃料（棟・月）": (16500, "円/棟・月", SRC_SOFIX),
    "ユニットハウス 基本料（棟）": (3000, "円/棟", SRC_SOFIX),
    "タワークレーン 組立解体（式）": (None, "円", "公共・公開とも見つからない"),
    "タワークレーン 賃料（月）": (None, "円/月", "公共・公開とも見つからない"),
}
PRICE_FILE = "仮設単価.csv"


@dataclass
class CostRow:
    group: str                  # 直接仮設 / 共通仮設（積み上げ）/ 共通仮設（率に含む）/ 共通仮設費率
    item: str
    qty: float
    unit: str
    labor: int = 0
    rent: int = 0
    machine: int = 0
    basis: list = field(default_factory=list)
    missing: list = field(default_factory=list)   # 単価が無くて足していないもの
    guess: bool = False

    @property
    def total(self) -> int:
        return self.labor + self.rent + self.machine


def load_prices(out: Path) -> dict[str, float | None]:
    """単価表（ashiba_out/仮設単価.csv）。無ければ既定で雛形を書く. 単価の欄が空なら「単価なし」."""
    p = Path(out) / PRICE_FILE
    prices = {k: v[0] for k, v in DEFAULTS.items()}
    if not p.exists():
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(["項目", "単価", "単位", "出典（自社・物価資料の値に書き換えてよい。空は単価なし）"])
                for k, (v, u, s) in DEFAULTS.items():
                    w.writerow([k, "" if v is None else v, u, s])
        except OSError:
            pass
        return prices
    try:
        with p.open(encoding="utf-8-sig") as f:
            for row in csv.reader(f):
                if len(row) >= 2 and row[0] in prices:
                    t = row[1].replace(",", "").strip()
                    try:
                        prices[row[0]] = float(t) if t else None
                    except ValueError:
                        pass
    except OSError:
        pass
    return prices


def labor_cost(rate_key: str, qty: float, crews: int = 1) -> tuple[int, str]:
    """正味の作業日数 × 班の編成 × 労務単価 ×（1＋諸経費）."""
    r = RATES[rate_key]
    d = r.days if r.days else days_of(qty, r.per_day, crews)
    crew = CREW.get(rate_key, {})
    day = sum(LABOR[k] * n for k, n in crew.items())
    yen = round(d * crews * day * (1 + OVERHEAD))
    who = "・".join(f"{k}{n}" for k, n in crew.items())
    return yen, f"手間 {d}日×{crews}班（{who}）×労務単価×1.{round(OVERHEAD * 100)}＝{yen:,}"


def _months(d0: _dt.date, d1: _dt.date) -> float:
    return max(1, (d1 - d0).days + 1) / 30.0


def _by_months(table, m: float) -> int:
    for lim, yen in table:
        if m < lim:
            return yen
    return table[-1][1]


def kusabi_unit(months: float, height_m: float, width: int = 900) -> tuple[int, bool, str]:
    """くさび緊結式足場 材工共の単価（円／掛m²）、【目安】か、根拠."""
    t = KUSABI_600 if width == 610 or width == 600 else KUSABI_900
    yen = _by_months(t, months)
    guess = False
    note = f"東京都 くさび緊結式 幅{600 if t is KUSABI_600 else 900} 12m未満 存置 {months:.1f}か月 {yen:,}円/掛m²"
    if months >= 6:
        extra = math.ceil(months - 6) * KUSABI_STEP
        yen += extra
        guess = True
        note += f"＋6か月を超える {extra:,}【目安】"
    if height_m >= 12:
        k = 0.049 if height_m < 22 else 0.054
        add = round((k - 0.044) * LABOR["とび工"] * (1 + OVERHEAD))
        yen += add
        guess = True
        note += f"＋高さ {height_m:.0f}m の手間の差 {add:,}（K 表A1-1-10 の {k}−0.044人）【目安】"
    return yen, guess, note


def common_rate(direct_k: float, months: float) -> float:
    """共通仮設費率 Kr（％）＝ exp(3.346 − 0.282 ln P ＋ 0.625 ln T)（新営建築、P 千円・T か月）."""
    if direct_k <= 0 or months <= 0:
        return 0.0
    return round(math.exp(3.346 - 0.282 * math.log(direct_k) + 0.625 * math.log(months)), 2)


def estimate(tasks: list[Task], q: Quantities, prices: dict, crews: dict | None = None, direct_k: float = 0.0,
             work_months: float = 0.0, scaffold_width: int = 900, cal=None, guard_days: int = 0) -> list[CostRow]:
    """工程表の作業と数量 → 項目ごとの金額."""
    by = {t.key: t for t in tasks}
    crews = crews or {}
    rows: list[CostRow] = []

    def span(a: str, b: str) -> tuple[_dt.date, _dt.date] | None:
        if a in by and b in by and by[a].start and by[b].end:
            return by[a].start, by[b].end
        return None

    def price(key: str, row: CostRow) -> float:
        v = prices.get(key)
        if v is None:
            row.missing.append(key)
            return 0.0
        return float(v)

    # ---- 直接仮設: 外部足場（材工共）・養生シート ----
    sp = span("sc_up", "sc_dn")
    if q.scaffold_m2 and sp:
        m = _months(*sp)
        unit, g, note = kusabi_unit(m, q.scaffold_h, scaffold_width)
        r = CostRow("直接仮設", "外部足場（くさび緊結式・手すり先行。材工共）", q.scaffold_m2, "掛m²", rent=round(unit * q.scaffold_m2),
                    basis=[f"{note} × {q.scaffold_m2:,.1f}掛m²（{SRC_TZ}）", f"存置 {sp[0]:%Y-%m-%d}〜{sp[1]:%Y-%m-%d}"], guess=g)
        rows.append(r)
        r = CostRow("直接仮設", "養生シート（張り・払い）", q.scaffold_m2, "掛m²")
        r.labor, t = labor_cost("養生シート", q.scaffold_m2, crews.get("養生シート", 1))
        r.basis.append(t + f"（{SRC_L}・{SRC_K} 表A1-1-27）")
        u = price("養生シート 賃料（掛m2・日）", r)
        days = (sp[1] - sp[0]).days + 1
        r.rent = round(u * q.scaffold_m2 * days)
        if u:
            r.basis.append(f"賃料 {u:g}円/掛m²・日 × {days}日")
        rows.append(r)
    # ---- 共通仮設（積み上げ）: 仮囲い・ゲート ----
    sp = span("kakoi", "kakoi_x")
    if q.hoarding_m and sp:
        r = CostRow("共通仮設（積み上げ）", "仮囲い（安全鋼板 H3m）設置・撤去", q.hoarding_m, "m")
        a, ta = labor_cost("仮囲い", q.hoarding_m, crews.get("仮囲い", 1))
        b, tb = labor_cost("仮囲い撤去", q.hoarding_m, crews.get("仮囲い", 1))
        r.labor = a + b
        r.basis += [ta + "（設置）", tb + f"（撤去。{SRC_L}・{SRC_K} 表A1-1-1）"]
        days = (sp[1] - sp[0]).days + 1
        u = price("仮囲い 鋼板H3m 賃料（m・日）", r)
        r.rent = round(u * q.hoarding_m * days)
        if u:
            r.basis.append(f"賃料 {u:g}円/m・日 × {days}日")
        rows.append(r)
        if q.gates:
            gy = _by_months(GATE, _months(*sp))
            rows.append(CostRow("共通仮設（積み上げ）", "出入口ゲート W6000×H5000（材工共）", q.gates, "か所", rent=gy * q.gates,
                                basis=[f"存置 {_months(*sp):.1f}か月 {gy:,}円/か所（{SRC_TZ}）"]))
    # ---- 敷鉄板・場内通路 ----
    sp = span("plate", "plate_x")
    if q.plates and sp:
        r = CostRow("共通仮設（積み上げ）", "敷鉄板 22mm（場内通路）敷設・撤去", q.plates, "枚")
        r.labor, t = labor_cost("敷鉄板", q.plates * 2, crews.get("敷鉄板", 1))
        r.basis.append(t + f"（敷設と撤去。{SRC_L}・{SRC_K} 表A1-1-3）")
        days = max(10, (sp[1] - sp[0]).days + 1)
        u = price("敷鉄板22mm 5×20 賃料（枚・日）", r)
        f = price("敷鉄板22mm 5×20 出入庫・清掃（枚）", r)
        r.rent = round((u * days + f) * q.plates)
        r.basis.append(f"賃料 {u:g}円/枚・日 × {days}日＋出入庫・清掃 {f:,.0f}円/枚（{SRC_KAINOS}）")
        nd = days_of(q.plates * 2, RATES["敷鉄板"].per_day)
        cu = price("クレーン付きトラック4.9t（日・オペ付き）", r)
        r.machine = round(cu * nd)
        r.guess = True
        rows.append(r)
    # ---- 交通誘導員（ゲート。共通費積算基準では率に含めず積み上げ）----
    sp = span("kakoi", "kakoi_x") or span("plate", "plate_x")
    if q.guards and sp:
        wd = cal.count(sp[0], sp[1]) if cal else round(((sp[1] - sp[0]).days + 1) * 6 / 7)
        every = not guard_days
        if guard_days:
            wd = int(guard_days)                                    # 条件（搬入のある日だけ）
        day = LABOR["交通誘導警備員B"]
        r = CostRow("共通仮設（積み上げ）", "交通誘導員（ゲート）", q.guards * wd, "人日",
                    labor=round(q.guards * wd * day * (1 + OVERHEAD)),
                    basis=[f"{q.guards}人 × {wd}日（" + ("仮囲いの設置〜撤去の稼働日に毎日つく【目安】" if every else "条件の guard_days")
                           + f"）× 交通誘導警備員B {day:,}円×1.{round(OVERHEAD * 100)}（{SRC_L} p12）。"
                           + ("搬入のある日だけなら工程表_条件.json の override に guard_days を入れる" if every else "")], guess=every)
        rows.append(r)
    # ---- 山留め・土工 ----
    if "yama" in by and by["yama"].qty:
        n = by["yama"].qty
        r = CostRow("共通仮設（積み上げ）", "山留め 親杭の建込み・引抜き", n, "本")
        a, ta = labor_cost("親杭", n, crews.get("親杭", 1))
        b, tb = labor_cost("親杭引抜", n, 1)
        r.labor = a + b
        r.basis += [ta + "（建込み）", tb + f"（引抜き。{SRC_L}・農水省 標準歩掛 仮設工）"]
        nd = days_of(n, RATES["親杭"].per_day) + days_of(n, RATES["親杭引抜"].per_day)
        r.machine = round(price("杭打機・バイブロ（日・オペ付き）", r) * nd)
        sp = span("yama", "yama_x")
        if sp:
            r.rent = round(price("H形鋼（親杭）賃料（本・日）", r) * n * ((sp[1] - sp[0]).days + 1))
        r.guess = True
        rows.append(r)
    for key, rk, name in (("ex1", "掘削", "1次根切り"), ("ex2", "掘削", "2次根切り・床付け"), ("fill", "埋戻し", "埋戻し")):
        t = by.get(key)
        if t and t.qty:
            r = CostRow("土工（参考）", name, t.qty, "m³")
            r.labor, tt = labor_cost(rk, t.qty, 1)
            nd = days_of(t.qty, RATES[rk].per_day)
            r.machine = round(price("バックホウ0.45m3（日・オペ無し）", r) * nd)
            r.basis += [tt + f"（{SRC_L}・島根県 作業日当り標準作業量）", f"バックホウ {nd}日（{SRC_KENKIGO}）"]
            r.guess = True
            rows.append(r)
    # ---- 構台 ----
    sp = span("kodai", "kodai_x")
    if q.deck_m2 and sp:
        days = (sp[1] - sp[0]).days + 1
        r = CostRow("共通仮設（積み上げ）", "乗入れ構台 架設・撤去", q.deck_m2, "m²")
        a, ta = labor_cost("構台架設", q.deck_m2, crews.get("構台架設", 1))
        b, tb = labor_cost("構台撤去", q.deck_m2, 1)
        r.labor = a + b
        r.basis += [ta + "（架設）", tb + f"（撤去。{SRC_L}・農水省 標準歩掛 仮桟橋で代用）【目安】"]
        fu = price("覆工板 設置撤去（m2）", r)
        nd = days_of(q.deck_m2, RATES["構台架設"].per_day) + days_of(q.deck_m2, RATES["構台撤去"].per_day)
        r.machine = round(price("ラフター25t（日・オペ付き）", r) * nd + fu * q.deck_m2)
        r.basis.append(f"25t ラフター {nd}日（{SRC_SHINODA}）＋覆工板の設置撤去 {fu:,.1f}円/m²（{SRC_P}）")
        r.rent = round(price("覆工板 賃料（m2・日）", r) * q.deck_m2 * days + price("構台の鋼材 賃料（t・日）", r) * q.deck_t * days)
        r.guess = True
        rows.append(r)
    # ---- 揚重（タワークレーン）----
    sp = span("tc_up", "tc_dn")
    if q.tower and sp:
        r = CostRow("共通仮設（積み上げ）", f"タワークレーン（{q.tower}）", 1, "基")
        r.machine = round(price("タワークレーン 組立解体（式）", r))
        r.rent = round(price("タワークレーン 賃料（月）", r) * _months(*sp))
        nd = RATES["タワークレーン組立"].days + RATES["タワークレーン解体"].days
        r.machine += round(price("ラフター50t（日・オペ付き）", r) * nd)
        r.basis.append(f"組立・解体の移動式クレーン 50t {nd}日（{SRC_SHINODA}）・存置 {_months(*sp):.1f}か月")
        r.guess = True
        rows.append(r)
    # ---- 率に含む（公共の積算では共通仮設費率の中）: 仮設建物・仮設電気 ----
    sp = span("house", "house_x")
    if q.house_units and sp:
        m = _months(*sp)
        r = CostRow("共通仮設（率に含む）", "仮設建物（ユニットハウス）", q.house_units, "棟")
        r.labor, t = labor_cost("仮設建物", q.house_units * 2, 1)
        mu, bu = price("ユニットハウス 賃料（棟・月）", r), price("ユニットハウス 基本料（棟）", r)
        r.rent = round((mu * math.ceil(m) + bu) * q.house_units)
        r.basis += [t + "（据付と撤去）", f"賃料 {mu:,.0f}円/棟・月 × {math.ceil(m)}か月＋基本料 {bu:,.0f}（{SRC_SOFIX}）。運搬は別"]
        r.guess = True
        rows.append(r)
    if "util" in by:
        r = CostRow("共通仮設（率に含む）", "仮設電気・給排水の引込み（手間）", 1, "式")
        r.labor, t = labor_cost("仮設電気", 0, 1)
        r.basis.append(t + "。引込みの負担金・電気料金・水道料金は別")
        rows.append(r)
    # ---- 共通仮設費率（建物の直接工事費と工期を入れたとき）----
    if direct_k > 0 and work_months > 0:
        kr = common_rate(direct_k, work_months)
        rows.append(CostRow("共通仮設費率", f"共通仮設費（率 {kr}％ × 直接工事費 {direct_k:,.0f}千円）", 1, "式",
                            rent=round(direct_k * 1000 * kr / 100),
                            basis=[f"Kr＝exp(3.346−0.282 lnP＋0.625 lnT)、P＝{direct_k:,.0f}千円・T＝{work_months:.1f}か月（{SRC_C}）。"
                                   "仮設建物・仮設電気・安全用品などを含む（上の「率に含む」は参考で、足すと二重）"]))
    return rows


GROUP_ORDER = ("直接仮設", "共通仮設（積み上げ）", "土工（参考）", "共通仮設（率に含む）", "共通仮設費率")


def totals(rows: list[CostRow]) -> dict[str, int]:
    out = {g: sum(r.total for r in rows if r.group == g) for g in GROUP_ORDER}
    rate = out["共通仮設費率"]
    out["仮設の合計"] = out["直接仮設"] + out["共通仮設（積み上げ）"] + (rate if rate else out["共通仮設（率に含む）"])
    return out


def to_markdown(rows: list[CostRow], title: str) -> str:
    tt = totals(rows)
    lines = [f"# {title}", "", "- 金額は税抜の概算。手間＝正味の作業日数×班×労務単価×1.47（専門工事業者の諸経費）、賃料は工程表の存置の日数で。",
             "- 【目安】は業者の公開価格・他の工種の値・式で延ばした値。単価は ashiba_out/仮設単価.csv で自社・物価資料の値に書き換えられる。",
             "- 「単価なし」は公開値が無く足していないもの（単価表に入れると足す）。", "",
             "| 区分 | 項目 | 数量 | 単位 | 手間 | 賃料・材料 | 機械 | 金額 | 根拠 |", "|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda x: GROUP_ORDER.index(x.group)):
        note = "・".join(r.basis) + ("【目安】" if r.guess and "【目安】" not in "".join(r.basis) else "")
        if r.missing:
            note += "。単価なし: " + "・".join(r.missing)
        lines.append(f"| {r.group} | {r.item} | {r.qty:,.1f} | {r.unit} | {r.labor:,} | {r.rent:,} | {r.machine:,} | {r.total:,} | {note} |")
    lines += ["", "| 計 | 金額 |", "|---|---|"]
    for g in GROUP_ORDER:
        if any(r.group == g for r in rows):
            lines.append(f"| {g} | {tt[g]:,} |")
    lines.append(f"| **仮設の合計** | **{tt['仮設の合計']:,}** |")
    if tt["共通仮設費率"]:
        lines.append("")
        lines.append("- 共通仮設費率を入れたので、「率に含む」の項目は合計に足していない（二重に数えない）")
    return "\n".join(lines) + "\n"


def to_sheet(wb, rows: list[CostRow], title: str) -> None:
    from .xlsx_writer import STYLE_BORDER, STYLE_TEXT, STYLE_YEN

    sh = wb.sheet("仮設の金額")
    sh.add_title(title, 9)
    sh.add(["金額は税抜の概算。単価は ashiba_out/仮設単価.csv で書き換えられる（空は単価なし）"])
    sh.add_blank()
    sh.add_header(["区分", "項目", "数量", "単位", "手間", "賃料・材料", "機械", "金額", "根拠"])
    from .xlsx_writer import Cell

    for r in sorted(rows, key=lambda x: GROUP_ORDER.index(x.group)):
        note = "・".join(r.basis) + ("。単価なし: " + "・".join(r.missing) if r.missing else "") + ("【目安】" if r.guess else "")
        sh.add_cells([Cell(r.group, STYLE_TEXT), Cell(r.item, STYLE_TEXT), Cell(round(r.qty, 1), STYLE_BORDER), Cell(r.unit, STYLE_BORDER),
                      Cell(r.labor, STYLE_YEN), Cell(r.rent, STYLE_YEN), Cell(r.machine, STYLE_YEN), Cell(r.total, STYLE_YEN),
                      Cell(note, STYLE_TEXT)])
    sh.add_blank()
    tt = totals(rows)
    for g in GROUP_ORDER:
        if any(r.group == g for r in rows):
            sh.add_cells([Cell(g, STYLE_TEXT), Cell(""), Cell(""), Cell(""), Cell(""), Cell(""), Cell(""), Cell(tt[g], STYLE_YEN)])
    sh.add_cells([Cell("仮設の合計", STYLE_TEXT), Cell(""), Cell(""), Cell(""), Cell(""), Cell(""), Cell(""),
                  Cell(tt["仮設の合計"], STYLE_YEN)])
    for i, w in enumerate((16, 30, 9, 6, 11, 11, 11, 12, 90)):
        sh.set_width(i, w)


# 月ごとの金額（工程表と連動）: 項目の頭 → (手間・機械を割り振る作業, 賃料を割り振る存置の期間（始めの作業, 終わりの作業）)
PERIODS = (("外部足場", ("sc_up", "sc_dn"), ("sc_up", "sc_dn")), ("養生シート", ("sheet",), ("sc_up", "sc_dn")),
           ("仮囲い", ("kakoi", "kakoi_x"), ("kakoi", "kakoi_x")), ("出入口ゲート", (), ("kakoi", "kakoi_x")),
           ("敷鉄板", ("plate", "plate_x"), ("plate", "plate_x")), ("山留め", ("yama", "yama_x"), ("yama", "yama_x")),
           ("1次根切り", ("ex1",), None), ("2次根切り", ("ex2",), None), ("埋戻し", ("fill",), None),
           ("乗入れ構台", ("kodai", "kodai_x"), ("kodai", "kodai_x")), ("タワークレーン", ("tc_up", "tc_dn"), ("tc_up", "tc_dn")),
           ("仮設建物", ("house", "house_x"), ("house", "house_x")), ("仮設電気", ("util",), None),
           ("交通誘導員", (), ("kakoi", "kakoi_x")))


def _spread(out: dict, d0: _dt.date, d1: _dt.date, yen: float) -> None:
    """d0〜d1（暦の日）に yen を日割りで月へ."""
    if yen == 0 or d0 is None or d1 is None:
        return
    n = (d1 - d0).days + 1
    if n <= 0:
        return
    d = d0
    while d <= d1:
        k = f"{d:%Y-%m}"
        out[k] = out.get(k, 0.0) + yen / n
        d += _dt.timedelta(days=1)


def monthly(rows: list[CostRow], tasks: list[Task], include_reference: bool = False) -> dict[str, int]:
    """項目の金額を工程表の作業の期間へ割り振った月ごとの金額 {"YYYY-MM": 円}. 手間・機械はその作業の期間に（いくつかあれば等分）、
    賃料・材料は存置の期間に日割り。共通仮設費率は工程の全体に。土工（参考）と「率に含む」は合計と同じ扱い（率を入れたら除く）."""
    by = {t.key: t for t in tasks if t.start and t.end}
    out: dict[str, float] = {}
    has_rate = any(r.group == "共通仮設費率" for r in rows)
    s0 = min((t.start for t in by.values()), default=None)
    s1 = max((t.end for t in by.values()), default=None)
    for r in rows:
        if r.group == "土工（参考）" and not include_reference:
            continue
        if r.group == "共通仮設（率に含む）" and has_rate:
            continue
        if r.group == "共通仮設費率":
            _spread(out, s0, s1, r.total)
            continue
        hit = next((p for p in PERIODS if r.item.startswith(p[0])), None)
        if hit is None:
            _spread(out, s0, s1, r.total)
            continue
        _k, works, span = hit
        ws = [by[w] for w in works if w in by]
        lm = r.labor + r.machine
        if ws:
            for t in ws:
                _spread(out, t.start, t.end, lm / len(ws))
        elif span and span[0] in by and span[1] in by:                 # 期間についている手間（交通誘導員）
            _spread(out, by[span[0]].start, by[span[1]].end, lm)
        else:
            _spread(out, s0, s1, lm)
        if span and span[0] in by and span[1] in by:
            _spread(out, by[span[0]].start, by[span[1]].end, r.rent)
        else:
            _spread(out, s0, s1, r.rent)
    return {k: round(v) for k, v in sorted(out.items())}


def monthly_markdown(m: dict[str, int]) -> str:
    if not m:
        return ""
    lines = ["", "## 月ごとの金額（工程表の作業の期間へ割り振り）", "",
             "- 手間・機械はその作業の期間に、賃料・材料は存置の期間に日割り。土工（参考）は入れない", "",
             "| 月 | 金額 | 累計 |", "|---|---|---|"]
    acc = 0
    for k, v in m.items():
        acc += v
        lines.append(f"| {k} | {v:,} | {acc:,} |")
    return "\n".join(lines) + "\n"


def monthly_sheet(wb, m: dict[str, int], title: str) -> None:
    from .xlsx_writer import Cell, STYLE_BORDER, STYLE_YEN

    sh = wb.sheet("月ごとの金額")
    sh.add_title(title + "　月ごとの金額", 3)
    sh.add(["手間・機械はその作業の期間に、賃料・材料は存置の期間に日割り（工程表と連動）。土工（参考）は入れない"])
    sh.add_blank()
    sh.add_header(["月", "金額", "累計"])
    acc = 0
    for k, v in m.items():
        acc += v
        sh.add_cells([Cell(k, STYLE_BORDER), Cell(v, STYLE_YEN), Cell(acc, STYLE_YEN)])
    for i, w in enumerate((10, 14, 14)):
        sh.set_width(i, w)
