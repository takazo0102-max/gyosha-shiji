"""帳票出力.

- 数量表CSV: 発注書としてそのまま使える型番ベース
- 割付レポートMD: 人が読む成果物。冒頭に総合判定、末尾に要確認一覧（着手前
  チェックリスト）。間に平面割付・昇降設備・法規チェック・壁つなぎ・構造計算
  （検定比）・敷地の高低差・付帯設備・数量サマリ。該当が無い節は出さない。
  一覧に載る長文は本文では件数と見出しに畳む（1つの文書で二度読ませない）
- plan.json: 配置・再編集用。各辺にGDLパラメータと配置座標を持つので、
  割付を解き直さずに再配置できる（scripts/place_from_plan_json.py が実証）
- ジャッキ量一覧CSV: 支柱ごとのGL標高・下げ段数・ジャッキ量・地盤調整量

設置届（様式第20号）要否の自動判定もここで行う:
高さ10m以上かつ設置期間60日以上 → 工事開始30日前までに所轄労基署へ（安衛法88条）。
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path

from .dp import spans_text
from .law_check import CheckResult
from .model import ScaffoldModel
from .notification import notification_required  # 判定はnotificationに一元化
from .quantity import QuantityResult

__all__ = [
    "notification_required",
    "write_quantity_csv",
    "write_report_md",
    "write_plan_json",
    "write_jack_table_csv",
]


def _csv_safe(v) -> str:
    """プロジェクトから来た文字列（フロア名など）を表計算の式として解釈させない（先頭 = + - @ には ' を付ける）."""
    s = str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def write_level_quantity_csv(lt, path: Path) -> None:
    """層ごとの数量（level_quantity.take_off_by_level）。支柱は1本ずつに分解して下端の層に数える."""
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        labels = [b.label + (f" {_csv_safe(lt.floors[i])}" if lt.floors else "") for i, b in enumerate(lt.bands)]
        w.writerow(["型番", "分類", "呼び寸法"] + labels + ["合計"])
        for row in lt.rows:
            p = row.part
            w.writerow([p.model_no, p.category, p.nominal_dim] + list(row.per_level) + [row.total])
        w.writerow([])
        w.writerow(["重量kg", "", ""] + lt.level_weights() + [round(sum(lt.level_weights()), 1)])
        names, by_floor = lt.by_floor()
        if names:
            # 建物のフロアごと（作業床の高さが入るフロアに、その層の部材をまとめる）
            w.writerow([])
            w.writerow(["■フロア別", "", ""] + [_csv_safe(n) for n in names] + ["合計"])
            for p, vals in by_floor:
                w.writerow([p.model_no, p.category, p.nominal_dim] + vals + [sum(vals)])
        for n in lt.notes:
            w.writerow(["注記", n])


def write_face_quantity_csv(ft, path: Path) -> None:
    """面ごとの数量（level_quantity.take_off_by_face）。最後の列は全体の数量表の値."""
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["型番", "分類", "呼び寸法"] + list(ft.faces) + ["面の合計", "全体（数量表）"])
        for p, vals in ft.rows:
            w.writerow([p.model_no, p.category, p.nominal_dim] + list(vals)
                       + [sum(vals), ft.totals.get((p.model_no, p.category), 0)])
        for n in ft.notes:
            w.writerow(["注記", n])


def write_quantity_csv(result: QuantityResult, path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["型番", "分類", "呼び寸法", "実寸法", "単位重量kg", "数量", "小計重量kg", "備考"])
        for line in result.lines:
            p = line.part
            note = p.note + ("　" + line.note if line.note else "")
            w.writerow(
                [p.model_no, p.category, p.nominal_dim, p.actual_dim,
                 p.weight_kg, line.qty, round(line.subtotal_weight, 1), note]
            )
        # 分類別の集計。発注前のざっくり確認用（支柱が何本、布材が何本…）。
        # 型番別の明細だけだと、系列全体の規模感がつかめない
        w.writerow([])
        w.writerow(["■分類別集計", "数量計", "重量計kg"])
        for c, q, wt in result.category_totals():
            w.writerow([c, q, wt])
        w.writerow([])
        w.writerow(["総重量kg", round(result.total_weight_kg, 1)])
        w.writerow(["トラック台数概算(4t)", result.truck_count])
        w.writerow(["架け面積m2", result.kake_menseki_m2])
        # 手配・検討が要るものは、計上ルールの説明と同じ見た目にしない。
        # 発注書として使うので、拾えていない部材が注記に埋もれると発注漏れになる
        for n in result.warnings:
            w.writerow(["要手配・要検討", n])
        for n in result.notes:
            if n not in result.warnings:
                w.writerow(["注記", n])


def _short(msg: str, listed: set) -> str:
    """末尾の一覧に載る文は、本文では1行に切り詰めて参照に回す."""
    if msg not in listed:
        return msg
    head = msg.split("。")[0].split("（")[0]
    return f"{head[:60]}…（要確認一覧を参照）"


def _face_items(model: ScaffoldModel, edge_index: int, stair_plan, platforms, openings,
                bracket_sections) -> str:
    """その面に載るものを「壁つなぎ64／階段1／梁枠1…」の形で返す（無ければ壁つなぎ本数だけ）."""
    parts: list[str] = []
    n_ties = sum(1 for t in model.wall_ties if t.edge_index == edge_index)
    parts.append(f"壁つなぎ{n_ties}")

    def count(seq, attr="edge_index"):
        return sum(1 for x in (seq or []) if getattr(x, attr, None) == edge_index)

    n = count(getattr(stair_plan, "towers", None))
    if n:
        parts.append(f"階段{n}")
    n = count(getattr(openings, "openings", None))
    if n:
        parts.append(f"梁枠{n}")
    n = count(getattr(platforms, "stages", None))
    if n:
        parts.append(f"ステージ{n}")
    n = count(getattr(platforms, "hoists", None))
    if n:
        parts.append(f"昇降機{n}")
    n = count(bracket_sections)
    if n:
        parts.append(f"ブラケット区間{n}")
    zones = [z for z in (getattr(model.plan, "bridged_zones", None) or []) if z.edge_index == edge_index]
    if zones:
        kinds = "・".join(sorted({z.kind for z in zones}))
        parts.append(f"渡し{len(zones)}（{kinds}）")
    return "／".join(parts)


def write_report_md(
    model: ScaffoldModel,
    quantity: QuantityResult,
    checks: list[CheckResult],
    path: Path,
    project_name: str = "",
    stair_plan=None,
    verdict=None,
    structural=None,
    terrain=None,
    platforms=None,
    openings=None,
    bracket_sections=None,
    warnings=None,
) -> None:
    """割付レポート（人が読む成果物）.

    構造計算の検定比・壁つなぎの配置・敷地の高低差・付帯設備は、以前は
    plan.json と設置届Excelにしか出ておらず、この本文には無かった。
    計画の可否を左右する数字なので本文に出す。
    """
    e = model.elevation
    lines: list[str] = []
    a = lines.append
    # 末尾の要確認一覧に載る項目。本文で同じ長文を二度読ませないため先に決める
    checklist: list[tuple[str, str]] = [
        ("法規チェック", f"{c.name}: {c.message}（{c.basis}）")
        for c in checks if c.status == "WARN"
    ]
    checklist += [(kind, text) for kind, sev, text in (warnings or []) if sev != "NG"]
    listed = {text for _kind, text in checklist}
    # 法規チェック表に出ている文は、他の節では見出しだけにして重複を避ける
    in_law_table = {c.message for c in checks if c.status == "WARN"}
    a(f"# 足場割付レポート {project_name}".rstrip())
    a("")
    if verdict is not None:
        # 法規・構造・付帯設備がそれぞれ別々に判定を持つので、先頭で束ねて出す
        detail = "／".join(verdict.get("warn_breakdown", []))
        if verdict["ok"]:
            a("**判定: 計画は成立しています**"
              + (f"（要確認 {verdict['warn']}件: {detail}）" if verdict["warn"] else ""))
        else:
            a("**判定: ❌ 是正が必要です**")
            for b in verdict["blockers"]:
                a(f"- {b}")
            # NG の理由（付帯設備・開口部・ブラケット区間・衝突）は件数だけでは直せない。
            # 要確認一覧は WARN だけなので、是正項目の本文をここに出す（実機で「ブラケット区間NG 1件」
            # としか書かれず、60%規定に掛かったことがどこにも無かった）
            for kind, sev, text in (warnings or []):
                if sev == "NG":
                    a(f"  - 是正: {kind}: {text}")
            if verdict["warn"]:
                a(f"- ほかに要確認 {verdict['warn']}件: {detail}")
        a("")
    # コマピッチは枠組には無い概念（建枠を積む方式）
    from .master import SERIES_LABELS

    a(f"- 系列: {SERIES_LABELS.get(model.master.series_id, model.master.series_id)}（{model.master.series_id}）"
      + ("（建枠を積む方式）" if model.master.is_frame
         else f"（コマピッチ{model.master.koma_pitch}mm）"))
    from .terrain import actual_max_height_mm

    h_act, h_extra = actual_max_height_mm(model, terrain)
    a(f"- 足場高さ: {model.scaffold_height_mm}mm / 作業層数: {e.n_levels}"
      + (f"（敷地の低い側の実高さ {h_act:.0f}mm＝名目＋脚の伸び{h_extra:.0f}mm"
         "〈継ぎ足し・ジャッキ繰出しの差〉。法規・届出・風はこの値で判定）"
         if h_extra > 1 else ""))
    vm = model.master.vertical_member_name
    a(f"- {vm}構成（下から）: ジャッキ{e.jack_extension} + "
      + spans_text(e.posts).replace("+", " + ")
      + f" = {e.total_height}mm")
    if list(e.posts_alt) != list(e.posts):
        a(f"- 千鳥（1本おきの{vm}）: " + spans_text(e.posts_alt).replace("+", " + ")
          + ("（継ぎ目が重ならない）" if e.is_staggered() else "（継ぎ目が重なる所あり。要確認）"))
    else:
        a(f"- 継ぎ目: 全部の{vm}で同じ積み方（そろえる。千鳥にするなら \"post_stagger\": true）")
    if getattr(e, "base_shim", 0):
        a(f"- ジャッキの下の敷板: 全部の脚に {e.base_shim}mm（ジャッキの繰出しは {e.jack_extension - e.base_shim}mm）")
    a(f"- 1層あたり{vm}位置数: {model.plan.total_posts}（二重計上なし）")
    widths = model.deck_widths_in_use
    deck_desc = "＋".join(f"{w}" for w in widths) + f" ＝ 幅{sum(widths)}mm"
    one_sided = model.config.scaffold_form == "一側足場"
    if one_sided:
        deck_desc += "（一側足場・1枚敷き）"
    elif model.config.next_gen:
        deck_desc += "（次世代足場・幅広踏板）"
    # 一側足場は建地1列なので列間隔は無い（ブラケットで持ち出す）
    spacing = "" if one_sided else f" ／ {vm}列間隔 {model.post_row_spacing_mm}mm"
    a(f"- 作業床: {model.master.deck_category} {deck_desc}" + spacing)
    a(f"- 手すり方式: {model.guard_rail_method}")
    if getattr(model.config, "post_reinforcement", ""):
        # 補強前提の耐力で検定している。書かないと通常仕様の計画に見える
        a(f"- {model.master.vertical_member_name}補強: {model.config.post_reinforcement}"
          "（腕木を方杖付きに替え、支柱の許容支持力はその仕様の値で検定）")
    a("- 設置届: " + ("**要**（高さ10m以上かつ60日以上 → 開始30日前までに労基署へ）"
                    if notification_required(model, terrain) else "不要"))
    a("")
    a("## 平面割付")
    a("")
    # 現場で通じるのは辺番号ではなく面（南面・東面）。立面図の面名と揃える
    faces = model.plan.face_names()
    # 躯体頂点（辺の始点）を出す。外形を整理（反転・重複除去・渡し）すると辺番号が
    # 入力の頂点順とずれるので、付帯設備の edge_index を突き合わせる手がかりにする
    verts = model.plan.outline.vertices
    # 面に載るもの（壁つなぎ本数・階段・梁枠・ステージ・昇降機・ブラケット区間・渡した区間）を
    # 辺ごとに1列で見せる。付帯設備は章ごとに散らばるので、面単位で突き合わせる手がかりにする
    a("| 辺 | 面 | 躯体頂点(始点) | 足場長 | スパン構成 | 離れ | 面に載るもの | 対処案 |")
    a("|---|---|---|---|---|---|---|---|")
    for ep, face in zip(model.plan.edges, faces):
        spans = spans_text(ep.spans)
        vx, vy = verts[ep.edge_index] if ep.edge_index < len(verts) else (0, 0)
        items = _face_items(model, ep.edge_index, stair_plan, platforms, openings, bracket_sections)
        a(f"| {ep.edge_index} | {face} | ({vx:.0f}, {vy:.0f}) | {ep.scaffold_length:.0f} | {spans} "
          f"| {ep.standoff:.0f} | {items} | {ep.remedy or '—'} |")
    for z in getattr(model.plan, "bridged_zones", None) or []:
        deep = getattr(z, "deep_end", "uniform")
        how = (f"離れ＋最大{z.depth_mm:.0f}mm（{'終点' if deep == 'end' else '始点'}側で最大、斜辺に沿って線形）"
               if z.kind == "斜辺" else f"離れ＋{z.depth_mm:.0f}mm")
        a(f"- 渡した区間: {model.face_name(z.edge_index)} 始点から{z.start_mm:.0f}〜{z.end_mm:.0f}mm"
          f"（{z.kind} 幅{z.width_mm:.0f}mm、{z.span_count}スパン）。{how}"
          "（措置の本数は数量サマリの要確認）")
    if model.plan.corner_steps:
        wedge = any(cs.edge_index >= 0 for cs in model.plan.corner_steps)
        a("")
        a("## コーナーステップ（" + ("くさび: 離れを固定し、繋がらない隅はコーナーステップで納める"
                                   if wedge else "枠組: 離れ固定で余りをコーナーで吸収") + "）")
        a("")
        a("| コーナー | 面 | 隙間 | 判定 | 備考 |")
        a("|---|---|---|---|---|")
        for cs in model.plan.corner_steps:
            face = model.face_name(cs.edge_index) + "の終点" if cs.edge_index >= 0 else "-"
            rule = "隙間 150〜400mm（コマが当たらない）" if cs.edge_index >= 0 else "建枠70mm以上・ステップ250mm以内"
            a(f"| {cs.corner_index} | {face} | {cs.gap_mm:.0f}mm | "
              f"{'OK' if cs.ok else 'NG'} | {cs.message or rule} |")
    if stair_plan is not None and stair_plan.towers:
        a("")
        a("## 昇降設備（階段室）")
        a("")
        a(f"- 箇所数: {stair_plan.count}（移動距離30m以内に必要な数: "
          f"{stair_plan.required_count}）")
        a(f"- 最大水平移動距離: {stair_plan.max_travel_mm / 1000:.1f}m")
        a("- 昇り方: 同じ向きで2層ずつ（奇数層へは始点側、偶数層へは終点側のスパン）。"
          "2層ごとに階段室を出て外の作業床を通る（作業床が踊り場を兼ねるので踊り場の床は使わない）")
        a("- 階段室の床: 各層で階段が上がってくる1スパンだけ開口、もう一方のスパンには床を敷く")
        a("")
        a("| # | 辺 | 始点からの位置 | 占有 | 選定理由 |")
        a("|---|---|---|---|---|")
        for i, t in enumerate(stair_plan.towers, 1):
            a(f"| {i} | {t.edge_index} | {t.start_mm:.0f}mm | "
              f"{t.span_count}スパン({t.length_mm:.0f}mm) | "
              f"{t.reason or ('位置指定' if t.manual else '自動配置')} |")
        # 必要数を大きく超える配置は費用に効くので、そうと分かるように書く
        if stair_plan.count > stair_plan.required_count:
            a("")
            a(f"> 移動距離の目安を満たすだけなら{stair_plan.required_count}箇所で足ります"
              f"（現在{stair_plan.count}箇所）。各面配置などの方針で増えている分です。")
        for w in stair_plan.warnings:
            a(f"- ⚠️ {w}")
    a("")
    a("## 法規チェック")
    a("")
    a("| # | 項目 | 判定 | 内容 | 根拠 |")
    a("|---|---|---|---|---|")
    for c in checks:
        mark = {"OK": "✅", "WARN": "⚠️", "NG": "❌"}.get(c.status, c.status)
        a(f"| {c.check_id} | {c.name} | {mark} {c.status} | {c.message} | {c.basis} |")
    a("")
    a("## 壁つなぎ")
    a("")
    v_lim, h_lim, tie_basis = model.wall_tie_limits()
    v_max, h_max = model.wall_tie_max_spacing()
    from .ties import kind_labels, tie_counts

    counts = tie_counts(model)
    labels = kind_labels(model)
    breakdown = "／".join(f"{labels.get(k, k)} {n}" for k, n in counts.items() if k != "grid")
    a(f"- 本数: {len(model.wall_ties)}箇所"
      + (f"（格子{counts.get('grid', 0)}＋{breakdown}。同じ位置は同じ金具で兼ねる）" if breakdown else ""))
    a(f"- 実配置の最大間隔: 垂直{v_max:.0f}mm × 水平{h_max:.0f}mm "
      f"（法定 垂直{v_lim:.0f} × 水平{h_lim:.0f}以下）")
    a(f"- 根拠: {tie_basis}")
    untied = model.edges_without_wall_ties()
    if untied:
        a("- ⚠️ 壁つなぎが入らない面: "
          + "、".join(f"{model.face_name(i)}" for i in untied)
          + "（両隣の面にコーナー経由で支持される前提。単管等での別途拘束を検討）")

    if structural is not None:
        w, t, ps = structural.wind, structural.wall_tie, structural.post
        a("")
        a("## 構造計算（有資格者の確認前提の下書き）")
        a("")
        a(f"- 設計風速 V = {w.v_design_ms}m/s（V0={w.v0_ms} × K={w.k_height} "
          f"× E={w.e_adjacent} × S={w.s_region}）／速度圧 q = {w.q_n_m2}N/m²")
        a(f"- 風力係数 C = {w.c_force}（養生材 {structural.site.sheet_type}・充実率{w.fill_ratio}）")
        a("")
        a("| 検定 | 作用 | 許容 | 検定比 | 判定 |")
        a("|---|---|---|---|---|")
        a(f"| 壁つなぎ | {t.force_kn}kN | {t.allowable_increased_kn}kN（×1.3） "
          f"| {t.ratio} | {'✅ OK' if t.ok else '❌ NG'} |")
        a(f"| 建地圧縮 | {ps.total_kn}kN | {ps.allowable_kn}kN "
          f"| {ps.ratio} | {'✅ OK' if ps.ok else '❌ NG'} |")
        a("")
        a(f"- 支配的な壁つなぎ: {t.governing or '—'}（支配面積{t.tributary_area_m2}m²）")
        a(f"- 建地の支配検定: {ps.governing}")
        a(f"- 建地1本の内訳: 自重{ps.dead_load_kn}kN ＋ 積載{ps.live_load_kn}kN"
          + (f" ＋ 局所{ps.extra_load_kn}kN" if ps.extra_load_kn > 0 else ""))
        if ps.inner_uplift_kn > 0:
            a(f"- 内側建地の引抜き: {ps.inner_uplift_kn}kN vs 自重{ps.dead_load_kn}kN "
              f"→ {'✅ 浮かない' if ps.uplift_ok else '⚠️ 自重超過（方杖の効果を見込まない値。浮き止めの要否を要確認）'}")
        for oc in structural.openings:
            a(f"- 開口部 {model.face_name(oc.edge_index)} 梁枠{oc.beam_model}: 支点 {oc.support_kn}kN"
              + (f" / {oc.support_allow_kn}kN" if oc.support_allow_kn is not None else "（許容はマスタに無し）")
              + f"、両端{model.master.vertical_member_name} {oc.end_post_kn}kN / {oc.end_post_allow_kn}kN"
              + f"、梁枠上の積載 {oc.live_above_kn}kN"
              + (f" / {oc.live_limit_kn}kN" if oc.live_limit_kn is not None else "")
              + (f" → ✅ OK（{oc.condition}）" if oc.ok and oc.condition else
                 (" → ✅ OK" if oc.ok else " → ❌ 要対応")))
        for nmsg in structural.notes:
            a(f"- ℹ️ {nmsg}")
        for wmsg in structural.warnings:
            a(f"- ⚠️ {_short(wmsg, listed)}")

    if terrain is not None and terrain.gl_difference_mm > 0:
        a("")
        a("## 敷地の高低差")
        a("")
        a(f"- 高低差: {terrain.gl_difference_mm:.0f}mm "
          f"／ 脚部構成 {len({f.koma_offset for f in terrain.feet})}種類")
        a(f"- ジャッキ繰出し: {terrain.jack_min_mm:.0f}〜{terrain.jack_max_mm:.0f}mm")
        need_plate = [f for f in terrain.feet if abs(f.base_plate_adjust_mm) > 1e-6]
        if need_plate:
            a(f"- 敷板・床掘りでの調整が要る{vm}: {len(need_plate)}本"
              f"（{vm}ごとの量はジャッキ量一覧CSV）")
        a(f"- 作業床レベルは全周で通し、高低差は{vm}ごとのジャッキと{vm}長で吸収しています")
        # terrain.notes は上の箇条書き（高低差・脚部構成）と同じ内容なので出さない。
        # 対応が要るものだけ出す
        for wmsg in terrain.warnings:
            if wmsg in in_law_table:
                head = wmsg.split("。")[0]
                a(f"- ⚠️ {head}（法規チェック6を参照）")
            else:
                a(f"- ⚠️ {_short(f'敷地: {wmsg}', listed)}")

    extras = []
    if bracket_sections:
        extras.append(f"ブラケット区間 {len(bracket_sections)}箇所")
    if platforms is not None and platforms.stages:
        extras.append(f"荷受けステージ {len(platforms.stages)}基")
    if platforms is not None and platforms.hoists:
        extras.append(f"昇降機 {len(platforms.hoists)}基")
    if openings is not None and openings.openings:
        extras.append(f"開口部（梁枠）{len(openings.openings)}箇所")
    if extras:
        a("")
        a("## 付帯設備")
        a("")
        a("- " + "／".join(extras))
        if platforms is not None and platforms.max_post_load_kn > 0:
            a(f"- ステージ直下の建地に加わる軸力: {platforms.max_post_load_kn:.2f}kN"
              f"（{platforms.governing}）")
        # 昇降機は「1基」だけでは位置も乗り込み口も分からない。
        # マストの位置・到達高さ・乗り込み口の層を出す（干渉と防護の確認用）
        for h in (getattr(platforms, "hoists", None) or []):
            face = model.face_name(h.edge_index)
            reach = h.reach_height_mm or model.scaffold_height_mm
            landings = h.landings(model)
            hm = h.spec
            guard = "開閉式手すり"
            if hm is not None and hm.gate:
                from .hoist_models import FLOOR_GATES

                guard = FLOOR_GATES.get(hm.gate, {}).get("name", "フロアーゲート")
            a(f"- 昇降機: {face} 始点から{h.position_mm:.0f}mm・"
              + (f"機種 {hm.name}・" if hm is not None else "")
              + f"到達高さ{reach:.0f}mm・乗り込み口 第{'・'.join(str(l) for l in landings)}層"
              f"（各層の開口は{guard}で防護／安衛則563条）")
        if openings is not None and openings.removed_posts:
            vm = model.master.vertical_member_name
            a(f"- 開口部で抜いた{vm}: {openings.removed_posts}本"
              f"（両端{vm}の軸力と梁枠上の積載制限は構造計算の開口部の行を参照）")
        # ブラケット区間は「1箇所」だけでは何をするか分からない。
        # どの面のどの範囲を、どちら向きに、どの幅で持ち出す/追従するかを出す
        for b in (bracket_sections or []):
            face = model.face_name(b.edge_index)
            if b.direction == "張出":
                arm = "張出"
            elif getattr(b, "auto", False):
                arm = f"内（離れを詰めるため自動・踏板{b.inner_deck_width}）"
            elif getattr(b, "inner_deck_width", None):
                arm = f"内（躯体側へ踏板{b.inner_deck_width}）"
            else:
                arm = "内（躯体側へ追従）"
            detail = (f"- ブラケット区間: {face} {b.start_mm:.0f}〜{b.end_mm:.0f}mm"
                      f"・{arm}・ブラケット{b.width}")
            if b.deck_width:
                detail += f"・床幅{b.deck_width}に変更"
            if b.levels:
                detail += f"・第{'・'.join(str(l) for l in b.levels)}層"
            a(detail)

    a("")
    a("## 数量サマリ")
    a("")
    a(f"- 総重量: {quantity.total_weight_kg}kg / トラック概算: 4t車{quantity.truck_count}台")
    a(f"- 架け面積: {quantity.kake_menseki_m2}m²（(外周+4m)×(高さ+0.5m)）")
    # 分類別の規模感を1画面で（明細は数量表CSV・部材等明細書）
    cats = quantity.category_totals()
    if cats:
        a("")
        a("| 分類 | 数量計 | 重量計kg |")
        a("|---|---|---|")
        for c, q, wt in cats:
            a(f"| {c} | {q} | {wt} |")
        a("")
    dup = [n for n in quantity.warnings if n in listed]
    if dup:
        # 全文は末尾の一覧にある。同じ長文を2箇所に並べない
        a(f"- **要手配・要検討 {len(dup)}件**（末尾の要確認一覧を参照）")
    for n in quantity.warnings:
        if n not in listed:
            a(f"- **要手配・要検討**: {n}")
    for n in quantity.notes:
        if n not in quantity.warnings:
            a(f"- 注記: {n}")
    items = checklist
    if items:
        a("")
        a("## 要確認一覧")
        a("")
        a("計画は成立していますが、着手前に次の項目を確認・措置してください。"
          if verdict is None or verdict["ok"] else
          "是正項目とは別に、着手前に次の項目を確認・措置してください。")
        a("")
        a("| # | 分類 | 内容 |")
        a("|---|---|---|")
        for i, (kind, text) in enumerate(items, 1):
            a(f"| {i} | {kind} | {text} |")

    a("")
    a("> 本レポートは計画作成参画者（有資格者）が確認する前提の下書きです。")
    a("> 部材形状はカタログ寸法からの再現。単位重量はマスタのカタログ値で、型番仮の行（要確認一覧に品番を明示）だけ概算値。")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_jack_table_csv(terrain, path: Path) -> None:
    """支柱ごとのジャッキ量一覧（敷地高低差対応・本ツールの差別化機能）."""
    from .terrain import jack_table_rows

    rows = jack_table_rows(terrain)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        for row in rows:
            w.writerow(row)
        w.writerow([])
        w.writerow(["基準GL(mm)", round(terrain.reference_gl_mm, 1)])
        w.writerow(["GL範囲(mm)", round(terrain.gl_range_mm[0], 1),
                    round(terrain.gl_range_mm[1], 1)])
        w.writerow(["高低差(mm)", round(terrain.gl_difference_mm, 1)])
        w.writerow(["ジャッキ繰出し範囲(mm)", round(terrain.jack_min_mm, 1),
                    round(terrain.jack_max_mm, 1)])
        for note in terrain.warnings:
            w.writerow(["注記", note])


def write_plan_json(
    model: ScaffoldModel,
    path: Path,
    stair_plan=None,
    terrain=None,
    platforms=None,
    openings=None,
    bracket_sections=None,
    warnings=None,
) -> None:
    """GDL配置・再編集用の機械可読データ.

    「配置用」と謳う以上、これだけで再配置できる必要がある。以前は
    系列と割付しか入っておらず、内外建地間隔・踏板幅・手すり高さ・
    建地列数といったGDLパラメータも、配置座標も回転角も無かったため、
    読む側が割付を解き直さないと配置できなかった。

    出力スキーマ（読む側の実装が推測しなくて済むよう明記する）:
    {
      "series_id": "nikken_nd1800",     // 系列（既定は日建ND1800・フィート寸法）。混在は不可（系列ロック）
      "system_type": "くさび" | "枠組" | "単管",
      "koma_pitch": 450,                 // 枠組は0（コマの概念が無い）、単管は高さの刻み50
      "scaffold_height_mm": 16300,
      "config": {                        // 図面・数量に効く設定
        "scaffold_form": "本足場" | "一側足場",
        "single_row_kind": "" | "ブラケット" | "抱き",   // 建地1列の組み方
        "bracket_post": "支柱" | "単管",  // ブラケット足場の建地
        "form_label": "単管抱き足場",     // 帳票に書く形式
        "deck_widths": [400, 250],       // 実際に敷く幅（一側は1枚）
        "post_row_spacing_mm": 600,      // 内外建地列の芯々
        "guard_rail_type": "布材" | "先行手すり",
        "post_reinforcement": "" | "強力つなぎ材",
        "guard_rail_height_mm": 900, "midrail_height_mm": 450,
        "toe_board_height_mm": 157, "next_gen": false, "period_days": 90
      },
      "elevation": {
        "jack_extension": 100,           // ジャッキ繰出し（平坦時）
        "posts": [3600, ...],            // 下から積む支柱（枠組は建枠高さ）
        "posts_alt": [...],              // 千鳥用の並べ替え
        "level_heights": [550, ...],     // 作業床高さ（GLから）
        "first_ledger_height": 550
      },
      "edges": [{                        // 面ごと。1辺=1オブジェクト
        "edge_index": 0, "face": "南面",
        "spans": [1800, ...], "scaffold_length": 30600.0, "standoff": 350.0,
        "start_post": [x, y], "end_post": [x, y],
        "remedy": null,                  // 離れ超過時の対処案
        "placement": {"x_mm": .., "y_mm": .., "angle_deg": ..},
        "gdl_params": {...}              // set_gdl_parameters にそのまま渡せる
      }],
      "scaffold_vertices": [[x, y], ...],// 足場中心線ループ
      "outline_mm": [[x, y], ...],       // 躯体外形（配置に使ったスラブ）
      "wall_ties": [{"edge_index": 0, "position_mm": 3600.0, "height_mm": 4600,
                     "kind": "grid"}],   // kind: grid / asagao / stage / hoist
      "base_height_mm": 0.0,             // 足場の立つ高さ（下の屋根から建てた上の部分）
      "warnings": [...],                 // 割付・立面の警告
      // 以下は該当があるときだけ入る
      "stairs": {"count": 2, "max_travel_mm": 28800.0,
                 "landings_per_tower": 3, "towers": [...]},
      "openings": [{"edge_index": 0, "start_mm": 3600.0,
                    "beam_span_mm": 3600, "level": 2, "reason": ""}],
      "platforms": {"stages": [...], "hoists": [...], "extra_wall_ties": 0},
      "bridged_zones": [{"kind": "凹み", "edge_index": 0, "start_mm": 12300.0,
                         "end_mm": 15900.0, "span_count": 3, "width_mm": 3600.0,
                         "depth_mm": 300.0,
                         "deep_end": "uniform"}],   // 直線で渡した凹み・張り出し（無ければ省略）（deep_end: 離れの増え方 uniform＝一定／end＝終点側で最大／start＝始点側で最大、斜辺の置き換え）
      "bracket_sections": [{"edge_index": 0, "start_mm": 0.0, "end_mm": 5400.0,
                            "direction": "内" | "張出", "width": 300,
                            "deck_width": null, "levels": [1], "has_hozue": false,
                            "is_widening": false, "on_kessokubu": false,
                            "reason": "",
                            "inner_deck_width": null, "auto": false}],   // inner_deck_width: 内ブラケットに敷く踏板の幅（離れを詰める）／auto: 離れ350超でツールが自動で付けた区間
      "terrain": {"reference_gl_mm": 0.0, "gl_difference_mm": 0.0,
                  "deck_levels_abs_mm": [...], "feet": [...]}
    }
    """
    from .gdl_params import line_params, placement_of

    cfg = model.config
    data = {
        "series_id": model.master.series_id,
        "system_type": model.master.system_type,
        "koma_pitch": model.master.koma_pitch,
        "scaffold_height_mm": model.scaffold_height_mm,
        "config": {
            "scaffold_form": cfg.scaffold_form,
            "single_row_kind": cfg.single_row_kind,
            "bracket_post": cfg.bracket_post,
            "form_label": cfg.form_label,
            "deck_widths": list(cfg.deck_widths or []),
            "post_row_spacing_mm": model.post_row_spacing_mm,
            "guard_rail_type": cfg.guard_rail_type,
            "post_reinforcement": cfg.post_reinforcement,
            "guard_rail_height_mm": model.guard_rail_height_mm,
            "midrail_height_mm": model.midrail_height_mm,
            "toe_board_height_mm": cfg.toe_board_height_mm,
            "next_gen": cfg.next_gen,
            "period_days": cfg.period_days,
        },
        "elevation": {
            "jack_extension": model.elevation.jack_extension,
            "posts": model.elevation.posts,
            "posts_alt": model.elevation.posts_alt,
            "level_heights": model.elevation.level_heights,
            "first_ledger_height": model.elevation.first_ledger_height,
        },
        "edges": [
            {
                "edge_index": ep.edge_index,
                "face": face,
                "spans": ep.spans,
                "scaffold_length": ep.scaffold_length,
                "standoff": ep.standoff,
                "start_post": list(ep.start_post),
                "end_post": list(ep.end_post),
                "remedy": ep.remedy,
                # そのまま set_gdl_parameters に渡せる形で持つ
                "placement": placement_of(model, ep.edge_index),
                "gdl_params": line_params(
                    model, ep, stair_plan=stair_plan, openings=openings,
                    platforms=platforms, bracket_sections=bracket_sections,
                    terrain=terrain,
                ),
            }
            for ep, face in zip(model.plan.edges, model.plan.face_names())
        ],
        "scaffold_vertices": [list(v) for v in model.plan.scaffold_vertices],
        # 躯体外形（読み戻し→解き直しがスラブの選択なしで動くように）
        "outline_mm": [list(v) for v in model.plan.outline.vertices],
        "wall_ties": [asdict(t) for t in model.wall_ties],
        # 足場の立つ高さ（上の部分を下の屋根から建てたとき）。壁つなぎの読み戻しで高さを戻すのに使う
        "base_height_mm": float(model.base_height_mm),
        "warnings": model.plan.warnings + model.elevation.warnings,
    }
    if stair_plan is not None and stair_plan.towers:
        data["stairs"] = {
            "count": stair_plan.count,
            "max_travel_mm": round(stair_plan.max_travel_mm, 1),
            "landings_per_tower": stair_plan.landings_per_tower,
            "towers": [asdict(t) for t in stair_plan.towers],
        }
    if openings is not None and openings.openings:
        data["openings"] = [asdict(o) for o in openings.openings]
    if bracket_sections:
        # 区間指定は利用者の入力。再編集用データなら往復できないと意味がない
        data["bracket_sections"] = [asdict(b) for b in bracket_sections]
    # 直線で渡した凹み・張り出し（辺上の区間・スパン数・増える離れ）。
    # 平面図の破線・数量の要確認と同じ区間を機械可読で持つ
    zones = getattr(model.plan, "bridged_zones", None) or []
    if zones:
        data["bridged_zones"] = [asdict(z) for z in zones]
    if platforms is not None and (platforms.stages or platforms.hoists):
        data["platforms"] = {
            "stages": [asdict(s) for s in platforms.stages],
            "hoists": [asdict(h) for h in platforms.hoists],
            "extra_wall_ties": platforms.extra_wall_ties,
        }
    if terrain is not None and terrain.feet:
        data["terrain"] = {
            "reference_gl_mm": round(terrain.reference_gl_mm, 1),
            "gl_difference_mm": round(terrain.gl_difference_mm, 1),
            "deck_levels_abs_mm": [round(v, 1) for v in terrain.deck_levels_abs_mm],
            "feet": [
                {
                    "index": f.index, "x": round(f.x, 1), "y": round(f.y, 1),
                    "gl_mm": round(f.gl_mm, 1), "koma_offset": f.koma_offset,
                    "jack_mm": round(f.jack_mm, 1),
                    "base_plate_adjust_mm": round(f.base_plate_adjust_mm, 1),
                    "posts": f.posts,
                }
                for f in terrain.feet
            ],
        }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
