"""Tapir パレットの入口（Phase 10-3）: 「仮設_パレット」1つ。押すと仮設パレット（浮いた小窓）が開く（利用者の指定 2026-11-01:
足場パレットじゃなく仮設パレットに。入口と窓の題だけ変え、中のボタンの入口名 足場_*.py はそのまま）.

利用者の指定（2026-10-22）「Tapirの足場を一つにパレットとしてまとめて、使いやすいように工夫して」。Tapir の一覧には
入口を1つだけ置き、すべての操作はパレットの窓のボタンに並べる（組: 建てる・直す・見る／出す（足場用・型枠用））。窓は Archicad の前に
浮いたまま残り、押しても Archicad の選択は外れない。選んでいるもの（躯体スラブ・足場・分解した支柱・足場条件の部品）
を数秒ごとに見て、合う操作のボタンに★を付ける。結果の要点は窓の下に出す（ダイアログを出さない）。
窓は tapir/palette_panel.swift（AppKit。tkinter は使えない Python で、osascript の JavaScript は窓の
ボタンを受ける仕組みが止まった）。初めて開くときに swiftc で作る。

Tapir のパレットは ~/Documents/Tapir の下のフォルダにある .py を一覧に出し、
`uv run --script ファイル --port 番号` で起動する（配筋ツールで確かめた仕組み。Tapir は
~/Documents/Tapir の下のフォルダを全部読む）。配筋ツールは custom-scripts を使っているので、
足場は別のフォルダ「仮設足場」にリンクして並べ、配筋ツールのファイルには触らない。

入口は小さな .py で、本体（scripts/*.py）は写さない（写すと直したときに2つの版ができる）。
パレットは標準出力を見せないので、終わったら要点（配置の本数・総合判定・是正・要確認・エラー）を
ダイアログで出し、割付レポートを開けるようにする。全文は ashiba_out/パレット実行.log に残す。
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass

FOLDER_NAME = "仮設足場"          # ~/Documents/Tapir/仮設足場 → <ashiba>/tapir/palette
MARK = "# ashiba-palette-entry"   # install が作った入口の印（印の無いファイルには触らない）


@dataclass(frozen=True)
class Entry:
    file: str          # パレットに出る名前（.py）
    script: str        # scripts/ の下の本体
    args: tuple = ()
    title: str = ""
    hint: str = ""     # ダイアログの先頭に出す一言
    when: tuple = ()   # メニューで上に出す選択の種類（slab・line・member・spec・none）
    quiet: bool = False   # 入口が終わりのダイアログを出さない（パレットの窓を開くだけの入口）


# パレットのすべての操作。利用者の指定（2026-10-21）「タピアーコマンドをまとめて使いやすいものに」: パレットには
# 「メニュー」と、よく使う3つ（配置・解き直し・3D表示）だけを並べ、ほかはメニューから選ぶ。メニューは選んでいる
# もの（躯体スラブ・足場ライン・分解した支柱・足場条件の部品・何も無し）に合う操作を上に出す（scripts/ashiba_menu.py）
ACTIONS: tuple[Entry, ...] = (
    Entry("足場_配置.py", "run_from_archicad.py", (), "配置",
          "躯体スラブを選んでから押す。条件の窓で足場の種類・系列・幅・手すり・階段などを選んで「配置」", ("slab",)),
    Entry("足場_地足場.py", "ground_scaffold_run.py", (), "地足場",
          "躯体スラブを選んでから押す。窓で層数（1〜3）を選ぶと、地上に低く組む足場（基礎・1階まわりの作業用。2層以下は"
          "はしごで昇降）を置く", ("slab",)),
    Entry("足場_解き直し.py", "read_back_spans.py", ("--apply",), "解き直し",
          "スパン・階段室・ステージ・昇降機を平面で、足場の高さを3Dで引いたあと、"
          "壁つなぎの部品を動かした・消した・コピーしたあとに押す", ("line",)),
    Entry("足場_区切る.py", "split_line.py", (), "区切る",
          "平面で、区切りたいところに足場を横切る線を引いて選んでから押す（線にいちばん近い支柱で縦に区切る。何本でも）。"
          "横に区切るときは 3D で足場を選び、始点の横のつまみを引いてから押す", ("line", "none")),
    Entry("足場_区切りを戻す.py", "split_line.py", ("--undo",), "区切りを戻す",
          "区切った足場の部品を選んでから押す。その面の部品を1つに戻す", ("line",)),
    Entry("足場_面の切替.py", "switch_face_form.py", (), "面の切替",
          "切り替える足場ラインを選んでから押す。区切った部品を選べばその範囲だけ（面の途中で種類が変わる）、区切っていなければ"
          "面全体を別の種類の足場（本足場・一側・ブラケット（支柱・単管）・単管抱き・単管本足場・枠組）に切り替えて置き直す", ("line",)),
    Entry("足場_朝顔の面.py", "asagao_faces.py", (), "朝顔の面",
          "朝顔の要る面（道路・隣地・人の通る側）の足場ラインを選んでから押す。選んだ面に朝顔を付ける・外す"
          "（全部の面に付けることもできる）して置き直す。面の一部だけなら「朝顔の範囲」", ("line",)),
    Entry("足場_朝顔の範囲.py", "asagao_range_run.py", (), "朝顔の範囲",
          "配置では朝顔を付けない。平面で、朝顔の要るところ（道路・隣地・人の通る側）に足場の面に沿って線を引いて選んでから"
          "押す（何本でも）。線がかかるスパンに寄せ、窓で「付ける／外す」を選ぶと、その面の朝顔と取付部の壁つなぎを直す",
          ("none",)),
    Entry("足場_幅の変更.py", "width_range_run.py", (), "幅の変更",
          "平面で、足場の幅を途中の床から変えたいところに足場の面に沿って線を引いて選んでから押す（何本でも）。線がかかる"
          "スパンに寄せ、窓で幅の変え方（拡幅 610→914・914→1219／縮幅）と幅を変える床の段を選んで「付ける」と、その範囲だけ"
          "拡幅ブラケットで幅を変えて置き直す（「外す」「全部外す」で戻す）", ("none",)),
    Entry("足場_階段の位置.py", "stair_move_run.py", (), "階段の位置",
          "平面で、階段を置きたいところに足場の面に沿って線を引いて選んでから押す。線がかかるスパンに寄せ、窓で動かす階段"
          "（新しく足すこともできる）とスパン数を確かめて置き直す。線を選ばずに押すと、外す階段を選べる（「全部」で階段なし）",
          ("none",)),
    Entry("足場_開口.py", "opening_run.py", (), "開口",
          "平面で、開けたい幅に足場の面に沿って線を1本引き、その線を選んでから押す。両端が支柱に乗る規格の梁枠に寄せ、"
          "窓で梁枠・抜く層・理由を確かめて置き直す（同じ所に開口があれば「外す」も出る）", ("none",)),
    Entry("足場_昇降機.py", "hoist_run.py", (), "昇降機",
          "平面で、昇降機を据えたい所に足場の面に沿って線（ガイドレールの芯から芯）を1本引き、その線を選んでから押す。窓で"
          "機種・取付け（外付け／足場の幅 914 の中）・乗り込む層を選んで「置く」と、昇降機の部品を置いて全体を置き直す"
          "（線の近くの昇降機は置き換え、「外す」で消す）", ("none",)),
    Entry("足場_手動配置.py", "manual_run.py", (), "手動配置",
          "平面で、足場の内側の建地の列に線を1本（縦か横。始点が1本目の支柱）引いて選んでから押す。スパン（1829×4, 914）・"
          "高さ・離れ・幅・手すり・足場の種類を入れて「配置」を押すと、その線の上に足場を置く（建物を選ばなくてよい）",
          ("none",)),
    Entry("足場_箱を置く.py", "box_run.py", ("--place",), "箱を置く",
          "超簡易モード。平面で、足場を置きたい所に線かポリライン（縦横）を引いて選んでから押すと、線の範囲だけに足場の辺が出る"
          "（線1本は1辺、ポリラインは折れ目ごと、四角は閉じたポリライン。斜めの線もその向きで）。辺ごとに終わりの端のつまみで伸び縮み（スパンは定尺に"
          "吸着）、中ほどのつまみで厚み（足場の種類。150＝抱き足場・300＝ブラケット足場・600〜1200＝本足場。辺の設定の「一側の組み方」で"
          "抱き足場も選べる）、3D の天端のつまみで作業床の段数を決める", ("none",)),
    Entry("足場_箱を足場に.py", "box_run.py", ("--build",), "箱を足場に",
          "足場の箱（辺）をまとめて選んでから押す。つながった辺を一周・コの字・L字・1本として、辺ごとのスパン・厚み・段数で"
          "足場一式（階段・壁つなぎ・シート・数量・帳票）に置き直し、箱を消す",
          ("none",)),
    Entry("足場_切梁上の足場.py", "excav_run.py", ("--kiribari",), "切梁上の足場",
          "根切りの切梁（梁）を選んでから押す。切梁の上のフランジに切梁ブラケット（西南機材。H形鋼 250〜400・2m 以内ごと）を挟み、"
          "嵩上金具 W900 で床（鋼製布板）、伸縮手摺柱で手すり・中桟・幅木を付けた通路を置く。数量と検定は帳票に", ("struct",)),
    Entry("足場_外周の腹起し足場.py", "excav_run.py", ("--haraokoshi",), "外周の足場",
          "山留め（壁）を選んでから押す。内側の腹起し（高さ・H形鋼は近くの切梁から）に腹起ブラケット（西南機材。250〜500・2m 以内）を"
          "掛け、山留めの面から根切りの側へ 900 の腕に足場板3枚、先の単管で手すり・中桟・幅木（根切りの側）の外周の通路を置く",
          ("struct",)),
    Entry("足場_山留めの手すり.py", "excav_run.py", ("--rail",), "山留めの手すり",
          "山留め（壁）か、根切りの縁に引いた線を選んでから押す。親杭の天端に単管の手すり柱をキャッチクランプ（2個1組）で"
          "1.8m 以内ごとに留め、手すり 950・中桟・幅木を根切りの縁に付ける（安衛則 519条）", ("struct", "none")),
    Entry("足場_仮囲い.py", "kakoi_run.py", (), "仮囲い",
          "仮囲いの線（線・ポリライン。斜めの辺も）を選んでから押す（選んでいなければ敷地境界から 150 中に）。単管の支柱 1.8m ごと・"
          "横地・安全鋼板（フックボルト）・控え（高さ 2.1m から後ろ 1.55m）と根がらみ・打込みパイプを、敷地メッシュの高低差に合わせて"
          "置く（日建リースのカタログの寸法。山留めのそばは控えを親杭に取る --found 山留め）。角は二等分線まで延ばし、数量と検定（高さ 1.8m 以上・風の計算・角の角度・ゲートの"
          "通れる幅）は帳票に", ("none",)),
    Entry("足場_仮囲いを消す.py", "kakoi_run.py", ("--remove",), "仮囲いを消す",
          "置いた仮囲いを消す（控え ashiba_out/仮囲い.json の部品だけ）", ("none",)),
    Entry("足場_クレーン.py", "crane_run.py", (), "クレーン",
          "線（ポリライン）を選んでから押す。始めの点＝クレーンの旋回中心、ほかの点＝吊り荷の位置（重さ・要る高さは条件で）。"
          "吊り荷を満たす一番小さいラフテレーンクレーン（25t・50t・70t。タダノの性能表）とブーム長さを選び、アウトリガ・敷鉄板・"
          "立入禁止の円・作業半径の円を描く。定格総荷重・フックの高さ・接地圧の検定は帳票に", ("none",)),
    Entry("足場_クレーンを消す.py", "crane_run.py", ("--remove",), "クレーンを消す",
          "置いたクレーンを消す（控え ashiba_out/クレーン.json の部品だけ）", ("none",)),
    Entry("足場_揚重判定.py", "crane_check.py", ("--lift",), "揚重判定",
          "クレーンと吊る部材（柱・梁・壁・床・オブジェクト）を選んでから押す。重さ（体積×密度。柱・梁 7.85・ほか 2.4t/m³）と"
          "作業半径・要るフックの高さから 揚重可能（緑）・重すぎ（橙）・遠すぎ（灰）・高すぎ（黄）に色分けし、帳票に", ("none",)),
    Entry("足場_ブームの干渉.py", "crane_check.py", ("--clash",), "ブームの干渉",
          "クレーンを選んでから押す。ブームの中心軸から 1,000 以内の躯体を赤（接触）、4,000 以内を黄（警告）に色分けし、帳票に",
          ("none",)),
    Entry("足場_判定の色を消す.py", "crane_check.py", ("--clear",), "判定の色を消す",
          "揚重判定・ブームの干渉の色を消す", ("none",)),
    Entry("足場_敷鉄板.py", "plate_run.py", (), "敷鉄板",
          "敷く範囲の線（ポリライン・線）を選んでから押す。日建の厚板鋼板 5×10（1,524×3,048・802kg）で覆う部品を置く。"
          "置いたあとは平面のホットスポット（右の辺・上の辺の真ん中）で引けば広がり、1枚の倍数に切り上がる。枚数・重さ・固定金具は帳票に",
          ("none",)),
    Entry("足場_敷鉄板を消す.py", "plate_run.py", ("--remove",), "敷鉄板を消す",
          "置いた敷鉄板を消す（控え ashiba_out/敷鉄板.json の部品だけ。クレーンの下の敷鉄板はクレーンを消すと消える）", ("none",)),
    Entry("足場_乗入れ構台.py", "kodai_run.py", (), "乗入れ構台",
          "構台の範囲の線（ポリライン・線。始めの辺＝進行方向）を選んでから押す。覆工板・根太・大引・支柱・水平つなぎ・垂直ブレース・"
          "手すり・入口のスロープを置き、根太・大引・支柱・支持力・ブレースの検定（25t ラフター）と数量を帳票に。置いたあとは"
          "ホットスポットで広げられる", ("none",)),
    Entry("足場_乗入れ構台3m.py", "kodai_run.py", ("--deck3", "1"), "構台 3mを1列",
          "「乗入れ構台」と同じで、覆工板の 3m（624kg）を必ず1列混ぜる（残りは 2m）。「乗入れ構台」は幅が奇数 m のときだけ 3m を1列。"
          "置いたあとも部品の設定の「3m の覆工板」で列の数と位置を変えられる", ("none",)),
    Entry("足場_構台の検定.py", "kodai_run.py", ("--recheck",), "構台の検定",
          "置いた構台を、ホットスポットで動かした支柱（構台杭）・大引・水平つなぎの位置と、設定で選んだ H形鋼・覆工板で検定し直し、"
          "帳票と最大積載荷重の注記を新しくする", ("none",)),
    Entry("足場_構台を消す.py", "kodai_run.py", ("--remove",), "構台を消す",
          "置いた構台を消す（控え ashiba_out/構台.json の部品だけ）", ("none",)),
    Entry("足場_場内通路.py", "route_run.py", (), "場内通路",
          "通路の中心線（ポリライン。始め＝ゲートの側）を選んでから押す。通路の帯（一方通行 4.0m）・曲がり角の車両の掃引（10t ダンプ）・"
          "敷鉄板 5×20 の縦敷きを置き、通路の幅・曲がり角の拡幅・敷鉄板の数量を帳票に", ("none",)),
    Entry("足場_場内通路を消す.py", "route_run.py", ("--remove",), "場内通路を消す",
          "置いた場内通路と敷鉄板を消す（控え ashiba_out/場内通路.json の部品だけ）", ("none",)),
    Entry("足場_仮設建物.py", "house_run.py", (), "仮設建物",
          "建物の手前の線（始めの辺＝長手、始め＝左の隅）を選んでから押す。スーパーハウス 3.8坪の事務所を1棟置く。型・連棟・段・用途は"
          "部品の設定で変え、「仮設建物の検定」で便所の数・事務所の広さ・休憩所・転倒などを判定し直す", ("none",)),
    Entry("足場_仮設事務所2階.py", "house_run.py", ("--units", "3", "--tiers", "2", "--use", "事務所,事務所"), "仮設事務所 2階",
          "「仮設建物」と同じで、3.8坪を3連棟の2段積み（1階を連棟に）、手前に外廊下と左の端に外階段", ("none",)),
    Entry("足場_仮設トイレ.py", "house_run.py", ("--type", "6", "--units", "4"), "仮設トイレ",
          "線を選んで押す。仮設トイレ（洋式・個室）を横に4基。便所の数は安衛則 628条（男性の大便所 60人・小便所 30人・女性 20人ごと）",
          ("none",)),
    Entry("足場_仮設建物の検定.py", "house_run.py", ("--recheck",), "仮設建物の検定",
          "置いた仮設建物（設定を変えたあとの形）と人数（職員・男性・女性。--people で控える）で、便所の数・事務所の広さ・休憩所・"
          "休養室・消火器・転倒を判定し直して帳票に", ("none",)),
    Entry("足場_仮設建物を消す.py", "house_run.py", ("--remove",), "仮設建物を消す",
          "置いた仮設建物を消す（控え ashiba_out/仮設建物.json の部品だけ）", ("none",)),
    Entry("足場_開口養生.py", "opening_run.py", (), "開口養生",
          "床（スラブ）を選んでから押す（選んでいなければ全部の床）。床の開口を拾い、大きさで 蓋 12mm・24mm か 手すり・幅木・水平ネット"
          "を置く。下の床までの落差（2m 以上は安衛則 519条で義務）とネットの下の空き（安全ネット指針）を帳票に", ("none",)),
    Entry("足場_床の縁の手すり.py", "opening_run.py", ("--edges-only",), "床の縁の手すり",
          "床を選んで押す。外に同じ高さの床が続かない縁に手すり 950・中桟 450・幅木 150（外部足場の無い所）", ("none",)),
    Entry("足場_開口養生を消す.py", "opening_run.py", ("--remove",), "開口養生を消す",
          "置いた開口養生・床の縁の手すりを消す（控え ashiba_out/開口養生.json の部品だけ）", ("none",)),
    Entry("足場_歩行者通路の柵.py", "fence_run.py", (), "歩行者通路の柵",
          "柵を立てる線（ポリライン・線）を選んでから押す。PPフェンス PP1512G（1,500×1,214）を1枚ずつ、ジョイント・ウエイトを数えて"
          "発注表に（歩行者用通路は幅 0.75m・多い所 1.5m 以上、有効高さ 2.1m）", ("none",)),
    Entry("足場_防護柵.py", "fence_run.py", ("--kind", "vulcan", "--road"), "防護柵",
          "線を選んで押す。車両の通路と接する所にバルカンバリア JW4型（4,115・463kg、アンカーで A種相当）を1基ずつ", ("none",)),
    Entry("足場_柵を消す.py", "fence_run.py", ("--remove",), "柵を消す",
          "置いた柵を消す（控え ashiba_out/柵.json の部品だけ）", ("none",)),
    Entry("足場_親綱.py", "lifeline_run.py", (), "親綱",
          "鉄骨梁を選んでから押す（選んでいなければ全部の梁）。上フランジに親綱支柱 NTP を立て、スパン（10m 以下かつ 40(H−4)/11、H は"
          "下の床までの落差）ごとに親綱 NSPR20 と緊張器 NSPJK。1スパン1人、角の支柱は2方向で共有しない。発注表を帳票に", ("none",)),
    Entry("足場_親綱を消す.py", "lifeline_run.py", ("--remove",), "親綱を消す",
          "置いた親綱を消す（控え ashiba_out/親綱.json の部品だけ）", ("none",)),
    Entry("足場_型枠.py", "form_run.py", (), "型枠",
          "壁・柱・梁・スラブを選んでから押す（何も選んでいなければ全部）。側圧から桟木・外端太・フォームタイの間隔を決め、型枠"
          "（せき板・桟木・外端太・フォームタイ、梁は底板と受けの単管）を置く。スラブはせき板・根太・大引と支保工（パイプサポート・"
          "水平つなぎ）。材料の目安と計算を帳票に書く。角・T字・柱との取り合いは相手の型枠から飛び出さないように止める",
          ("struct", "slab", "none")),
    Entry("足場_支保工足場.py", "shoring_run.py", (), "支保工足場",
          "「型枠」のあとに、スラブを選んでから押す（何も選んでいなければ全部）。スラブの下のパイプサポートを、梁・壁で区切った"
          "長方形ごとの内部足場（用途 支保工。承認値・水平荷重 5%・Uジャッキ・設置届を検定）に置き換える。図面は「型枠計画図」に出る",
          ("slab", "none")),
    Entry("足場_支保工をパイプサポートに.py", "shoring_run.py", ("--pipe",), "支保工を戻す",
          "支保工足場にしたスラブを選んでから押す（何も選んでいなければ全部）。内部足場を消してパイプサポートに戻す",
          ("slab",)),
    Entry("足場_型枠支保工計画図.py", "form_plan_run.py", (), "型枠計画図",
          "「型枠」で型枠を置いたあとに押す。型枠支保工計画図（伏図・断面図と詳細図・構造計算書・計画届の要否と様式第20号の"
          "下書き）を A3 の PDF に、計算書を xlsx にして帳票の出力先に書き、同じ図をレイアウト「型枠支保工 1〜」にも描く",
          ("struct", "slab", "none")),
    Entry("足場_型枠の撤去.py", "form_run.py", ("--remove",), "型枠の撤去",
          "「型枠」で置いた型枠（壁・柱・梁・スラブの型枠と支保工）と、型枠支保工のレイアウトを消す（躯体と足場は消さない）",
          ("none",)),
    Entry("足場_取り入れ口.py", "intake_run.py", (), "取り入れ口",
          "平面で、資材を取り込む幅に足場の面に沿って線を引いて選んでから押す。窓で層を選んで「付ける」と、そのスパンの"
          "固定の手すり・幅木を外して可動手すりにし、シートは巻き上げ式にする（「外す」で戻す）", ("none",)),
    Entry("足場_内部足場.py", "interior_stage_run.py", (), "内部足場",
          "平面で、室内のステージを組む範囲に長方形（ポリラインの4点か対角の線）を引いて選んでから押す。作業床の高さ・積載を"
          "入れて置くと、格子の支柱と全面の作業床の内部ステージ足場を置き、検証と数量を帳票に書く", ("none",)),
    Entry("足場_仮設通路.py", "walkway_run.py", (), "仮設通路",
          "平面で、渡す所に線を1本（始め→終わりの向き）引いて選んでから押す。床の高さ・機種を入れて置くと、両端の島"
          "（始めは階段つき）とアルミの伸縮通路（日工セック ライトブリッジ）を置き、検証と数量を帳票に書く", ("none",)),
    Entry("足場_支柱だけ分解.py", "explode_line.py", (), "支柱だけ分解",
          "足場ライン（区切った部品でもよい）を選んでから押す。支柱（枠組は建枠）を1本ずつの部品にする", ("line",)),
    Entry("足場_分解を戻す.py", "explode_line.py", ("--undo",), "分解を戻す",
          "分解した足場ライン（または支柱）を選んでから押す。支柱を消して足場ラインで描く", ("line", "member")),
    Entry("足場_3D表示.py", "toggle_3d.py", (), "3D表示",
          "押すたびに足場の3Dを 自動→軽量→線→ブロック→精細 と切り替える（重いときは軽量か線、取り合いはブロック）",
          ("line", "none")),
    Entry("足場_平面表示.py", "toggle_plan.py", (), "平面表示",
          "押すたびに足場の平面を 詳細→精細（実寸）→単線 と切り替える（精細は支柱・布材・踏板・幅木を太さ・幅どおり）",
          ("line", "none")),
    Entry("足場_条件.py", "spec_form_run.py", (), "条件",
          "条件の窓を開く（足場の種類・系列・幅・手すり・階段・朝顔・養生・高さ・立面断面）。「保存して配置」で置き直す。"
          "細かい条件（離れ・ネット・部材編集）は足場条件の部品を選んで ⌘T", ("slab", "none")),
    Entry("足場_条件の登録.py", "spec_preset.py", ("save",), "条件の登録",
          "足場条件の部品の「登録名」に名前を書いてから押す。条件（建物ごとの値を除く）を控える", ("spec",)),
    Entry("足場_条件の呼び出し.py", "spec_preset.py", ("load",), "条件の呼び出し",
          "別の建物の足場条件の部品の「登録名」に登録した名前を書いてから押し、「配置」で置き直す", ("spec",)),
    Entry("足場_図面を作る.py", "drawings_run.py", (), "図面を作る",
          "足場の調整が済んだら押す。立面図・断面図・平面図・詳細図のレイアウトと PDF を作る（足場は置き直さない）。"
          "断面は、平面に足場を横切る線を引いて選んでから押すとその線で切る（線なしは前の線か自動の A-A・B-B）",
          ("none", "line", "slab")),
    Entry("足場_ペン.py", "pen_colors.py", (), "ペン",
          "図面のペンを区分ごと（支柱・足場の線・床・階段・付帯設備・壁つなぎ・層間ネット・養生・寸法文字）に色見本から選ぶ。"
          "「適用」で置いてある足場をその場で書き換え、次の配置でも使う", ("none",)),
    Entry("足場_帳票.py", "open_outputs.py", (), "帳票",
          "帳票の出力先を開き、最新の割付レポートを開く", ("none", "slab")),
    Entry("足場_撤去.py", "remove_from_archicad.py", (), "撤去",
          "躯体スラブを選んでから押す。足場部品と立面・平面・詳細図のレイアウトを消す", ("slab",)),
)


def _action(title: str) -> Entry:
    return next(a for a in ACTIONS if a.title == title)


# パレットの窓の組（ACTIONS のすべてをどれか1つの組に）
PANEL_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    # 利用者の指定（2026-11-01）「パレットを整理して」: 仕事の種類ごとの組に分け、窓の上で組を選んでその組のボタンだけを出す
    ("足場を建てる", ("配置", "地足場", "箱を置く", "箱を足場に", "手動配置", "内部足場", "仮設通路", "条件", "条件の登録",
                      "条件の呼び出し")),
    ("足場を直す", ("解き直し", "区切る", "区切りを戻す", "面の切替", "朝顔の面", "朝顔の範囲", "幅の変更", "階段の位置", "開口",
                    "昇降機", "取り入れ口", "支柱だけ分解", "分解を戻す")),
    ("足場を見る・出す", ("3D表示", "平面表示", "図面を作る", "ペン", "帳票", "撤去")),
    ("型枠・支保工", ("型枠", "支保工足場", "支保工を戻す", "型枠計画図", "型枠の撤去")),
    ("山留め・構台", ("切梁上の足場", "外周の足場", "山留めの手すり", "乗入れ構台", "構台 3mを1列", "構台の検定", "構台を消す")),
    ("揚重・敷鉄板", ("クレーン", "揚重判定", "ブームの干渉", "判定の色を消す", "クレーンを消す", "敷鉄板", "敷鉄板を消す")),
    ("場内・仮設建物", ("仮囲い", "仮囲いを消す", "場内通路", "場内通路を消す", "歩行者通路の柵", "防護柵", "柵を消す", "仮設建物",
                        "仮設事務所 2階", "仮設トイレ", "仮設建物の検定", "仮設建物を消す")),
    ("墜落・落下防止", ("開口養生", "床の縁の手すり", "開口養生を消す", "親綱", "親綱を消す")),
)


def panel_layout() -> list[dict]:
    """パレットの窓に渡す並び [{group, actions: [{title, hint, when}]}]."""
    return [{"group": g, "actions": [{"title": a.title, "hint": a.hint, "when": list(a.when)}
                                     for a in (_action(t) for t in titles)]}
            for g, titles in PANEL_GROUPS]


# Tapir の一覧に置く入口は1つ（パレットの窓を開く）。以前はメニュー＋よく使う3つの4つだった
ENTRIES: tuple[Entry, ...] = (
    Entry("仮設_パレット.py", "ashiba_palette.py", (), "パレット",
          "仮設パレットの窓を開く。窓のボタンで配置・解き直し・区切る・3D表示などを実行する"
          "（★は今の選択に合う操作）", quiet=True),
)


def menu_items(kinds: set) -> list[Entry]:
    """メニューの並び: 選んでいるものに合う操作を先に、残りはその後（並びは ACTIONS の順）."""
    kinds = set(kinds) or {"none"}
    hit = [a for a in ACTIONS if set(a.when) & kinds]
    return hit + [a for a in ACTIONS if a not in hit]


def summary(output: str, limit: int = 14) -> str:
    """実行の出力から、ダイアログに出す要点の行（keys で始まる行）。無ければ最後の数行."""
    keys = ("足場ライン", "総合判定", "  是正", "  要確認", "  表題欄", "  詳細図:", "  平面図:", "  立面:", "  PDF:",
            "書き込み", "配置時と同じ", "撤去", "足場部品", "立面図（断面", "注意:", "エラー", "[ashiba]",
            "足場条件", "帳票", "建物が分かりません", "この建物の", "配置:", "条件:", "朝顔の面", "朝顔の範囲", "幅の変更", "階段の位置", "図面を作る", "  図面:", "取り入れ口", "昇降機", "内部足場", "仮設通路", "  検証", "地足場", "手動配置", "箱を置く", "箱を足場に", "型枠",
            "  計算書", "  計画届", "TapirError", "TapirTimeout", "Traceback")
    lines = [ln.rstrip() for ln in output.splitlines() if ln.strip()]
    picked = [ln for ln in lines if ln.startswith(keys) or ln.lstrip().startswith(keys)]
    if not picked:
        picked = lines[-6:]
    if len(picked) > limit:
        picked = picked[:limit - 1] + [f"…ほか {len(picked) - limit + 1} 行（ashiba_out/パレット実行.log）"]
    return "\n".join(picked)


ENTRY_TEMPLATE = '''#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = []
# ///
# -*- coding: utf-8 -*-
{mark}
"""仮設足場 {title}

Tapir パレットから呼ぶ入口（python3 scripts/install_palette.py で作り直す。手で直さない）。
{hint}
本体は <ashiba>/scripts/{script}。Tapir が付ける --port は ASHIBA_PORT に移して本体へ渡す。
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.realpath(__file__))           # <ashiba>/tapir/palette（リンクをたどる）
ROOT = os.path.dirname(os.path.dirname(HERE))
SCRIPT = os.path.join(ROOT, "scripts", "{script}")
ARGS = {args!r}
TITLE = "仮設足場 {title}"
QUIET = {quiet}
OUT = os.path.join(os.path.expanduser("~"), "Desktop", "ashiba_out")


{summary_src}

def _port():
    a = sys.argv[1:]
    for i, v in enumerate(a):
        if v == "--port" and i + 1 < len(a):
            return a[i + 1]
        if v.startswith("--port="):
            return v.split("=", 1)[1]
    return ""


def _dialog(text, with_report):
    text = text.replace("\\\\", "\\\\\\\\").replace('"', '\\\\"')
    buttons = '{{"割付レポートを開く", "OK"}}' if with_report else '{{"OK"}}'
    script = 'display dialog "' + text + '" with title "' + TITLE + '" buttons ' + buttons + ' default button "OK"'
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if r.returncode != 0:
        # 画面を持たないプロセスからは出せないことがある。理由をログに足す
        try:
            with open(os.path.join(OUT, "パレット実行.log"), "a", encoding="utf-8") as f:
                f.write("\\n[ダイアログを出せませんでした] " + (r.stderr or "").strip() + "\\n")
        except OSError:
            pass
    return "割付レポートを開く" in (r.stdout or "")


DESKTOP_HELP = ("Archicad からデスクトップの ashiba_out を読めません（macOS の許可待ち）。\\n\\n"
                "システム設定 → プライバシーとセキュリティ → ファイルとフォルダ → Archicad で\\n"
                "「デスクトップフォルダ」をオンにしてから、もう一度押してください。\\n"
                "（項目が無ければ Archicad を再起動すると許可を求める窓が出ます）")


def _desktop_ok():
    """デスクトップを読めるか（許可待ちだと黙って止まるので、別プロセスで5秒だけ試す）."""
    try:
        subprocess.run(["/bin/ls", os.path.dirname(OUT)], capture_output=True, timeout=5)
        return True
    except subprocess.TimeoutExpired:
        return False


def main():
    if not _desktop_ok():
        if os.environ.get("ASHIBA_PALETTE_NODIALOG"):
            print(DESKTOP_HELP)
        else:
            _dialog(DESKTOP_HELP, False)
        return 3
    py = "/usr/local/bin/python3.13" if os.path.exists("/usr/local/bin/python3.13") else sys.executable
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    port = _port()
    if port:
        env["ASHIBA_PORT"] = port
    if QUIET:                                            # 窓を開くだけ（結果は窓に出る）
        return subprocess.run([py, SCRIPT] + list(ARGS), env=env, cwd=ROOT,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
    proc = subprocess.run([py, SCRIPT] + list(ARGS), capture_output=True, text=True, env=env, cwd=ROOT)
    out = (proc.stdout or "") + (proc.stderr or "")
    try:
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, "パレット実行.log"), "w", encoding="utf-8") as f:
            f.write(TITLE + "\\n" + out)
    except OSError:
        pass
    head = "完了" if proc.returncode == 0 else "止まりました（終了コード " + str(proc.returncode) + "）"
    reports = sorted((os.path.join(OUT, n) for n in os.listdir(OUT) if n.endswith("_割付レポート.md")),
                     key=os.path.getmtime) if os.path.isdir(OUT) else []
    text = head + "\\n\\n" + summary(out)
    if os.environ.get("ASHIBA_PALETTE_NODIALOG"):        # 試験用: ダイアログを出さずに要点を出す
        print(text)
        return proc.returncode
    if _dialog(text, bool(reports)) and reports:
        subprocess.run(["open", reports[-1]])
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
'''


def entry_source(e: Entry) -> str:
    """入口ファイルの中身（要点の関数は summary をそのまま埋め込む）."""
    return ENTRY_TEMPLATE.format(mark=MARK, title=e.title, hint=e.hint, script=e.script, args=tuple(e.args),
                                 quiet=bool(e.quiet),
                                 summary_src=inspect.getsource(summary))
