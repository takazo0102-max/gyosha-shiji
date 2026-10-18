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
- SetGDLParametersOfElements はコマンド自体は成功で返し、個別の失敗は
  executionResults に入る。パラメータ名が1つでも無いと**全パラメータが適用されない**
  ので、結果を見ないと既定値のまま描かれた図面を「成功」と報告してしまう
  （古いGSMに新パラメータを送り、立面図の位置に平面図が出たまま成功と出た実績がある）
- 上と同じ理由で、検証スクリプトは部品名を固定せず毎回HSFからコンパイルして注入する
  （名前はHSFの内容ハッシュ。scripts/dev_gsm_iterate.py の build_current_gsm）
- 整数パラメータ（warnPen・nRows等）にfloatを送ると型不一致で弾かれる
"""

from __future__ import annotations

from pathlib import Path

import contextlib
import json
import time
import math
import urllib.error
import urllib.request
from typing import Any, Optional

from .gdl_params import line_params
from .model import ScaffoldModel

DEFAULT_PORT = 19723


class TapirError(Exception):
    pass


def is_ashiba_part(name: str, bases: tuple = ("ashiba_line", "ashiba_detail", "ashiba_mvo", "ashiba_spec")) -> bool:
    """部品名がこのツールの部品（基本名、または基本名_版のハッシュ付き）か.

    埋め込みライブラリの部品は Tapir から上書きも削除もできない（同じ名前で
    AddFilesToEmbeddedLibrary すると「not a valid relative path」で弾かれる）。
    GSM を更新すると古い部品が居座って「railAdv is not a GDL parameter」で配置が
    止まったので、配布部品は「ashiba_line_<HSFのハッシュ8桁>」の名前で埋め込む。
    撤去・置き換えでは版違いも同じ部品として拾う。
    """
    if not name:
        return False
    for b in bases:
        if name == b:
            return True
        if name.startswith(b + "_") and len(name) == len(b) + 9 and name[len(b) + 1:].isalnum():
            return True
    return False


class TapirTimeout(TapirError):
    """Archicad は起動しているが、アドオンの命令が時間内に返らない（操作中など）."""


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
            if "timed out" in str(exc):
                # Archicad は起動しているが、操作中（ドラッグ・ダイアログ・再構築）でアドオンの
                # 命令が待たされている。起動していないのとは打つ手が違う
                raise TapirTimeout(
                    f"Archicad が {self.timeout:.0f}秒応答しません（{command}）。操作中・ダイアログ表示中・"
                    "再構築中の可能性があります。手を止めてから、もう一度実行してください"
                ) from exc
            raise TapirError(
                f"Archicadに接続できません（{self.url}）。Archicadを起動してください: {exc}"
            ) from exc
        if not data.get("succeeded"):
            err = data.get("error") or {}
            msg = err.get("message", "") if isinstance(err, dict) else str(err)
            hint = ""
            # Tapirが入っていない／古いときの 4010 は、原因を書かないと
            # 「失敗しました」だけで何をすればよいか分からない
            if "TapirCommand." in msg:
                hint = (
                    "\nArchicadにTapirアドオンが入っていないか、"
                    "このコマンドに対応していない版の可能性があります"
                    "（動作確認: Tapir 1.7.0 / Archicad 30）。"
                    "アドオンを入れて Archicad を再起動してください"
                )
            raise TapirError(f"{command} が失敗: {err}{hint}")
        return data.get("result", {})

    # 読むだけの命令は、時間切れなら待って再試行してよい（作る・消す命令は Archicad 側で
    # 実行済みのことがあるので再試行しない。重複して作ってしまう）
    READ_ONLY_PREFIXES = ("Get", "Is", "FitInWindow")

    def tapir(self, command: str, parameters: Optional[dict] = None, retries: int = 2,
              wait_s: float = 5.0) -> dict:
        body = {
            "addOnCommandId": {
                "commandNamespace": "TapirCommand",
                "commandName": command,
            },
            "addOnCommandParameters": parameters or {},
        }
        for attempt in range(retries + 1):
            try:
                result = self.post("API.ExecuteAddOnCommand", body)
                break
            except TapirTimeout:
                if attempt >= retries or not command.startswith(self.READ_ONLY_PREFIXES):
                    raise
                time.sleep(wait_s)
        resp = result.get("addOnCommandResponse", {})
        if isinstance(resp, dict) and resp.get("error"):
            raise TapirError(f"Tapir {command} が失敗: {resp['error']}")
        return resp

    # ---- 基本操作 ------------------------------------------------------

    def wait_ready(self, max_wait_s: float = 120.0, poll_s: float = 5.0, echo=print) -> bool:
        """アドオンの命令が通るまで待つ（Archicad が操作中だと待たされる）。通れば True."""
        start = time.time()
        told = False
        while True:
            try:
                self.post("API.ExecuteAddOnCommand", {
                    "addOnCommandId": {"commandNamespace": "TapirCommand", "commandName": "GetCurrentWindowType"},
                    "addOnCommandParameters": {}})
                return True
            except TapirTimeout:
                if time.time() - start > max_wait_s:
                    return False
                if not told and echo:
                    echo("Archicad が操作中のため待っています…（手を止めてください）")
                    told = True
                time.sleep(poll_s)

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

    def delete_elements(self, elements: list[dict]) -> None:
        self.tapir("DeleteElements", {"elements": elements})

    def current_window_type(self) -> str:
        """アクティブなウィンドウの種類（FloorPlan / Layout / 3D など）。取れなければ空."""
        try:
            return str(self.tapir("GetCurrentWindowType", {}).get("currentWindowType", ""))
        except TapirError:
            return ""

    def create_slab(
        self, polygon_mm: list[tuple[float, float]], level: float = 0.0, thickness: float = 0.3
    ) -> dict:
        # スラブはレイアウト・3D ウィンドウがアクティブだと作れない（オブジェクトは置ける）。
        # 「Failed to create new Slab」だけでは原因が分からず、半日を無駄にした
        win = self.current_window_type()
        if win and win != "FloorPlan":
            raise TapirError(
                f"アクティブなウィンドウが {win} です。スラブの作成は平面図（FloorPlan）で"
                "行うので、Archicad で平面図のウィンドウを前面にしてから実行してください"
            )
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
        # 失敗は要素ごとの error で返る（elements は空にならない）。素通しすると
        # 後段が「外形が取れません」で止まり、原因（多角形の指定）が見えない
        if "error" in elements[0]:
            raise TapirError(
                f"スラブを作成できませんでした: {elements[0]['error']}"
                f"（頂点{len(polygon_mm)}点。閉じた多角形か、自己交差していないか確認）"
            )
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
        # 失敗は要素ごとに error で返る（コマンド自体は成功扱い）。そのまま返すと
        # 後段で KeyError 'elementId' になり、部品が無いことが分からない
        if "error" in elements[0]:
            msg = elements[0]["error"].get("message", elements[0]["error"])
            raise TapirError(
                f"オブジェクト {library_part_name} を配置できませんでした: {msg}\n"
                "ライブラリ部品が読み込まれていない可能性があります。gdl/ashiba_line.gsm"
                "（詳細図は ashiba_detail.gsm）をライブラリに読み込むか、"
                "scripts/dev_gsm_iterate.py で現行HSFを埋め込みライブラリへ注入してください"
            )
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

    def set_gdl_parameters(
        self, element: dict, params: dict[str, Any], object_name: str = ""
    ) -> None:
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
                # 失敗の原因はほぼ「部品が無い／古い」。次に何をすればよいかまで書く
                part = f"「{object_name}」" if object_name else ""
                raise TapirError(
                    "GDLパラメータの設定に失敗しました: "
                    f"{err.get('message', err)}"
                    f"（送信: {', '.join(params)}）\n"
                    f"ライブラリ部品{part}が読み込まれていないか、"
                    "このパラメータを持たない古い版の可能性があります。"
                    "gdl/ashiba_line.gsm（詳細図は ashiba_detail.gsm）を"
                    "ライブラリに読み込むか、scripts/dev_gsm_iterate.py で"
                    "現行HSFをコンパイルして埋め込みライブラリへ注入してください"
                )

    def get_gdl_parameters(self, element: dict) -> dict:
        return self.tapir(
            "GetGDLParametersOfElements", {"elements": [element]}
        )

    def add_file_to_embedded_library(self, input_path: str, output_name: str) -> None:
        # Archicad はこのプロセスの作業ディレクトリを知らない。相対パスを渡すと
        # 「Failed to read file on the given inputPath」で落ちる（実際に踏んだ）
        abs_path = str(Path(input_path).resolve())
        # outputPath は「フォルダ/名前.gsm」の形で渡す。直下に「名前.gsm」だと
        # 「not a valid relative path」、拡張子無しだと入るが部品として見つからない
        # （Archicad 28 + Tapir 1.5.8 で実際に踏んだ）。追加後は ReloadLibraries を
        # 掛けないと直後の配置で「Not found library part」になる
        out = output_name if "/" in output_name else f"ashiba/{output_name}"
        resp = self.tapir(
            "AddFilesToEmbeddedLibrary",
            {"files": [{"inputPath": abs_path, "outputPath": out}]},
        )
        results = resp.get("executionResults", [])
        if results and not results[0].get("success"):
            raise TapirError(f"埋め込みライブラリへの追加に失敗: {results[0].get('error')}")
        try:
            self.tapir("ReloadLibraries", {})
        except TapirError:
            pass    # 古い Tapir に無ければ、配置側の再試行に任せる

    def ensure_embedded_parts(self, files: list) -> list[str]:
        """配布GSMを埋め込みライブラリに入れる（既に入っていれば何もしない）.

        ツールバーからの実行は「gdl/ashiba_line.gsm をライブラリに読み込み済み」を
        前提にしていて、読み込んでいないと「Not found library part」で止まった。
        ツールに同梱している部品なので、無ければ自分で入れる。各要素はパス、または
        (パス, 埋め込み名) の組。埋め込み名を省くとファイル名がそのまま部品名になる。
        戻り値は今回入れた埋め込み名（既にあるものは Tapir が弾くので含まれない）。
        """
        added: list[str] = []
        for item in files:
            f, name = (item if isinstance(item, tuple) else (item, None))
            f = Path(f)
            if not f.exists():
                continue
            name = name or f.name
            if not name.lower().endswith(".gsm"):
                name += ".gsm"
            try:
                self.add_file_to_embedded_library(str(f), name)
                added.append(name)
            except TapirError:
                pass    # 同名の部品が既にある（Tapir は「not a valid relative path」で弾く）
        return added

    def delete_stale_duplicates(self, placed: list[dict]) -> int:
        """今回置いたオブジェクトと同じ部品・同じ位置・同じ向きの古いオブジェクトを消す.

        同じスラブでツールバーを再実行すると、前回の足場ライン・立面図・詳細図の上に
        新しいものが重なって溜まる（実機で13個ずつ増えた）。位置が1mm以内で一致する
        同名部品だけを消すので、別の建物の配置や他ツールの部品には触らない。
        戻り値は消した個数。
        """
        if not placed:
            return 0
        placed_guids = {e["elementId"]["guid"] for e in placed}
        keys = set()
        for d in self.get_details(placed):
            dd = d.get("details", {})
            lp = dd.get("libPart") or {}
            name = lp.get("name") if isinstance(lp, dict) else ""
            o = dd.get("origin") or {}
            if name and o:
                keys.add((name, round(float(o.get("x", 0)) * 1000), round(float(o.get("y", 0)) * 1000),
                          round(float(dd.get("angle") or 0.0), 4)))
        if not keys:
            return 0
        names = {k[0] for k in keys}
        all_objs = self.tapir("GetElementsByType", {"elementType": "Object"}).get("elements", [])
        candidates = [e for e in all_objs if e["elementId"]["guid"] not in placed_guids]
        stale = []
        for e, d in zip(candidates, self.get_details(candidates) if candidates else []):
            dd = d.get("details", {})
            lp = dd.get("libPart") or {}
            name = lp.get("name") if isinstance(lp, dict) else ""
            if name not in names:
                continue
            o = dd.get("origin") or {}
            key = (name, round(float(o.get("x", 0)) * 1000), round(float(o.get("y", 0)) * 1000),
                   round(float(dd.get("angle") or 0.0), 4))
            if key in keys:
                stale.append(e)
        if stale:
            self.delete_elements(stale)
        return len(stale)

    def objects_for_slab(
        self, outline_mm: list[tuple[float, float]], names: tuple = ("ashiba_line", "ashiba_detail"),
        elevation_offset_mm: float = -45000.0, detail_offset_mm: float = -20000.0,
        margin_mm: float = 1000.0,
    ) -> list[dict]:
        """そのスラブ（外形）に対して置いた足場ライン・立面図・詳細図のオブジェクトを集める.

        足場ラインは外形の範囲（＋余裕）、立面図と詳細図はツールバーが並べる行
        （外形の左下から elevation_offset / detail_offset 下）にあるものを拾う。
        他の建物の配置や他ツールの部品は拾わない。撤去スクリプト用。
        """
        xs = [float(p[0]) for p in outline_mm]
        ys = [float(p[1]) for p in outline_mm]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        rows = (y0 + elevation_offset_mm, y0 + detail_offset_mm)
        # 行の右端はこの建物の並べ幅（各面の足場長＋面間4m）まで。上限を付けないと、
        # 同じ行に並ぶ東隣の建物の立面図まで拾う（30m棟の4面目が x0+94m まで来る）
        n = len(outline_mm)
        perimeter = sum(
            ((outline_mm[(i + 1) % n][0] - outline_mm[i][0]) ** 2
             + (outline_mm[(i + 1) % n][1] - outline_mm[i][1]) ** 2) ** 0.5
            for i in range(n)
        )
        row_x_max = x0 + perimeter + 4000.0 * (n + 1) + margin_mm
        all_objs = self.tapir("GetElementsByType", {"elementType": "Object"}).get("elements", [])
        out: list[dict] = []
        for e, d in zip(all_objs, self.get_details(all_objs) if all_objs else []):
            dd = d.get("details", {})
            lp = dd.get("libPart") or {}
            name = lp.get("name") if isinstance(lp, dict) else ""
            if not is_ashiba_part(name, names):
                continue
            o = dd.get("origin") or {}
            ox, oy = float(o.get("x", 0)) * 1000, float(o.get("y", 0)) * 1000
            in_plan = (x0 - margin_mm <= ox <= x1 + margin_mm) and (y0 - margin_mm <= oy <= y1 + margin_mm)
            in_row = (x0 - margin_mm <= ox <= row_x_max) and any(abs(oy - r) <= margin_mm for r in rows)
            if in_plan or in_row:
                out.append(e)
        return out

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
    polys = [p for p in (_extract_polygon(det) for det in client.get_details(elements)) if p]
    if not polys:
        raise TapirError("選択要素から外形ポリゴンを取得できませんでした（スラブを選択してください）")
    if len(polys) > 1:
        # Archicad の選択は追加式で溜まる。最初の1つを黙って使うと、別の建物に足場が
        # 置かれる（実機で2棟目のつもりが1棟目に置き換わった）
        raise TapirError(
            f"外形を持つ要素が{len(polys)}個選択されています。足場を組む躯体スラブを1つだけ選択してください"
        )
    return [(p[0] * 1000.0, p[1] * 1000.0) for p in polys[0]]


def slab_outline_mm_by_guid(client: ArchicadClient, guid_prefix: str) -> list[tuple[float, float]]:
    """GUID の先頭一致でスラブを探して外形[mm]を返す（選択に頼らない検証用）.

    選択は現在のフロアに無い要素を拾えない（基礎下端が表示中だと 1FL のスラブは
    選択しても GetSelectedElements に出ない）。スクリプトからの検証はこちらで指定する。
    """
    pref = guid_prefix.upper()
    els = client.tapir("GetElementsByType", {"elementType": "Slab"}).get("elements", [])
    hit = [e for e in els if e["elementId"]["guid"].upper().startswith(pref)]
    if not hit:
        raise TapirError(f"GUID {guid_prefix}… のスラブがありません")
    if len(hit) > 1:
        raise TapirError(f"GUID {guid_prefix}… のスラブが{len(hit)}個あります。桁を増やしてください")
    poly = _extract_polygon(client.get_details(hit)[0])
    if not poly:
        raise TapirError(f"スラブ {guid_prefix}… から外形ポリゴンを取得できませんでした")
    return [(p[0] * 1000.0, p[1] * 1000.0) for p in poly]


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


@contextlib.contextmanager
def _rollback_on_error(client, placed: list):
    """一括配置の途中で失敗したら、置いた分を消してから例外を投げ直す."""
    try:
        yield
    except Exception as exc:
        if placed:
            try:
                client.delete_elements(placed)
            except Exception:      # 後始末の失敗で元の原因を隠さない
                raise TapirError(
                    f"{exc}\n（途中まで配置した{len(placed)}個の削除にも失敗しました。"
                    "手動で削除してください）"
                ) from exc
            placed.clear()
            raise TapirError(
                f"{exc}\n（途中まで配置した要素は削除しました）") from exc
        raise


def place_scaffold_lines(
    model: ScaffoldModel,
    object_name: str = "ashiba_line",
    client: Optional[ArchicadClient] = None,
    stair_plan=None,
    openings=None,
    platforms=None,
    bracket_sections=None,
    terrain=None,
) -> list[dict]:
    """割付結果の各辺に「足場ライン」オブジェクトを1つずつ配置する.

    配置規約（GDL側と一致）: 原点=始点コーナー支柱（内側建地列）、+X=辺方向、+Y=躯体側。
    平面ループはCCWで躯体は進行方向左側 → 配置角は辺方向そのまま。
    """
    client = client or ArchicadClient()
    placed: list[dict] = []
    # 途中で失敗したら、置いた分を消してから投げる。中途半端な足場が
    # モデルに残ると、どこまで置けたのか利用者が確かめる羽目になる
    with _rollback_on_error(client, placed):
        for ep, edge in zip(model.plan.edges, model.plan.outline.edges):
            elem = client.create_object(
                object_name, ep.start_post[0], ep.start_post[1])
            placed.append(elem)
            angle = math.atan2(edge.direction[1], edge.direction[0])
            if abs(angle) > 1e-9:
                client.rotate_element(
                    elem, angle, ep.start_post[0], ep.start_post[1])
            client.set_gdl_parameters(
                elem,
                line_params(
                    model, ep, stair_plan=stair_plan, openings=openings,
                    platforms=platforms, bracket_sections=bracket_sections,
                    terrain=terrain,
                ),
                object_name,
            )
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
    placed: list[dict] = []
    with _rollback_on_error(client, placed):
        for i, sheet in enumerate(sheets):
            elem = client.create_object(
                object_name, origin_mm[0] + i * pitch_mm, origin_mm[1]
            )
            placed.append(elem)
            client.set_gdl_parameters(
                elem,
                {"detailType": sheet.key, "warnPen": warn_pen, **sheet.params},
                object_name,
            )
    return placed


MESH_MARGIN_MM = 3000.0   # 建物外形からこの距離までに掛かるメッシュだけを敷地として使う


def _mesh_touches(mesh_pts_mm: list[tuple[float, float]], outline_mm, margin: float) -> bool:
    """メッシュ外形の矩形範囲が、建物外形（＋余裕）の矩形範囲と重なるか."""
    if not mesh_pts_mm or not outline_mm:
        return True
    mx0 = min(p[0] for p in mesh_pts_mm); mx1 = max(p[0] for p in mesh_pts_mm)
    my0 = min(p[1] for p in mesh_pts_mm); my1 = max(p[1] for p in mesh_pts_mm)
    bx0 = min(float(p[0]) for p in outline_mm) - margin; bx1 = max(float(p[0]) for p in outline_mm) + margin
    by0 = min(float(p[1]) for p in outline_mm) - margin; by1 = max(float(p[1]) for p in outline_mm) + margin
    return not (mx1 < bx0 or mx0 > bx1 or my1 < by0 or my0 > by1)


def read_ground_model(client: Optional[ArchicadClient] = None, outline_mm=None):
    """プロジェクトの敷地メッシュから標高サンプル点群を読み、GroundModelを作る.

    メッシュの外形ポリゴン頂点とレベリングサブラインの点を標高サンプルとして使う。
    メッシュが無ければ空（平坦扱い）のGroundModelを返す。
    outline_mm（建物外形）を渡すと、その範囲（＋MESH_MARGIN_MM）に掛かるメッシュだけを
    使う。離れた別棟のメッシュまで拾うと、その外挿値でこの棟の地盤が決まる
    （実機で300m離れた棟が GL-377mm の「高低差あり」になった）。無視した数は
    GroundModel.ignored_meshes に入れる。
    ⚠️ 三角形分割ではなく近傍点の逆距離加重で補間する近似（terrain.py参照）。
    """
    from .terrain import GroundModel

    client = client or ArchicadClient()
    points: list[tuple[float, float, float]] = []
    ignored = 0
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
        poly = [(c["x"] * 1000.0, c["y"] * 1000.0) for c in (d.get("polygonCoordinates") or [])
                if isinstance(c, dict) and "x" in c and "y" in c]
        if outline_mm is not None and not _mesh_touches(poly, outline_mm, MESH_MARGIN_MM):
            ignored += 1
            continue

        def take(coords) -> None:
            for c in coords or []:
                if isinstance(c, dict) and "x" in c and "y" in c:
                    z = (float(c.get("z", 0.0)) + level) * 1000.0
                    points.append((c["x"] * 1000.0, c["y"] * 1000.0, z))

        take(d.get("polygonCoordinates"))
        for sub in d.get("sublines", []) or []:
            take(sub.get("coordinates"))
    return GroundModel(points=points, ignored_meshes=ignored)


def place_elevations(
    model: ScaffoldModel,
    object_name: str = "ashiba_line",
    stair_plan=None,
    openings=None,
    platforms=None,
    bracket_sections=None,
    origin_mm: tuple[float, float] = (0.0, 0.0),
    gap_mm: float = 4000.0,
    floor_levels_mm: Optional[list[float]] = None,
    face_names: Optional[list[str]] = None,
    client: Optional[ArchicadClient] = None,
    terrain=None,
) -> list[dict]:
    """各面の立面図を横に並べて配置する（viewMode="elev"）.

    実務の作図順（平面を固めてから立面を起こす）に合わせ、平面割付の結果を
    そのまま渡す。壁つなぎは位置と高さの対で渡し、立面上は大きな丸印で示す。
    """
    client = client or ArchicadClient()
    # 面名を渡さない場合は方位で呼ぶ（辺0では図面を見た人に伝わらない）
    face_names = face_names or model.plan.face_names()
    fl_str = ",".join(str(int(f)) for f in (floor_levels_mm or []))
    placed: list[dict] = []
    x = origin_mm[0]
    with _rollback_on_error(client, placed):
        for i, ep in enumerate(model.plan.edges):
            elem = client.create_object(object_name, x, origin_mm[1])
            placed.append(elem)
            client.set_gdl_parameters(
                elem,
                {
                    **line_params(
                        model, ep, stair_plan=stair_plan, openings=openings,
                        platforms=platforms, bracket_sections=bracket_sections,
                        terrain=terrain,
                    ),
                    "viewMode": "elev",
                    "flList": fl_str,
                    "faceName": (
                        face_names[i] if face_names and i < len(face_names)
                        else f"辺{ep.edge_index}"
                    ),
                },
                object_name,
            )
            x += ep.scaffold_length + gap_mm
    return placed
