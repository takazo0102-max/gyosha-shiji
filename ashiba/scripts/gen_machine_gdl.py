"""部品 ashiba_machine（重機 1台に1部品）の HSF を書き出す.

利用者の指定（2026-11-01）「重機の詳細度もっとあげて　種類も増やして」。機種と寸法は src/ashiba/machine.py（出典はそちら）、置くのは
scripts/machine_run.py。mcKind 1 バックホウ・2 クローラクレーン・3 コンクリートポンプ車・4 生コン車（トラックミキサ）・5 ダンプ・
6 高所作業車（トラック式）・7 垂直昇降（自走式シザース）・8 三点式杭打機（SMW の3軸も）・9 アースドリル・10 全周回転機・11 解体機・
12 圧入機。バックホウ・解体機の先は解体アタッチメント（atK 1 圧砕機・2 鉄骨切断機・3 つかみ機・4 ブレーカ）、クローラクレーンの
フックにバイブロ（vbK）。原点＝旋回中心の地盤（ミキサ・ダンプ・垂直昇降は車体の真ん中）、+X＝車体の前。旋回 slew で上部（バックホウ・
クローラクレーンの上部旋回体、ポンプ車・高所作業車のブーム）を回す。

クローラ（履帯の全長 trkL・全幅 trkW・シュー幅 shoeW・高さ trkH）は履帯の板（グローサ）・遊動輪・起動輪・下転輪まで、上部旋回体は後端
旋回半径 tailR の円弧の後ろ（カウンタウエイト）・エンジンカバー・運転室の窓、バックホウはくの字のブーム・アーム・バケット（爪）と
3本のシリンダ、クローラクレーンはラチスブーム（主材4本・斜材）・ガントリ・ペンダント・フック。トラックは運転室（傾いた前窓）・
フレーム・前輪と後ろの2軸・フェンダー・サイドガード・燃料タンク、ポンプ車は旋回台と折り曲げのブーム（段ごとの角度 pA1〜pA5）と
輸送管・先端ホース・アウトリガ4本・ホッパ、生コン車は傾いたドラム（前後の円錐）・ホッパ・シュート・水タンク、ダンプは荷台
（あおり・鳥居）と上げ角 bedA・ホイストシリンダ、高所作業車は伸縮ブームとバスケット（手すり）、アウトリガは3組まで
（o1〜o3 の位置と張出スパン）、垂直昇降は車台・X 字の腕3段・作業床（高さ pfH）と手すり。
平面は外形・上部の外形（旋回で回す）・後端旋回半径（立入禁止）・作業半径（maxR）・アウトリガの位置・注記。
  python3 scripts/gen_machine_gdl.py     # gdl/hsf/ashiba_machine を書き直す（そのあと build_flat_gdl・build_dist_gsm）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from gen_hoist_gdl import _param  # noqa: E402
from gen_ywall_gdl import _list  # noqa: E402
import gdl_draft  # noqa: E402
import gdl_radii  # noqa: E402

OUT = ROOT / "gdl" / "hsf" / "ashiba_machine"
MAIN_GUID = "5C2E8A71-3D96-4B1F-A7E4-9F6B2D8C1A35"


def paramlist() -> str:
    ps = [
        _param("Length", "A", "Dimension 1", 1, True),
        _param("Length", "B", "Dimension 2", 1, True),
        _param("Length", "ZZYZX", "Height", 1, True),
        _param("Integer", "mcKind", "種類（1 バックホウ・2 クローラクレーン・3 ポンプ車・4 生コン車・5 ダンプ・6 高所作業車・7 垂直昇降・"
               "8 三点式杭打機・9 アースドリル・10 全周回転機・11 解体機・12 圧入機・13 搬入トラック・14 トレーラー連結車）", 1),
        _param("Integer", "mcModel", "機種（選ぶと寸法を書き込む。0＝手入力）", 3),
        _param("String", "mcName", "機種の名前（平面の注記）", "バックホウ 0.45m³"),
        _param("String", "mcNote", "諸元の注記", ""),
        _param("Angle", "slew", "旋回角（車体の前から左回り）", 0.0),
        _param("Integer", "cbS", "運転室の側（1＝左・-1＝右）", 1),
        # クローラ
        _param("Length", "trkL", "履帯の全長", 4.45),
        _param("Length", "trkW", "履帯の全幅", 2.8),
        _param("Length", "shoeW", "シュー幅", 0.6),
        _param("Length", "trkH", "履帯の高さ", 0.85),
        # 上部旋回体
        _param("Length", "upF", "上部旋回体の前端（旋回中心から）", 1.6),
        _param("Length", "upW", "上部旋回体の幅", 2.7),
        _param("Length", "tailR", "後端旋回半径", 2.75),
        _param("Length", "upZ", "上部旋回体の下端の高さ", 1.0),
        _param("Length", "upH", "運転室の上の高さ（全高）", 2.95),
        _param("Length", "cabW", "運転室の幅", 0.95),
        _param("Length", "cabL", "運転室の長さ", 1.6),
        # バックホウ
        _param("Length", "pvX", "ブームの根元（旋回中心から前）", 0.15),
        _param("Length", "pvH", "ブームの根元の高さ", 1.75),
        _param("Length", "boomL", "ブームの長さ（根元から先の弦）", 5.7),
        _param("Length", "armL", "アームの長さ", 2.9),
        _param("Length", "bkL", "バケットの長さ（ピンから爪）", 1.45),
        _param("Length", "bkW", "バケットの幅", 1.05),
        _param("Length", "bmY", "作業機の中心のずれ（旋回中心から左が +）", 0.0),
        _param("Angle", "bmA", "ブームの角度（弦）", 35.0),
        _param("Angle", "amA", "アームの角度（水平から）", -70.0),
        _param("Angle", "bkA", "バケットの角度（水平から）", -150.0),
        _param("Length", "maxR", "最大作業半径（平面の円）", 9.9),
        _param("Length", "maxD", "最大掘削深さ", 6.6),
        _param("Length", "bldW", "排土板の幅（0＝無し）", 0.0),
        _param("Length", "bldH", "排土板の高さ", 0.45),
        # クローラクレーン
        _param("Length", "lbL", "ラチスブームの長さ", 30.0),
        _param("Angle", "lbA", "ブームの起伏角", 70.0),
        _param("Boolean", "lbGnd", "ブームを地面に寝かせる（組立モード）", 0),
        _param("Boolean", "lbRW", "赤白ブーム", 0),
        _param("Boolean", "lbFat", "太トラス（トラスを目立たせる）", 0),
        _param("Boolean", "wrOn", "作業半径を 3D に描く", 0),
        _param("Boolean", "infoOn", "クレーン情報を 3D に描く", 0),
        *gdl_radii.params(_param),
        _param("RealNum", "texZ", "クレーン情報の文字の高さ（m）", 0.6),
        _param("Integer", "mcClr", "色の組（0 重機の既定・1 コベルコの青緑）", 0),
        _param("Length", "lbR", "作業半径（旋回中心からフック。平面のフックのホットスポットで引くと起伏角が変わる）", 11.0),
        _param("Length", "hfX", "フックの位置 X（平面のホットスポットで引くと起伏角と旋回が変わる）", 11.0),
        _param("Length", "hfY", "フックの位置 Y", 0.0),
        _param("Length", "jbL", "ジブの長さ（0＝ジブなし）", 0.0),
        _param("Angle", "jbO", "ジブのオフセット角", 10.0),
        _param("RealNum", "sfRate", "安全率（定格総荷重に掛ける。0.9＝90%）", 0.9),
        _param("String", "rtB", "定格総荷重表のブーム長さ（mm）", ""),
        _param("String", "rtR", "定格総荷重表の作業半径（mm）", ""),
        _param("String", "rtN", "ブームごとの最小の作業半径（mm）", ""),
        _param("String", "rtX", "ブームごとの最大の作業半径（mm）", ""),
        *[_param("String", f"rc{i}", f"定格総荷重（10kg 単位。{i}番目のブーム）", "") for i in range(1, 6)],
        _param("String", "jrR", "ジブの定格総荷重表の作業半径（mm。選んだブームとジブの組）", ""),
        _param("String", "jrT", "ジブの定格総荷重（10kg 単位）", ""),
        _param("Length", "jrN", "ジブの最小の作業半径", 0.0),
        _param("Length", "jrX", "ジブの最大の作業半径", 0.0),
        _param("Length", "lbW", "ブームの幅", 1.2),
        _param("Length", "hkD", "ブームの先からフックまで", 6.0),
        _param("Length", "hkH", "フックの全高", 1.47),
        _param("Length", "hkW", "フックの幅", 0.59),
        _param("Length", "hkT", "フックの厚み", 0.435),
        _param("Length", "gnX", "ガントリ頂部（旋回中心から後ろ）", 3.16),
        _param("Length", "gnH", "ガントリ頂部の高さ", 6.145),
        _param("Length", "cwW", "カウンタウエイトの幅（0＝上部旋回体と同じ）", 0.0),
        _param("Length", "cwH", "カウンタウエイトの高さ（0＝上に載る薄い形）", 0.0),
        # トラック
        _param("Length", "carL", "全長", 8.0),
        _param("Length", "carW", "全幅", 2.49),
        _param("Length", "carF", "原点から前端", 4.0),
        _param("Length", "cabH", "運転室の上の高さ", 3.0),
        _param("Length", "frOv", "前端から前の車軸", 1.3),
        _param("Length", "wb", "前の車軸から後ろの車軸（1軸め）", 4.0),
        _param("Integer", "nFr", "前の車軸の数", 1),
        _param("Length", "frSp", "前の車軸の間", 1.7),
        _param("Integer", "nRear", "後ろの車軸の数", 2),
        _param("Length", "rearSp", "後ろの車軸の間", 1.3),
        _param("Length", "whR", "タイヤの半径", 0.5),
        _param("Length", "frZ", "フレームの上の高さ", 1.0),
        # ポンプ車・高所作業車のブームとアウトリガ
        _param("Integer", "nSec", "ブームの段の数", 4),
        _param("Length", "sL1", "ブーム1段の長さ", 7.5),
        _param("Length", "sL2", "ブーム2段の長さ", 6.5),
        _param("Length", "sL3", "ブーム3段の長さ", 6.5),
        _param("Length", "sL4", "ブーム4段の長さ", 6.0),
        _param("Length", "sL5", "ブーム5段の長さ", 0.0),
        _param("Angle", "pA1", "ブーム1段の角度", 70.0),
        _param("Angle", "pA2", "ブーム2段の角度", 25.0),
        _param("Angle", "pA3", "ブーム3段の角度", -10.0),
        _param("Angle", "pA4", "ブーム4段の角度", -60.0),
        _param("Angle", "pA5", "ブーム5段の角度", -80.0),
        _param("Length", "tuH", "ブームの根元の高さ", 3.2),
        _param("Length", "o1x", "アウトリガ1組め（原点から前が +）", 1.4),
        _param("Length", "o1y", "アウトリガ1組めの張出スパン", 5.43),
        _param("Length", "o2x", "アウトリガ2組め", -2.0),
        _param("Length", "o2y", "アウトリガ2組めの張出スパン", 5.43),
        _param("Length", "o3x", "アウトリガ3組め", -4.6),
        _param("Length", "o3y", "アウトリガ3組めの張出スパン（0＝無し）", 2.3),
        _param("Boolean", "otOn", "アウトリガを張る", 1),
        # 生コン車・ダンプ・高所作業車
        _param("Length", "drL", "ドラムの長さ", 4.3),
        _param("Length", "drD", "ドラムの径", 2.1),
        _param("Angle", "drA", "ドラムの傾き", 14.0),
        _param("Length", "bedL", "荷台の長さ", 5.1),
        _param("Length", "bedW", "荷台の幅", 2.25),
        _param("Length", "bedH", "あおりの高さ", 0.6),
        _param("Angle", "bedA", "荷台の上げ角", 0.0),
        _param("Length", "abL", "伸縮ブームの長さ（今）", 9.0),
        _param("Angle", "abA", "伸縮ブームの起伏角", 55.0),
        _param("Length", "pfL", "バスケットの長さ", 1.2),
        _param("Length", "pfW", "バスケットの幅", 0.7),
        _param("Length", "pfH", "作業床の高さ（垂直昇降）", 3.0),
        # 解体アタッチメント（バックホウ・解体機の先）
        _param("Integer", "atK", "アタッチメント（0 バケット・1 圧砕機・2 鉄骨切断機・3 つかみ機・4 ブレーカ・5 バイブロ）", 0),
        _param("Length", "atL", "アタッチメントの本体長さ（ピンから先端）", 2.0),
        _param("Length", "atW", "アタッチメントの最大開口幅（ブレーカはチゼル径）", 1.0),
        _param("Angle", "atO", "爪の開き", 50.0),
        # 三点式杭打機（リーダ・ステー・オーガ・ジャッキ）
        _param("Length", "ldX", "リーダの中心（旋回中心から前）", 3.0),
        _param("Length", "ldL", "リーダの長さ", 33.0),
        _param("Length", "ldDia", "リーダの主管の径", 0.66),
        _param("Length", "ldZ", "リーダの下端の高さ", 0.35),
        _param("Length", "stZ", "ステーの上端の高さ", 26.75),
        _param("Length", "auOff", "オーガの中心（リーダから前）", 1.24),
        _param("Length", "auD", "オーガの径（アースドリルはバケットの径）", 0.6),
        _param("Length", "auL", "スクリューの長さ", 28.8),
        _param("Length", "auZ", "オーガのモータの下端の高さ", 30.25),
        _param("Integer", "auN", "オーガの本数（SMW は 3）", 1),
        _param("Length", "auP", "オーガの軸間", 0.45),
        _param("Length", "auH", "モータの高さ", 2.6),
        _param("Length", "auW", "モータの前後の長さ", 1.2),
        _param("Length", "fjX", "フロントジャッキ（旋回中心から前）", 3.61),
        _param("Length", "fjW", "フロントジャッキの間", 2.52),
        _param("Length", "rjX", "後ろのアウトリガ（旋回中心から後ろ）", 3.64),
        _param("Length", "rjW", "後ろのアウトリガの幅", 4.1),
        # アースドリル
        _param("Length", "tbL", "テレスコブームの長さ", 20.6),
        _param("Angle", "tbA", "テレスコブームの起伏角", 82.5),
        _param("Length", "kdR", "掘削中心（旋回中心から前）", 4.492),
        _param("Length", "kdZ", "ケリードライブの高さ", 1.5),
        _param("Length", "kyD", "ケリーバの径", 0.53),
        _param("Length", "bkH", "ドリリングバケットの高さ", 2.089),
        _param("Length", "bkD", "バケットの下端の深さ（地面から下）", 0.0),
        # 全周回転機
        _param("Length", "rtL", "本体の長さ", 4.148),
        _param("Length", "rtW", "本体の幅", 3.167),
        _param("Length", "rtH", "本体の高さ（手すりの上）", 3.086),
        _param("Length", "rtD", "本体の通り穴の径", 1.98),
        _param("Length", "rtS", "チャックの上がり（押抜ストローク）", 0.0),
        _param("Length", "brL", "反力ブラケットを含む長さ", 8.39),
        _param("Length", "brW", "反力ブラケットを含む幅", 6.98),
        _param("Length", "csD", "ケーシングの径", 1.5),
        _param("Length", "csH", "ケーシングの本体の上の高さ", 2.0),
        _param("Length", "puX", "油圧ユニット・パワーユニットの芯（前が +）", -7.5),
        _param("Length", "puY", "油圧ユニット・パワーユニットの芯（左が +）", 0.0),
        _param("Length", "puL", "ユニットの長さ", 4.8),
        _param("Length", "puW", "ユニットの幅", 2.105),
        _param("Length", "puH", "ユニットの高さ", 2.112),
        # 解体機のフロント（3段の弦の長さと水平からの角度。先の角度は bkA）
        _param("Length", "dbL1", "メインブーム（＋インサート）", 6.0),
        _param("Length", "dbL2", "フロントブーム（＋インター）", 8.35),
        _param("Length", "dbL3", "アーム", 8.7),
        _param("Angle", "dA1", "メインブームの角度", 65.0),
        _param("Angle", "dA2", "フロントブームの角度", 85.0),
        _param("Angle", "dA3", "アームの角度", -30.0),
        # 圧入機（完成杭の上。チャックに次の杭）
        _param("Length", "piL", "圧入機の全長", 2.07),
        _param("Length", "piW", "圧入機の全幅", 1.0),
        _param("Length", "piH", "圧入機の全高", 2.32),
        _param("Length", "piC", "チャック投入高", 0.955),
        _param("Length", "piS", "チャックの上がり", 0.0),
        _param("Length", "piP", "鋼矢板の幅", 0.4),
        _param("Integer", "piN", "後ろの完成杭の枚数", 4),
        _param("Length", "piT", "チャックの杭の天端（チャックの上）", 3.0),
        # 搬入トラック（荷台は bedL・bedW・bedH・bedA を使う）
        _param("Length", "flZ", "荷台の床面地上高", 1.09),
        _param("Length", "trT", "後ろの輪距（トレッド）", 1.66),
        _param("Length", "tnR", "最小回転半径（最外側のわだち）", 7.2),
        _param("Length", "rpL", "道板の長さ（0＝無し）", 0.0),
        _param("Boolean", "ucOn", "クレーン付き", 0),
        _param("Length", "ucX", "クレーンの旋回中心（原点から前が +）", 1.7),
        _param("Length", "ucL", "クレーンのブームの長さ（今）", 7.78),
        _param("Length", "ucLmin", "ブームの最短", 3.34),
        _param("Length", "ucLmax", "ブームの最長", 10.0),
        _param("Length", "ucH", "ブームの根元の高さ", 2.4),
        _param("Boolean", "cgOn", "積荷を描く", 0),
        _param("Length", "cgL", "積荷の長さ", 0.0),
        _param("Length", "cgW", "積荷の幅", 0.0),
        _param("Length", "cgH", "積荷の高さ", 0.0),
        _param("Length", "cgX", "積荷の中心のずれ（トラックは荷台の中心から、トレーラーはキングピンから）", 0.0),
        _param("RealNum", "cgT", "積荷の質量 t", 0.0),
        _param("Boolean", "tkOn", "平面に旋回軌跡を描く", 1),
        _param("Integer", "tkS", "曲がる側（1＝左・-1＝右）", 1),
        _param("Length", "tkW", "カタログの所要道路幅（0＝式で）", 0.0),
        _param("Angle", "tkA", "旋回軌跡の曲がる角度（平面の円弧の先のホットスポットで動かす）", 90),
        _param("Length", "tkD", "最小回転半径より広げる量（回転の中心のホットスポットで動かす）", 0.0),
        _param("Length", "tkF", "曲がる前の直進（前端の角の線の先のホットスポットで動かす）", 0.0),
        _param("Length", "tkE", "曲がった後の直進（内側の線の先のホットスポットで動かす）", 0.0),
        # トレーラー連結車（原点はトラクタの真ん中、トレーラーはキングピンまわりに trA だけ折れる）
        _param("Length", "kpC", "カプラオフセット（後軸の中心から前）", 0.175),
        _param("Length", "kpZ", "カプラ上面地上高", 1.345),
        _param("Integer", "tlK", "トレーラー（1 低床・中低床・2 平床・3 ポール）", 1),
        _param("Length", "tlF", "キングピンから前端", 0.39),
        _param("Length", "tlB", "キングピンから後端", 11.81),
        _param("Length", "tlW", "トレーラーの全幅", 2.99),
        _param("Length", "gnL", "グースネックの長さ（前端〜荷台前端）", 2.99),
        _param("Length", "gnT", "グースネックの厚み", 0.39),
        _param("Length", "dkZ", "トレーラーの床面地上高（ポールは連結パイプの高さ）", 0.55),
        _param("Length", "dkL", "トレーラーの荷台の長さ（ポールは後台車の長さ）", 6.3),
        _param("Length", "rrZ", "後ろ（車軸の上）の荷台の高さ", 0.78),
        _param("Length", "tlAx", "キングピンから第1軸", 9.41),
        _param("Integer", "tlN", "トレーラーの車軸の列の数", 2),
        _param("Length", "tlSp", "トレーラーの軸間", 1.3),
        _param("Length", "tlR", "トレーラーのタイヤの半径", 0.387),
        _param("Length", "tlT", "トレーラーの輪距", 2.465),
        _param("Integer", "tlQ", "片側のダブルタイヤの組の数（4軸16輪は 2）", 1),
        _param("Angle", "trA", "トレーラーの向き（トラクタに対して左回りが +）", 0.0),
        # クレーンに吊るバイブロ
        _param("Integer", "vbK", "フックの先（0 フック・1 バイブロ）", 0),
        _param("Length", "vbW", "バイブロの幅", 1.337),
        _param("Length", "vbT", "バイブロの厚み", 0.722),
        _param("Length", "vbH", "バイブロの全高（チャック込み）", 3.479),
        _param("Length", "vbP", "バイブロの杭の長さ", 12.0),
        _param("RealNum", "texSiz", "文字の大きさ（mm）", 2.5),
        "\t\t<PenColor Name=\"penEquip\">\n\t\t\t<Description><![CDATA[\"線のペン（色。文字もこのペン）\"]]></Description>\n"
        "\t\t\t<Value>1</Value>\n\t\t</PenColor>\n",
        *gdl_draft.params(),
    ]
    return ("﻿<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<ParamSection>\n\t<ParamSectHeader>\n"
            "\t\t<AutoHotspots>false</AutoHotspots>\n\t\t<StatBits>\n\t\t\t<STBit_UIDefault/>\n\t\t</StatBits>\n"
            "\t\t<WDLeftFrame>0</WDLeftFrame>\n\t\t<WDRightFrame>0</WDRightFrame>\n\t\t<WDTopFrame>0</WDTopFrame>\n"
            "\t\t<WDBotFrame>0</WDBotFrame>\n\t\t<LayFlags>65535</LayFlags>\n\t\t<WDMirrorThickness>0</WDMirrorThickness>\n"
            "\t\t<WDWallInset>0</WDWallInset>\n\t</ParamSectHeader>\n"
            "\t<Parameters SectVersion=\"27\" SectionFlags=\"0\" SubIdent=\"0\">\n" + "".join(ps)
            + "\t</Parameters>\n</ParamSection>\n")


SCRIPT_1D = """﻿! 重機: 種類ごとの形（m・度）
isCr = (mcKind <= 2 or mcKind = 8 or mcKind = 9 or mcKind = 11)
isTk = ((mcKind >= 3 and mcKind <= 7) or mcKind = 13 or mcKind = 14)
isVh = (mcKind = 13 or mcKind = 14)
! 上部旋回体の後ろの円弧（後端旋回半径）と幅の合う所
w2 = min(upW / 2, tailR * 0.995)
xs = -sqr(tailR ^ 2 - w2 ^ 2)
aS = asn(w2 / tailR)
! カウンタウエイトの幅（クレーンは上部旋回体より広い）
w2c = min(max(cwW, upW) / 2, tailR * 0.995)
xsc = -sqr(tailR ^ 2 - w2c ^ 2)
aSc = asn(w2c / tailR)
! トラック: 前端・後端・車軸（後ろの車軸は1軸めから rearSp ずつ後ろ）
xF = carF
xR = carF - carL
axF = xF - frOv
axR1 = axF - wb
axR2 = axR1 - rearSp * (nRear >= 2)
! 車軸の位置（前 nFr 本・後ろ nRear 本）
dim axs[4]
nAx = 0
for i = 1 to max(1, min(2, nFr))
	nAx = nAx + 1
	axs[nAx] = axF - (i - 1) * frSp
next i
for i = 1 to max(1, min(2, nRear))
	nAx = nAx + 1
	axs[nAx] = axR1 - (i - 1) * rearSp
next i
! アウトリガの組（x と片側の張出）
dim ox[3], oy[3]
ox[1] = o1x
ox[2] = o2x
ox[3] = o3x
oy[1] = o1y / 2
oy[2] = o2y / 2
oy[3] = o3y / 2
nJk = 2 + (o3y > 0.01)
whW = 0.32 + 0.12 * (carW > 2.2)
! バックホウ: ブームの先（弦）・くの字の折れ・アームの先・バケットのピン
bmX1 = pvX + boomL * cos(bmA)
bmZ1 = pvH + boomL * sin(bmA)
knX = pvX + 0.55 * boomL * cos(bmA) - 0.13 * boomL * sin(bmA)
knZ = pvH + 0.55 * boomL * sin(bmA) + 0.13 * boomL * cos(bmA)
amX1 = bmX1 + armL * cos(amA)
amZ1 = bmZ1 + armL * sin(amA)
amX0 = bmX1 - 0.2 * armL * cos(amA)
amZ0 = bmZ1 - 0.2 * armL * sin(amA)
! ポンプ車のブームの段（長さと角度）
dim sl[5], sa[5]
sl[1] = sL1
sl[2] = sL2
sl[3] = sL3
sl[4] = sL4
sl[5] = sL5
sa[1] = pA1
sa[2] = pA2
sa[3] = pA3
sa[4] = pA4
sa[5] = pA5
nSc = max(1, min(5, nSec))
pmX = 0
pmZ = tuH
for i = 1 to nSc
	pmX = pmX + sl[i] * cos(sa[i])
	pmZ = pmZ + sl[i] * sin(sa[i])
next i
! 高所作業車のブームの先
abX = -0.4 + abL * cos(abA)
abZ = tuH + abL * sin(abA)
! クローラクレーンのブームの先・ジブの先・フック・定格総荷重（表の読み方は src/ashiba/machine.py の crane_rating と同じ）
if mcKind = 2 and lbGnd then
	lbA = -atn((pvH - 0.3) / lbL)
	hkD = 0.9
endif
lbX = pvX + lbL * cos(lbA)
lbZ = pvH + lbL * sin(lbA)
jbW = min(lbW, 1.0) * 0.7
jbX = lbX
jbZ = lbZ
if jbL > 0.01 then
	jbX = lbX + jbL * cos(lbA - jbO)
	jbZ = lbZ + jbL * sin(lbA - jbO)
endif
hkX = jbX + 0.4
tpZ = jbZ
rated = 0
rMin = 0
rMax = 0
if mcKind = 2 then
	iR = 0
	if jbL > 0.01 then
		rMin = jrN
		rMax = jrX
		for k = min(nJr, nJt) to 1 step -1
			if jtR[k] >= hkX - 0.001 then iR = k
		next k
		if iR > 0 then rated = jtT[iR] / 100
	else
		jB = nMb
		for k = nMb to 1 step -1
			if mtB[k] >= lbL - 0.001 then jB = k
		next k
		if jB > 0 and jB <= nMn and jB <= nMx then
			rMin = mtN[jB]
			rMax = mtX[jB]
		endif
		for k = nMr to 1 step -1
			if mtR[k] >= hkX - 0.001 then iR = k
		next k
		if iR > 0 then
			if jB = 1 and iR <= nC1 then rated = mtC1[iR] / 100
			if jB = 2 and iR <= nC2 then rated = mtC2[iR] / 100
			if jB = 3 and iR <= nC3 then rated = mtC3[iR] / 100
			if jB = 4 and iR <= nC4 then rated = mtC4[iR] / 100
			if jB = 5 and iR <= nC5 then rated = mtC5[iR] / 100
		endif
	endif
	if hkX < rMin - 0.001 or hkX > rMax + 0.001 then rated = 0
endif
capT = rated * sfRate
@WI@! アースドリルのテレスコブームの先
tbX = pvX + tbL * cos(tbA)
tbZ = pvH + tbL * sin(tbA)
! 解体機のフロント（3段の関節とアームの先）
dmX1 = pvX + dbL1 * cos(dA1)
dmZ1 = pvH + dbL1 * sin(dA1)
dmX2 = dmX1 + dbL2 * cos(dA2)
dmZ2 = dmZ1 + dbL2 * sin(dA2)
dmX3 = dmX2 + dbL3 * cos(dA3)
dmZ3 = dmZ2 + dbL3 * sin(dA3)
! 先の長さ（バケットかアタッチメント）
tpL = bkL
if atK > 0 then tpL = atL
! 杭打機のオーガ（本数と1本めの y）
nAu = max(1, min(3, auN))
yAu0 = -(nAu - 1) * auP / 2
! 搬入トラック・トレーラー: 後ろの軸群の中心・キングピン・クレーンの先・荷台の先
xAxR = axR1 - rearSp * (nRear >= 2) / 2
kpX = xAxR + kpC
ucTx = ucL * cos(abA)
ucTz = ucH + ucL * sin(abA)
nFa = max(1, min(2, nFr))
! 全周回転機のデッキの高さ（本体の高さから手すり 0.969 下）
zDk = max(0.5, rtH - 0.969)
"""

SCRIPT_1D = SCRIPT_1D.replace("@WI@", gdl_radii.master("mcKind = 2") + gdl_radii.rated_loop('\tiQ = 0\n\tif jbL > 0.01 then\n\t\tfor k = min(nJr, nJt) to 1 step -1\n\t\t\tif jtR[k] >= wiRq[wq] - 0.001 then iQ = k\n\t\tnext k\n\t\tif iQ > 0 then vq = jtT[iQ] / 100\n\telse\n\t\tfor k = nMr to 1 step -1\n\t\t\tif mtR[k] >= wiRq[wq] - 0.001 then iQ = k\n\t\tnext k\n\t\tif iQ > 0 then\n\t\t\tif jB = 1 and iQ <= nC1 then vq = mtC1[iQ] / 100\n\t\t\tif jB = 2 and iQ <= nC2 then vq = mtC2[iQ] / 100\n\t\t\tif jB = 3 and iQ <= nC3 then vq = mtC3[iQ] / 100\n\t\t\tif jB = 4 and iQ <= nC4 then vq = mtC4[iQ] / 100\n\t\t\tif jB = 5 and iQ <= nC5 then vq = mtC5[iQ] / 100\n\t\tendif\n\tendif\n\tif wiRq[wq] < rMin - 0.001 or wiRq[wq] > rMax + 0.001 then vq = 0\n\tvq = vq * sfRate\n'), 1)
SCRIPT_1D = SCRIPT_1D.replace("! クローラクレーンのブームの先・ジブの先", (
    _list("rtB", "mtB", "nMb") + _list("rtN", "mtN", "nMn") + _list("rtX", "mtX", "nMx") + _list("rtR", "mtR", "nMr")
    + "".join(_list(f"rc{i}", f"mtC{i}", f"nC{i}", "1") for i in range(1, 6))
    + _list("jrR", "jtR", "nJr") + _list("jrT", "jtT", "nJt", "1")) + "! クローラクレーンのブームの先・ジブの先", 1)

SCRIPT_VL = """﻿! 重機: 種類の一覧
dim kdV[], kdS[]
kdV[1] = 1
kdS[1] = "バックホウ"
kdV[2] = 2
kdS[2] = "クローラクレーン"
kdV[3] = 3
kdS[3] = "コンクリートポンプ車"
kdV[4] = 4
kdS[4] = "生コン車"
kdV[5] = 5
kdS[5] = "ダンプ"
kdV[6] = 6
kdS[6] = "高所作業車"
kdV[7] = 7
kdS[7] = "垂直昇降"
kdV[8] = 8
kdS[8] = "三点式杭打機"
kdV[9] = 9
kdS[9] = "アースドリル"
kdV[10] = 10
kdS[10] = "全周回転機"
kdV[11] = 11
kdS[11] = "解体機"
kdV[12] = 12
kdS[12] = "圧入機"
kdV[13] = 13
kdS[13] = "搬入トラック"
kdV[14] = 14
kdS[14] = "トレーラー連結車"
values{2} "mcKind" kdV, kdS
values{2} "atK" 0, "バケット", 1, "圧砕機", 2, "鉄骨切断機", 3, "つかみ機", 4, "ブレーカ", 5, "バイブロ"
values "auN" 1, 3
values{2} "vbK" 0, "フック", 1, "バイブロ"
values{2} "tlK" 1, "低床・中低床", 2, "平床", 3, "ポール"
values{2} "tkS" 1, "左", -1, "右"
values "tkA" range [5, 180]
values "tkD" range [0, ]
values "tkF" range [0, ]
values "tkE" range [0, ]
values "tlN" 1, 2, 3
values "tlQ" 1, 2
values "nFr" 1, 2
values{2} "cbS" 1, "左", -1, "右"
""" + gdl_draft.values() + """values "nRear" 1, 2
values "nSec" 3, 4, 5
"""

SCRIPT_2D_T = """﻿! 重機 2D（CAD の平面図の描き方: scripts/gdl_draft.py）: 外形は太線、細部は細線、車体の下に隠れるもの（タイヤ・第5輪）は破線、
! 中心と作業半径は一点鎖線、後端旋回半径（立入禁止）と旋回軌跡は二点鎖線。上に載るもの（上部旋回体・荷台・トレーラー・積荷）は
! 背景の色で塗って下の線を隠す。縮尺で 詳細（1/100）・標準（1/200）・簡略 を描き分ける
@HEAD@
define style "mcT" "ＭＳ Ｐゴシック", texSiz, 1, 0
define style "mcR" "ＭＳ Ｐゴシック", texSiz, 3, 0
style "mcT"
dT = texSiz * GLOB_SCALE / 1000 * 1.6
pen pO
line_type ltS
if isCr then
	! 履帯（2本）。詳細は履板の線と起動輪・遊動輪
	drawindex 10
	for s = -1 to 1 step 2
		yc = s * (trkW / 2 - shoeW / 2)
		pen pO
		rect2 -trkL / 2, yc - shoeW / 2, trkL / 2, yc + shoeW / 2
		if drLv = 1 then
			pen pT
			nSh = max(2, int(trkL / 0.5))
			for k = 1 to nSh - 1
				xk = -trkL / 2 + k * trkL / nSh
				line2 xk, yc - shoeW / 2, xk, yc + shoeW / 2
			next k
		endif
	next s
	! 後端旋回半径（立入禁止の範囲）
	pen pZ
	line_type ltZ
	circle2 0, 0, tailR
	line_type ltS
	rot2 slew
	! 上部旋回体とカウンタウエイト: 下の履帯を隠してから外形
	if mk then
		drawindex 20
@UPMASK@
		if w2c > w2 + 0.01 then
@CWMASK@
		endif
	endif
	drawindex 30
	pen pO
	! 外形は円弧と線で（put と poly2 の多角形は平面を止めた）
	arc2 0, 0, tailR, 180 - aS, 180 + aS
	line2 xs, w2, upF, w2
	line2 upF, w2, upF, -w2
	line2 upF, -w2, xs, -w2
	if w2c > w2 + 0.01 then
		arc2 0, 0, tailR, 180 - aSc, 180 + aSc
		xCw = xsc + 1.0
		line2 xsc, w2c, xCw, w2c
		line2 xsc, -w2c, xCw, -w2c
		line2 xCw, w2c, xCw, -w2c
	endif
	if drLv = 1 and mcKind <> 8 and mcKind <> 9 then
		! 運転室（cbS の側の前）と前窓・カウンタウエイトの前の縁・エンジンカバー（3D と同じ寸法）
		drawindex 40
		pen pT
		yC0 = w2 - cabW
		if cbS < 0 then yC0 = -w2
		rect2 upF - cabL, yC0, upF, yC0 + cabW
		line2 upF - 0.12, yC0 + 0.08, upF - 0.12, yC0 + cabW - 0.08
		xC = xsc + min(0.9, tailR * 0.35)
		if cwH > 0.01 then xC = xsc + 1.0
		line2 xC, -min(w2, w2c), xC, min(w2, w2c)
		yE0 = -w2 + 0.05
		yE1 = w2 - cabW - 0.1
		if cbS < 0 then
			yE0 = -w2 + cabW + 0.1
			yE1 = w2 - 0.05
		endif
		if upF - cabL - xC > 0.3 then rect2 xC, yE0, upF - cabL - 0.05, yE1
	endif
	drawindex 30
	pen pO
	if mcKind = 1 and bldW > 0.1 then
		del 1
		rect2 trkL / 2 + 0.25, -bldW / 2, trkL / 2 + 0.25 + 0.12, bldW / 2
		rot2 slew
	endif
	if mcKind = 1 then
		! ブーム・アーム（上から見える）と先のアタッチメント
		line2 pvX, bmY - 0.25, amX1, bmY - 0.15
		line2 pvX, bmY + 0.25, amX1, bmY + 0.15
		if drLv < 3 then
			pen pT
			line_type ltC
			line2 pvX, bmY, amX1, bmY
			line_type ltS
			pen pO
		endif
		if atK = 5 then
			hX2 = amX1 + atL * cos(bkA) + atW * sin(bkA)
			line2 amX1, bmY, hX2, bmY
			rect2 hX2 - vbW / 2, bmY - vbT / 2, hX2 + vbW / 2, bmY + vbT / 2
		endif
		if atK > 0 and atK < 5 then
			wA = max(0.3, min(atW, 1.2))
			rect2 amX1, bmY - wA / 2, amX1 + atL * max(0.2, cos(bkA)), bmY + wA / 2
		endif
		if atK = 0 then
			rect2 amX1 - 0.1, bmY - bkW / 2, amX1 + 0.35, bmY + bkW / 2
			if drLv = 1 then
				pen pT
				for k = 1 to 4
					line2 amX1 + 0.35, bmY - bkW / 2 + k * bkW / 5, amX1 + 0.45, bmY - bkW / 2 + k * bkW / 5
				next k
				pen pO
			endif
		endif
	endif
	if mcKind = 2 then
		! ラチスブーム（2本の弦材。詳細は斜材）と先端・吊り荷
		line2 pvX, -lbW / 2, lbX, -lbW / 2
		line2 pvX, lbW / 2, lbX, lbW / 2
		line2 lbX, -lbW / 2, lbX, lbW / 2
		if drLv = 1 then
			pen pT
			nLc = max(2, int((lbX - pvX) / max(lbW, 0.6)))
			for k = 0 to nLc - 1
				xa = pvX + k * (lbX - pvX) / nLc
				xb = pvX + (k + 1) * (lbX - pvX) / nLc
				line2 xa, (1 - 2 * (k mod 2)) * lbW / 2, xb, -(1 - 2 * (k mod 2)) * lbW / 2
			next k
			pen pO
		endif
		if drLv < 3 then
			pen pT
			line_type ltC
			line2 pvX, 0, lbX + 0.6, 0
			line_type ltS
			pen pO
		endif
		circle2 lbX, 0, 0.4
		if jbL > 0.01 then
			! ジブ（先へ細くなる）
			line2 lbX, -jbW / 2, jbX, -jbW / 4
			line2 lbX, jbW / 2, jbX, jbW / 4
			line2 jbX, -jbW / 4, jbX, jbW / 4
			circle2 jbX, 0, 0.25
		endif
		if vbK = 1 then rect2 hkX - vbW / 2, -vbT / 2, hkX + vbW / 2, vbT / 2
	endif
	if mcKind = 8 then
		! リーダ・リーダブラケット・オーガ・ステー・ジャッキ
		circle2 ldX, 0, ldDia / 2
		rect2 upF - 0.1, -0.6, ldX, 0.6
		pen pT
		for i = 1 to nAu
			circle2 ldX + auOff, yAu0 + (i - 1) * auP, auD / 2
			if drLv < 3 then
				line_type ltC
				line2 ldX + auOff - auD / 2 - 0.2, yAu0 + (i - 1) * auP, ldX + auOff + auD / 2 + 0.2, yAu0 + (i - 1) * auP
				line2 ldX + auOff, yAu0 + (i - 1) * auP - auD / 2 - 0.2, ldX + auOff, yAu0 + (i - 1) * auP + auD / 2 + 0.2
				line_type ltS
			endif
		next i
		rect2 ldX + auOff - auW / 2, yAu0 - auD / 2 - 0.1, ldX + auOff + auW / 2, -yAu0 + auD / 2 + 0.1
		for s = -1 to 1 step 2
			line2 -tailR * 0.35, s * upW * 0.35, ldX, s * ldDia * 0.3
			if drLv < 3 then
				rect2 fjX - 0.3, s * fjW / 2 - 0.3, fjX + 0.3, s * fjW / 2 + 0.3
				rect2 -rjX - 0.3, s * rjW / 2 - 0.3, -rjX + 0.3, s * rjW / 2 + 0.3
			endif
			line2 -rjX, 0, -rjX, s * rjW / 2
		next s
		pen pO
	endif
	if mcKind = 9 then
		! テレスコブーム・ケリードライブ・バケット（掘削中心は一点鎖線）
		line2 pvX, -0.45, tbX, -0.45
		line2 pvX, 0.45, tbX, 0.45
		rect2 kdR - 0.9, -0.9, kdR + 0.9, 0.9
		pen pT
		circle2 kdR, 0, auD / 2
		if drLv < 3 then line_type ltC
		line2 kdR - auD / 2 - 0.3, 0, kdR + auD / 2 + 0.3, 0
		line2 kdR, -auD / 2 - 0.3, kdR, auD / 2 + 0.3
		line_type ltS
		pen pO
	endif
	if mcKind = 11 then
		! フロント（3段）と先のアタッチメント
		line2 pvX, -0.35, max(dmX1, dmX3), -0.3
		line2 pvX, 0.35, max(dmX1, dmX3), 0.3
		wA = max(0.3, min(atW, 1.2))
		if atK = 0 then wA = bkW
		rect2 dmX3, -wA / 2, dmX3 + tpL * max(0.2, abs(cos(bkA))), wA / 2
	endif
	del 1
endif
if mcKind = 10 then
	! 全周回転機: 反力ブラケット・本体・通り穴・ケーシング（一点鎖線の中心）・水平ジャッキ・油圧ユニット
	drawindex 30
	pen pO
	rect2 -brL / 2, -0.3, brL / 2, 0.3
	rect2 -0.3, -brW / 2, 0.3, brW / 2
	rect2 -rtL / 2, -rtW / 2, rtL / 2, rtW / 2
	circle2 0, 0, csD / 2
	pen pT
	circle2 0, 0, rtD / 2
	if drLv < 3 then
		for s = -1 to 1 step 2
			for t = -1 to 1 step 2
				circle2 s * (rtL / 2 - 0.35), t * (rtW / 2 - 0.35), 0.25
			next t
		next s
		line_type ltC
		line2 -csD / 2 - 0.4, 0, csD / 2 + 0.4, 0
		line2 0, -csD / 2 - 0.4, 0, csD / 2 + 0.4
		line_type ltS
	endif
	pen pO
	rect2 puX - puL / 2, puY - puW / 2, puX + puL / 2, puY + puW / 2
endif
if mcKind = 12 then
	! 圧入機: 本体・チャックの杭・後ろの完成杭（つかむ反力杭）・パワーユニット
	drawindex 30
	pen pO
	rect2 -piL + 0.35, -piW / 2, 0.35, piW / 2
	pen pT
	for i = 0 to piN
		xP = -i * piP
		line2 xP - piP / 2, 0, xP - piP / 4, (1 - 2 * (i mod 2)) * 0.15
		line2 xP - piP / 4, (1 - 2 * (i mod 2)) * 0.15, xP + piP / 4, (1 - 2 * (i mod 2)) * 0.15
		line2 xP + piP / 4, (1 - 2 * (i mod 2)) * 0.15, xP + piP / 2, 0
	next i
	pen pO
	rect2 puX - puL / 2, puY - puW / 2, puX + puL / 2, puY + puW / 2
endif
if isTk then
	! 車体・運転室: 下の線を隠してから外形（太線）。タイヤは車体の下なので破線（簡略は描かない）
	cL2 = min(2.3, carL * 0.28)
	if mk then
		drawindex 20
		if mcKind = 14 then
@CABMASK@
		else
@CARMASK@
		endif
	endif
	drawindex 30
	pen pO
	if mcKind = 14 then
		rect2 xF - cL2 - 0.1, -carW / 2, xF, carW / 2
		pen pT
		line2 xR, -carW / 2 + 0.35, xF - cL2 - 0.1, -carW / 2 + 0.35
		line2 xR, carW / 2 - 0.35, xF - cL2 - 0.1, carW / 2 - 0.35
		line2 xR, -carW / 2 + 0.35, xR, carW / 2 - 0.35
		pen pO
	else
		rect2 xR, -carW / 2, xF, carW / 2
	endif
	pen pT
	if mcKind <> 7 then line2 xF - cL2, -carW / 2, xF - cL2, carW / 2
	if isVh and drLv = 1 then
		! 前窓とミラー
		line2 xF - 0.12, -carW / 2 + 0.08, xF - 0.12, carW / 2 - 0.08
		for s = -1 to 1 step 2
			rect2 xF - 0.35, s * (carW / 2 + 0.05), xF - 0.25, s * (carW / 2 + 0.22)
			line2 xF - 0.3, s * carW / 2, xF - 0.3, s * (carW / 2 + 0.05)
		next s
	endif
	if drLv < 3 then
		drawindex 40
		line_type ltH
		for i = 1 to nAx
			if isVh and drLv = 1 then line2 axs[i], -carW / 2 + 0.1, axs[i], carW / 2 - 0.1
			for s = -1 to 1 step 2
				if drLv = 1 then
					rect2 axs[i] - whR, s * carW / 2 - s * 0.05, axs[i] + whR, s * carW / 2 - s * (0.05 + whW)
					if isVh and i > nFa then rect2 axs[i] - whR, s * carW / 2 - s * (0.08 + whW), axs[i] + whR, s * carW / 2 - s * (0.08 + 2 * whW)
				else
					wq = whW * (1 + (isVh and i > nFa))
					rect2 axs[i] - whR, s * carW / 2 - s * 0.05, axs[i] + whR, s * carW / 2 - s * (0.05 + wq)
				endif
			next s
		next i
		line_type ltS
		drawindex 30
	endif
	pen pO
	if (mcKind = 3 or mcKind = 6 or (mcKind = 13 and ucOn)) and otOn then
		! アウトリガ（張り出した形）
		for j = 1 to 3
			if oy[j] > 0.01 then
				for s = -1 to 1 step 2
					line2 ox[j], s * 0.3, ox[j], s * oy[j]
					if drLv < 3 then rect2 ox[j] - 0.3, s * oy[j] - 0.3, ox[j] + 0.3, s * oy[j] + 0.3
				next s
			endif
		next j
	endif
	if mcKind = 7 then rect2 -pfL / 2, -pfW / 2, pfL / 2, pfW / 2
	if mcKind = 3 then
		circle2 0, 0, 0.6
		rot2 slew
		line2 0, -0.2, pmX, -0.15
		line2 0, 0.2, pmX, 0.15
		circle2 pmX, 0, 0.15
		del 1
	endif
	if mcKind = 6 then
		circle2 0, 0, 0.5
		rot2 slew
		line2 -0.4, -0.2, abX, -0.2
		line2 -0.4, 0.2, abX, 0.2
		rect2 abX, -pfL / 2, abX + pfW, pfL / 2
		del 1
	endif
	if mcKind = 4 then
		rect2 xF - 2.2 - drL * cos(drA), -drD / 2, xF - 2.2, drD / 2
	endif
	if mcKind = 5 then
		rect2 xR + 0.1, -bedW / 2, xR + 0.1 + bedL * cos(bedA), bedW / 2
		if drLv = 1 then
			pen pT
			rect2 xR + 0.14, -bedW / 2 + 0.04, xR + 0.06 + bedL * cos(bedA), bedW / 2 - 0.04
			pen pO
		endif
	endif
	if mcKind = 13 then
		! 荷台（外形・あおりの内側・鳥居）・道板・クレーン・積荷
		dkx = xR + (bedL + 0.1) * cos(bedA)
		rect2 xR, -bedW / 2 - 0.05, dkx, bedW / 2 + 0.05
		pen pT
		if bedH > 0.01 and drLv < 3 then rect2 xR + 0.04, -bedW / 2, dkx - 0.08, bedW / 2
		line2 dkx - 0.08, -bedW / 2 - 0.05, dkx - 0.08, bedW / 2 + 0.05
		if drLv = 1 and bedH > 0.01 then
			! 床の根太（あおりの内に 0.6m ごと）
			nJs = int((dkx - xR - 0.2) / 0.6)
			for k = 1 to nJs
				line2 dkx - 0.08 - k * 0.6, -bedW / 2 + 0.04, dkx - 0.08 - k * 0.6, bedW / 2 - 0.04
			next k
		endif
		if rpL > 0.01 then
			rpx = rpL * cos(asn(min(1, flZ / rpL)))
			for s = -1 to 1 step 2
				rect2 xR - rpx, s * (bedW / 2 - 0.25) - 0.2, xR, s * (bedW / 2 - 0.25) + 0.2
			next s
		endif
		pen pO
		if ucOn then
			circle2 ucX, 0, 0.35
			add2 ucX, 0
			rot2 slew + 180
			line2 0, -0.18, ucTx, -0.12
			line2 0, 0.18, ucTx, 0.12
			circle2 ucTx, 0, 0.15
			del 2
			pen pZ
			line_type ltC
			circle2 ucX, 0, ucLmax
			line_type ltS
			pen pO
		endif
		if cgOn then
			xg1 = xR + bedL / 2 + cgX - cgL / 2
			xg2 = xR + bedL / 2 + cgX + cgL / 2
			if mk then
				drawindex 35
@CG13MASK@
			endif
			drawindex 38
			rect2 xg1, -cgW / 2, xg2, cgW / 2
			if drLv < 3 then
				pen pT
				line2 xg1, -cgW / 2, xg2, cgW / 2
				line2 xg1, cgW / 2, xg2, -cgW / 2
				pen pO
			endif
			drawindex 30
		endif
	endif
	if mcKind = 14 then
		! 第5輪（カプラ。トレーラーの下なので破線）とキングピン、トレーラー（キングピンまわりに trA）
		pen pT
		if drLv < 3 then
			drawindex 40
			line_type ltH
			circle2 kpX, 0, 0.45
			line_type ltS
			circle2 kpX, 0, 0.1
		endif
		add2 kpX, 0
		rot2 trA
		if mk then
			drawindex 33
@TLMASK@
		endif
		drawindex 36
		pen pO
		rect2 -tlB, -tlW / 2, tlF, tlW / 2
		pen pT
		if tlK = 1 then
			line2 tlF - gnL, -tlW / 2, tlF - gnL, tlW / 2
			line2 tlF - gnL - dkL, -tlW / 2, tlF - gnL - dkL, tlW / 2
			if drLv = 1 then
				! 荷台の縞鋼板の目地（1.0m ごと）
				for k = 1 to int(dkL) - 1
					line2 tlF - gnL - k, -tlW / 2 + 0.05, tlF - gnL - k, tlW / 2 - 0.05
				next k
			endif
		endif
		if tlK = 2 and drLv < 3 then
			for k = 0 to 3
				for s = -1 to 1 step 2
					rect2 tlF - 1.5 - k * (tlB - 2.5) / 3, s * tlW / 2 - 0.05, tlF - 1.4 - k * (tlB - 2.5) / 3, s * tlW / 2 + 0.05
				next s
			next k
		endif
		if tlK = 3 then
			line2 0, -0.15, -tlAx + 1.0, -0.15
			line2 0, 0.15, -tlAx + 1.0, 0.15
		endif
		circle2 0, 0, 0.08
		if drLv < 3 then
			drawindex 42
			line_type ltH
			for i = 0 to tlN - 1
				xa = -(tlAx + i * tlSp)
				if drLv = 1 then line2 xa, -tlW / 2 + 0.1, xa, tlW / 2 - 0.1
				for s = -1 to 1 step 2
					for q = 1 to max(1, tlQ)
						yq = s * (tlT / 2 - (q - 1) * 0.885)
						if drLv = 1 then
							rect2 xa - tlR, yq - 0.27, xa + tlR, yq - 0.02
							rect2 xa - tlR, yq + 0.02, xa + tlR, yq + 0.27
						else
							rect2 xa - tlR, yq - 0.27, xa + tlR, yq + 0.27
						endif
					next q
				next s
			next i
			line_type ltS
		endif
		pen pO
		if cgOn then
			if mk then
				drawindex 35
@CG14MASK@
			endif
			drawindex 38
			rect2 cgX - cgL / 2, -cgW / 2, cgX + cgL / 2, cgW / 2
			if drLv < 3 then
				pen pT
				line2 cgX - cgL / 2, -cgW / 2, cgX + cgL / 2, cgW / 2
				line2 cgX - cgL / 2, cgW / 2, cgX + cgL / 2, -cgW / 2
				pen pO
			endif
		endif
		drawindex 30
		del 2
	endif
endif
! 旋回軌跡（最小回転半径で曲がり続けるとき。外側の前端の角と内側の後輪。単車は場内通路と同じ式、連結車はトレーラーの後軸群まで。
! 円弧は今の向きから 90° 分。二点鎖線、回転の中心は一点鎖線の十字）
if isTk and mcKind <> 7 and tkOn and tnR > 0.5 then
	L1 = axF - xAxR
	if L1 < tnR then
		aRr = sqr(tnR ^ 2 - L1 ^ 2) + tkD
		if mcKind <> 14 then
			rCen = aRr - trT / 2
			rOut = sqr((aRr + (carW - trT) / 2) ^ 2 + (L1 + frOv) ^ 2)
			rIn = aRr - (carW + trT) / 2
		else
			rCen = aRr - (trT + 0.2) / 2
			rOut = sqr((L1 + frOv) ^ 2 + (rCen + carW / 2) ^ 2)
			rKp = sqr(rCen ^ 2 + kpC ^ 2)
			L2 = tlAx + (tlN - 1) * tlSp / 2
			rIn = 0
			if tkW > 0.01 then
				rIn = tnR + tkD - tkW
				rOut = tnR + tkD
			else
				if L2 < rKp then
					rTrl = sqr(rKp ^ 2 - L2 ^ 2)
					rIn = rTrl - tlT / 2
					rOut = max(rOut, sqr((rTrl + tlW / 2) ^ 2 + (tlB - L2) ^ 2))
				endif
			endif
		endif
		yC = tkS * rCen
		dxq = xF - xAxR
		dyq = -tkS * carW / 2 - yC
		aQ = 90
		if dyq < 0 then aQ = -90
		if abs(dxq) > 0.000001 then aQ = atn(dyq / dxq)
		if dxq < 0 then aQ = aQ + 180
		drawindex 45
		pen pZ
		line_type ltZ
		! 直進 tkF のあと、回転の中心 xC のまわりに tkA 曲がり、また直進 tkE（ハンドルを切る途中の緩和は描かない）
		xC = xAxR + tkF
		yO = -tkS * carW / 2
		yI = yC - tkS * rIn
		aE = aQ + tkS * tkA
		aI = tkS * (tkA - 90)
		hdX = cos(tkS * tkA)
		hdY = sin(tkS * tkA)
		xP = xC + rOut * cos(aE)
		yP = yC + rOut * sin(aE)
		xI = xC + rIn * cos(aI)
		yJ = yC + rIn * sin(aI)
		if tkS > 0 then
			arc2 xC, yC, rOut, aQ, aQ + tkA
			if rIn > 0.1 then arc2 xC, yC, rIn, -90, -90 + tkA
		else
			arc2 xC, yC, rOut, aQ - tkA, aQ
			if rIn > 0.1 then arc2 xC, yC, rIn, 90 - tkA, 90
		endif
		if tkF > 0.001 then
			line2 xF, yO, xF + tkF, yO
			if rIn > 0.1 then line2 xAxR, yI, xC, yI
		endif
		if tkE > 0.001 then
			line2 xP, yP, xP + tkE * hdX, yP + tkE * hdY
			if rIn > 0.1 then line2 xI, yJ, xI + tkE * hdX, yJ + tkE * hdY
		endif
		line_type ltC
		line2 xC, yC - 0.6, xC, yC + 0.6
		line2 xC - 0.6, yC, xC + 0.6, yC
		line_type ltS
		! ホットスポット: 円弧の先で曲がる角度（tkA）、回転の中心で最小回転半径より広げる量（tkD。狭くはできない）、
		! 前端の角の線の先で曲がる前の直進（tkF）、内側の線の先で曲がった後の直進（tkE）
		fA = 512 * (tkS < 0)
		hotspot2 xC, yC, 31, tkA, 6 + fA
		hotspot2 xC + rOut * cos(aQ), yC + rOut * sin(aQ), 32, tkA, 4 + fA
		hotspot2 xP, yP, 33, tkA, 5 + fA
		hotspot2 xC, yC - tkS * tkD, 34, tkD, 1 + 128
		hotspot2 xC, yC, 35, tkD, 2
		hotspot2 xC, yC - tkS * (tkD + 1), 36, tkD, 3
		hotspot2 xF, yO, 37, tkF, 1 + 128
		hotspot2 xF + tkF, yO, 38, tkF, 2
		hotspot2 xF - 1, yO, 39, tkF, 3
		if rIn > 0.1 then
			hotspot2 xI, yJ, 40, tkE, 1 + 128
			hotspot2 xI + tkE * hdX, yJ + tkE * hdY, 41, tkE, 2
			hotspot2 xI - hdX, yJ - hdY, 42, tkE, 3
		endif
	endif
endif
! 作業半径（バックホウは最大掘削半径、クレーン・ポンプ車・高所作業車は最大作業半径）。一点鎖線
rW = maxR
if mcKind = 2 then rW = hkX
isR = (mcKind <= 3 or mcKind = 6 or mcKind = 11)
drawindex 45
if rW > 0.1 and isR then
	pen pZ
	line_type ltC
	circle2 0, 0, rW
	line_type ltS
endif
if mcKind = 2 then
	! 作業の最小半径（二点鎖線）と、ブームの先の定格総荷重・安全率を掛けた荷重
	if rMin > 0.1 then
		pen pZ
		line_type ltZ
		circle2 0, 0, rMin
		line_type ltS
	endif
	drawindex 50
	pen penEquip
	dQ = texSiz * GLOB_SCALE / 1000 * 1.6
	! フックのホットスポット（X と Y の組を同じ点に置いて、どの向きにも引ける。前後は起伏角、横は旋回）
	xF = hkX * cos(slew)
	yF = hkX * sin(slew)
	hotspot2 0, yF, 51, hfX, 1 + 128
	hotspot2 xF, yF, 52, hfX, 2
	hotspot2 -1, yF, 53, hfX, 3
	hotspot2 xF, 0, 54, hfY, 1 + 128
	hotspot2 xF, yF, 55, hfY, 2
	hotspot2 xF, -1, 56, hfY, 3
	add2 hkX * cos(slew), hkX * sin(slew)
	rot2 -SYMB_ROTANGLE
	if rated > 0 then
		text2 0.6, dQ, "定格 " + str(rated, 5, 2) + "t×" + str(sfRate, 4, 2) + "＝" + str(capT, 5, 2) + "t"
	else
		text2 0.6, dQ, "定格 表の外"
	endif
	text2 0.6, 0, "R" + str(round_int(hkX * 1000), 1, 0) + "・" + str(round_int(lbA), 1, 0) + "°"
	del 2
	if rMin > 0.1 then
		add2 rMin * cos(slew + 40), rMin * sin(slew + 40)
		rot2 -SYMB_ROTANGLE
		text2 0, 0, "最小 R" + str(round_int(rMin * 1000), 1, 0)
		del 2
	endif
	drawindex 45
endif
@RADII@! 旋回の中心（一点鎖線の十字。簡略は小さく）
if isCr or mcKind = 3 or mcKind = 6 then
	pen pT
	cq = 0.6 + 0.6 * (drLv = 3)
	line_type ltC
	line2 -cq, 0, cq, 0
	line2 0, -cq, 0, cq
	line_type ltS
endif
! 注記（機種・諸元）。簡略は名前だけ
drawindex 50
pen penEquip
xN = -max(tailR, trkL / 2 * isCr) - 0.6
if isTk then xN = xR - 0.6
yN = 0
if isVh then
	! 搬入車両は車体の下（右側の外）に書く
	xN = xR
	yN = -max(carW, tlW * (mcKind = 14)) / 2 - 0.8
	if mcKind = 14 then xN = min(xR, kpX - tlB)
endif
if mcKind = 10 then xN = min(-brL / 2, puX - puL / 2) - 0.6
if mcKind = 12 then xN = min(-piL, puX - puL / 2) - 0.6
add2 xN, yN
rot2 -SYMB_ROTANGLE
! 車体の左に書くときは右寄せ（文字が車体へ伸びて重ならないように。向きは画面の上で見る）
if not(isVh) and xN * cos(SYMB_ROTANGLE) - yN * sin(SYMB_ROTANGLE) < 0 then style "mcR"
text2 0, 0, mcName
nL = 1
if strlen(mcNote) > 0 and drLv < 3 then
	text2 0, -dT, mcNote
	nL = 2
endif
if isCr and drLv < 3 then text2 0, -nL * dT, "後端R" + str(round_int(tailR * 1000), 1, 0)
style "mcT"
del 2
if rW > 0.1 and isR then
	add2 rW * cos(45), rW * sin(45)
	rot2 -SYMB_ROTANGLE
	text2 0, 0, "R" + str(round_int(rW * 1000), 1, 0)
	del 2
endif
if mcKind = 14 then
	hotspot2 kpX, 0, 11, trA, 6
	hotspot2 kpX - 1, 0, 12, trA, 4
	hotspot2 kpX - tlB * cos(trA), -tlB * sin(trA), 13, trA, 5
endif
! 旋回角のホットスポット
rH = max(2.0, tailR)
hotspot2 0, 0, 1, slew, 6
hotspot2 rH, 0, 2, slew, 4
hotspot2 rH * cos(slew), rH * sin(slew), 3, slew, 5
hotspot2 0, 0
"""


def _script_2d() -> str:
    """2D スクリプト: 型（SCRIPT_2D_T）に描き方の決めと隠す塗りの多角形を入れる."""
    D = gdl_draft
    t = "\t"
    rep = {
        "@HEAD@": D.head().rstrip("\n"),
        "@UPMASK@": D.mask([("upF", "-w2"), ("upF", "w2")] + D.arc_pts("tailR", "180 - aS", "180 + aS"), t * 2).rstrip("\n"),
        "@CWMASK@": D.mask([("xsc + 1.0", "-w2c"), ("xsc + 1.0", "w2c")] + D.arc_pts("tailR", "180 - aSc", "180 + aSc"),
                           t * 3).rstrip("\n"),
        "@CABMASK@": (D.rect_mask("xF - cL2 - 0.1", "-carW / 2", "xF", "carW / 2", t * 3)
                      + D.rect_mask("xR", "-carW / 2 + 0.35", "xF - cL2 - 0.1", "carW / 2 - 0.35", t * 3)).rstrip("\n"),
        "@CARMASK@": D.rect_mask("xR", "-carW / 2", "xF", "carW / 2", t * 3).rstrip("\n"),
        "@TLMASK@": D.rect_mask("-tlB", "-tlW / 2", "tlF", "tlW / 2", t * 3).rstrip("\n"),
        "@CG13MASK@": D.rect_mask("xg1", "-cgW / 2", "xg2", "cgW / 2", t * 4).rstrip("\n"),
        "@CG14MASK@": D.rect_mask("cgX - cgL / 2", "-cgW / 2", "cgX + cgL / 2", "cgW / 2", t * 4).rstrip("\n"),
    }
    out = SCRIPT_2D_T.replace("@RADII@", gdl_radii.plan("pZ", "ltS", "penEquip", "mcT"))
    for k, v in rep.items():
        assert k in out, k
        out = out.replace(k, v)
    return out


SCRIPT_2D = _script_2d()


SCRIPT_3D = """﻿! 重機 3D
! 車体の色（バックホウ・解体機は黄、ほかは白。同じ名前の define material を2回書くと 3D が止まる）
cR = 0.95
cG = 0.72
cB = 0.08
if mcClr = 1 then
	cR = 0.03
	cG = 0.60
	cB = 0.66
endif
if mcKind >= 2 and mcKind <> 11 and mcClr = 0 then
	cR = 0.93
	cG = 0.94
	cB = 0.95
endif
define material "mc_body" 2, cR, cG, cB
define material "mc_dark" 2, 0.18, 0.18, 0.20
define material "mc_steel" 2, 0.55, 0.56, 0.58
define material "mc_cw" 2, 0.35, 0.36, 0.38
define material "mc_tire" 2, 0.10, 0.10, 0.10
define material "mc_rim" 2, 0.80, 0.80, 0.78
define material "mc_lamp" 2, 0.95, 0.60, 0.10
define material "mc_hook" 2, 0.95, 0.75, 0.10
define material "mc_red" 2, 0.80, 0.12, 0.10
define material "mc_wht" 2, 0.94, 0.94, 0.94
define material "mc_head" 2, 0.92, 0.93, 0.85
define material "mc_tail" 2, 0.75, 0.10, 0.10
define material "mc_glass" 2, 0.30, 0.45, 0.60
define material "mc_rod" 2, 0.85, 0.86, 0.88
define material "mc_drum" 2, 0.92, 0.40, 0.12
define material "mc_bed" 2, 0.30, 0.52, 0.35
resol 12
if isCr then gosub "crawler"
if mcKind = 1 and bldW > 0.1 then gosub "blade"
if isTk and mcKind <> 7 then gosub "truck"
if mcKind = 1 then
	rotz slew
	gosub "upper"
	add 0, bmY, 0
	gosub "backhoe"
	del 2
endif
if mcKind = 2 then
	rotz slew
	gosub "upper"
	gosub "lattice"
	del 1
endif
if mcKind = 3 then
	gosub "outrig"
	gosub "pumpbody"
	rotz slew
	gosub "pumpboom"
	del 1
endif
if mcKind = 4 then gosub "mixer"
if mcKind = 5 then gosub "dump"
if mcKind = 6 then
	gosub "outrig"
	rotz slew
	gosub "aerial"
	del 1
endif
if mcKind = 7 then gosub "scissor"
if mcKind = 8 then
	rotz slew
	gosub "upper"
	gosub "pileleader"
	del 1
endif
if mcKind = 9 then
	rotz slew
	gosub "upper"
	gosub "earthdrill"
	del 1
endif
if mcKind = 10 then gosub "rotator"
if mcKind = 11 then
	rotz slew
	gosub "upper"
	gosub "demolish"
	del 1
endif
if mcKind = 12 then gosub "piler"
if mcKind = 13 then
	gosub "flatdeck"
	if ucOn then
		gosub "outrig"
		! 旋回角 0 は後ろ向き（格納の向き）
		add ucX, 0, 0
		rotz slew + 180
		gosub "cargocrane"
		del 2
	endif
	if cgOn then
		material "mc_drum"
		add xR + bedL / 2 + cgX - cgL / 2, -cgW / 2, flZ + (bedL / 2 + cgX) * sin(bedA)
		roty -bedA
		block cgL, cgW, cgH
		del 2
	endif
endif
if mcKind = 14 then
	! 第5輪（カプラ）とトレーラー（キングピンまわりに trA）
	material "mc_dark"
	add kpX, 0, kpZ - 0.2
	cylind 0.2, 0.6
	del 1
	add kpX, 0, 0
	rotz trA
	gosub "semitrailer"
	del 2
endif
gosub "hotspots"
if mcKind = 2 then gosub "crinfo"
end

"hotspots":
	! 動かせるホットスポット（利用者の指定 2026-11-03: 他の重機もホットスポットで動かせるように）。角度は 6＝中心・4＝基準（水平）・
	! 5＝動く点・7＝回る面の法線の点（側面の xz 面。−y）。長さは 1＝基点（+128 で見せない）・2＝動く点・3＝向きの基準
	if mcKind = 1 then
		rotz slew
		add 0, bmY, 0
		hotspot pvX, 0, pvH, 201, bmA, 6
		hotspot pvX + 1, 0, pvH, 202, bmA, 4
		hotspot bmX1, 0, bmZ1, 203, bmA, 5
		hotspot pvX, -1, pvH, 204, bmA, 7
		hotspot bmX1, 0, bmZ1, 205, amA, 6
		hotspot bmX1 + 1, 0, bmZ1, 206, amA, 4
		hotspot amX1, 0, amZ1, 207, amA, 5
		hotspot bmX1, -1, bmZ1, 208, amA, 7
		hotspot amX1, 0, amZ1, 209, bkA, 6
		hotspot amX1 + 1, 0, amZ1, 210, bkA, 4
		hotspot amX1 + tpL * cos(bkA), 0, amZ1 + tpL * sin(bkA), 211, bkA, 5
		hotspot amX1, -1, amZ1, 212, bkA, 7
		atX0 = amX1
		atZ0 = amZ1
		hid = 351
		gosub "jawhot"
		del 2
	endif
	if mcKind = 2 then
		! ブームの先を平面のどの向きにも引く（平面の 51〜56 と同じ組）
		xF = hkX * cos(slew)
		yF = hkX * sin(slew)
		zF = tpZ + 0.3
		hotspot 0, yF, zF, 228, hfX, 1 + 128
		hotspot xF, yF, zF, 229, hfX, 2
		hotspot -1, yF, zF, 230, hfX, 3
		hotspot xF, 0, zF, 231, hfY, 1 + 128
		hotspot xF, yF, zF, 232, hfY, 2
		hotspot xF, -1, zF, 233, hfY, 3
		rotz slew
		hotspot pvX, 0, pvH, 221, lbA, 6
		hotspot pvX + 1, 0, pvH, 222, lbA, 4
		hotspot lbX, 0, lbZ, 223, lbA, 5
		hotspot pvX, -1, pvH, 224, lbA, 7
		hotspot hkX, 0, tpZ, 225, hkD, 1 + 128
		hotspot hkX, 0, tpZ - hkD, 226, hkD, 2
		hotspot hkX, 0, tpZ + 1, 227, hkD, 3
		del 1
	endif
	if mcKind = 3 then
		! ポンプ車のブームの段ごとの角度（水平から）。段の根元が中心
		rotz slew
		hx = 0
		hz = tuH
		for i = 1 to nSc
			qx = hx + sl[i] * cos(sa[i])
			qz = hz + sl[i] * sin(sa[i])
			hid = 230 + 4 * i
			if i = 1 then hotspot hx, 0, hz, hid, pA1, 6
			if i = 2 then hotspot hx, 0, hz, hid, pA2, 6
			if i = 3 then hotspot hx, 0, hz, hid, pA3, 6
			if i = 4 then hotspot hx, 0, hz, hid, pA4, 6
			if i = 5 then hotspot hx, 0, hz, hid, pA5, 6
			if i = 1 then hotspot hx + 1, 0, hz, hid + 1, pA1, 4
			if i = 2 then hotspot hx + 1, 0, hz, hid + 1, pA2, 4
			if i = 3 then hotspot hx + 1, 0, hz, hid + 1, pA3, 4
			if i = 4 then hotspot hx + 1, 0, hz, hid + 1, pA4, 4
			if i = 5 then hotspot hx + 1, 0, hz, hid + 1, pA5, 4
			if i = 1 then hotspot qx, 0, qz, hid + 2, pA1, 5
			if i = 2 then hotspot qx, 0, qz, hid + 2, pA2, 5
			if i = 3 then hotspot qx, 0, qz, hid + 2, pA3, 5
			if i = 4 then hotspot qx, 0, qz, hid + 2, pA4, 5
			if i = 5 then hotspot qx, 0, qz, hid + 2, pA5, 5
			if i = 1 then hotspot hx, -1, hz, hid + 3, pA1, 7
			if i = 2 then hotspot hx, -1, hz, hid + 3, pA2, 7
			if i = 3 then hotspot hx, -1, hz, hid + 3, pA3, 7
			if i = 4 then hotspot hx, -1, hz, hid + 3, pA4, 7
			if i = 5 then hotspot hx, -1, hz, hid + 3, pA5, 7
			hx = qx
			hz = qz
		next i
		del 1
	endif
	if mcKind = 5 then
		! ダンプの荷台の上げ角（後ろのヒンジが中心）
		hX = xR + 0.1
		hZ = frZ + 0.05
		hotspot hX, 0, hZ, 261, bedA, 6
		hotspot hX + 1, 0, hZ, 262, bedA, 4
		hotspot hX + bedL * cos(bedA), 0, hZ + bedL * sin(bedA), 263, bedA, 5
		hotspot hX, -1, hZ, 264, bedA, 7
	endif
	if mcKind = 6 then
		rotz slew
		hotspot -0.4, 0, tuH, 271, abA, 6
		hotspot 0.6, 0, tuH, 272, abA, 4
		hotspot abX, 0, abZ, 273, abA, 5
		hotspot -0.4, -1, tuH, 274, abA, 7
		hotspot -0.4, 0, tuH, 275, abL, 1 + 128
		hotspot abX, 0, abZ, 276, abL, 2
		hotspot -0.4 - cos(abA), 0, tuH - sin(abA), 277, abL, 3
		del 1
	endif
	if mcKind = 7 then
		hotspot 0, 0, 0, 281, pfH, 1 + 128
		hotspot 0, 0, pfH, 282, pfH, 2
		hotspot 0, 0, -1, 283, pfH, 3
	endif
	if mcKind = 8 then
		! オーガのモータの高さ（下げるとスクリューが地面に入る）とリーダの長さ
		rotz slew
		xA = ldX + auOff
		hotspot xA, 0, 0, 291, auZ, 1 + 128
		hotspot xA, 0, auZ, 292, auZ, 2
		hotspot xA, 0, -1, 293, auZ, 3
		hotspot ldX, 0, ldZ, 294, ldL, 1 + 128
		hotspot ldX, 0, ldZ + ldL, 295, ldL, 2
		hotspot ldX, 0, ldZ - 1, 296, ldL, 3
		del 1
	endif
	if mcKind = 9 then
		! テレスコブームの起伏と長さ、バケットの深さ（下へ）
		rotz slew
		hotspot pvX, 0, pvH, 301, tbA, 6
		hotspot pvX + 1, 0, pvH, 302, tbA, 4
		hotspot tbX, 0, tbZ, 303, tbA, 5
		hotspot pvX, -1, pvH, 304, tbA, 7
		hotspot pvX, 0, pvH, 305, tbL, 1 + 128
		hotspot tbX, 0, tbZ, 306, tbL, 2
		hotspot pvX - cos(tbA), 0, pvH - sin(tbA), 307, tbL, 3
		hotspot kdR, 0, 0, 308, bkD, 1 + 128
		hotspot kdR, 0, -bkD, 309, bkD, 2
		hotspot kdR, 0, 1, 310, bkD, 3
		del 1
	endif
	if mcKind = 10 then
		! チャックの上がりとケーシングの高さ
		hotspot rtL / 2, 0, zDk, 311, rtS, 1 + 128
		hotspot rtL / 2, 0, zDk + rtS, 312, rtS, 2
		hotspot rtL / 2, 0, zDk - 1, 313, rtS, 3
		hotspot 0, 0, rtH + rtS, 314, csH, 1 + 128
		hotspot 0, 0, rtH + rtS + csH, 315, csH, 2
		hotspot 0, 0, rtH + rtS - 1, 316, csH, 3
	endif
	if mcKind = 11 then
		! フロント3段と先の角度（関節が中心）
		rotz slew
		hotspot pvX, 0, pvH, 321, dA1, 6
		hotspot pvX + 1, 0, pvH, 322, dA1, 4
		hotspot dmX1, 0, dmZ1, 323, dA1, 5
		hotspot pvX, -1, pvH, 324, dA1, 7
		hotspot dmX1, 0, dmZ1, 325, dA2, 6
		hotspot dmX1 + 1, 0, dmZ1, 326, dA2, 4
		hotspot dmX2, 0, dmZ2, 327, dA2, 5
		hotspot dmX1, -1, dmZ1, 328, dA2, 7
		hotspot dmX2, 0, dmZ2, 329, dA3, 6
		hotspot dmX2 + 1, 0, dmZ2, 330, dA3, 4
		hotspot dmX3, 0, dmZ3, 331, dA3, 5
		hotspot dmX2, -1, dmZ2, 332, dA3, 7
		hotspot dmX3, 0, dmZ3, 333, bkA, 6
		hotspot dmX3 + 1, 0, dmZ3, 334, bkA, 4
		hotspot dmX3 + tpL * cos(bkA), 0, dmZ3 + tpL * sin(bkA), 335, bkA, 5
		hotspot dmX3, -1, dmZ3, 336, bkA, 7
		atX0 = dmX3
		atZ0 = dmZ3
		hid = 355
		gosub "jawhot"
		del 1
	endif
	if mcKind = 13 then
		! 荷台の傾き（セルフローダ。後ろのヒンジが中心）・クレーンの起伏と長さ
		hX = xR
		hZ = flZ - 0.12
		hotspot hX, 0, hZ, 372, bedA, 6
		hotspot hX + 1, 0, hZ, 373, bedA, 4
		hotspot hX + (bedL + 0.1) * cos(bedA), 0, hZ + (bedL + 0.1) * sin(bedA), 374, bedA, 5
		hotspot hX, -1, hZ, 375, bedA, 7
		if ucOn then
			add ucX, 0, 0
			rotz slew + 180
			hotspot 0, 0, ucH, 365, abA, 6
			hotspot 1, 0, ucH, 366, abA, 4
			hotspot ucTx, 0, ucTz, 367, abA, 5
			hotspot 0, -1, ucH, 368, abA, 7
			hotspot 0, 0, ucH, 369, ucL, 1 + 128
			hotspot ucTx, 0, ucTz, 370, ucL, 2
			hotspot -cos(abA), 0, ucH - sin(abA), 371, ucL, 3
			del 2
		endif
	endif
	if mcKind = 14 then
		! 連結の折れ角（平面の xy 面。上から見て左回りが +）
		hotspot kpX, 0, kpZ, 361, trA, 6
		hotspot kpX - 1, 0, kpZ, 362, trA, 4
		hotspot kpX - tlB * cos(trA), -tlB * sin(trA), kpZ, 363, trA, 5
		hotspot kpX, 0, kpZ + 1, 364, trA, 7
	endif
	if mcKind = 12 then
		! チャックの上がりと杭の天端
		hotspot 0.35, 0, piC, 341, piS, 1 + 128
		hotspot 0.35, 0, piC + piS, 342, piS, 2
		hotspot 0.35, 0, piC - 1, 343, piS, 3
		hotspot 0, 0, piC + piS, 344, piT, 1 + 128
		hotspot 0, 0, piC + piS + piT, 345, piT, 2
		hotspot 0, 0, piC + piS - 1, 346, piT, 3
	endif
return

"crinfo":
	if wrOn then
		material "mc_red"
		add 0, 0, 0.05
		circle hkX
		del 1
	endif
	if infoOn then
		! クレーン情報（フックと車体の後ろ。視点の向きへ回す）
		define style "mcI" "Arial", 900 * texZ, 1, 0
		style "mcI"
		aV = 0
		dxV = GLOB_EYEPOS_X - SYMB_POS_X
		dyV = GLOB_EYEPOS_Y - SYMB_POS_Y
		if abs(dxV) > 0.01 then aV = atn(dyV / dxV) + 180 * (dxV < 0)
		aV = aV - SYMB_ROTANGLE + 90
		material "mc_red"
		add hkX * cos(slew), hkX * sin(slew), tpZ - hkD + hkH + 0.6
		rotz aV
		rotx 90
		if rated > 0 then
			text 0.02, 0, "Max " + str(rated * sfRate, 5, 2) + "t (" + str(sfRate * 100, 3, 0) + "%)"
		else
			text 0.02, 0, "Max -"
		endif
		del 3
		add -gnX, 0, gnH + 1.2
		rotz aV
		rotx 90
		text 0.02, 0, mcName
		add 0, -0.9 * texZ, 0
		text 0.02, 0, "Boom=" + str(lbL, 4, 1) + "m R=" + str(hkX, 4, 1) + "m"
		del 4
	endif
	return

"lbHalf":
	! ラチスブームの x（xq）での半幅 hyq・半高 hzq（下部は根元へ、上部は先へ絞る）
	hyq = lbW / 2
	hzq = lbD / 2
	if xq < lLo then
		hyq = lbW * (0.42 + 0.08 * xq / lLo)
		hzq = 0.22 + (lbD / 2 - 0.22) * xq / lLo
	endif
	if xq > lbL - lUp then
		tq = (lbL - xq) / lUp
		hyq = lbW * (0.26 + 0.24 * tq)
		hzq = 0.3 + (lbD / 2 - 0.3) * tq
	endif
return

"jawhot":
	! 爪の開き atO（圧砕機・鉄骨切断機・つかみ機）: 中心は爪の付け根、基準は下の爪、動く点は上の爪の先
	if atK >= 1 and atK <= 3 then
		jx = atX0 + 0.45 * atL * cos(bkA)
		jz = atZ0 + 0.45 * atL * sin(bkA)
		jl = 0.55 * atL
		hotspot jx, 0, jz, hid, atO, 6
		hotspot jx + jl * cos(bkA - atO / 2), 0, jz + jl * sin(bkA - atO / 2), hid + 1, atO, 4
		hotspot jx + jl * cos(bkA + atO / 2), 0, jz + jl * sin(bkA + atO / 2), hid + 2, atO, 5
		hotspot jx, -1, jz, hid + 3, atO, 7
	endif
	return

"crawler":
	! 履帯（帯・両端の輪・グローサ・横のフレームと下転輪・遊動輪と起動輪）と下部の枠・旋回輪
	rT = trkH / 2
	for s = -1 to 1 step 2
		yc = s * (trkW / 2 - shoeW / 2)
		material "mc_dark"
		add -trkL / 2 + rT, yc - shoeW / 2, 0
		block trkL - 2 * rT, shoeW, trkH
		del 1
		for e = -1 to 1 step 2
			add e * (trkL / 2 - rT), yc + shoeW / 2, rT
			rotx 90
			cylind shoeW, rT
			del 2
		next e
		nG = int((trkL - 2 * rT) / 0.2)
		for k = 0 to nG
			add -trkL / 2 + rT + k * 0.2, yc - shoeW / 2, trkH
			block 0.05, shoeW, 0.03
			del 1
		next k
		! 外の面: 履帯のフレーム（板 0.02）と、その外に下転輪・遊動輪・起動輪（円柱は rotx 90 で -y へ伸びる）
		yP = yc + s * shoeW / 2 - (s < 0) * 0.02
		material "mc_body"
		add -trkL / 2 + rT, yP, trkH * 0.3
		block trkL - 2 * rT, 0.02, trkH * 0.4
		del 1
		yR = yP + (s > 0) * 0.05
		material "mc_steel"
		nRl = max(2, int((trkL - 2 * rT) / 0.45))
		for k = 0 to nRl
			add -trkL / 2 + rT + k * (trkL - 2 * rT) / nRl, yR, 0.13
			rotx 90
			cylind 0.03, 0.09
			del 2
		next k
		for e = -1 to 1 step 2
			add e * (trkL / 2 - rT), yR, rT
			rotx 90
			cylind 0.03, rT * 0.72
			del 2
		next e
		! 上転輪（帯の上を支える）
		material "mc_steel"
		for q = -1 to 1 step 2
			add q * trkL * 0.18, yR, trkH - 0.12
			rotx 90
			cylind 0.03, 0.07
			del 2
		next q
		! 両端の輪に回るシュー（グローサ）
		material "mc_dark"
		for e = -1 to 1 step 2
			for q = -2 to 2
				add e * (trkL / 2 - rT) + e * rT * cos(q * 36), yc - shoeW / 2, rT + rT * sin(q * 36)
				mul e, 1, 1
				roty -q * 36
				add 0, 0, -0.025
				block 0.03, shoeW, 0.05
				del 4
			next q
		next e
		! 起動輪の歯（後ろの輪）
		material "mc_steel"
		for q = 0 to 7
			add -(trkL / 2 - rT) + rT * 0.72 * cos(q * 45) - 0.03, yR - 0.03, rT + rT * 0.72 * sin(q * 45) - 0.03
			block 0.06, 0.03, 0.06
			del 1
		next q
	next s
	material "mc_body"
	lF = min(1.8, trkL * 0.55)
	add -lF / 2, -(trkW / 2 - shoeW), trkH * 0.35
	block lF, trkW - 2 * shoeW, trkH * 0.45
	del 1
	material "mc_steel"
	add 0, 0, trkH * 0.8
	cylind upZ - trkH * 0.8, min(0.85, upW * 0.3)
	del 1
	return

"blade":
	! 排土板（履帯の前。腕2本とシリンダ）
	material "mc_body"
	add trkL / 2 + 0.25, -bldW / 2, 0.02
	block 0.12, bldW, bldH
	del 1
	for s = -1 to 1 step 2
		x0q = trkL / 2 - 0.4
		z0q = trkH * 0.45
		x1q = trkL / 2 + 0.3
		z1q = bldH * 0.5
		bwq = 0.1
		bhq = 0.12
		add 0, s * bldW * 0.3, 0
		gosub "bar"
		del 1
	next s
	crq = 0.04
	cx0 = trkL / 2 - 0.25
	cy0 = 0
	cz0 = trkH * 0.7
	cx1 = trkL / 2 + 0.25
	cy1 = 0
	cz1 = bldH * 0.85
	gosub "cyl2"
	return

"upper":
	! 上部旋回体（後ろは後端旋回半径の円弧）・カウンタウエイト・エンジンカバー・運転室と窓・手すり
	hB = 0.12 * (upH - upZ) + 0.45
	material "mc_body"
	for i = 0 to 8
		aa = 180 + aS - i * aS / 4
		put tailR * cos(aa), tailR * sin(aa)
	next i
	put upF, w2, upF, -w2
	add 0, 0, upZ
	prism nsp / 2, hB, get(nsp)
	del 1
	! カウンタウエイト（cwH があれば下面 upZ から高さ cwH・幅 cwW、無ければ上に載る薄い形）
	xC = xsc + min(0.9, tailR * 0.35)
	zC0 = upZ + hB
	hC = 0.35
	if cwH > 0.01 then
		xC = xsc + 1.0
		zC0 = upZ
		hC = cwH
	endif
	material "mc_cw"
	for i = 0 to 8
		aa = 180 + aSc - i * aSc / 4
		put tailR * cos(aa), tailR * sin(aa)
	next i
	put xC, w2c, xC, -w2c
	add 0, 0, zC0
	prism nsp / 2, hC, get(nsp)
	del 1
	material "mc_body"
	yE0 = -w2 + 0.05
	yE1 = w2 - cabW - 0.1
	if cbS < 0 then
		yE0 = -w2 + cabW + 0.1
		yE1 = w2 - 0.05
	endif
	add xC, yE0, upZ + hB
	block max(0.2, upF - cabL - xC - 0.05), yE1 - yE0, 0.4
	del 1
	material "mc_dark"
	for i = 0 to 4
		add xC + 0.1 + i * 0.18, yE0 + 0.1, upZ + hB + 0.4
		block 0.09, max(0.1, yE1 - yE0 - 0.2), 0.01
		del 1
	next i
	! 運転室（cbS の側の前）
	yC0 = w2 - cabW
	if cbS < 0 then yC0 = -w2
	material "mc_body"
	add upF - cabL, yC0, upZ + hB
	block cabL, cabW, upH - upZ - hB
	del 1
	material "mc_glass"
	hW = (upH - upZ - hB) * 0.62
	add upF + 0.005, yC0 + 0.08, upH - hW - 0.08
	block 0.006, cabW - 0.16, hW
	del 1
	yG = yC0 + cabW + 0.002
	if cbS < 0 then yG = yC0 - 0.008
	add upF - cabL + 0.12, yG, upH - hW - 0.08
	block cabL - 0.24, 0.006, hW
	del 1
	material "mc_steel"
	add upF - cabL - 0.05, yE0, upZ + hB + 0.4
	block 0.04, yE1 - yE0, 0.03
	del 1
	! カウンタウエイトの段の目地（0.45m ごと）
	if hC > 0.7 then
		material "mc_dark"
		for qi = 1 to int(hC / 0.45)
			for i = 0 to 8
				aa = 180 + aSc - i * aSc / 4
				put (tailR + 0.004) * cos(aa), (tailR + 0.004) * sin(aa)
			next i
			put xC, w2c + 0.004, xC, -w2c - 0.004
			add 0, 0, zC0 + qi * 0.45
			prism nsp / 2, 0.012, get(nsp)
			del 1
		next qi
	endif
	! 運転室の反対の側の手すり（上面の通路。柱3本と2段のパイプ）
	yH = -(w2 - 0.06)
	if cbS < 0 then yH = w2 - 0.06
	zH = upZ + hB + 0.4
	material "mc_lamp"
	rq = 0.018
	xH0 = xC + 0.15
	xH1 = upF - 0.2
	if xH1 - xH0 > 0.6 and tailR >= 2.5 then
		for qi = 0 to 2
			add xH0 + qi * (xH1 - xH0) / 2, yH, zH
			cylind 0.9, rq
			del 1
		next qi
		for qi = 1 to 2
			x0q = xH0
			y0q = yH
			z0q = zH + qi * 0.45
			x1q = xH1
			y1q = yH
			z1q = z0q
			gosub "seg3"
		next qi
	endif
	! 運転室の横の昇降ステップ（3段）
	yS = w2 + 0.06
	if cbS < 0 then yS = -w2 - 0.18
	material "mc_steel"
	for qi = 0 to 2
		add upF - cabL - 0.05, yS, upZ - 0.55 + qi * 0.3
		block 0.45, 0.12, 0.02
		del 1
	next qi
	! ミラー・回転灯・ワイパー
	yM = yC0 + cabW + 0.12
	if cbS < 0 then yM = yC0 - 0.12
	material "mc_dark"
	add upF + 0.1, yM - 0.05, upH - 0.55
	block 0.03, 0.1, 0.28
	del 1
	material "mc_lamp"
	add upF - cabL / 2, yC0 + cabW / 2, upH
	cylind 0.12, 0.05
	del 1
	material "mc_dark"
	add upF + 0.012, yC0 + cabW / 2 - 0.01, upH - hW * 0.9
	block 0.006, 0.02, hW * 0.6
	del 1
	return

"bar":
	! (x0q, z0q) から (x1q, z1q) の箱（幅 bwq・せい bhq。y は 0 を中心）
	dxq = x1q - x0q
	dzq = z1q - z0q
	lq = sqr(dxq ^ 2 + dzq ^ 2)
	anq = 90
	if dzq < 0 then anq = -90
	if abs(dxq) > 0.000001 then anq = atn(dzq / dxq)
	if dxq < 0 then anq = anq + 180
	add x0q, 0, z0q
	roty -anq
	add 0, -bwq / 2, -bhq / 2
	block lq, bwq, bhq
	del 3
	return

"seg3":
	! (x0q, y0q, z0q) から (x1q, y1q, z1q) の円柱（半径 rq）
	dxq = x1q - x0q
	dyq = y1q - y0q
	dzq = z1q - z0q
	hq = sqr(dxq ^ 2 + dyq ^ 2)
	lq = sqr(hq ^ 2 + dzq ^ 2)
	if lq > 0.001 then
		az = 0
		if hq > 0.0001 then
			if abs(dxq) < 0.0001 then
				az = 90
				if dyq < 0 then az = -90
			else
				az = atn(dyq / dxq)
				if dxq < 0 then az = az + 180
			endif
		endif
		el = 90
		if dzq < 0 then el = -90
		if hq > 0.0001 then el = atn(dzq / hq)
		add x0q, y0q, z0q
		rotz az
		roty 90 - el
		cylind lq, rq
		del 3
	endif
	return

"cyl2":
	! 油圧シリンダ（太い筒 6 割と細いロッド）: (cx0, cy0, cz0) から (cx1, cy1, cz1)
	material "mc_dark"
	x0q = cx0
	y0q = cy0
	z0q = cz0
	x1q = cx0 + 0.6 * (cx1 - cx0)
	y1q = cy0 + 0.6 * (cy1 - cy0)
	z1q = cz0 + 0.6 * (cz1 - cz0)
	rq = crq
	gosub "seg3"
	material "mc_rod"
	x0q = x1q
	y0q = y1q
	z0q = z1q
	x1q = cx1
	y1q = cy1
	z1q = cz1
	rq = crq * 0.55
	gosub "seg3"
	return

"backhoe":
	! ブーム（くの字の2本の箱）・アーム・バケット（側板の形と爪）・シリンダ3本
	bwq = 0.075 * boomL
	material "mc_body"
	add pvX - 0.2, -bwq / 2 - 0.08, upZ
	block 0.5, bwq + 0.16, pvH - upZ + 0.15
	del 1
	x0q = pvX
	z0q = pvH
	x1q = knX
	z1q = knZ
	bhq = 0.1 * boomL
	gosub "bar"
	x0q = knX
	z0q = knZ
	x1q = bmX1
	z1q = bmZ1
	bhq = 0.075 * boomL
	gosub "bar"
	bwq = 0.06 * boomL
	bhq = 0.06 * boomL
	x0q = amX0
	z0q = amZ0
	x1q = amX1
	z1q = amZ1
	gosub "bar"
	material "mc_steel"
	add bmX1, bwq / 2 + 0.03, bmZ1
	rotx 90
	cylind bwq + 0.06, 0.07
	del 2
	atX0 = amX1
	atZ0 = amZ1
	if atK = 5 then
		gosub "lhv"
	else
		if atK > 0 then
			gosub "attach"
		else
			gosub "bucket"
		endif
	endif
	! シリンダ（ブーム2本・アーム・バケット）
	crq = 0.045 * boomL / 3.5
	for s = -1 to 1 step 2
		cx0 = pvX + 0.35
		cy0 = s * (0.075 * boomL / 2 + 0.06)
		cz0 = upZ + 0.25
		cx1 = pvX + 0.42 * boomL * cos(bmA) + 0.04 * boomL * sin(bmA)
		cy1 = cy0
		cz1 = pvH + 0.42 * boomL * sin(bmA) - 0.04 * boomL * cos(bmA)
		gosub "cyl2"
	next s
	cx0 = knX - 0.06 * boomL * sin(bmA)
	cy0 = 0
	cz0 = knZ + 0.07 * boomL
	cx1 = amX0
	cy1 = 0
	cz1 = amZ0
	gosub "cyl2"
	crq = crq * 0.8
	cx0 = bmX1 + 0.2 * armL * cos(amA) - 0.08 * sin(amA)
	cy0 = 0
	cz0 = bmZ1 + 0.2 * armL * sin(amA) + 0.08 * cos(amA)
	cx1 = amX1 - 0.12 * armL * cos(amA) - 0.12 * sin(amA)
	cy1 = 0
	cz1 = amZ1 - 0.12 * armL * sin(amA) + 0.12 * cos(amA)
	gosub "cyl2"
	return

"bucket":
	! バケット（ピン atX0, atZ0 から爪へ bkA の向き。側板の形を幅 bkW で押し出す）
	material "mc_dark"
	add atX0, bkW / 2, atZ0
	rotx 90
	rotz bkA
	prism 6, bkW, 0, 0.1 * bkL, 0.3 * bkL, 0.42 * bkL, 0.8 * bkL, 0.38 * bkL, bkL, 0, 0.85 * bkL, -0.06 * bkL, 0.12 * bkL, -0.1 * bkL
	nTh = max(3, int(bkW / 0.22))
	for k = 0 to nTh - 1
		add bkL - 0.02, -0.03, 0.06 + k * (bkW - 0.12) / max(1, nTh - 1) - 0.04
		block 0.14, 0.06, 0.08
		del 1
	next k
	del 3
	return

"attach":
	! 解体アタッチメント（ピン atX0, atZ0 から bkA の向き）: 本体（全旋回のリング）と爪2枚（atO だけ開く）、つかみ機は爪が2本ずつ、
	! ブレーカは筒とチゼル。爪はピンから 0.45×atL で開き、長さ 0.55×atL
	bWq = min(0.7, max(0.2, 0.22 * atL))
	add atX0, 0, atZ0
	roty -bkA
	if atK = 4 then
		material "mc_dark"
		roty 90
		cylind 0.75 * atL, max(0.08, 0.11 * atL)
		material "mc_steel"
		cylind atL, max(0.03, atW / 2)
		del 1
	else
		material "mc_dark"
		add 0, -bWq / 2, -bWq / 2
		block 0.45 * atL, bWq, bWq
		del 1
		material "mc_steel"
		add 0.12 * atL, 0, 0
		roty 90
		cylind 0.08, bWq * 0.75
		del 2
		jl = 0.55 * atL
		th = 0.16 * atL
		wq = bWq
		if atK = 2 then
			th = 0.1 * atL
			wq = bWq * 0.6
		endif
		material "mc_drum"
		for sj = -1 to 1 step 2
			add 0.45 * atL, 0, 0
			roty -sj * atO / 2
			if atK = 3 then
				for tj = -1 to 1 step 2
					add 0, tj * bWq * 0.32, 0
					wq = bWq * 0.25
					gosub "jawp"
					del 1
				next tj
			else
				gosub "jawp"
			endif
			del 2
		next sj
	endif
	del 2
	return

"lhv":
	! ショベル装着式バイブロ（調和工業 LHV）: エクステンション（ピンから bkA の向きへ水平 atL、そこから下へ atW のくの字の腕）と、
	! 下のピンに吊った本体（幅 vbW・奥行き vbT・全高 vbH。いつも鉛直）・ハンガー・チャック・杭（長さ vbP）
	exq = atX0 + atL * cos(bkA)
	ezq = atZ0 + atL * sin(bkA)
	hxq = exq + atW * sin(bkA)
	hzq = ezq - atW * cos(bkA)
	material "mc_body"
	bwq = max(0.12, 0.18 * vbT)
	bhq = max(0.12, 0.2 * atL)
	x0q = atX0
	z0q = atZ0
	x1q = exq
	z1q = ezq
	gosub "bar"
	x0q = exq
	z0q = ezq
	x1q = hxq
	z1q = hzq
	gosub "bar"
	material "mc_steel"
	add hxq, vbT / 2, hzq
	rotx 90
	cylind vbT, 0.05
	del 2
	! ハンガー（上のピンから本体の上まで）・本体（起振機）・チャック（幅 0.16）
	material "mc_drum"
	add hxq - vbW * 0.45, -0.06, hzq - vbH * 0.32
	block vbW * 0.9, 0.12, vbH * 0.3
	del 1
	add hxq - vbW / 2, -vbT / 2, hzq - vbH * 0.62
	block vbW, vbT, vbH * 0.32
	del 1
	material "mc_dark"
	add hxq - 0.08, -vbT * 0.3, hzq - vbH
	block 0.16, vbT * 0.6, vbH * 0.38
	del 1
	material "mc_steel"
	add hxq - 0.2, -0.006, hzq - vbH - vbP + 0.2
	block 0.4, 0.012, vbP
	del 1
	return

"flatdeck":
	! 平ボディの荷台: 床（根太の見える厚み）・あおり（側・後ろ）・鳥居（前）。後ろのヒンジで bedA だけ傾ける（セルフローダ）。道板は
	! 後端から地面へ2枚
	dLq = bedL + 0.1
	dWq = bedW + 0.1
	add xR, 0, flZ - 0.12
	roty -bedA
	material "mc_bed"
	add 0, -dWq / 2, 0
	block dLq, dWq, 0.12
	del 1
	material "mc_dark"
	for k = 0 to 4
		add 0.05 + k * (dLq - 0.15) / 4, -dWq / 2, -0.1
		block 0.08, dWq, 0.1
		del 1
	next k
	material "mc_bed"
	if bedH > 0.01 then
		for s = -1 to 1 step 2
			add 0, s * dWq / 2 - (s > 0) * 0.04, 0.12
			block dLq - 0.1, 0.04, bedH
			del 1
		next s
		add 0, -dWq / 2, 0.12
		block 0.04, dWq, bedH
		del 1
	endif
	! 鳥居（前の板と上の枠）
	material "mc_steel"
	add dLq - 0.1, -dWq / 2, 0.12
	block 0.08, dWq, bedH + 0.5
	del 1
	for s = -1 to 1 step 2
		add dLq - 0.1, s * (dWq / 2 - 0.06) - 0.04, 0.12
		block 0.08, 0.08, bedH + 0.9
		del 1
	next s
	add dLq - 0.1, -dWq / 2, bedH + 0.95
	block 0.08, dWq, 0.07
	del 1
	del 2
	if rpL > 0.01 then
		rpA = asn(min(1, flZ / rpL))
		material "mc_steel"
		for s = -1 to 1 step 2
			add 0, s * (bedW / 2 - 0.25), 0
			x0q = xR
			z0q = flZ
			x1q = xR - rpL * cos(rpA)
			z1q = 0.02
			bwq = 0.4
			bhq = 0.06
			gosub "bar"
			del 1
		next s
	endif
	return

"cargocrane":
	! 積載形クレーン（原点＝旋回中心。タダノ ZX の公表: 七角形 3・4 段、複動シリンダ押上式、フック・イン。コラムとブームの断面は【目安】）
	material "mc_body"
	add -0.45, -0.55, frZ
	block 0.9, 1.1, 0.35
	del 1
	! 台の操作レバー（左右）
	material "mc_dark"
	for s = -1 to 1 step 2
		for k = 0 to 2
			add -0.42 + k * 0.1, s * 0.6, frZ + 0.1
			cylind 0.45, 0.012
			del 1
		next k
	next s
	! コラム（円筒と上の二股）とウインチ
	material "mc_body"
	add 0, 0, frZ + 0.35
	cylind max(0.2, ucH - frZ - 0.5), 0.225
	del 1
	for s = -1 to 1 step 2
		add -0.3, s * 0.2 - 0.02, ucH - 0.4
		block 0.55, 0.04, 0.55
		del 1
	next s
	material "mc_steel"
	add -0.28, -0.17, ucH - 0.32
	rotx -90
	cylind 0.34, 0.14
	del 2
	add 0, -0.2, ucH
	rotx -90
	cylind 0.4, 0.04
	del 2
	! ブーム（基本は長さ一定、先の段が同じ量ずつ出る）
	nUc = max(2, min(5, nSec))
	lUb = ucLmin * 0.92
	add 0, 0, ucH
	roty -abA
	for i = 1 to nUc
		wS = 0.3 - 0.04 * (i - 1)
		hS = 0.35 - 0.04 * (i - 1)
		eK = lUb + (i - 1) * (ucL - 0.18 - lUb) / (nUc - 1)
		sK = -0.1
		if i > 1 then sK = lUb + (i - 2) * (ucL - 0.18 - lUb) / (nUc - 1) - 0.04
		material "mc_body"
		add sK, 0, -0.12
		roty 90
		put -0.5 * hS, -0.34 * wS, -0.5 * hS, 0.34 * wS, -0.2 * hS, 0.5 * wS, 0.2 * hS, 0.42 * wS, 0.5 * hS, 0, 0.2 * hS, -0.42 * wS, -0.2 * hS, -0.5 * wS
		prism nsp / 2, eK - sK, get(nsp)
		del 2
		if i < nUc then
			material "mc_steel"
			add eK - 0.04, -wS / 2 - 0.01, -0.12 - hS / 2 - 0.01
			block 0.04, wS + 0.02, hS + 0.02
			del 1
		endif
	next i
	! ブームの先（シーブ 2 枚）
	material "mc_steel"
	for s = -1 to 1 step 2
		add ucL - 0.2, s * 0.09 - 0.012, -0.25
		block 0.34, 0.024, 0.3
		del 1
	next s
	for k = 0 to 1
		add ucL, -0.06 + k * 0.07, -0.05
		rotx -90
		cylind 0.05, 0.1
		del 2
	next k
	del 2
	! 起伏シリンダ（下ピンはコラムの前、上ピンは基本ブームの下に固定）
	crq = 0.075
	cx0 = 0.24
	cy0 = 0
	cz0 = ucH - 0.75
	cx1 = lUb * 0.42 * cos(abA) + 0.34 * sin(abA)
	cy1 = 0
	cz1 = ucH + lUb * 0.42 * sin(abA) - 0.34 * cos(abA)
	gosub "cyl2"
	material "mc_steel"
	nW = 4
	for k = 1 to nW
		add ucTx, (k - 2.5) * 0.02, ucTz - hkD - 0.05
		cylind hkD, 0.006
		del 1
	next k
	material "mc_hook"
	add ucTx, 0, ucTz - hkD - 0.32
	mul 0.6, 1, 0.6
	add 0, 0.02, 0
	rotx 90
	prism 15, 0.04, -0.04, 0.45, 0.04, 0.45, 0.05, 0.32, 0.17, 0.2, 0.19, 0.09, 0.12, 0.01, 0, 0, -0.13, 0.05, -0.19, 0.14, -0.13, 0.2, -0.1, 0.13, -0.03, 0.08, 0.07, 0.09, 0.1, 0.15, -0.03, 0.26
	del 4
	add ucTx - 0.1, -0.07, ucTz - hkD - 0.05
	block 0.2, 0.14, 0.18
	del 1
	return

"semitrailer":
	! セミトレーラー（原点＝キングピン、後ろが −x）: tlK 1 グースネック・荷台（床 dkZ）・車軸の上の荷台（rrZ）、2 平床とスタンション・
	! ヘッドボード、3 連結パイプと後台車。車軸の列 tlN・片側のダブルタイヤの組 tlQ・積荷
	material "mc_body"
	hwq = tlW / 2
	if tlK = 1 then
		x0g = tlF - gnL
		add x0g, -hwq * 0.85, kpZ
		block gnL, tlW * 0.85, gnT
		del 1
		add x0g - 0.25, -hwq, dkZ - 0.2
		block 0.25, tlW, kpZ + gnT - dkZ + 0.2
		del 1
		material "mc_bed"
		add x0g - dkL, -hwq, dkZ - 0.15
		block dkL, tlW, 0.15
		del 1
		material "mc_dark"
		for s = -1 to 1 step 2
			add x0g - dkL, s * (hwq - 0.15) - 0.1, max(0.15, dkZ - 0.45)
			block dkL, 0.2, min(0.3, dkZ - 0.15)
			del 1
		next s
		material "mc_body"
		add -tlB, -hwq, rrZ - 0.35
		block tlB + x0g - dkL, tlW, 0.35
		del 1
	endif
	if tlK = 2 then
		add -tlB, -hwq, dkZ - 0.25
		block tlB + tlF, tlW, 0.25
		del 1
		material "mc_dark"
		for s = -1 to 1 step 2
			add -tlB, s * (hwq - 0.2) - 0.1, dkZ - 0.6
			block tlB + tlF, 0.2, 0.35
			del 1
		next s
		material "mc_steel"
		add tlF - 0.1, -hwq, dkZ
		block 0.1, tlW, 1.0
		del 1
		for k = 0 to 3
			for s = -1 to 1 step 2
				add tlF - 1.5 - k * (tlB - 2.5) / 3, s * (hwq - 0.05) - 0.05, dkZ
				block 0.1, 0.1, 0.8
				del 1
			next s
		next k
	endif
	if tlK = 3 then
		material "mc_steel"
		add 0.3, 0, dkZ
		roty -90
		cylind tlAx - 1.0 + 0.3, 0.12
		del 2
		material "mc_body"
		xb = -(tlAx + (tlN - 1) * tlSp / 2)
		add xb - dkL / 2 - 0.9, -hwq, 0.9
		block dkL + 1.8, tlW, max(0.2, rrZ - 0.9)
		del 1
	endif
	! 車軸とタイヤ（ダブル）
	for i = 0 to tlN - 1
		xa = -(tlAx + i * tlSp)
		material "mc_dark"
		add xa - 0.08, -tlT / 2, tlR - 0.08
		block 0.16, tlT, 0.16
		del 1
		for s = -1 to 1 step 2
			for q = 1 to max(1, tlQ)
				yq = s * (tlT / 2 - (q - 1) * 0.885)
				for d = 0 to 1
					material "mc_tire"
					add xa, yq + (d - 0.5) * 0.29 + 0.12, tlR
					rotx 90
					cylind 0.24, tlR
					del 2
					material "mc_rim"
					add xa, yq + (d - 0.5) * 0.29 + 0.125, tlR
					rotx 90
					cylind 0.25, tlR * 0.55
					del 2
				next d
			next q
		next s
	next i
	if cgOn then
		material "mc_drum"
		zL = dkZ
		if tlK = 3 then zL = max(kpZ + 0.3, rrZ)
		add cgX - cgL / 2, -cgW / 2, zL
		block cgL, cgW, cgH
		del 1
	endif
	return

"jawp":
	! 爪1枚（xz 面の四角形を厚み wq で押し出す。sj＝1 は上、-1 は下）
	add 0, wq / 2, 0
	rotx 90
	prism 4, wq, 0, 0, jl, sj * th * 0.15, jl * 0.85, sj * th * 0.75, 0, sj * th
	del 2
	return

"demolish":
	! 解体機のフロント（メインブーム・フロントブーム・アームの3段。弦の長さ dbL1〜3・水平からの角度 dA1〜3）・関節のピン・
	! シリンダ・先のアタッチメント（atK 0 はバケット）
	bw1 = max(0.18, min(0.6, 0.06 * dbL1 + 0.12))
	material "mc_body"
	add pvX - 0.35, -bw1 / 2 - 0.1, upZ
	block 0.7, bw1 + 0.2, pvH - upZ + 0.15
	del 1
	bwq = bw1
	bhq = bw1 * 1.3
	x0q = pvX
	z0q = pvH
	x1q = dmX1
	z1q = dmZ1
	gosub "bar"
	bwq = bw1 * 0.85
	bhq = bwq * 1.2
	x0q = dmX1
	z0q = dmZ1
	x1q = dmX2
	z1q = dmZ2
	gosub "bar"
	bwq = bw1 * 0.7
	bhq = bwq * 1.2
	x0q = dmX2
	z0q = dmZ2
	x1q = dmX3
	z1q = dmZ3
	gosub "bar"
	material "mc_steel"
	add dmX1, bw1 / 2 + 0.05, dmZ1
	rotx 90
	cylind bw1 + 0.1, bw1 * 0.3
	del 2
	add dmX2, bw1 / 2 + 0.05, dmZ2
	rotx 90
	cylind bw1 + 0.1, bw1 * 0.25
	del 2
	! シリンダ（段の下側。1本ずつ。離れは段の幅 bw1 に合わせる）
	crq = max(0.02, bw1 * 0.22)
	eq = bw1 * 0.6
	cx0 = pvX + bw1
	cy0 = 0
	cz0 = upZ + bw1 * 0.8
	cx1 = pvX + 0.5 * dbL1 * cos(dA1) + eq * sin(dA1)
	cy1 = 0
	cz1 = pvH + 0.5 * dbL1 * sin(dA1) - eq * cos(dA1)
	gosub "cyl2"
	crq = crq * 0.85
	cx0 = pvX + 0.7 * dbL1 * cos(dA1) + eq * sin(dA1)
	cz0 = pvH + 0.7 * dbL1 * sin(dA1) - eq * cos(dA1)
	cx1 = dmX1 + 0.3 * dbL2 * cos(dA2) + eq * sin(dA2)
	cz1 = dmZ1 + 0.3 * dbL2 * sin(dA2) - eq * cos(dA2)
	gosub "cyl2"
	crq = crq * 0.85
	cx0 = dmX1 + 0.75 * dbL2 * cos(dA2) + eq * sin(dA2)
	cz0 = dmZ1 + 0.75 * dbL2 * sin(dA2) - eq * cos(dA2)
	cx1 = dmX2 + 0.2 * dbL3 * cos(dA3) + eq * sin(dA3)
	cz1 = dmZ2 + 0.2 * dbL3 * sin(dA3) - eq * cos(dA3)
	gosub "cyl2"
	atX0 = dmX3
	atZ0 = dmZ3
	if atK = 5 then
		gosub "lhv"
	else
		if atK > 0 then
			gosub "attach"
		else
			gosub "bucket"
		endif
	endif
	return

"pileleader":
	! 三点式杭打機: リーダブラケット・リーダ（主管 ldDia と前のガイド管2本・頂部のシーブ）・ステー2本（上部の後ろから stZ）・
	! フロントジャッキと後ろのアウトリガ・オーガ（モータ auH×auW、スクリュー auN 本・軸間 auP・下端に先のヘッド）
	lzT = ldZ + ldL
	hBq = 0.12 * (upH - upZ) + 0.45
	material "mc_body"
	add upF - 0.1, -0.6, upZ
	block max(0.2, ldX - upF + 0.1), 1.2, 0.9
	del 1
	add ldX, 0, ldZ
	cylind ldL, ldDia / 2
	del 1
	material "mc_steel"
	for s = -1 to 1 step 2
		add ldX + ldDia * 0.67, s * ldDia * 0.38, ldZ
		cylind ldL, max(0.03, ldDia * 0.077)
		del 1
	next s
	material "mc_dark"
	add ldX - ldDia * 0.6, -ldDia * 0.6, lzT
	block ldDia * 1.6, ldDia * 1.2, ldDia * 2.7
	del 1
	material "mc_steel"
	for s = -1 to 1 step 2
		x0q = -tailR * 0.35
		y0q = s * upW * 0.35
		z0q = upZ + hBq
		x1q = ldX - ldDia / 2
		y1q = s * ldDia * 0.3
		z1q = min(stZ, lzT - 0.5)
		rq = max(0.04, 0.0045 * ldL)
		gosub "seg3"
	next s
	! ジャッキ（筒とパッド）と後ろのアウトリガの梁
	for s = -1 to 1 step 2
		material "mc_dark"
		add fjX, s * fjW / 2, 0.05
		cylind upZ + 0.4, 0.12
		del 1
		add -rjX, s * rjW / 2, 0.05
		cylind upZ + 0.4, 0.12
		del 1
		material "mc_steel"
		add fjX - 0.3, s * fjW / 2 - 0.3, 0
		block 0.6, 0.6, 0.05
		del 1
		add -rjX - 0.3, s * rjW / 2 - 0.3, 0
		block 0.6, 0.6, 0.05
		del 1
		material "mc_body"
		add -rjX - 0.15, min(0, s * rjW / 2), upZ + 0.2
		block 0.3, rjW / 2, 0.3
		del 1
	next s
	! オーガ
	xA = ldX + auOff
	material "mc_dark"
	add ldX + ldDia / 2, -0.3, auZ + auH * 0.4
	block max(0.1, auOff - auW / 2 - ldDia / 2 + 0.05), 0.6, 0.6
	del 1
	material "mc_drum"
	add xA - auW / 2, yAu0 - auD / 2 - 0.15, auZ
	block auW, -2 * yAu0 + auD + 0.3, auH
	del 1
	for i = 1 to nAu
		yA = yAu0 + (i - 1) * auP
		material "mc_steel"
		add xA, yA, auZ - auL
		cylind auL, max(0.04, auD * 0.18)
		del 1
		nF = max(2, int(auL / max(0.3, auD)))
		for k = 0 to nF - 1
			add xA, yA, auZ - auL + (k + 0.5) * auL / nF
			cylind 0.03, auD / 2
			del 1
		next k
		material "mc_dark"
		add xA, yA, auZ - auL - 0.4 * auD
		cone 0.4 * auD, 0.03, auD / 2, 90, 90
		del 1
	next i
	return

"earthdrill":
	! アースドリル: テレスコブーム（3段の箱。根元 pvX, pvH・長さ tbL・起伏 tbA）・頂部のシーブ・ケリードライブとフレーム（kdZ）・
	! ケリーバ（径 kyD。バケットの上から頂部の下まで）・ドリリングバケット（径 auD・高さ bkH・下端は地面から bkD 下）
	material "mc_steel"
	add pvX - 0.4, -0.5, upZ
	block 0.8, 1.0, pvH - upZ
	del 1
	material "mc_body"
	for i = 0 to 2
		f0 = 0.3 * i
		f1 = min(1, f0 + 0.42)
		bwq = 0.9 - 0.15 * i
		bhq = bwq
		x0q = pvX + f0 * tbL * cos(tbA)
		z0q = pvH + f0 * tbL * sin(tbA)
		x1q = pvX + f1 * tbL * cos(tbA)
		z1q = pvH + f1 * tbL * sin(tbA)
		gosub "bar"
	next i
	material "mc_dark"
	add tbX - 0.5, -0.6, tbZ - 0.4
	block 1.0, 1.2, 0.8
	del 1
	! ケリードライブ（上部の前からのフレーム）
	material "mc_body"
	add upF - 0.2, -0.4, min(kdZ, upZ + 0.3)
	block max(0.2, kdR - 0.9 - upF + 0.2), 0.8, 0.5
	del 1
	material "mc_steel"
	add kdR - 0.9, -0.9, kdZ
	block 1.8, 1.8, 1.0
	del 1
	! ケリーバとワイヤ
	zB = -bkD
	material "mc_rod"
	kz0 = zB + bkH
	kz1 = tbZ - 0.8
	add kdR, 0, kz0
	cylind max(0.1, kz1 - kz0), kyD / 2
	del 1
	! バケット（底は浅い円錐）
	material "mc_dark"
	add kdR, 0, zB + 0.25
	cylind max(0.1, bkH - 0.25), auD / 2
	del 1
	add kdR, 0, zB
	cone 0.25, auD * 0.3, auD / 2, 90, 90
	del 1
	return

"rotator":
	! 全周回転機（据置）: 反力ブラケット（十字）・本体の下の枠（通り穴 rtD を残す4つの箱）・チャック（押抜ストローク rtS で上下）・
	! 手すり・水平ジャッキ4本（底 φ500）・ケーシング（径 csD、本体の上 csH）・油圧ユニット（台 0.3）とホース
	hR = rtD / 2
	material "mc_steel"
	add -brL / 2, -0.3, 0
	block brL, 0.6, 0.5
	del 1
	add -0.3, -brW / 2, 0
	block 0.6, brW, 0.5
	del 1
	material "mc_body"
	zF = 0.2
	hF = zDk * 0.5
	add -rtL / 2, -rtW / 2, zF
	block rtL / 2 - hR, rtW, hF
	del 1
	add hR, -rtW / 2, zF
	block rtL / 2 - hR, rtW, hF
	del 1
	add -hR, -rtW / 2, zF
	block 2 * hR, rtW / 2 - hR, hF
	del 1
	add -hR, hR, zF
	block 2 * hR, rtW / 2 - hR, hF
	del 1
	! チャック（回転部）とデッキ
	material "mc_drum"
	add 0, 0, zF + hF + rtS
	cylind max(0.2, zDk - zF - hF), hR + 0.3
	del 1
	material "mc_steel"
	for s = -1 to 1 step 2
		for t = -1 to 1 step 2
			add s * (rtL / 2 - 0.05) - 0.025, t * (rtW / 2 - 0.05) - 0.025, zDk + rtS
			block 0.05, 0.05, rtH - zDk
			del 1
			add s * (rtL / 2 - 0.35), t * (rtW / 2 - 0.35), 0
			cylind zF + 0.3, 0.25
			del 1
		next t
		add -rtL / 2, s * (rtW / 2 - 0.05) - 0.025, rtH + rtS - 0.05
		block rtL, 0.05, 0.05
		del 1
		add s * (rtL / 2 - 0.05) - 0.025, -rtW / 2, rtH + rtS - 0.05
		block 0.05, rtW, 0.05
		del 1
	next s
	! ケーシング
	material "mc_rod"
	add 0, 0, 0
	cylind rtH + rtS + csH, csD / 2
	del 1
	! 油圧ユニット
	material "mc_dark"
	add puX - min(4.2, puL) / 2, puY - puW / 2 + 0.1, 0
	block min(4.2, puL), puW - 0.2, 0.3
	del 1
	material "mc_body"
	add puX - puL / 2, puY - puW / 2, 0.3
	block puL, puW, max(0.2, puH - 0.3)
	del 1
	material "mc_dark"
	x0q = puX + puL / 2
	y0q = puY
	z0q = 1.0
	x1q = -rtL / 2
	y1q = 0
	z1q = zDk * 0.5
	rq = 0.05
	gosub "seg3"
	return

"piler":
	! 圧入機: 後ろの完成杭（U形を交互に。地面の上 0.5m まで）をクランプでつかむ本体（サドル・スライドベース・リーダーマスト）と、
	! チャックの杭（チャック投入高 piC＋上がり piS、天端はその上 piT）・パワーユニット（クローラの上の箱）とホース
	material "mc_steel"
	for i = 1 to piN
		xP = -i * piP
		sg = 1 - 2 * (i mod 2)
		add xP - piP / 2, sg * 0.15 - 0.006, -2.0
		block piP, 0.012, 2.5
		del 1
	next i
	! チャックの杭
	zC = piC + piS
	add -piP / 2, -0.15 - 0.006, zC + piT - 12.0
	block piP, 0.012, 12.0
	del 1
	! 本体: クランプ（完成杭の上）・サドル・リーダーマスト・チャック
	material "mc_body"
	xB = -piL + 0.35
	add xB, -piW / 2, 0.5
	block piL - 0.6, piW, piC * 0.45
	del 1
	material "mc_dark"
	for i = 1 to min(3, piN)
		add -i * piP - 0.15, -piW * 0.3, 0.2
		block 0.3, piW * 0.6, 0.35
		del 1
	next i
	material "mc_body"
	add -0.75, -piW * 0.4, 0.5 + piC * 0.45
	block 0.6, piW * 0.8, max(0.3, piH - 0.5 - piC * 0.45)
	del 1
	material "mc_drum"
	add -0.25, -piW * 0.45, zC
	block 0.6, piW * 0.9, 0.45
	del 1
	! パワーユニット
	material "mc_dark"
	add puX - puL * 0.3, puY - puW / 2, 0
	block puL * 0.6, puW, 0.545
	del 1
	material "mc_body"
	add puX - puL / 2, puY - puW / 2, 0.545
	block puL, puW, max(0.2, puH - 0.545)
	del 1
	material "mc_dark"
	x0q = puX + puL / 2
	y0q = puY
	z0q = 1.0
	x1q = xB
	y1q = 0
	z1q = 0.8
	rq = 0.04
	gosub "seg3"
	return

"lattice":
	! ラチスブーム（主材4本・斜材は4面）・根元と先・ガントリとペンダント・ワイヤとフック
	! ブームの根元の耳 2 枚とピン（公表 ブームフートピン）
	material "mc_steel"
	for s = -1 to 1 step 2
		add pvX - 0.55, s * lbW * 0.42 - 0.03, upZ
		block 0.9, 0.06, pvH - upZ + 0.16
		del 1
	next s
	add pvX, -lbW * 0.46, pvH
	rotx -90
	cylind lbW * 0.92, 0.07
	del 2
	! ラチスブーム（下部は根元が絞られ、上部は先が絞られる。主弦材 4 本・斜材は 4 面の W 形。コベルコ 7070G-2 の図）
	material "mc_body"
	add pvX, 0, pvH
	roty -lbA
	resol 6
	lbD = lbW * 1.1
	lLo = min(lbL * 0.4, 3.55 * lbW)
	lUp = min(lbL * 0.35, 3.0 * lbW)
	rcq = lbW * 0.031 * (1 + 0.9 * lbFat)
	if lbRW then material "mc_red"
	! 主弦材（節の点を結ぶ）
	for sy = -1 to 1 step 2
		for sz = -1 to 1 step 2
			for k = 0 to 2
				xq = 0
				if k = 1 then xq = lLo
				if k = 2 then xq = lbL - lUp
				gosub "lbHalf"
				x0q = xq
				y0q = sy * hyq
				z0q = sz * hzq
				xq = lLo
				if k = 1 then xq = lbL - lUp
				if k = 2 then xq = lbL
				gosub "lbHalf"
				x1q = xq
				y1q = sy * hyq
				z1q = sz * hzq
				rq = rcq
				gosub "seg3"
			next k
		next sz
	next sy
	! 斜材（節 約 1.4m。側面も上下の面も W 形）
	nP = max(4, int(lbL / (lbW * 0.95)))
	pP = lbL / nP
	rq = lbW * 0.02 * (1 + 0.9 * lbFat)
	for i = 0 to nP - 1
		sg = 1 - 2 * (i mod 2)
		if lbRW then
			if int(i / 3) mod 2 = 0 then
				material "mc_red"
			else
				material "mc_wht"
			endif
		endif
		xq = i * pP
		gosub "lbHalf"
		x0q = xq
		hA = hyq
		zA = hzq
		xq = (i + 1) * pP
		gosub "lbHalf"
		x1q = xq
		hBq = hyq
		zBq = hzq
		for sz = -1 to 1 step 2
			y0q = -sg * hA
			y1q = sg * hBq
			z0q = sz * zA
			z1q = sz * zBq
			gosub "seg3"
		next sz
		for sy = -1 to 1 step 2
			y0q = sy * hA
			y1q = sy * hBq
			z0q = -sg * zA
			z1q = sg * zBq
			gosub "seg3"
		next sy
	next i
	! 継ぎ（6.1m ごとの枠と四隅の耳）
	resol 12
	nJn = int((lbL - lLo - lUp) / 6.1)
	for k = 0 to nJn + 1
		xq = lLo + k * 6.1
		if k > nJn then xq = lbL - lUp
		gosub "lbHalf"
		xJ = xq
		hA = hyq
		zA = hzq
		rq = rcq * 0.8
		if lbRW then material "mc_red"
		for sy = -1 to 1 step 2
			x0q = xJ
			x1q = xJ
			y0q = sy * hA
			y1q = sy * hA
			z0q = -zA
			z1q = zA
			gosub "seg3"
		next sy
		for sz = -1 to 1 step 2
			x0q = xJ
			x1q = xJ
			y0q = -hA
			y1q = hA
			z0q = sz * zA
			z1q = sz * zA
			gosub "seg3"
			material "mc_steel"
			for sy = -1 to 1 step 2
				add xJ - 0.12, sy * hA - 0.05, sz * zA - 0.05
				block 0.24, 0.1, 0.1
				del 1
			next sy
			material "mc_body"
			if lbRW then material "mc_red"
		next sz
		y0q = -hA
		y1q = hA
		z0q = -zA
		z1q = zA
		gosub "seg3"
	next k
	! 根元の板の箱
	material "mc_body"
	add 0, -lbW * 0.42, -0.22
	block 1.1, lbW * 0.84, 0.44
	del 1
	! ブームの先（側板・主シーブ・補助シーブの腕）
	material "mc_steel"
	for s = -1 to 1 step 2
		add lbL - 0.5, s * lbW * 0.26 - 0.02, -0.3
		block 1.05, 0.04, 0.6
		del 1
	next s
	nSh = max(1, min(5, int(lbW * 3)))
	for k = 1 to nSh
		add lbL + 0.4, (k - (nSh + 1) / 2) * 0.095 - 0.03, 0
		rotx -90
		cylind 0.06, 0.45
		del 2
	next k
	if jbL < 0.01 then
		for s = -1 to 1 step 2
			x0q = lbL
			y0q = s * lbW * 0.2
			z0q = 0.25
			x1q = lbL + 1.2
			y1q = s * 0.06
			z1q = 0.55
			rq = 0.035
			gosub "seg3"
		next s
		add lbL + 1.2, -0.03, 0.55
		rotx -90
		cylind 0.06, 0.22
		del 2
	endif
	del 2
	! バックストップ 2 本（ばね入りの管）
	xq = 3.2
	gosub "lbHalf"
	xS = pvX + 3.2 * cos(lbA) - hzq * sin(lbA)
	zS = pvH + 3.2 * sin(lbA) + hzq * cos(lbA)
	for sy = -1 to 1 step 2
		x0q = pvX - 0.85
		y0q = sy * 0.42
		z0q = upH
		x1q = x0q + (xS - x0q) * 0.62
		y1q = sy * 0.42
		z1q = z0q + (zS - z0q) * 0.62
		rq = 0.07
		material "mc_steel"
		gosub "seg3"
		x0q = x1q
		z0q = z1q
		x1q = xS
		y1q = sy * hyq
		z1q = zS
		rq = 0.04
		material "mc_rim"
		gosub "seg3"
	next sy
	if jbL > 0.01 then
		! ジブ（ブームの先から。先へ細くなるラチス）とジブストラット・ガイライン
		material "mc_body"
		add lbX, 0, lbZ
		roty -(lbA - jbO)
		resol 6
		rq = 0.03
		for sy = -1 to 1 step 2
			for sz = -1 to 1 step 2
				x0q = 0
				y0q = sy * jbW / 2
				z0q = sz * jbW / 2
				x1q = jbL
				y1q = sy * jbW / 4
				z1q = sz * jbW / 4
				gosub "seg3"
			next sz
		next sy
		nP = max(2, int(jbL / jbW))
		rq = 0.016
		for i = 0 to nP - 1
			sg = 1 - 2 * (i mod 2)
			wA = jbW * (1 - 0.5 * i / nP) / 2
			wB = jbW * (1 - 0.5 * (i + 1) / nP) / 2
			x0q = i * jbL / nP
			x1q = (i + 1) * jbL / nP
			for sz = -1 to 1 step 2
				y0q = -sg * wA
				y1q = sg * wB
				z0q = sz * wA
				z1q = sz * wB
				gosub "seg3"
			next sz
		next i
		rq = 0.02
		x0q = 0
		y0q = 0
		z0q = jbW / 2
		x1q = 0.3
		y1q = 0
		z1q = jbW / 2 + 1.6
		gosub "seg3"
		x0q = 0.3
		z0q = jbW / 2 + 1.6
		x1q = jbL
		z1q = jbW / 4
		gosub "seg3"
		resol 12
		material "mc_steel"
		add jbL - 0.15, -jbW / 4, -jbW / 4
		block 0.3, jbW / 2, jbW / 2
		del 1
		add jbL + 0.15, -0.04, 0
		rotx -90
		cylind 0.08, 0.25
		del 2
		del 2
	endif
	! ガントリ（太い前の脚 1 本・後ろの柱 2 本・頭のシーブ。7070G-2 の図）と、ブライドル・多本掛け・ペンダント
	gX = -gnX
	gZ = gnH - 0.22
	material "mc_body"
	x0q = -1.035 * gnX / 3.16
	y0q = 0
	z0q = upH - 0.05
	x1q = gX
	y1q = 0
	z1q = gZ
	rq = 0.15
	gosub "seg3"
	for s = -1 to 1 step 2
		x0q = gX + 0.03
		y0q = s * 0.55
		z0q = upH - 0.05
		x1q = gX
		y1q = s * 0.2
		z1q = gZ
		rq = 0.07
		gosub "seg3"
	next s
	material "mc_steel"
	add gX, -0.28, gZ
	rotx -90
	cylind 0.56, 0.25
	del 2
	dG = sqr((lbX - gX) ^ 2 + (lbZ - gZ) ^ 2)
	tB = min(0.8, (dG * 0.2 + 1.5) / max(1, dG))
	xBr = gX + (lbX - gX) * tB
	zBr = gZ + (lbZ - gZ) * tB
	aBr = atn((lbZ - gZ) / max(0.01, lbX - gX))
	add xBr, 0, zBr
	roty -aBr
	add -0.3, -0.35, -0.12
	block 0.6, 0.7, 0.24
	del 3
	for k = -2 to 2
		x0q = gX
		y0q = k * 0.06
		z0q = gZ + 0.15
		x1q = xBr
		y1q = k * 0.1
		z1q = zBr
		rq = 0.012
		gosub "seg3"
	next k
	for s = -1 to 1 step 2
		x0q = xBr
		y0q = s * 0.3
		z0q = zBr
		x1q = lbX
		y1q = s * lbW * 0.2
		z1q = lbZ + 0.1
		rq = 0.02
		gosub "seg3"
	next s
	! ワイヤとフック
	material "mc_steel"
	for s = -1 to 1 step 2
		add hkX + s * 0.12, 0, tpZ - hkD + 0.8
		cylind hkD - 0.8, 0.015
		del 1
	next s
	! フック（仕様書の全高 hkH・幅 hkW・厚み hkT。上の 7 割がブロック、下がフック）
	material "mc_hook"
	for s = -1 to 1 step 2
		add hkX, s * hkT * 0.42 - 0.02, tpZ - hkD + hkH * 0.7 - hkW / 2
		rotx -90
		cylind 0.04, hkW / 2
		del 2
	next s
	material "mc_steel"
	add hkX, -hkT * 0.4, tpZ - hkD + hkH * 0.7 - hkW / 2
	rotx -90
	cylind hkT * 0.8, hkW * 0.42
	del 2
	add hkX, 0, tpZ - hkD - hkH * 0.12
	cylind hkH * 0.32, 0.07
	del 1
	material "mc_hook"
	add hkX, 0.04, tpZ - hkD - hkH * 0.3
	mul hkH * 0.9, 1, hkH * 0.9
	rotx 90
	prism 15, 0.08, -0.04, 0.45, 0.04, 0.45, 0.05, 0.32, 0.17, 0.2, 0.19, 0.09, 0.12, 0.01, 0, 0, -0.13, 0.05, -0.19, 0.14, -0.13, 0.2, -0.1, 0.13, -0.03, 0.08, 0.07, 0.09, 0.1, 0.15, -0.03, 0.26
	del 3
	if vbK = 1 then
		! バイブロ（ハンガー・起振機・チャック）と杭（vbP）
		zV = tpZ - hkD - hkH * 0.3 - vbH
		material "mc_drum"
		add hkX - vbW / 2, -vbT / 2, zV + vbH * 0.25
		block vbW, vbT, vbH * 0.75
		del 1
		material "mc_dark"
		add hkX - vbW * 0.3, -vbT * 0.4, zV
		block vbW * 0.6, vbT * 0.8, vbH * 0.25
		del 1
		material "mc_steel"
		add hkX - 0.2, -0.006, zV - vbP + 0.1
		block 0.4, 0.012, vbP
		del 1
	endif
	return

"truck":
	! トラックの車体: フレーム・運転室（前窓は傾ける）・タイヤとホイール・フェンダー・バンパー・サイドガード・燃料タンク・ミラー
	material "mc_dark"
	for s = -1 to 1 step 2
		add xR + 0.15, s * 0.45 - 0.05, frZ - 0.28
		block carL - 0.45, 0.1, 0.28
		del 1
	next s
	cZ0 = whR * 2 - 0.1
	cL = min(2.3, carL * 0.28)
	material "mc_body"
	add xF - cL, carW / 2, cZ0
	rotx 90
	prism 5, carW, 0, 0, cL, 0, cL, (cabH - cZ0) * 0.45, cL - 0.3, cabH - cZ0, 0, cabH - cZ0
	del 2
	material "mc_glass"
	x0q = xF + 0.012
	z0q = cZ0 + (cabH - cZ0) * 0.47
	x1q = xF - 0.3 + 0.012
	z1q = cabH - 0.06
	bwq = carW - 0.25
	bhq = 0.01
	gosub "bar"
	for s = -1 to 1 step 2
		add xF - cL + 0.25, s * (carW / 2 + 0.003) - 0.003, cZ0 + (cabH - cZ0) * 0.48
		block cL - 0.75, 0.006, (cabH - cZ0) * 0.4
		del 1
	next s
	! バンパー（運転室の下端に付ける）
	material "mc_dark"
	add xF - 0.12, -carW / 2 + 0.05, cZ0 - 0.3
	block 0.16, carW - 0.1, 0.35
	del 1
	for s = -1 to 1 step 2
		add xF - 0.2, s * (carW / 2 + 0.12) - 0.04, cabH - 0.7
		block 0.04, 0.08, 0.35
		del 1
	next s
	! ヘッドライト・テールランプ・運転室の昇降ステップ・泥よけ
	material "mc_head"
	for s = -1 to 1 step 2
		add xF + 0.041, s * (carW / 2 - 0.34) - 0.12, cZ0 - 0.2
		block 0.008, 0.24, 0.13
		del 1
	next s
	material "mc_tail"
	for s = -1 to 1 step 2
		add xR + 0.02, s * (carW / 2 - 0.3) - 0.11, frZ - 0.2
		block 0.012, 0.22, 0.09
		del 1
	next s
	material "mc_steel"
	for s = -1 to 1 step 2
		for k = 0 to 1
			add axF - whR - 0.5, s * (carW / 2 - 0.02) - 0.08 * (s > 0), 0.42 + k * 0.32
			block 0.42, 0.08, 0.025
			del 1
		next k
	next s
	material "mc_dark"
	for s = -1 to 1 step 2
		add axR2 - whR - 0.12, s * (carW / 2 - 0.03) - (s > 0) * (whW + 0.05), 0.2
		block 0.012, whW + 0.05, 0.5
		del 1
	next s
	! タイヤ（前は1本・後ろはダブル）
	for i = 1 to nAx
		axX = axs[i]
		for s = -1 to 1 step 2
			! 円柱は rotx 90 で -y へ伸びる。ホイールは外の面に 0.015 出す
			yT = s * (carW / 2 - 0.03) + (s < 0) * whW
			material "mc_tire"
			add axX, yT, whR
			rotx 90
			cylind whW, whR
			del 2
			material "mc_rim"
			add axX, yT + (s > 0) * 0.015, whR
			rotx 90
			cylind whW + 0.015, whR * 0.55
			del 2
			material "mc_body"
			add axX - whR - 0.08, s * (carW / 2 - 0.02) - (s + 1) / 2 * (whW + 0.04), 2 * whR + 0.04
			block 2 * whR + 0.16, whW + 0.04, 0.05
			del 1
		next s
	next i
	! サイドガード（前の車軸と後ろの車軸の間）と燃料タンク
	material "mc_steel"
	for s = -1 to 1 step 2
		for k = 0 to 1
			add axR1 + whR + 0.15, s * (carW / 2 - 0.12) - 0.02, 0.45 + k * 0.25
			block max(0.2, axs[max(1, min(2, nFr))] - axR1 - 2 * whR - 0.3), 0.04, 0.06
			del 1
		next k
	next s
	add axF - whR - 0.25, carW / 2 - 0.35, 0.7
	rotx 90
	cylind 0.6, 0.25
	del 2
	return

"outrig":
	! アウトリガ（組ごとに両側。横の箱・ジャッキ・敷板。3組めは張出スパン 0 なら無し）
	if otOn then
		for s = -1 to 1 step 2
			for e = 1 to nJk
				jX = ox[e]
				jY = max(0.35, oy[e])
				material "mc_body"
				add jX - 0.15, min(s * 0.3, s * jY), frZ - 0.45
				block 0.3, abs(jY - 0.3), 0.25
				del 1
				material "mc_dark"
				add jX, s * jY, 0.08
				cylind frZ - 0.4, 0.09
				del 1
				material "mc_steel"
				add jX - 0.3, s * jY - 0.3, 0
				block 0.6, 0.6, 0.08
				del 1
			next e
		next s
	endif
	return

"pumpbody":
	! ポンプ車: 荷台の機器箱・ホッパ（後ろ）・旋回台
	material "mc_body"
	add xR + 1.2, -carW / 2 + 0.15, frZ
	block max(0.5, -0.8 - xR - 1.2), carW - 0.3, 0.9
	del 1
	material "mc_dark"
	add xR, -0.6, frZ - 0.2
	block 1.0, 1.2, 0.75
	del 1
	material "mc_steel"
	add 0, 0, frZ
	cylind tuH - frZ - 0.3, 0.55
	del 1
	return

"pumpboom":
	! 折り曲げのブーム（段ごとに細く）・関節・輸送管・先端ホース
	material "mc_body"
	add -0.5, -0.45, tuH - 0.6
	block 1.0, 0.9, 0.6
	del 1
	px = 0
	pz = tuH
	for i = 1 to nSc
		qx = px + sl[i] * cos(sa[i])
		qz = pz + sl[i] * sin(sa[i])
		material "mc_body"
		x0q = px
		z0q = pz
		x1q = qx
		z1q = qz
		bwq = 0.38 - 0.05 * i
		bhq = 0.5 - 0.06 * i
		gosub "bar"
		material "mc_steel"
		add qx, bwq / 2 + 0.04, qz
		rotx 90
		cylind bwq + 0.08, bhq * 0.45
		del 2
		material "mc_rod"
		rq = 0.06
		x0q = px - (bhq / 2 + 0.1) * sin(sa[i])
		y0q = -bwq / 2 - 0.1
		z0q = pz + (bhq / 2 + 0.1) * cos(sa[i])
		x1q = qx - (bhq / 2 + 0.1) * sin(sa[i])
		y1q = y0q
		z1q = qz + (bhq / 2 + 0.1) * cos(sa[i])
		gosub "seg3"
		px = qx
		pz = qz
	next i
	material "mc_dark"
	add pmX, 0, max(0.3, pmZ - 3.0)
	cylind min(3.0, pmZ - 0.3), 0.065
	del 1
	return

"mixer":
	! 生コン車: ドラム（前の短い円錐・後ろの長い円錐）・帯・ホッパ・シュート・水タンク・後ろの足場
	zD = frZ + drD / 2 + 0.1
	dX0 = xF - min(2.3, carL * 0.28) - 0.35
	material "mc_drum"
	add dX0, 0, zD
	roty drA - 90
	cone drL * 0.3, drD * 0.3, drD / 2, 90, 90
	addz drL * 0.3
	cone drL * 0.7, drD / 2, drD * 0.22, 90, 90
	material "mc_body"
	for k = 1 to 3
		zk = k * drL * 0.2
		addz zk - 0.04
		cylind 0.08, drD / 2 + (drD * 0.22 - drD / 2) * zk / (drL * 0.7) + 0.02
		del 1
	next k
	del 3
	dX1 = dX0 - drL * cos(drA)
	dZ1 = zD + drL * sin(drA)
	material "mc_steel"
	add dX1 - 0.3, 0, dZ1 + 0.1
	cone 0.6, 0.15, 0.45, 90, 90
	del 1
	x0q = dX1 - 0.2
	z0q = dZ1 - 0.4
	x1q = xR - 0.5
	z1q = frZ + 0.2
	bwq = 0.4
	bhq = 0.05
	gosub "bar"
	add dX0 + 0.1, -0.35, frZ
	cylind 0.7, 0.3
	del 1
	add xR, -0.4, frZ
	block 0.3, 0.8, 0.05
	del 1
	return

"dump":
	! ダンプ: 荷台（床・あおり・鳥居）を後ろのヒンジで bedA だけ上げる・ホイストシリンダ
	hX = xR + 0.1
	hZ = frZ + 0.05
	add hX, 0, hZ
	roty -bedA
	material "mc_bed"
	add 0, -bedW / 2, 0
	block bedL, bedW, 0.12
	block bedL, 0.05, bedH + 0.12
	addy bedW - 0.05
	block bedL, 0.05, bedH + 0.12
	del 2
	add bedL - 0.08, -bedW / 2, 0
	block 0.08, bedW, bedH + 0.35
	addz bedH + 0.3
	block 0.45, bedW, 0.05
	del 2
	add 0, -bedW / 2, 0
	block 0.06, bedW, bedH + 0.12
	del 1
	material "mc_dark"
	for k = 1 to 4
		add k * bedL / 5, -bedW / 2 - 0.04, 0.12
		block 0.06, 0.04, bedH
		addy bedW + 0.04
		block 0.06, 0.04, bedH
		del 2
	next k
	del 2
	if bedA > 0.5 then
		crq = 0.09
		cx0 = hX + bedL * 0.6
		cy0 = 0
		cz0 = frZ - 0.2
		cx1 = hX + bedL * 0.62 * cos(bedA)
		cy1 = 0
		cz1 = hZ + bedL * 0.62 * sin(bedA)
		gosub "cyl2"
	endif
	return

"aerial":
	! 高所作業車: 旋回台・伸縮ブーム（段ごとに細く）・起伏シリンダ・バスケット（床・手すり）
	material "mc_steel"
	add 0, 0, frZ
	cylind tuH - frZ - 0.4, 0.45
	del 1
	material "mc_body"
	add -0.8, -0.5, tuH - 0.45
	block 1.3, 1.0, 0.5
	del 1
	nAb = max(2, min(5, nSec))
	for i = 1 to nAb
		x0q = -0.4 + (i - 1) * abL / nAb * 0.9 * cos(abA)
		z0q = tuH + (i - 1) * abL / nAb * 0.9 * sin(abA)
		x1q = -0.4 + min(abL, i * abL / nAb + 0.3) * cos(abA)
		z1q = tuH + min(abL, i * abL / nAb + 0.3) * sin(abA)
		bwq = 0.36 - 0.05 * i
		bhq = 0.42 - 0.05 * i
		gosub "bar"
	next i
	crq = 0.08
	cx0 = 0.4
	cy0 = 0
	cz0 = tuH - 0.3
	cx1 = -0.4 + abL * 0.35 * cos(abA) + 0.15 * sin(abA)
	cy1 = 0
	cz1 = tuH + abL * 0.35 * sin(abA) - 0.15 * cos(abA)
	gosub "cyl2"
	material "mc_body"
	add abX, -pfL / 2, abZ - 1.2
	block pfW, pfL, 0.1
	del 1
	rx0 = abX
	ry0 = -pfL / 2
	rlx = pfW
	rly = pfL
	rz0 = abZ - 1.1
	gosub "rail"
	return

"rail":
	! 作業床の手すり（rx0, ry0 から rlx × rly、床 rz0 から上桟 1.0・中桟 0.5・隅の柱）
	material "mc_steel"
	for k = 1 to 2
		add rx0, ry0, rz0 + k * 0.5 - 0.04
		block rlx, 0.04, 0.04
		addy rly - 0.04
		block rlx, 0.04, 0.04
		del 1
		block 0.04, rly, 0.04
		addx rlx - 0.04
		block 0.04, rly, 0.04
		del 2
	next k
	for e = 0 to 1
		for s = 0 to 1
			add rx0 + e * (rlx - 0.04), ry0 + s * (rly - 0.04), rz0
			block 0.04, 0.04, 1.0
			del 1
		next s
	next e
	return

"scissor":
	! 自走式の垂直昇降（シザース）: 車台・車輪・X 字の腕（3段）・作業床と手すり
	material "mc_body"
	add xR, -carW / 2, 0.08
	block carL, carW, 0.42
	del 1
	material "mc_tire"
	for e = -1 to 1 step 2
		for s = -1 to 1 step 2
			add e * (carL / 2 - 0.3), s * (carW / 2 - 0.02) + (s < 0) * 0.12, 0.15
			rotx 90
			cylind 0.12, 0.15
			del 2
		next s
	next e
	zA = 0.5
	zB = max(zA + 0.3, pfH - 0.15)
	hS = (zB - zA) / 3
	xa = -carL / 2 + 0.2
	xb = carL / 2 - 0.2
	material "mc_cw"
	bwq = 0.06
	bhq = 0.08
	for s = -1 to 1 step 2
		for k = 0 to 2
			add 0, s * (carW / 2 - 0.08), 0
			x0q = xa
			z0q = zA + k * hS
			x1q = xb
			z1q = zA + (k + 1) * hS
			gosub "bar"
			x0q = xb
			x1q = xa
			gosub "bar"
			del 1
		next k
	next s
	material "mc_body"
	add -pfL / 2, -pfW / 2, zB
	block pfL, pfW, 0.15
	del 1
	rx0 = -pfL / 2
	ry0 = -pfW / 2
	rlx = pfL
	rly = pfW
	rz0 = zB + 0.15
	gosub "rail"
	return
"""


CRANE_VL = """! クローラクレーン: 平面のフックを引いたら、ブームの長さはそのままで起伏角を解き、横に引いた分は旋回にする（ジブ付きも）
if mcKind = 2 then
	mq = GLOB_MODPAR_NAME
	rF = -1
	aF = slew
	if mq = "lbR" then rF = lbR
	if (mq = "hfX" or mq = "hfY") and abs(hfX) + abs(hfY) > 0.1 then
		rF = sqr(hfX * hfX + hfY * hfY)
		if abs(hfX) < 0.0001 then
			aF = 90 + 180 * (hfY < 0)
		else
			aF = atn(hfY / hfX) + 180 * (hfX < 0)
			if aF < 0 then aF = aF + 360
		endif
	endif
	if rF >= 0 then
		aL = 0
		aH = 85
		for k = 1 to 24
			aM = (aL + aH) / 2
			rM = pvX + lbL * cos(aM) + 0.4
			if jbL > 0.01 then rM = rM + jbL * cos(aM - jbO)
			if rM > rF then
				aL = aM
			else
				aH = aM
			endif
		next k
		aM = (aL + aH) / 2
		rM = pvX + lbL * cos(aM) + 0.4
		if jbL > 0.01 then rM = rM + jbL * cos(aM - jbO)
		parameters lbA = aM, slew = aF, lbR = rM, hfX = rM * cos(aF), hfY = rM * sin(aF)
	else
		if abs(lbR - hkX) > 0.001 then parameters lbR = hkX
		if abs(hfX - hkX * cos(slew)) + abs(hfY - hkX * sin(slew)) > 0.001 then parameters hfX = hkX * cos(slew), hfY = hkX * sin(slew)
	endif
endif
"""


def model_vl() -> str:
    """機種の一覧（mcModel）と、選んだときに寸法・種類・注記を書き込む（GLOB_MODPAR_NAME。1行は 522 バイトまで）."""
    from ashiba.machine import MACHINES, Placed, model_code, part_params

    out = ["! 機種を選ぶと、src/ashiba/machine.py の寸法を書き込む（gen_machine_gdl.py が書き出す）"]
    # 一覧は配列で渡す（1行に全部並べると 408 バイトで部品が止まった。218 バイトは通った）
    out += ["dim mdV[], mdS[]", "mdV[1] = 0", 'mdS[1] = "手入力"']
    for i, (k, m) in enumerate(MACHINES.items(), 2):
        out += [f"mdV[{i}] = {model_code(k)}", f'mdS[{i}] = "{m.name}"']
    out.append('values{2} "mcModel" mdV, mdS')
    out.append('if GLOB_MODPAR_NAME = "mcModel" then')
    for k, m in MACHINES.items():
        ps = {a: b for a, b in part_params(Placed("", m)).items() if a not in ("mcName", "mcNote", "slew", "mcModel")}
        out.append(f"\tif mcModel = {model_code(k)} then")
        out.append(f'\t\tparameters mcName = "{m.name}", mcNote = "{part_params(Placed("", m))["mcNote"]}"')
        pairs = [f"{a} = {b:g}" for a, b in ps.items() if not isinstance(b, str)]
        for i in range(0, len(pairs), 8):
            out.append("\t\tparameters " + ", ".join(pairs[i:i + 8]))
        out += [f'\t\tparameters {a} = "{b}"' for a, b in ps.items() if isinstance(b, str)]
        out.append("\tendif")
    out.append("endif")
    return "\n".join(out) + "\n"


def main() -> int:
    (OUT / "scripts").mkdir(parents=True, exist_ok=True)
    (OUT / "paramlist.xml").write_text(paramlist(), encoding="utf-8")
    (OUT / "scripts" / "1d.gdl").write_text(SCRIPT_1D, encoding="utf-8")
    (OUT / "scripts" / "vl.gdl").write_text(SCRIPT_VL + CRANE_VL + gdl_radii.vl("mcKind = 2") + model_vl(), encoding="utf-8")
    (OUT / "scripts" / "2d.gdl").write_text(SCRIPT_2D, encoding="utf-8")
    (OUT / "scripts" / "3d.gdl").write_text(SCRIPT_3D, encoding="utf-8")
    (OUT / "scripts" / "ui.gdl").write_text(gdl_radii.ui("mcKind = 2"), encoding="utf-8")
    (OUT / "libpartdata.xml").write_text(
        "﻿<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<LibpartData Owner=\"1196638531\" Signature=\"1196644685\" Version=\"44\">\n"
        f"\t<Identification>\n\t\t<MainGUID>{MAIN_GUID}</MainGUID>\n\t\t<IsPlaceable>true</IsPlaceable>\n"
        "\t\t<IsArchivable>false</IsArchivable>\n\t\t<MigrationValue>Normal</MigrationValue>\n\t\t<IsTemplate>false</IsTemplate>\n"
        "\t</Identification>\n\t<Ancestry SectVersion=\"1\" SectionFlags=\"0\" SubIdent=\"0\"/>\n"
        "\t<CalledMacros SectVersion=\"2\" SectionFlags=\"0\" SubIdent=\"0\"/>\n"
        "\t<Script_3D SectVersion=\"20\" SectionFlags=\"0\" SubIdent=\"0\"/>\n"
        "\t<Script_2D SectVersion=\"20\" SectionFlags=\"0\" SubIdent=\"0\"/>\n"
        "\t<Script_1D SectVersion=\"20\" SectionFlags=\"0\" SubIdent=\"0\"/>\n"
        "\t<Script_UI SectVersion=\"20\" SectionFlags=\"0\" SubIdent=\"0\"/>\n"
        "\t<Script_VL SectVersion=\"20\" SectionFlags=\"0\" SubIdent=\"0\"/>\n"
        "\t<ParamSection SectVersion=\"27\" SectionFlags=\"0\" SubIdent=\"0\"/>\n</LibpartData>\n", encoding="utf-8")
    (OUT / "ancestry.xml").write_text(
        "﻿<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<Ancestry>\n"
        "\t<MainGUID>F938E33A-329D-4A36-BE3E-85E126820996</MainGUID>\n"
        "\t<MainGUID>103E8D2C-8230-42E1-9597-46F84CCE28C0</MainGUID>\n</Ancestry>\n", encoding="utf-8")
    (OUT / "calledmacros.xml").write_text("﻿<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<CalledMacros>\n</CalledMacros>\n",
                                         encoding="utf-8")
    print(f"ashiba_machine: 書き出しました（{OUT}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
