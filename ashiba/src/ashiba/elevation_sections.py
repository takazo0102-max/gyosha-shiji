"""足場の立面図を Archicad の断面図（立面ツール相当）で作り、レイアウトに置く.

以前は立面図を平面図の下に 2D オブジェクト（ashiba_line の viewMode=elev）として並べていた。
Archicad の流儀では立面は立面図／断面図ビューポイントで 3D から投影し、図面としてレイアウトに
置く。Tapir には立面図マーカーを作る命令が無いので、切断線を足場の外側に置いて躯体側を見る
断面図を面ごとに作る（見え方は立面図と同じ）。断面はモデルの 3D（支柱・布材・斜材・階段・
付帯設備）をそのまま映すので、平面の 2D オブジェクトと食い違わない。

面ごとに:
  1. 切断線: 足場の外側建地列からさらに clearance 外、面の両端を ext 延長。向きは
     始点→終点（外形が反時計回りなので左手＝躯体側を見る。Tapir の CreateSections は
     始点→終点の左手を見る向きで作る）
  2. 奥行き: 切断線から躯体の最も遠い頂点まで（向こう側の足場は入れない）
  3. レイアウトブックのサブセット「仮設足場」の下に面ごとのレイアウトを作り、
     用紙（マスターレイアウト）に収まる縮尺で図面を置く
同じ名前の断面・レイアウトが残っていれば先に消す（再実行で置き換え）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Optional

from .model import ScaffoldModel

SUBSET_NAME = "仮設足場"
CLEARANCE_MM = 3500.0        # 外側建地列から切断線まで（ステージ出1500・昇降機の搬器と マストの外側 ≈2.5m を越える）
END_EXT_MM = 2000.0          # 面の両端の延長（出隅コーナー・隣の面の端部が入る）
DEPTH_MARGIN_MM = 300.0      # 躯体の最遠点からの余裕
SCALE_CANDIDATES = (100, 200, 300, 500)


@dataclass
class SectionSpec:
    face_name: str
    name: str
    start_mm: tuple[float, float]
    end_mm: tuple[float, float]
    depth_mm: float
    length_mm: float


@dataclass
class DrawingPlan:
    scale: int                       # 縮尺の分母（100 → 1/100）
    position_mm: tuple[float, float]  # 用紙上の図面の左下（mm）
    paper_mm: tuple[float, float]     # 用紙の幅・高さ（mm）


@dataclass
class ElevationPlacement:
    """1面ぶんの結果（再配置・撤去・帳票の照合用）."""
    face_name: str
    section_name: str
    section_guid: str = ""
    section_item_guid: str = ""
    layout_name: str = ""
    layout_item_guid: str = ""
    drawing_guid: str = ""
    scale: int = 100
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- 幾何（純粋関数）

def section_name(prefix: str, face_name: str) -> str:
    return f"{prefix} {face_name} 足場立面"


def layout_name(prefix: str, face_name: str) -> str:
    return f"{prefix} 足場立面図 {face_name}"


def section_specs(model: ScaffoldModel, prefix: str = "足場",
                  clearance_mm: float = CLEARANCE_MM, end_ext_mm: float = END_EXT_MM) -> list[SectionSpec]:
    """面ごとの切断線（mm, 絶対座標）と奥行き.

    足場ラインの配置と同じ座標系: 面の始点支柱 start_post → 終点支柱 end_post が内側建地列。
    外形は反時計回りなので躯体は進行方向の左、外側建地列は右（局所 y=-rowW）。
    """
    verts = [(float(x), float(y)) for x, y in model.plan.outline.vertices]
    row_w = float(model.post_row_spacing_mm)
    out: list[SectionSpec] = []
    for ep in model.plan.edges:
        sx, sy = ep.start_post
        ex, ey = ep.end_post
        dx, dy = ex - sx, ey - sy
        length = math.hypot(dx, dy)
        if length < 1e-6:
            continue
        ux, uy = dx / length, dy / length
        # 右手（外側）と左手（躯体側）
        ox, oy = uy, -ux
        nx, ny = -ox, -oy
        off = row_w + clearance_mm
        s = (sx + ox * off - ux * end_ext_mm, sy + oy * off - uy * end_ext_mm)
        e = (ex + ox * off + ux * end_ext_mm, ey + oy * off + uy * end_ext_mm)
        # 奥行き: 切断線から躯体の最も遠い頂点まで
        far = max(((vx - s[0]) * nx + (vy - s[1]) * ny) for vx, vy in verts) if verts else off
        depth = max(far, off) + DEPTH_MARGIN_MM
        face = model.face_name(ep.edge_index)
        out.append(SectionSpec(face, section_name(prefix, face), s, e, depth, length + 2 * end_ext_mm))
    return out


def drawing_plan(section_length_mm: float, scaffold_height_mm: float, paper_mm: tuple[float, float],
                 margins_mm: tuple[float, float, float, float] = (20.0, 20.0, 20.0, 20.0),
                 title_band_mm: float = 60.0) -> DrawingPlan:
    """用紙に収まる縮尺（1/100 から）と図面の位置（用紙の左下から mm）.

    margins は (左, 上, 右, 下)。下に図面タイトル帯（title_band）を空ける。
    """
    pw, ph = paper_mm
    left, top, right, bottom = margins_mm
    usable_w = pw - left - right - 10.0
    usable_h = ph - top - bottom - title_band_mm
    scale = SCALE_CANDIDATES[-1]
    for cand in SCALE_CANDIDATES:
        if section_length_mm / cand <= usable_w and (scaffold_height_mm + 2000.0) / cand <= usable_h:
            scale = cand
            break
    return DrawingPlan(scale=scale, position_mm=(left + 10.0, bottom + title_band_mm), paper_mm=paper_mm)


# ---------------------------------------------------------------- ナビゲータツリー

def walk_tree(node: dict, depth: int = 0) -> Iterable[dict]:
    """GetNavigatorItemTree の応答を平らに（type, name, guid, depth）."""
    yield {"type": node.get("type"), "name": node.get("name", ""), "prefix": node.get("prefix", ""),
           "guid": (node.get("navigatorItemId") or {}).get("guid", ""), "depth": depth}
    for ch in node.get("children", []) or []:
        yield from walk_tree(ch.get("navigatorItem", ch), depth + 1)


def find_items(tree: dict, item_type: str, name: Optional[str] = None, contains: Optional[str] = None) -> list[dict]:
    out = []
    for it in walk_tree(tree):
        if it["type"] != item_type:
            continue
        if name is not None and it["name"] != name:
            continue
        if contains is not None and contains not in it["name"]:
            continue
        out.append(it)
    return out


def pick_master_layout(masters: list[dict], prefer: str = "A1") -> Optional[dict]:
    """マスターレイアウト（用紙）。A1 を優先、無ければ最初のもの（フォルダ「マスタ」は除く）."""
    cands = [m for m in masters if m["name"] not in ("マスタ", "マスターレイアウト", "")]
    for m in cands:
        if prefer in m["name"]:
            return m
    return cands[0] if cands else None


# ---------------------------------------------------------------- Tapir 操作

def _tree(client, map_id: str) -> dict:
    return client.tapir("GetNavigatorItemTree", {"navigatorMapId": map_id})["navigatorItemTree"]


def _delete_items(client, guids: list[str]) -> int:
    if not guids:
        return 0
    client.tapir("DeleteNavigatorItems", {"navigatorItemIds": [{"navigatorItemId": {"guid": g}} for g in guids]})
    return len(guids)


def remove_elevations(client, names: Iterable[str], layout_names: Iterable[str],
                      section_guids: Iterable[str] = ()) -> tuple[int, int, list[str]]:
    """前回の断面（要素 GUID）とレイアウト（名前）を消す。戻り値は (断面, レイアウト, 消せなかった断面名).

    断面のナビゲータ項目は DeleteNavigatorItems で消せない（実機で "Failed to delete navigator item"）。
    断面は CutPlane 要素として DeleteElements で消えるので、配置時に控えた GUID で消す。
    GUID が無い（控えが消えた）同名の断面は残るので名前を返して注意に出す。
    """
    names = set(names)
    layout_names = set(layout_names)
    guids = [g for g in section_guids if g]
    n_sec = 0
    if guids:
        client.tapir("DeleteElements", {"elements": [{"elementId": {"guid": g}} for g in guids]})
        n_sec = len(guids)
    lb = _tree(client, "LayoutBook")
    lays = [it["guid"] for it in walk_tree(lb) if it["type"] == "LayoutItem" and it["name"] in layout_names]
    n_lay = _delete_items(client, lays)
    pm = _tree(client, "ProjectMap")
    left = [it["name"] for it in walk_tree(pm) if it["type"] == "SectionItem" and it["name"] in names]
    return n_sec, n_lay, left


def remove_all_scaffold_elevations(client, section_guids: Iterable[str] = (), prefix_contains: str = "足場立面") -> tuple[int, int, list[str]]:
    """控えた断面（要素）と、名前に「足場立面」を含むレイアウトを全部消す（撤去 --all 用）.

    サブセットは Archicad API で消せない（"Deleting layout subsets is not supported"）ので残る。
    戻り値は (断面, レイアウト, 残った断面名)。
    """
    lb = _tree(client, "LayoutBook")
    lays = [it["guid"] for it in walk_tree(lb) if it["type"] == "LayoutItem" and prefix_contains in it["name"]]
    guids = [g for g in section_guids if g]
    if guids:
        client.tapir("DeleteElements", {"elements": [{"elementId": {"guid": g}} for g in guids]})
    n_l = _delete_items(client, lays)
    pm = _tree(client, "ProjectMap")
    left = [it["name"] for it in walk_tree(pm) if it["type"] == "SectionItem" and prefix_contains in it["name"]]
    return len(guids), n_l, left


def ensure_subset(client, name: str = SUBSET_NAME) -> str:
    """レイアウトブック直下のサブセット（無ければ作る）。ID を返す.

    CreateLayoutSubset は作っても ID を返せないことがある（実機で確認）ので、作った後に
    ツリーを引き直して名前で見つける。
    """
    lb = _tree(client, "LayoutBook")
    hit = find_items(lb, "SubSetItem", name=name)
    if hit:
        return hit[0]["guid"]
    books = find_items(lb, "BookItem")
    if not books:
        raise RuntimeError("レイアウトブックが見つかりません")
    client.tapir("CreateLayoutSubset", {"subsetsData": [{"name": name, "parentNavigatorItemId": {"guid": books[0]["guid"]}}]})
    lb = _tree(client, "LayoutBook")
    hit = find_items(lb, "SubSetItem", name=name)
    if not hit:
        raise RuntimeError(f"サブセット「{name}」を作れませんでした")
    return hit[0]["guid"]


def _layout_paper_mm(client, layout_item_guid: str, fallback=(841.0, 594.0)) -> tuple[tuple[float, float], tuple[float, float, float, float]]:
    """レイアウトの用紙サイズと余白（mm）。取れなければ A1 横."""
    try:
        r = client.tapir("GetLayoutSettings", {"layoutDatabaseIds": [{"navigatorItemId": {"guid": layout_item_guid}}]})
        s = (r.get("layoutSettings") or [{}])[0]
        s = s.get("layoutSettings", s)
        pw, ph = float(s.get("horizontalSize", 0)), float(s.get("verticalSize", 0))
        if pw > 0 and ph > 0:
            m = (float(s.get("leftMargin", 20)), float(s.get("topMargin", 20)), float(s.get("rightMargin", 20)), float(s.get("bottomMargin", 20)))
            return (pw, ph), m
    except Exception:
        pass
    return fallback, (20.0, 20.0, 20.0, 20.0)


def place_section_elevations(model: ScaffoldModel, client, prefix: str = "足場", replace: bool = True,
                             previous: Optional[dict] = None) -> list[ElevationPlacement]:
    """面ごとの断面図を作り、サブセット「仮設足場」の下のレイアウトに図面として置く.

    previous は前回の控え {断面名: 要素GUID}（run_from_archicad が書く）。再実行で置き換える。
    """
    specs = section_specs(model, prefix)
    stale_notes: list[str] = []
    if replace:
        prev = previous or {}
        _, _, left = remove_elevations(client, [s.name for s in specs], [layout_name(prefix, s.face_name) for s in specs],
                                       [prev.get(s.name, "") for s in specs])
        if left:
            stale_notes.append("前回の断面「" + "・".join(left) + "」は控えが無く消せませんでした。プロジェクトマップで手で消してください")
    # 1. 断面（CutPlane 要素）
    resp = client.tapir("CreateSections", {"sectionsData": [
        {"startCoordinate": {"x": s.start_mm[0] / 1000.0, "y": s.start_mm[1] / 1000.0},
         "endCoordinate": {"x": s.end_mm[0] / 1000.0, "y": s.end_mm[1] / 1000.0},
         "depth": s.depth_mm / 1000.0, "name": s.name} for s in specs]})
    results: list[ElevationPlacement] = []
    for s, el in zip(specs, resp.get("elements", [])):
        pl = ElevationPlacement(face_name=s.face_name, section_name=s.name)
        pl.notes.extend(stale_notes)
        stale_notes = []
        if "elementId" in el:
            pl.section_guid = el["elementId"]["guid"]
        else:
            pl.notes.append(f"断面を作れませんでした: {el.get('error', el)}")
        results.append(pl)
    # 2. プロジェクトマップの項目（図面の元）
    pm = _tree(client, "ProjectMap")
    for pl in results:
        # 同名が残っていれば新しい方（最後）を使う
        hit = find_items(pm, "SectionItem", name=pl.section_name)
        if hit:
            pl.section_item_guid = hit[-1]["guid"]
        else:
            pl.notes.append("プロジェクトマップに断面が見つかりません")
    # 3. レイアウトと図面
    subset = ensure_subset(client)
    lb = _tree(client, "LayoutBook")
    master = pick_master_layout([it for it in walk_tree(lb) if it["type"] and "Master" in it["type"]])
    for pl, s in zip(results, specs):
        if not pl.section_item_guid:
            continue
        pl.layout_name = layout_name(prefix, pl.face_name)
        data = {"layoutName": pl.layout_name, "parentNavigatorItemId": {"guid": subset}}
        if master:
            data["masterNavigatorItemId"] = {"guid": master["guid"]}
        client.tapir("CreateLayout", {"layoutsData": [data]})
        lb = _tree(client, "LayoutBook")
        hit = find_items(lb, "LayoutItem", name=pl.layout_name)
        if not hit:
            pl.notes.append("レイアウトを作れませんでした")
            continue
        pl.layout_item_guid = hit[-1]["guid"]
        db = client.tapir("GetDatabaseIdFromNavigatorItemId", {"navigatorItemIds": [{"navigatorItemId": {"guid": pl.layout_item_guid}}]})
        dbid = db["databases"][0]["databaseId"]
        paper, margins = _layout_paper_mm(client, pl.layout_item_guid)
        plan = drawing_plan(s.length_mm, float(model.scaffold_height_mm), paper, margins)
        pl.scale = plan.scale
        dr = client.tapir("CreateDrawings", {"drawingsData": [{
            "navigatorItemId": {"guid": pl.section_item_guid}, "layoutDatabaseId": dbid,
            "position": {"x": plan.position_mm[0] / 1000.0, "y": plan.position_mm[1] / 1000.0},
            "drawingScale": float(plan.scale), "name": f"{pl.face_name} 足場立面図 1/{plan.scale}"}]})
        el = (dr.get("elements") or [{}])[0]
        if "elementId" in el:
            pl.drawing_guid = el["elementId"]["guid"]
            try:
                client.tapir("UpdateDrawings", {"elements": [el]})
            except Exception:
                pass
        else:
            pl.notes.append(f"図面を置けませんでした: {el.get('error', el)}")
    return results


ELEVATIONS_RECORD = "elevation_sections.json"


def load_record(out_dir) -> dict:
    """前回の控え {断面名: 要素GUID}（無ければ空）."""
    import json
    from pathlib import Path

    p = Path(out_dir) / ELEVATIONS_RECORD
    if not p.exists():
        return {}
    try:
        return {str(k): str(v) for k, v in json.loads(p.read_text(encoding="utf-8")).items()}
    except Exception:
        return {}


def save_record(out_dir, placements: list[ElevationPlacement], previous: Optional[dict] = None) -> dict:
    """今回置いた断面の GUID を控えに足して書く（他の建物の分は残す）."""
    import json
    from pathlib import Path

    rec = dict(previous or {})
    for pl in placements:
        if pl.section_guid:
            rec[pl.section_name] = pl.section_guid
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    (Path(out_dir) / ELEVATIONS_RECORD).write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return rec
