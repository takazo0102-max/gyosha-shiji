"""Archicad接続層（Tapirアドオン経由、標準ライブラリのみで動作）.

`archicad` pipパッケージには依存せず、ArchicadのJSON API (http://127.0.0.1:19723)
へ urllib で直接POSTする。Tapir 1.5.8 / Archicad 28 (Mac) で実機検証済み
（スラブ外形取得→4辺配置→回転→GDLパラメータ設定のE2E: scripts/e2e_archicad_test.py）。

実機で確認済みの仕様・落とし穴:
- CreateObjects は libraryPartName + coordinates のみ受ける。回転は RotateElements で行う
  （ModifyObjects の details に angle を渡すとスキーマ違反になる）
- 埋め込みライブラリへのGSM追加は AddFilesToEmbeddedLibrary。同名の上書きは不可
  （エラー文言は「not a valid relative path」）。開発イテレーションは版名を変えて追加する
- Get3DBoundingBoxes はオブジェクトに「2D記号外形×高さ」のフォールバック値を返すことが
  ある。3D生成の検証には GetElementPreviewImage(imageType="3D") を使うこと
- スラブ詳細の外形キーは details.polygonOutline（終点=始点の閉じたループ、単位m）
"""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
from typing import Any, Optional

from .gdl_params import line_params
from .model import ScaffoldModel

DEFAULT_PORT = 19723


class TapirError(Exception):
    pass


class ArchicadClient:
    """Archicad JSON API + Tapir AddOnCommand の薄いクライアント."""

    def __init__(self, host: str = "127.0.0.1", port: int = DEFAULT_PORT, timeout: float = 60.0):
        self.url = f"http://{host}:{port}"
        self.timeout = timeout

    def post(self, command: str, parameters: Optional[dict] = None) -> dict:
        payload = {"command": command}
        if parameters is not None:
            payload["parameters"] = parameters
        req = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError) as exc:
            raise TapirError(
                f"Archicadに接続できません（{self.url}）。Archicadを起動してください: {exc}"
            ) from exc
        if not data.get("succeeded"):
            raise TapirError(f"{command} が失敗: {data.get('error')}")
        return data.get("result", {})

    def tapir(self, command: str, parameters: Optional[dict] = None) -> dict:
        result = self.post(
            "API.ExecuteAddOnCommand",
            {
                "addOnCommandId": {
                    "commandNamespace": "TapirCommand",
                    "commandName": command,
                },
                "addOnCommandParameters": parameters or {},
            },
        )
        resp = result.get("addOnCommandResponse", {})
        if isinstance(resp, dict) and resp.get("error"):
            raise TapirError(f"Tapir {command} が失敗: {resp['error']}")
        return resp

    # ---- 基本操作 ------------------------------------------------------

    def is_alive(self) -> bool:
        try:
            return bool(self.post("API.IsAlive").get("isAlive"))
        except TapirError:
            return False

    def tapir_version(self) -> str:
        return self.tapir("GetAddOnVersion").get("version", "")

    def get_selected_elements(self) -> list[dict]:
        return self.tapir("GetSelectedElements").get("elements", [])

    def get_details(self, elements: list[dict]) -> list[dict]:
        return self.tapir("GetDetailsOfElements", {"elements": elements}).get(
            "detailsOfElements", []
        )

    def get_3d_bboxes(self, elements: list[dict]) -> list[dict]:
        return self.tapir("Get3DBoundingBoxes", {"elements": elements}).get(
            "boundingBoxes3D", []
        )

    def delete_elements(self, elements: list[dict]) -> None:
        self.tapir("DeleteElements", {"elements": elements})

    def create_slab(
        self, polygon_mm: list[tuple[float, float]], level: float = 0.0, thickness: float = 0.3
    ) -> dict:
        data = {
            "slabsData": [
                {
                    "level": level,
                    "thickness": thickness,
                    "polygonCoordinates": [
                        {"x": x / 1000.0, "y": y / 1000.0} for (x, y) in polygon_mm
                    ],
                }
            ]
        }
        elements = self.tapir("CreateSlabs", data).get("elements", [])
        if not elements:
            raise TapirError("スラブを作成できませんでした")
        return elements[0]

    def create_object(
        self, library_part_name: str, x_mm: float, y_mm: float, z_mm: float = 0.0
    ) -> dict:
        data = {
            "objectsData": [
                {
                    "libraryPartName": library_part_name,
                    "coordinates": {
                        "x": x_mm / 1000.0,
                        "y": y_mm / 1000.0,
                        "z": z_mm / 1000.0,
                    },
                }
            ]
        }
        elements = self.tapir("CreateObjects", data).get("elements", [])
        if not elements:
            raise TapirError(f"オブジェクト {library_part_name} を配置できませんでした")
        return elements[0]

    def rotate_element(
        self, element: dict, angle_rad: float, origin_x_mm: float, origin_y_mm: float
    ) -> None:
        """要素を原点(origin)まわりに angle_rad 回転する（RotateElements）."""
        ox, oy = origin_x_mm / 1000.0, origin_y_mm / 1000.0
        self.tapir(
            "RotateElements",
            {
                "elementsWithRotations": [
                    {
                        "elementId": element["elementId"],
                        "rotation": {
                            "origin": {"x": ox, "y": oy},
                            "beginPoint": {"x": ox + 1.0, "y": oy},
                            "endPoint": {
                                "x": ox + math.cos(angle_rad),
                                "y": oy + math.sin(angle_rad),
                            },
                        },
                    }
                ]
            },
        )

    def set_gdl_parameters(self, element: dict, params: dict[str, Any]) -> None:
        """GDLパラメータを設定する.

        SetGDLParametersOfElements はコマンド自体は成功扱いで返し、
        個別の失敗は executionResults に入る。パラメータ名が1つでも
        オブジェクト側に無いと**全パラメータが適用されない**ので、
        握りつぶすと既定値のまま描かれた図面を「成功」と報告してしまう。
        （古いGSMに新パラメータを送って、立面図の代わりに平面図が
        出ているのに成功と出た実績がある）
        """
        resp = self.tapir(
            "SetGDLParametersOfElements",
            {
                "elementsWithGDLParameters": [
                    {
                        "elementId": element["elementId"],
                        "gdlParameters": [
                            {"name": k, "value": v} for k, v in params.items()
                        ],
                    }
                ]
            },
        )
        for r in resp.get("executionResults", []):
            if not r.get("success", True):
                err = r.get("error", {})
                raise TapirError(
                    "GDLパラメータの設定に失敗しました: "
                    f"{err.get('message', err)}"
                    f"（送信: {', '.join(params)}）"
                )

    def get_gdl_parameters(self, element: dict) -> dict:
        return self.tapir(
            "GetGDLParametersOfElements", {"elements": [element]}
        )

    def add_file_to_embedded_library(self, input_path: str, output_name: str) -> None:
        resp = self.tapir(
            "AddFilesToEmbeddedLibrary",
            {"files": [{"inputPath": input_path, "outputPath": output_name}]},
        )
        results = resp.get("executionResults", [])
        if results and not results[0].get("success"):
            raise TapirError(f"埋め込みライブラリへの追加に失敗: {results[0].get('error')}")

    def reload_libraries(self) -> None:
        self.tapir("ReloadLibraries")

    def find_red_pen(self, default: int = 20) -> int:
        """有効なペンテーブルから最も赤に近いペン番号を返す.

        警告表示に使う「赤」はペンテーブル依存（このプロジェクトのテーブルでは
        pen6は青、pen20が純赤だった）。番号を決め打ちせず実際の色から選ぶ。
        取得できない場合は default を返す。
        """
        try:
            attrs = self.tapir(
                "GetAttributesByType", {"attributeType": "PenTable"}
            ).get("attributes", [])
            if not attrs:
                return default
            res = self.tapir(
                "GetPenTables",
                {"attributeIds": [{"attributeId": attrs[0]["attributeId"]}],
                 "fields": ["pens"]},
            )
            pens = res["penTables"][0].get("pens", [])
            if not pens:
                return default

            def redness(p: dict) -> float:
                c = p["color"]
                return (c["red"] - 1.0) ** 2 + c["green"] ** 2 + c["blue"] ** 2

            return int(min(pens, key=redness)["index"])
        except (TapirError, KeyError, IndexError, TypeError):
            return default


# ---- 高水準API ----------------------------------------------------------


def get_selected_outline_mm(client: Optional[ArchicadClient] = None) -> list[tuple[float, float]]:
    """選択中のスラブから躯体外形ポリゴン[mm]を取得する."""
    client = client or ArchicadClient()
    elements = client.get_selected_elements()
    if not elements:
        raise TapirError("要素が選択されていません。躯体スラブ（外形）を選択してください")
    for det in client.get_details(elements):
        poly = _extract_polygon(det)
        if poly:
            return [(p[0] * 1000.0, p[1] * 1000.0) for p in poly]
    raise TapirError("選択要素から外形ポリゴンを取得できませんでした（スラブを選択してください）")


def _extract_polygon(details: dict) -> Optional[list[tuple[float, float]]]:
    d = details.get("details", details)
    for key in ("polygonOutline", "polygonCoordinates", "polygon", "coordinates", "outline"):
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
    client: Optional[ArchicadClient] = None,
    stair_plan=None,
    openings=None,
) -> list[dict]:
    """割付結果の各辺に「足場ライン」オブジェクトを1つずつ配置する.

    配置規約（GDL側と一致）: 原点=始点コーナー支柱（内側建地列）、+X=辺方向、+Y=躯体側。
    平面ループはCCWで躯体は進行方向左側 → 配置角は辺方向そのまま。
    """
    client = client or ArchicadClient()
    e = model.elevation
    placed = []
    for ep, edge in zip(model.plan.edges, model.plan.outline.edges):
        elem = client.create_object(object_name, ep.start_post[0], ep.start_post[1])
        angle = math.atan2(edge.direction[1], edge.direction[0])
        if abs(angle) > 1e-9:
            client.rotate_element(elem, angle, ep.start_post[0], ep.start_post[1])
        client.set_gdl_parameters(elem, line_params(model, ep, stair_plan=stair_plan, openings=openings))
        placed.append(elem)
    return placed


def place_details(
    model: ScaffoldModel,
    sheets: Optional[list] = None,
    object_name: str = "ashiba_detail",
    origin_mm: tuple[float, float] = (0.0, 0.0),
    pitch_mm: float = 4000.0,
    client: Optional[ArchicadClient] = None,
) -> list[dict]:
    """必要な詳細図を横一列に配置する（設置届の添付図書用）.

    警告表示のペン番号は、決め打ちせずプロジェクトのペンテーブルから赤を探して渡す。
    """
    from .details import required_details

    client = client or ArchicadClient()
    sheets = sheets if sheets is not None else required_details(model)
    warn_pen = client.find_red_pen()
    placed = []
    for i, sheet in enumerate(sheets):
        elem = client.create_object(
            object_name, origin_mm[0] + i * pitch_mm, origin_mm[1]
        )
        client.set_gdl_parameters(
            elem,
            {"detailType": sheet.key, "warnPen": warn_pen, **sheet.params},
        )
        placed.append(elem)
    return placed


def read_ground_model(client: Optional[ArchicadClient] = None):
    """プロジェクトの敷地メッシュから標高サンプル点群を読み、GroundModelを作る.

    メッシュの外形ポリゴン頂点とレベリングサブラインの点を標高サンプルとして使う。
    メッシュが無ければ空（平坦扱い）のGroundModelを返す。
    ⚠️ 三角形分割ではなく近傍点の逆距離加重で補間する近似（terrain.py参照）。
    """
    from .terrain import GroundModel

    client = client or ArchicadClient()
    points: list[tuple[float, float, float]] = []
    try:
        meshes = client.tapir(
            "GetElementsByType", {"elementType": "Mesh"}
        ).get("elements", [])
    except TapirError:
        return GroundModel()
    if not meshes:
        return GroundModel()

    for det in client.get_details(meshes):
        d = det.get("details", det)
        level = float(d.get("level", 0.0))

        def take(coords) -> None:
            for c in coords or []:
                if isinstance(c, dict) and "x" in c and "y" in c:
                    z = (float(c.get("z", 0.0)) + level) * 1000.0
                    points.append((c["x"] * 1000.0, c["y"] * 1000.0, z))

        take(d.get("polygonCoordinates"))
        for sub in d.get("sublines", []) or []:
            take(sub.get("coordinates"))
    return GroundModel(points=points)


def place_elevations(
    model: ScaffoldModel,
    object_name: str = "ashiba_line",
    stair_plan=None,
    openings=None,
    origin_mm: tuple[float, float] = (0.0, 0.0),
    gap_mm: float = 4000.0,
    floor_levels_mm: Optional[list[float]] = None,
    face_names: Optional[list[str]] = None,
    client: Optional[ArchicadClient] = None,
) -> list[dict]:
    """各面の立面図を横に並べて配置する（viewMode="elev"）.

    実務の作図順（平面を固めてから立面を起こす）に合わせ、平面割付の結果を
    そのまま渡す。壁つなぎは位置と高さの対で渡し、立面上は大きな丸印で示す。
    """
    client = client or ArchicadClient()
    e = model.elevation
    fl_str = ",".join(str(int(f)) for f in (floor_levels_mm or []))
    placed = []
    x = origin_mm[0]
    for i, ep in enumerate(model.plan.edges):
        elem = client.create_object(object_name, x, origin_mm[1])
        client.set_gdl_parameters(
            elem,
            {
                **line_params(model, ep, stair_plan=stair_plan, openings=openings),
                "viewMode": "elev",
                "flList": fl_str,
                "faceName": (
                    face_names[i] if face_names and i < len(face_names)
                    else f"辺{ep.edge_index}"
                ),
            },
        )
        placed.append(elem)
        x += ep.scaffold_length + gap_mm
    return placed
