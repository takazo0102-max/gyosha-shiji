"""重機（パレットの「重機」）.

利用者の指定（2026-11-01）「重機の詳細度もっとあげて　種類も増やして」。

  python3 scripts/machine_run.py --type bh045            # 選んだ線の始め＝旋回中心（車は真ん中）、始めの辺の向き＝車体の前
  python3 scripts/machine_run.py --type bh045            # 線を選ばなければ平面図で 2回クリック（置く所・車体の前の向き。Esc でやめる）
  python3 scripts/machine_run.py --type bh045 --ask       # 同じ種類の機種を窓で選ぶ（パレットのボタン。利用者の指定 2026-11-06）
  python3 scripts/machine_run.py --type pump36 --slew 90  # ブーム・上部を 90° 回す
  python3 scripts/machine_run.py --type cc50 --soil-q 150 --soil 3   # 地盤の許容支持力（短期 kN/m²）と土質（敷鉄板の表）
  python3 scripts/machine_run.py --type bh045 --att d135  # バックホウの先を解体アタッチメント（圧砕機）に（--att none でバケット）
  python3 scripts/machine_run.py --type lb4 --load 6.5,2.9,3.0,20   # 搬入車両に積荷（長さ,幅,高さ m,質量 t。高さ・総重量の判定に）
  python3 scripts/machine_run.py --type tr10 --turn 右     # 平面の旋回軌跡を右へ（--no-track で描かない）
  python3 scripts/machine_run.py --type pump36 --turn-r 9.5   # 最小回転半径 m を入れると軌跡を描く（ポンプ車・高所作業車は公表値が無い）
  python3 scripts/machine_run.py --type cc50 --boom 30.5 --jib 12.2 --jib-off 30 --angle 70 --safety 0.9   # クローラクレーンのブーム・ジブ・起伏角・安全率
  python3 scripts/machine_run.py --track toggle            # 置いた車両の旋回軌跡と場内通路の掃引を入り切り（on・off も。選んでいれば選んだ重機だけ）
  python3 scripts/machine_run.py --list                   # 機種の一覧（--list-att でアタッチメント）
  python3 scripts/machine_run.py --remove                 # 置いた重機を消す（--kinds 13,14 で搬入車両だけ）

部品 ashiba_machine を線1本に1台（src/ashiba/machine.py が機種・寸法・判定）。前に同じ線に置いたものは控え
（ashiba_out/重機.json）で消して置き直す。クリックは Tapir の GetLineFromUser（線を引かなくてよい）。手配表と判定は ashiba_out/重機.md.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ashiba.machine import TRACK_KINDS  # noqa: E402

PART = "ashiba_machine"
RECORD = "重機.json"


def main(argv=None) -> int:
    import argparse

    from ashiba.machine import ATTACHMENTS, KEEP_OUT, MACHINES, SOIL_Q, SOILS, Placed, check, find, part_params, report

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--type", default="bh045", help="機種（" + "・".join(MACHINES) + "）")
    ap.add_argument("--slew", type=float, default=0.0, help="上部・ブームの旋回角（度。車体の前から左回り）")
    ap.add_argument("--soil-q", type=float, default=SOIL_Q, help="地盤の許容支持力（短期 kN/m²。地盤調査の値）")
    ap.add_argument("--soil", type=int, default=1, choices=list(SOILS),
                    help="土質（敷鉄板の表）: " + "・".join(f"{k} {v[0]}" for k, v in SOILS.items()))
    ap.add_argument("--keep-out", type=float, default=KEEP_OUT, help="立入禁止の余裕 m（公的な数値は無く社内の決め）")
    ap.add_argument("--z", type=float, default=None, help="地盤の高さ mm（省くと敷地メッシュ、無ければ 0）")
    ap.add_argument("--att", default=None, help="バックホウ・解体機の先（" + "・".join(ATTACHMENTS) + "・none＝バケット）")
    ap.add_argument("--ask", action="store_true", help="同じ種類の機種を窓で選ぶ")
    ap.add_argument("--boom", type=float, default=0.0, help="クローラクレーンのブーム長さ m（省くと機種の既定）")
    ap.add_argument("--jib", type=float, default=0.0, help="ジブ長さ m（0＝なし）")
    ap.add_argument("--jib-off", dest="jib_off", type=float, default=10.0, help="ジブのオフセット角（10・30）")
    ap.add_argument("--angle", type=float, default=0.0, help="ブームの起伏角 度（省くと機種の既定）")
    ap.add_argument("--safety", type=float, default=0.9, help="定格総荷重に掛ける安全率（0.9＝90%）")
    ap.add_argument("--pick", action="store_true", help="線を選んでいてもクリックで置く")
    ap.add_argument("--list", action="store_true", help="機種の一覧を出す")
    ap.add_argument("--list-att", action="store_true", help="解体アタッチメントの一覧を出す")
    ap.add_argument("--remove", action="store_true", help="置いた重機を消す")
    ap.add_argument("--kinds", default="", help="--remove で消す種類（mcKind をカンマ区切り。空は全部）")
    ap.add_argument("--load", default="", help="搬入車両の積荷 長さ,幅,高さ m,質量 t")
    ap.add_argument("--turn", default="左", choices=("左", "右"), help="車両の平面の旋回軌跡を描く側")
    ap.add_argument("--no-track", action="store_true", help="車両の旋回軌跡を描かない")
    ap.add_argument("--turn-r", dest="turn_r", type=float, default=0.0, help="最小回転半径 m（カタログの値の代わりに）")
    ap.add_argument("--track", default="", choices=("", "on", "off", "toggle"), help="置いた車両の旋回軌跡を入り切りする")
    a = ap.parse_args(argv)
    if a.list:
        for k, m in MACHINES.items():
            print(f"{k:8s} {m.name}（{m.model}）")
        return 0
    if a.list_att:
        for k, v in ATTACHMENTS.items():
            print(f"{k:9s} {v[0]}（長さ {v[2]:g}m・{v[4]:,}kg）")
        return 0
    att = None if a.att is None else ("" if a.att == "none" else a.att)
    if att and att not in ATTACHMENTS:
        print(f"重機: アタッチメントは {'・'.join(ATTACHMENTS)} のどれか（{a.att}）")
        return 1
    try:
        mach = find(a.type)
    except KeyError as e:
        print(e.args[0])
        return 1

    import run_from_archicad as R
    from ashiba.pens import gdl_pens, parse_pens
    from ashiba.tapir_adapter import ArchicadClient, read_ground_model
    from excav_run import _delete_alive, _place
    from guide_lines import selected_guides
    from kakoi_run import chains

    c = ArchicadClient()
    R.OUT_DIR.mkdir(parents=True, exist_ok=True)
    rec_path = R.OUT_DIR / RECORD
    try:
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rec = {}
    if a.remove:
        kinds = {int(k) for k in a.kinds.split(",") if k.strip()}
        gone = {k: v for k, v in rec.items() if not kinds or (v.get("type") in MACHINES and MACHINES[v["type"]].kind in kinds)}
        n = _delete_alive(c, [v["guid"] for v in gone.values()])
        rec_path.write_text(json.dumps({k: v for k, v in rec.items() if k not in gone}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"重機: {n}台を消しました")
        return 0
    if a.track:
        return switch_tracks(c, rec, rec_path, a.track, R)
    if a.ask:
        mach = choose_model(mach, a)
        if mach is None or (mach.kind == 2 and not choose_crane(mach, a)):
            print("重機: やめました（何も置いていません）")
            return 0
    lines = [] if a.pick else [(k, pts) for k, pts, _closed in chains(selected_guides(c)) if len(pts) >= 2]
    if not lines:
        if c.tapir("GetCurrentWindowType", {}).get("currentWindowType") != "FloorPlan":
            print("重機: 平面図の窓を前にしてから押してください（線を選んであれば、その線に置きます）")
            return 1
        front_archicad(c)
        print("  平面図で 置く所 → 車体の前の向き の順にクリック（Esc でやめる）", flush=True)
        pts = pick_line(c)
        if pts is None:
            print("重機: やめました（何も置いていません）")
            return 0
        lines = [(f"クリック:{pts[0][0]:.0f}:{pts[0][1]:.0f}", pts)]
    R.ensure_parts(c)                                    # クリックを待たせないよう、部品の確認はあとで
    part = R.versioned_part_name(PART)
    spec = {**R.SPEC, **R.load_spec_override()}
    pens = gdl_pens(parse_pens(spec.get("pens")), PART)
    from pen_colors import draft_pens_for

    pens.update(draft_pens_for(c, pens.get("penEquip", 1)))      # 外形は太線・細部は細線（scripts/gdl_draft.py）
    ground = None
    if a.z is None:
        gm = read_ground_model(c, [p for _k, pts in lines for p in pts])
        ground = gm.elevation_at if getattr(gm, "points", None) else None
    used = {v.get("name") for v in rec.values()}
    now = 0
    for key, pts in lines:
        name = None
        if key in rec:                               # 同じ線は前の名前のまま置き直す
            old = rec.pop(key)
            name = old.get("name")
            _delete_alive(c, [old["guid"]])
        if not name:
            name = next(f"重機{i}" for i in range(1, 10000) if f"重機{i}" not in used)
        used.add(name)
        (x0, y0), (x1, y1) = pts[0], pts[1]
        ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
        extra = vehicle_extra(mach, a)
        p = check(Placed(name, mach, a.slew, params=extra, att=att if mach.kind in (1, 11) else None), a.soil_q, a.soil, a.keep_out)
        z = a.z if a.z is not None else (ground(x0, y0) if ground else 0.0)
        el = _place(c, part, (x0, y0), z, ang)
        if el is None:
            continue
        try:
            c.set_gdl_parameters(el, {**part_params(p), **pens})
        except Exception as ex:                       # 値が入らない部品は残さない（既定の形のまま残った。2026-11-03）
            _delete_alive(c, [el["elementId"]["guid"]])
            print(f"  {p.name}: パラメータを入れられず置きませんでした（{str(ex)[:120]}）")
            continue
        rec[key] = {"guid": el["elementId"]["guid"], "type": mach.key, "name": p.name, "slew": a.slew, "att": p.att, "params": extra,
                    "at": [x0, y0]}
        now += 1
        bad = sorted({x.item for x in p.checks if x.status not in ("OK", "注意")})
        print(f"  {p.name}: {mach.name}（{mach.model}）" + (f" 要確認 {'・'.join(bad)}" if bad else ""))
    rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    placed = [check(Placed(v["name"], MACHINES[v["type"]], v.get("slew", 0.0), params=v.get("params") or {}, att=v.get("att")),
                    a.soil_q, a.soil, a.keep_out)
              for v in rec.values() if v.get("type") in MACHINES]
    md = R.OUT_DIR / "重機.md"
    md.write_text(report(placed, a.soil_q, a.soil), encoding="utf-8")
    # 今置いた台数を先に（押した人に分かるように）。帳票は置いてある全部の重機
    print(f"重機: {now}台を置きました（置いてある重機は全部で {len(placed)}台・{md}）")
    return 0


PICK_WAIT_S = 900.0                                   # クリックを待つ長さ（Tapir の GetLineFromUser は Archicad の中で待つ）


def choose_model(mach, a) -> object:
    """同じ種類の機種を窓で選ぶ. やめたら None、1機種だけなら窓を出さない."""
    from form_dialog import show_form

    from ashiba.machine import MACHINES

    same = [m for m in MACHINES.values() if m.kind == mach.kind]
    track = mach.kind in TRACK_KINDS
    if len(same) < 2 and not track:
        return mach
    label = lambda m: f"{m.name}（{m.model}）"            # noqa: E731
    fields = [{"key": "model", "label": "機種", "kind": "choice", "options": [label(m) for m in same], "value": label(mach)}]
    if track:
        fields += [{"key": "track", "label": "平面の旋回軌跡", "kind": "choice", "options": ["描く", "描かない"], "value": "描く"},
                   {"key": "turn", "label": "曲がる側", "kind": "choice", "options": ["左", "右"], "value": "左"}]
        if not any(m.turn_r or m.params.get("tnR") for m in same):
            fields.append({"key": "turn_r", "label": "最小回転半径 m（公表値が無いので、入れると軌跡を描く）", "kind": "number", "value": ""})
    res = show_form({
        "title": "重機の機種",
        "intro": "機種を選ぶと、平面図で 1回目に置く所（旋回中心。車は車体の真ん中）、2回目に車体の前の向きをクリックします。"
                 "線を選んであれば、その線に置きます。",
        "fields": fields,
        "buttons": [{"id": "place", "label": "置く"}, {"id": "cancel", "label": "やめる"}]})
    if not res or res.get("button") != "place":
        return None
    v = res.get("values") or {}
    if track and a is not None:
        a.no_track = str(v.get("track")) == "描かない"
        a.turn = "右" if str(v.get("turn")) == "右" else "左"
        try:
            a.turn_r = float(str(v.get("turn_r") or 0).replace(",", ""))
        except ValueError:
            a.turn_r = 0.0
    want = str(v.get("model"))
    return next((m for m in same if label(m) == want), mach)


def crane_options(mach) -> dict:
    """窓の選択肢「ブーム 30.5m」「ブーム 30.5m＋ジブ 12.2m」→ (ブーム, ジブ)."""
    from ashiba.machine import jib_choices

    out = {f"ブーム {b:g}m": (float(b), 0.0) for b in sorted(mach.rated)}
    out.update({f"ブーム {b:g}m＋ジブ {j:g}m": (b, j) for b, j in jib_choices(mach)})
    return out


def choose_crane(mach, a) -> bool:
    """クローラクレーンのブーム・ジブ・起伏角・安全率を窓で選ぶ. やめたら False."""
    from form_dialog import show_form

    opts = crane_options(mach)
    boom = float(mach.params["lbL"])
    now = next((k for k, v in opts.items() if v == (boom, 0.0)), next(iter(opts)))
    res = show_form({
        "title": "クレーンのブームとジブ",
        "intro": f"{mach.name}。定格総荷重は仕様書の表から読み、平面のブームの先に定格と安全率を掛けた荷重、作業の最小半径を描きます。"
                 "平面のフックのホットスポットを引くと、長さはそのままで起伏角が変わります。",
        "fields": [{"key": "boom", "label": "ブームとジブ（ジブは表のある組）", "kind": "choice", "options": list(opts), "value": now},
                   {"key": "off", "label": "ジブのオフセット角", "kind": "choice", "options": ["10", "30"], "value": "10"},
                   {"key": "angle", "label": "ブームの起伏角 度", "kind": "number", "value": f"{float(mach.params['lbA']):g}"},
                   {"key": "safety", "label": "安全率（定格総荷重に掛ける。0.9＝90%）", "kind": "number", "value": f"{a.safety:g}"}],
        "buttons": [{"id": "place", "label": "置く"}, {"id": "cancel", "label": "やめる"}]})
    if not res or res.get("button") != "place":
        return False
    v = res.get("values") or {}
    a.boom, a.jib = opts.get(str(v.get("boom")), (boom, 0.0))
    a.jib_off = 30.0 if str(v.get("off")) == "30" else 10.0
    for key, attr in (("angle", "angle"), ("safety", "safety")):
        try:
            setattr(a, attr, float(str(v.get(key)).replace(",", "")))
        except (TypeError, ValueError):
            pass
    return True


def switch_tracks(c, rec: dict, rec_path: Path, how: str, R) -> int:
    """置いた車両の旋回軌跡（tkOn）と場内通路の掃引（showSw）を入り切りする. 重機を選んでいれば選んだものだけ."""
    from ashiba.machine import MACHINES

    alive = {x["elementId"]["guid"] for x in c.tapir("GetElementsByType", {"elementType": "Object"}).get("elements", [])}
    cars = {k: v for k, v in rec.items() if v.get("guid") in alive and v.get("type") in MACHINES
            and MACHINES[v["type"]].kind in TRACK_KINDS}
    sel = {e["elementId"]["guid"] for e in c.get_selected_elements()}
    picked = {k: v for k, v in cars.items() if v["guid"] in sel}
    targets = picked or cars
    try:
        road = json.loads((R.OUT_DIR / "場内通路.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        road = {}
    roads = [] if picked else [v[0] for v in road.values() if v and v[0] in alive]
    if not targets and not roads:
        print("車両の軌跡: 置いた車両がありません")
        return 1
    if how == "toggle":
        now = any(int((v.get("params") or {}).get("tkOn", 1)) for v in targets.values()) if targets else True
        on = not now
    else:
        on = how == "on"
    for v in targets.values():
        c.set_gdl_parameters({"elementId": {"guid": v["guid"]}}, {"tkOn": on})
        v["params"] = {**(v.get("params") or {}), "tkOn": int(on)}
    for g in roads:
        c.set_gdl_parameters({"elementId": {"guid": g}}, {"showSw": on})
    rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"車両の軌跡: {'描きます' if on else '消しました'}（車両 {len(targets)}台・場内通路 {len(roads)}本）")
    return 0


def front_archicad(c) -> None:
    """窓を閉じたあと Archicad を前に（クリックが Archicad に届くように）."""
    import subprocess

    try:
        v = c.post("API.GetProductInfo").get("version")
        subprocess.run(["open", "-b", f"com.graphisoft.archicad{v}"], capture_output=True, timeout=10)
    except Exception:  # noqa: BLE001 — 前に出せなくても、利用者が Archicad を押せば進む
        pass


def pick_line(c, start: str = "Click the place of the machine", end: str = "Click the front direction") -> list | None:
    """平面図で 2回クリックしてもらう → [置く所, 向きの点]（mm）. Esc なら None. 案内の文字は 1バイトのみ（Tapir の説明）."""
    from ashiba.tapir_adapter import TapirError

    saved, c.timeout = c.timeout, PICK_WAIT_S
    try:
        r = c.tapir("GetLineFromUser", {"startPrompt": start, "endPrompt": end,
                                        "showRubberLineFeedback": True}, retries=0)
    except TapirError as e:
        print(f"  クリックを受け取れませんでした（{str(e)[:120]}）")
        return None
    finally:
        c.timeout = saved
    if r.get("cancelled") or "startPoint" not in r:
        return None
    a = (float(r["startPoint"]["x"]) * 1000.0, float(r["startPoint"]["y"]) * 1000.0)
    b = (float(r["endPoint"]["x"]) * 1000.0, float(r["endPoint"]["y"]) * 1000.0)
    return [a, b if math.dist(a, b) > 1.0 else (a[0] + 1000.0, a[1])]


def vehicle_extra(mach, a) -> dict:
    """車両の旋回軌跡（TRACK_KINDS）と搬入車両（mcKind 13・14）の積荷、クローラクレーンのブーム・ジブ・安全率のパラメータ（ほかの種類は空）."""
    if mach.kind == 2:
        out = {"jbL": a.jib, "jbO": a.jib_off, "sfRate": a.safety}
        if a.boom > 0:
            out["lbL"] = a.boom
        if a.angle > 0:
            out["lbA"] = a.angle
        return out
    if mach.kind not in TRACK_KINDS:
        return {}
    out = {"tkOn": 0 if a.no_track else 1, "tkS": 1 if a.turn == "左" else -1}
    if a.turn_r > 0:
        out["tnR"] = a.turn_r
    if a.load and mach.kind in (13, 14):
        L, W, H, T = (float(v) for v in a.load.split(","))
        # トレーラーの積荷はキングピンから荷台の中心へ（低床は荷台、平床は前から、ポールは既定のまま）
        x = 0.0
        if mach.kind == 14:
            ps = mach.params
            x = {1: ps["tlF"] - ps["gnL"] - ps["dkL"] / 2, 2: ps["tlF"] - 0.3 - L / 2}.get(int(ps["tlK"]), ps.get("cgX", 0.0))
        out.update({"cgOn": 1, "cgL": L, "cgW": W, "cgH": H, "cgT": T, "cgX": x})
    return out


if __name__ == "__main__":
    sys.exit(main())
