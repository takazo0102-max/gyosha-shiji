"""山留め壁（パレットの「山留め壁」）.

利用者の指定（2026-11-05）「山留めの種類も増やして シートパイルや簡易山留めなど 他にもあったら増やして LOD高めて Hこう横やいたは
矢板の平米拾えるようにしてかかりしろは厚みの分だけにして１次ねぎりと2次ねぎりで分けれるようにあと矢板を止めるさんぎも」。

  python3 scripts/ywall_run.py                                   # 選んだ線（山留めの線）に。窓で種類・深さ・根切りの段を選ぶ
  python3 scripts/ywall_run.py --kind oyagui --depth 4000 --stages 2000      # 親杭横矢板・根切り 4m・1次根切り GL-2000
  python3 scripts/ywall_run.py --kind oyagui --model H-350 --pitch 1200 --lag-t 35 --kakari 35
  python3 scripts/ywall_run.py --kind sp_u --model IV --embed 4000            # U形鋼矢板 Ⅳ型・根入れ 4m
  python3 scripts/ywall_run.py --kind tatekomi --model TS1 --depth 2500       # たて込み簡易土留め
  python3 scripts/ywall_run.py --kind smw --model 650 --core-every 2          # SMW φ650・芯材 1本おき
  python3 scripts/ywall_run.py --support wale --depth 5000                  # 腹起し・切梁を描く（auto は深さ 3m を超えたら・none は自立）
  python3 scripts/ywall_run.py --support grid --depth 7000                  # 縦横の切梁（上下段）と交点の中間杭
  python3 scripts/ywall_run.py --list                            # 種類と型式の一覧
  python3 scripts/ywall_run.py --remove                          # 置いた山留め壁を消す

線（ポリライン・つながる線）1本を山留め1つとし、辺ごとに部品 ashiba_ywall を1つ置く（割付・数量・検定は src/ashiba/retaining.py）。
閉じた線は中が根切り、開いた線は線の右が根切り（線を引いた向き）。線は 親杭・SMW・鋼管は芯、鋼矢板は壁の中心線、たて込みは
土留め板の外面。部品はレイヤー「仮設_山留め」に。控えは ashiba_out/山留め壁.json（根切り図が山留めとして読む）、
数量と検定は ashiba_out/山留め壁.md.
縦横の切梁（--support grid、auto は広い根切り）は、切梁と中間杭を部品 ashiba_shiho で1本ずつ置く（割付は src/ashiba/shiho.py。
控えの shiho_guids）。手で引いた線から切梁・腹起しを置くのは scripts/shiho_run.py.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

PART = "ashiba_ywall"
RECORD = "山留め壁.json"
LAYER = "仮設_山留め"
SUPPORTS = {"自動（深さ 3m を超えたら腹起し・切梁。広い根切りは縦横）": "auto", "腹起し・切梁（1方向）": "wale",
            "縦横の切梁（上下段）＋中間杭": "grid", "自立（腹起し・切梁なし）": "none"}
SHIHO_PART = "ashiba_shiho"


def models_of(kind: str) -> list[str]:
    from ashiba import retaining as RT

    return {"oyagui": list(RT.PILE_SHAPES), "sp_u": list(RT.SP_U), "sp_hat": list(RT.SP_HAT), "lsp": list(RT.LSP),
            "alu": list(RT.ALU), "tatekomi": list(RT.TATEKOMI), "smw": [f"{d:.0f}" for d in RT.SMW],
            "koukan": [f"{RT.TUBE_D_MM:.0f}"]}[kind]


def model_label(kind: str, m: str) -> str:
    from ashiba import retaining as RT

    if kind in RT.SHEET_KINDS:
        return RT.sheet_spec(kind, m)[0]
    if kind == "tatekomi":
        return RT.TATEKOMI[m][0]
    if kind == "smw":
        return f"φ{m}"
    return m


def wall_from(rec: dict):
    """控えの1件 → 割付した Wall."""
    from ashiba import retaining as RT

    w = RT.Wall(rec["name"], rec["kind"], pts=[tuple(p) for p in rec["pts"]], closed=bool(rec["closed"]), gl=rec.get("gl", 0.0),
                depth=rec["depth"], stages_mm=rec.get("stages", []), top_up=rec.get("top_up", 0.0), embed=rec.get("embed"),
                model=rec.get("model", ""), pitch=rec.get("pitch", RT.PILE_PITCH_MM), lag_t=rec.get("lag_t", RT.LAG_T_MM),
                kakari=rec.get("kakari"), core=rec.get("core", ""), core_every=rec.get("core_every", 1),
                tube_d=rec.get("tube_d", RT.TUBE_D_MM), tube_t=rec.get("tube_t", RT.TUBE_T_MM), support=rec.get("support", "auto"),
                strut_hiuchi=rec.get("strut_hiuchi", True))
    return RT.plan(w)


def _num(v):
    s = str(v if v is not None else "").replace(",", "").strip()
    return float(s) if s else None


def ask(a, n_lines: int, closed: bool) -> bool:
    """窓で種類・型式・深さ・根切りの段を選ぶ. やめたら False."""
    from form_dialog import show_form

    from ashiba import retaining as RT

    kinds = list(RT.KIND_LABELS.values())
    all_models = ["既定（種類ごと）"] + [f"{RT.KIND_LABELS[k].split('（')[0]}: {model_label(k, m)}" for k in RT.KIND_LABELS
                                        for m in models_of(k)]
    res = show_form({
        "title": "山留め壁",
        "intro": f"山留めの線 {n_lines}本" + ("（閉じた線: 中が根切り）" if closed else "（開いた線: 線の右が根切り）")
                 + "。辺ごとに部品を置き、数量（横矢板の m² は根切りの段ごと・桟木・くさび、鋼矢板の枚数と t など）を帳票に書きます。",
        "fields": [
            {"key": "name", "label": "名前", "kind": "text", "value": a.name or "山留め1"},
            {"key": "kind", "label": "種類", "kind": "choice", "options": kinds, "value": RT.KIND_LABELS[a.kind]},
            {"key": "model", "label": "型式（種類と合わないものは既定に）", "kind": "choice", "options": all_models, "value": all_models[0]},
            {"key": "depth", "label": "根切りの深さ GL から mm（正）", "kind": "number", "value": f"{a.depth:.0f}"},
            {"key": "stages", "label": "1次・2次…根切りの底 GL から mm（カンマ区切り。空＝腹起しがあれば その下端＋1.0m ごと、無ければ1回）",
             "kind": "text", "value": a.stages or ""},
            {"key": "support", "label": "腹起し・切梁（H-300・壁から 100・ブラケット 2m ピッチ・切梁 5m 以下。縦横は交点に中間杭）", "kind": "choice",
             "options": list(SUPPORTS), "value": next(k for k, v in SUPPORTS.items() if v == (a.support or "auto"))},
            {"key": "hiuchi", "label": "切梁火打ち（切梁の両端の左右・45°）", "kind": "choice", "options": ["入れる", "入れない"],
             "value": "入れない" if a.no_strut_hiuchi else "入れる"},
            {"key": "embed", "label": "根入れ mm（空＝種類の既定: 親杭 1500・鋼矢板 3000・軽量 深さの1/2・アルミ 200）", "kind": "number",
             "value": "" if a.embed is None else f"{a.embed:.0f}"},
            {"key": "top_up", "label": "天端 GL から上 mm", "kind": "number", "value": f"{a.top_up:.0f}"},
            {"key": "pitch", "label": "親杭の芯々 mm（標準 1500・1000〜2000）", "kind": "number", "value": f"{a.pitch:.0f}"},
            {"key": "lag_t", "label": "横矢板の厚さ mm（最小 30）", "kind": "choice", "options": [f"{v:.0f}" for v in RT.LAG_T_OPTIONS],
             "value": f"{a.lag_t:.0f}"},
            {"key": "kakari", "label": "掛かり代 mm（空＝矢板の厚さ）", "kind": "number", "value": "" if a.kakari is None else f"{a.kakari:.0f}"},
            {"key": "core_every", "label": "SMW の芯材", "kind": "choice", "options": ["全孔", "1本おき"],
             "value": "全孔" if a.core_every == 1 else "1本おき"},
            {"key": "gl", "label": "GL の高さ mm（プロジェクトの 0 から）", "kind": "number", "value": f"{a.gl:.0f}"},
        ],
        "buttons": [{"id": "place", "label": "置く"}, {"id": "cancel", "label": "やめる"}]})
    if not res or res.get("button") != "place":
        return False
    v = res.get("values") or {}
    inv = {lab: k for k, lab in RT.KIND_LABELS.items()}
    a.kind = inv.get(str(v.get("kind")), a.kind)
    a.name = str(v.get("name") or a.name or "山留め1")
    m = str(v.get("model") or "")
    hit = next((mm for mm in models_of(a.kind) if m == f"{RT.KIND_LABELS[a.kind].split('（')[0]}: {model_label(a.kind, mm)}"), "")
    a.model = hit or a.model
    for key in ("depth", "top_up", "pitch", "gl"):
        val = _num(v.get(key))
        if val is not None:
            setattr(a, key, val)
    a.embed = _num(v.get("embed"))
    a.kakari = _num(v.get("kakari"))
    lt = _num(v.get("lag_t"))
    a.lag_t = lt if lt else a.lag_t
    a.stages = str(v.get("stages") or "")
    a.core_every = 2 if str(v.get("core_every")) == "1本おき" else 1
    a.support = SUPPORTS.get(str(v.get("support")), a.support or "auto")
    a.no_strut_hiuchi = str(v.get("hiuchi")) == "入れない"
    return True


def recorded_polygons(out_dir: Path, guids=None, point=None) -> list[tuple[str, list, float]]:
    """控え（山留め壁.json）の閉じた山留めの根切りの側の面の多角形 [(名前, 多角形 mm, 山留めの根切りの深さ mm)]. guids を渡せばその部品を含むものだけ、
    point を渡せばその点を囲むものだけ（根切り図が、選んだ山留め壁か、躯体を囲む山留め壁を山留めとして読む）."""
    from ashiba import retaining as RT
    from ashiba.negiri import inside

    try:
        rec = json.loads((Path(out_dir) / RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    want = {g.upper() for g in guids} if guids is not None else None
    out = []
    for v in rec.values():
        if not v.get("closed"):
            continue
        if want is not None and not want & {g.upper() for g in v.get("guids", [])}:
            continue
        try:
            poly = RT.inner_polygon(wall_from(v))
        except (KeyError, ValueError):
            continue
        if poly and (point is None or inside(point, poly)):
            out.append((v.get("name") or "山留め", poly, float(v.get("depth") or 0.0)))
    return out


def edges_for(out_dir: Path, guids) -> list[tuple]:
    """選んだ山留め壁の部品 → その辺の (始め, 終わり, 天端の高さ mm, 名前, 部品の GUID)。+Y（線の左）が地山（山留めの手すりが使う）."""
    try:
        rec = json.loads((Path(out_dir) / RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    want = {g.upper() for g in guids}
    out = []
    for v in rec.values():
        gs = [g.upper() for g in v.get("guids", [])]
        if not want & set(gs):
            continue
        try:
            w = wall_from(v)
        except (KeyError, ValueError):
            continue
        top = float(v.get("gl", 0.0)) + float(v.get("top_up", 0.0))
        for e, g in zip(w.edges, gs):
            if g in want:
                out.append((tuple(e.a), tuple(e.b), top, e.name, g))
    return out


YW_WALE = "腹起し:山留め壁:"          # 外周の足場の控え（山留め足場.json）の鍵の頭（Archicad の壁でなく山留め壁の辺）


def wale_walls(out_dir: Path, guids) -> dict:
    """選んだ山留め壁の部品 → {部品の GUID: 壁の形（excav_run の壁と同じ鍵 ca・cb・n・lo・hi・thick・z0・height と、
    腹起し 1段目の天端 wale_top・幅 wale_w mm）}. 腹起しの無い（自立の）山留めは wale_top が None.
    外周の足場（腹起し上）を「山留め壁」の部品からも置く（2026-11-07 ループの試験で、手すり・切梁上の足場は部品を受けるのに
    外周の足場だけ「山留め（壁）を選んで」と断っていた）."""
    import math

    from ashiba import retaining as RT

    try:
        rec = json.loads((Path(out_dir) / RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    want = {g.upper() for g in guids}
    out = {}
    for v in rec.values():
        gs = [g.upper() for g in v.get("guids", [])]
        if not want & set(gs):
            continue
        try:
            w = wall_from(v)
        except (KeyError, ValueError):
            continue
        t = RT.H_SHAPES[w.model][0] if w.model in RT.H_SHAPES else 300.0
        shape = RT.wale_shape(w)[0]
        wh, wb = RT.H_SHAPES[shape][0], RT.H_SHAPES[shape][1]
        top = float(v.get("gl", 0.0)) + float(v.get("top_up", 0.0))
        wale_top = float(v.get("gl", 0.0)) - min(w.wales) + wh / 2.0 if w.wales else None
        for e, g in zip(w.edges, gs):
            if g not in want:
                continue
            a, b = tuple(e.a), tuple(e.b)
            L = math.dist(a, b)
            if L < 100.0:
                continue
            u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
            out[g] = {"ca": a, "cb": b, "a": a, "b": b, "u": u, "n": (-u[1], u[0]), "lo": -t / 2.0, "hi": t / 2.0, "thick": t,
                      "z0": top, "height": 0.0, "length": L, "name": e.name, "wale_top": wale_top, "wale_w": wb}
    return out


YW_STRUT = "切梁:山留め壁:"          # 切梁上の足場の控え（山留め足場.json）の鍵の頭（Archicad の梁でなく山留め壁の切梁）


def struts_for(out_dir: Path, guids=None) -> dict:
    """山留め壁の切梁 → {控えの鍵: 梁の形（excav_run の切梁と同じ ca・cb・u・length・width・depth・top・bottom・ang）}.
    向かい合う辺の半分ずつを1本にまとめる。guids を渡せばその部品を含む山留めだけ（縦横の切梁と、手で引いた切梁 scripts/shiho_run.py
    は、選んだ切梁の部品だけ。山留め壁の辺の部品を選べばその山留めの全部）."""
    from ashiba import retaining as RT

    want = {g.upper() for g in guids} if guids is not None else None
    out = {}
    try:
        man = json.loads((Path(out_dir) / "支保工.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        man = {}
    if man.get("lines"):
        from shiho_run import build

        mg = [g.upper() for g in man.get("guids", [])]
        ms = build(man)
        pick = [m for m, g in zip(ms, mg) if want is None or g in want]
        out.update(member_struts(pick, float(man.get("gl", 0.0)), f"{YW_STRUT}手"))
    try:
        rec = json.loads((Path(out_dir) / RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return out
    for v in rec.values():
        whole = want is None or bool(want & {g.upper() for g in v.get("guids", [])})
        sg = [g.upper() for g in v.get("shiho_guids", [])]
        if not whole and not (want & set(sg)):
            continue
        try:
            w = wall_from(v)
        except (KeyError, ValueError):
            continue
        if not w.wales:
            continue
        H, B, *_ = RT.H_SHAPES[RT.wale_shape(w)[0]]
        if RT.use_grid(w):
            from ashiba import shiho as SH

            ms = SH.grid(w)
            pick = ms if whole else [m for m, g in zip(ms, sg) if g in want]
            out.update(member_struts(pick, float(v.get("gl", 0.0)), f"{YW_STRUT}{w.name}"))
            continue
        f = RT.face_offset(w) + RT.WALE_GAP_MM + H
        for e in w.edges:
            ux, uy = (e.b[0] - e.a[0]) / e.length, (e.b[1] - e.a[1]) / e.length
            n = (uy, -ux)
            for x, half in zip(e.strut_x, e.strut_len):
                if half <= 0:
                    continue
                ca = (e.a[0] + ux * x + n[0] * f, e.a[1] + uy * x + n[1] * f)
                cb = (ca[0] + n[0] * 2 * half, ca[1] + n[1] * 2 * half)
                for z in w.wales:
                    mid = (round((ca[0] + cb[0]) / 1000.0), round((ca[1] + cb[1]) / 1000.0), round(z))
                    key = f"{YW_STRUT}{w.name}:{mid[0]}:{mid[1]}:{mid[2]}"
                    if key in out:
                        continue
                    top = float(v.get("gl", 0.0)) - z + H / 2.0
                    L = 2 * half
                    out[key] = {"ca": ca, "cb": cb, "u": n, "length": L, "width": B, "depth": H, "top": top, "bottom": top - H,
                                "ang": math.degrees(math.atan2(n[1], n[0]))}
    return out


def member_struts(members, gl: float, prefix: str) -> dict:
    """支保工の部材（shiho.Member）の切梁 → struts_for と同じ梁の形の辞書."""
    from ashiba import retaining as RT

    out = {}
    for m in members:
        if m.kind != "strut" or m.length <= 0:
            continue
        H, B, *_ = RT.H_SHAPES[m.shape]
        u = ((m.b[0] - m.a[0]) / m.length, (m.b[1] - m.a[1]) / m.length)
        mid = (round((m.a[0] + m.b[0]) / 2000.0), round((m.a[1] + m.b[1]) / 2000.0), round(m.z))
        top = gl - m.z + H / 2.0
        out[f"{prefix}:{mid[0]}:{mid[1]}:{mid[2]}"] = {"ca": tuple(m.a), "cb": tuple(m.b), "u": u, "length": m.length, "width": B,
                                                       "depth": H, "top": top, "bottom": top - H, "ang": m.angle}
    return out


def sheet_info(out_dir: Path, name: str) -> dict:
    """山留め壁 name の、根切り・山留計画図に書く要点（種類・型式の注記・天端・長さ・根入れ・腹起しの段・根切りの段）."""
    from ashiba import retaining as RT

    try:
        rec = json.loads((Path(out_dir) / RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    v = next((x for x in rec.values() if x.get("name") == name), None)
    if not v:
        return {}
    try:
        w = wall_from(v)
    except (KeyError, ValueError):
        return {}
    shape = RT.wale_shape(w)[0] if w.wales else ""
    lens = sorted({round(2 * v) for e in w.edges for v in e.strut_len if v > 0})
    grid = RT.use_grid(w)
    piles = []
    from ashiba import shiho as SH

    if grid:
        ms = SH.grid(w)
        lens = sorted({round(m.length, -2) for m in ms if m.kind == "strut"})
        piles = [[round(m.a[0], 1), round(m.a[1], 1)] for m in ms if m.kind == "pile"]
    lines = {}                                             # 切梁伏図の線（段をまとめて平面の線1本）
    segs = [(*s["ca"], *s["cb"]) for s in struts_for(out_dir, v.get("guids", [])).values()]
    segs += [(*m.a, *m.b) for m in SH.members(w) if m.kind == "hiuchi"]
    if w.wales:
        fw = RT.face_offset(w) + RT.WALE_GAP_MM + RT.H_SHAPES[shape][0]
        for e in w.edges:                                  # 隅火打ち（始めの角。部品の中の線と同じ）
            if e.hiuchi:
                ux, uy = (e.b[0] - e.a[0]) / e.length, (e.b[1] - e.a[1]) / e.length
                at = lambda x, d: (e.a[0] + ux * x + uy * d, e.a[1] + uy * x - ux * d)   # noqa: E731
                segs.append((*at(fw, fw + RT.HIUCHI_LEG_MM), *at(fw + RT.HIUCHI_LEG_MM, fw)))
    for sg in segs:
        q = [round(c, 1) for c in sg]
        lines[tuple(round(c, -1) for c in q)] = q
    return {"grid": grid, "strut_lens": lens, "piles": len(piles), "pile_len": w.depth + w.embed_mm if piles else 0.0,
            "plan_struts": list(lines.values()), "plan_piles": piles, "name": w.name, "kind": RT.KIND_LABELS[w.kind], "label": RT.label(w), "top_up": w.top_up, "depth": w.depth,
            "embed": w.embed_mm, "length": w.wall_len, "wales": list(w.wales), "wale": shape,
            "wale_h": RT.H_SHAPES[shape][0] if shape else 0.0, "struts": any(e.strut_x for e in w.edges),
            "strut_len": max((2 * v for e in w.edges for v in e.strut_len), default=0.0),
            "stages": [[s.name, s.bottom] for s in w.stages]}


def wall_members(w):
    from ashiba import shiho as SH

    return SH.members(w)


def place_members(c, members, gl: float, li: int, pens: dict) -> list[str]:
    """支保工の部材を部品 ashiba_shiho で1本ずつ置く（レイヤー li）. 置いた GUID."""
    import run_from_archicad as R
    from ashiba import shiho as SH
    from excav_run import _place

    part = R.versioned_part_name(SHIHO_PART)
    guids = []
    for m in members:
        el = _place(c, part, m.a, gl, m.angle)
        if el is None:
            continue
        c.set_gdl_parameters(el, {**SH.part_params(m), **pens})
        guids.append(el["elementId"]["guid"])
    if guids:
        try:
            c.tapir("SetDetailsOfElements", {"elementsWithDetails": [
                {"elementId": {"guid": g}, "details": {"layerIndex": li}} for g in guids]})
        except Exception:  # noqa: BLE001 — レイヤーに移せなくても置いたものは残す
            pass
    return guids


def layer_index(c) -> int:
    attrs = c.tapir("GetAttributesByType", {"attributeType": "Layer"}).get("attributes", [])
    hit = next((x for x in attrs if x.get("name") == LAYER), None)
    if hit is None:
        c.tapir("CreateLayers", {"layerDataArray": [{"name": LAYER}]})
        attrs = c.tapir("GetAttributesByType", {"attributeType": "Layer"}).get("attributes", [])
        hit = next(x for x in attrs if x.get("name") == LAYER)
    return int(hit["index"])


def main(argv=None) -> int:
    import argparse

    from ashiba import retaining as RT

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kind", default=None, choices=list(RT.KIND_LABELS), help="種類")
    ap.add_argument("--model", default="", help="型式（--list で一覧。空＝種類の既定）")
    ap.add_argument("--name", default="", help="名前（控えの鍵。既定 山留め1…）")
    ap.add_argument("--depth", type=float, default=None, help="根切りの深さ GL から mm（正）")
    ap.add_argument("--stages", default=None, help="1次・2次…根切りの底 GL から mm（カンマ区切り）")
    ap.add_argument("--embed", type=float, default=None, help="根入れ mm（省くと種類の既定）")
    ap.add_argument("--top", dest="top_up", type=float, default=None, help="天端 GL から上 mm")
    ap.add_argument("--pitch", type=float, default=None, help="親杭の芯々 mm")
    ap.add_argument("--lag-t", dest="lag_t", type=float, default=None, help="横矢板の厚さ mm")
    ap.add_argument("--kakari", type=float, default=None, help="掛かり代 mm（省くと矢板の厚さ）")
    ap.add_argument("--core-every", dest="core_every", type=int, default=None, choices=(1, 2), help="SMW の芯材 1＝全孔・2＝1本おき")
    ap.add_argument("--support", default=None, choices=("auto", "wale", "grid", "none"),
                    help="腹起し・切梁（auto＝深さ 3m を超えたら・wale＝1方向・grid＝縦横＋中間杭・none＝自立）")
    ap.add_argument("--no-strut-hiuchi", dest="no_strut_hiuchi", action="store_true", help="切梁火打ちを入れない")
    ap.add_argument("--tube", default="", help="鋼管矢板の 外径×板厚 mm（例 800x12）")
    ap.add_argument("--gl", type=float, default=None, help="GL の高さ mm（プロジェクトの 0 から）")
    ap.add_argument("--list", action="store_true", help="種類と型式の一覧")
    ap.add_argument("--remove", action="store_true", help="置いた山留め壁を消す")
    a = ap.parse_args(argv)
    if a.list:
        for k, lab in RT.KIND_LABELS.items():
            print(f"{k:9s} {lab}: " + "・".join(f"{m}（{model_label(k, m)}）" if model_label(k, m) != m else m for m in models_of(k)))
        return 0

    import run_from_archicad as R
    from ashiba.pens import gdl_pens, parse_pens
    from ashiba.tapir_adapter import ArchicadClient
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
        n = _delete_alive(c, [g for v in rec.values() for g in v.get("guids", []) + v.get("shiho_guids", [])])
        rec_path.write_text("{}", encoding="utf-8")
        print(f"山留め壁: 部品 {n}個を消しました")
        return 0
    lines = [(k, pts, closed) for k, pts, closed in chains(selected_guides(c)) if len(pts) >= 2]
    if not lines:
        print("山留め壁: 山留めの線（ポリライン・線。閉じた線は中が根切り、開いた線は線の右が根切り）を選んでから押してください")
        return 1
    asked = all(getattr(a, k) is None for k in ("kind", "depth", "stages", "embed", "top_up", "pitch", "lag_t", "kakari",
                                                 "core_every", "gl", "support")) and not a.model and not a.no_strut_hiuchi
    a.kind = a.kind or "oyagui"
    a.depth = 3000.0 if a.depth is None else a.depth
    a.top_up = 0.0 if a.top_up is None else a.top_up
    a.pitch = RT.PILE_PITCH_MM if a.pitch is None else a.pitch
    a.lag_t = RT.LAG_T_MM if a.lag_t is None else a.lag_t
    a.core_every = 1 if a.core_every is None else a.core_every
    a.gl = 0.0 if a.gl is None else a.gl
    a.support = a.support or "auto"
    if asked and not ask(a, len(lines), any(cl for _k, _p, cl in lines)):
        print("山留め壁: やめました（何も置いていません）")
        return 0
    if a.model and a.model not in models_of(a.kind):
        print(f"山留め壁: 型式 {a.model} は {RT.KIND_LABELS[a.kind]} にありません（{'・'.join(models_of(a.kind))}）")
        return 1
    tube_d, tube_t = RT.TUBE_D_MM, RT.TUBE_T_MM
    if a.tube:
        try:
            tube_d, tube_t = (float(x) for x in a.tube.lower().replace("×", "x").split("x"))
        except ValueError:
            print("山留め壁: --tube は 外径x板厚（例 800x12）")
            return 1
    stages = [float(x) for x in str(a.stages or "").replace("、", ",").split(",") if x.strip()]

    R.ensure_parts(c)
    part = R.versioned_part_name(PART)
    spec = {**R.SPEC, **R.load_spec_override()}
    pens = gdl_pens(parse_pens(spec.get("pens")), PART)
    from pen_colors import draft_pens_for

    pens.update(draft_pens_for(c, pens.get("penEquip", 1)))      # 外形は太線・細部は細線（scripts/gdl_draft.py）
    li = layer_index(c)
    used = {v.get("name") for v in rec.values()}
    nxt = 1
    placed = 0
    for n, (key, pts, closed) in enumerate(lines, 1):
        old = rec.pop(key, None)
        if old:
            _delete_alive(c, old.get("guids", []) + old.get("shiho_guids", []))
        name = a.name if (a.name and len(lines) == 1) else (old or {}).get("name")
        if not name:
            while f"山留め{nxt}" in used:
                nxt += 1
            name = f"山留め{nxt}"
            used.add(name)
        pp = [tuple(p) for p in (pts[:-1] if closed else pts)]
        entry = {"name": name, "kind": a.kind, "model": a.model or RT.default_model(a.kind), "pts": [list(p) for p in pp],
                 "closed": closed, "gl": a.gl, "depth": a.depth, "stages": stages, "top_up": a.top_up, "embed": a.embed,
                 "pitch": a.pitch, "lag_t": a.lag_t, "kakari": a.kakari, "core_every": a.core_every, "tube_d": tube_d, "tube_t": tube_t,
                 "support": a.support, "strut_hiuchi": not a.no_strut_hiuchi}
        w = wall_from(entry)
        entry["pts"] = [list(p) for p in w.pts]            # 向きをそろえた点
        guids = []
        for e in w.edges:
            ang = math.degrees(math.atan2(e.b[1] - e.a[1], e.b[0] - e.a[0]))
            el = _place(c, part, e.a, a.gl, ang)
            if el is None:
                continue
            c.set_gdl_parameters(el, {**RT.part_params(w, e), **pens})
            guids.append(el["elementId"]["guid"])
        if guids:
            try:
                c.tapir("SetDetailsOfElements", {"elementsWithDetails": [
                    {"elementId": {"guid": g}, "details": {"layerIndex": li}} for g in guids]})
            except Exception:  # noqa: BLE001 — レイヤーに移せなくても置いたものは残す
                pass
        entry["guids"] = guids
        entry["shiho_guids"] = place_members(c, wall_members(w), a.gl, li, pens)
        rec[key] = entry
        placed += len(guids) + len(entry["shiho_guids"])
        bad = [f"{x.item} {x.status}" for x in w.checks if x.status in ("NG", "WARN")]
        ns = len(entry["shiho_guids"])
        print(f"  山留め壁 {name}: {RT.label(w)}・辺 {len(w.edges)}・周長 {w.perimeter / 1000:.1f}m" + (f"・切梁・火打ち・中間杭 {ns}本" if ns else "")
              + (f"・要確認 {'・'.join(bad)}" if bad else ""))
    rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    walls = []
    for v in rec.values():
        try:
            walls.append(wall_from(v))
        except (KeyError, ValueError):
            continue
    md = R.OUT_DIR / "山留め壁.md"
    md.write_text(RT.report(walls), encoding="utf-8")
    print(f"山留め壁: {len(lines)}か所・部品 {placed}個（数量と検定: {md}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
