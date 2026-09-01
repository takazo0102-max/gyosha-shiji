"""Archicad接続層（Tapirアドオン経由）.

⚠️ このモジュールだけがArchicadに依存する。割付エンジン本体はArchicad無しで動く。
⚠️ Archicad実機での動作検証は未実施（開発環境にArchicadが無いため）。
   実機で GetSelectedElements / GetDetailsOfElements / CreateObjects /
   SetGDLParametersOfElements のレスポンス形式を確認しながら調整すること。

前提:
- Archicad 27+ / Tapir Additional JSON Commands アドオン導入済み
- pip install archicad（Archicad同梱のPython環境なら同梱済み）
- 「足場ライン」オブジェクト(ashiba_line)がプロジェクトのライブラリに読込済み
"""

from __future__ import annotations

from typing import Any, Optional

from .model import ScaffoldModel


class TapirError(Exception):
    pass


def _connect():
    try:
        from archicad import ACConnection  # type: ignore
    except ImportError as exc:
        raise TapirError(
            "archicad パッケージがありません。Archicad同梱Pythonで実行するか "
            "`pip install archicad` してください"
        ) from exc
    conn = ACConnection.connect()
    if not conn:
        raise TapirError("Archicadに接続できません（Archicadを起動し、JSON APIを有効にしてください）")
    return conn


def _tapir(conn, command: str, params: Optional[dict] = None) -> Any:
    """Tapirの AddOnCommand を実行する."""
    cmd_id = conn.types.AddOnCommandId("TapirCommand", command)
    return conn.commands.ExecuteAddOnCommand(cmd_id, params or {})


def get_selected_outline_mm(conn=None) -> list[tuple[float, float]]:
    """選択中のスラブ/メッシュ等から躯体外形ポリゴン[mm]を取得する.

    選択要素の1つ目のポリゴンを採用。座標はArchicad内部(m)→mmに変換。
    """
    conn = conn or _connect()
    sel = _tapir(conn, "GetSelectedElements")
    elements = sel.get("elements", []) if isinstance(sel, dict) else []
    if not elements:
        raise TapirError("要素が選択されていません。躯体スラブ（外形）を選択してください")
    details = _tapir(conn, "GetDetailsOfElements", {"elements": elements})
    for det in details.get("detailsOfElements", []):
        poly = _extract_polygon(det)
        if poly:
            return [(p[0] * 1000.0, p[1] * 1000.0) for p in poly]
    raise TapirError("選択要素から外形ポリゴンを取得できませんでした（スラブを選択してください）")


def _extract_polygon(details: dict) -> Optional[list[tuple[float, float]]]:
    """要素詳細からポリゴン座標を探す（要素種別によりキーが異なる）."""
    d = details.get("details", details)
    for key in ("polygonOutline", "polygon", "coordinates", "outline"):
        coords = d.get(key)
        if isinstance(coords, list) and len(coords) >= 3:
            pts = []
            for c in coords:
                if isinstance(c, dict) and "x" in c and "y" in c:
                    pts.append((float(c["x"]), float(c["y"])))
            if len(pts) >= 3:
                return pts
    return None


def place_scaffold_lines(
    model: ScaffoldModel,
    object_name: str = "ashiba_line",
    conn=None,
) -> list:
    """割付結果の各辺に「足場ライン」オブジェクトを1つずつ配置する.

    配置規約（GDL側と一致させる）: 原点=始点コーナー支柱、+X=辺方向。
    """
    conn = conn or _connect()
    e = model.elevation
    span_strs = []
    placements = []
    import math

    for ep, edge in zip(model.plan.edges, model.plan.outline.edges):
        angle = math.atan2(edge.direction[1], edge.direction[0])
        placements.append(
            {
                "objectName": object_name,
                "coordinates": {
                    "x": ep.start_post[0] / 1000.0,
                    "y": ep.start_post[1] / 1000.0,
                    "z": 0.0,
                },
                "angle": angle,
            }
        )
        span_strs.append(",".join(str(s) for s in ep.spans))

    created = _tapir(conn, "CreateObjects", {"objects": placements})
    ids = created.get("elements", []) if isinstance(created, dict) else []
    if len(ids) != len(placements):
        raise TapirError(
            f"オブジェクト配置数が一致しません: 要求{len(placements)} / 生成{len(ids)}"
        )

    post_str = ",".join(str(p) for p in e.posts)
    for elem, ep, span_str in zip(ids, model.plan.edges, span_strs):
        params = [
            {"name": "spanList", "value": span_str},
            {"name": "postList", "value": post_str},
            {"name": "jackOut", "value": e.jack_extension / 1000.0},
            {"name": "komaPitch", "value": model.master.koma_pitch / 1000.0},
            {"name": "floorH", "value": model.master.floor_height / 1000.0},
            {"name": "standoff", "value": ep.standoff / 1000.0},
        ]
        _tapir(
            conn,
            "SetGDLParametersOfElements",
            {"elements": [elem], "gdlParameters": params},
        )
    return ids


def get_post_ground_levels(model: ScaffoldModel, conn=None) -> list[dict]:
    """敷地メッシュから各支柱位置のGL標高を取得（Phase 4の骨組み。未検証）.

    メッシュが無い場合は全支柱 z=0 を返す。
    """
    positions = model.plan.post_positions()
    try:
        conn = conn or _connect()
        # Tapir: GetTerrainHeight系コマンドは環境により無いことがある
        return [
            {"x": x, "y": y, "gl_mm": 0.0, "jack_mm": model.elevation.jack_extension}
            for (x, y) in positions
        ]
    except TapirError:
        return [
            {"x": x, "y": y, "gl_mm": 0.0, "jack_mm": model.elevation.jack_extension}
            for (x, y) in positions
        ]
