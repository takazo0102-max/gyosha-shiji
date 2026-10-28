"""敷地の高低差対応と支柱ごとのジャッキ量算出（仕様4.4・Phase 4）.

⚠️ ここが本ツール最大の差別化点:
敷地メッシュから各支柱位置のGL標高を取り、支柱1本ごとのジャッキ繰出し量を自動で出す。

原理（仕様4.4）:
- **布材・作業床レベルは全周で通す**。だから作業床の絶対標高は全支柱で共通
- くさび式はコマ位置が支柱下端から固定ピッチなので、作業床を揃えるには
  **各支柱の下端（ジャッキ天端）が基準からコマピッチの整数倍だけ下がっている**必要がある
- GLとその「あるべき下端」の差をジャッキ繰出しで吸収する

つまり支柱ごとに解くのは「何コマ下げるか(m_i)」で、残差がジャッキ量になる。
ジャッキの可動域(30〜450mm)はコマピッチ(450mm)よりわずかに狭いので、
どうしても収まらない位置が出る。その場合は敷板での調整量を明示する（黙って丸めない）。
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Optional

from .dp import spans_text
from .elevation_solver import JACK_MAX_EXTENSION, JACK_MIN_EXTENSION, _compose_table
from .model import ScaffoldModel

JACK_HARD_MAX_EXTENSION = 450   # ジャッキの機械的な最大繰出し（270は実務上限）
SLOPE_SHIM_LIMIT = 0.10         # 足元の勾配がこれを超えたら傾斜対応のベースか段切り（10%）
SHIM_UNIT_MM = 35               # 敷板1枚の厚さ（杉敷板 厚35）。実務上限超えの脚を敷板で持ち上げる単位
# 敷板をこの枚数以上重ねる脚は、敷角か床均しに替えるよう書き添える（重ねるほど据わりが悪い）
SHIM_STACK_WARN = 3
# 敷板この枚数までは床掘りより先に使う（並べて敷くのと変わらない）
SHIM_LIGHT = 2


@dataclass
class GroundModel:
    """敷地の標高サンプル点群. 任意座標の標高を、近い点（k 点）に重み付きで当てた平面で求める.

    Archicadの敷地メッシュ頂点をそのまま入れる想定。
    近い点に平面を当てるので、一様な勾配の敷地ではその勾配のとおりに出る（足元の勾配に合わせる。利用者の指定
    2026-10-24: 足元の勾配に合わせるように配置）。点が一直線に並ぶ・少ないときは逆距離加重(IDW)。
    ⚠️ 三角形分割による厳密な内挿ではない。急変する地形では実測値の確認が必要。
    """

    points: list[tuple[float, float, float]] = field(default_factory=list)  # (x,y,z) mm
    k_nearest: int = 4
    power: float = 2.0
    # 建物の範囲に掛からず無視した敷地メッシュの数（read_ground_model が建物外形で絞ったとき）
    ignored_meshes: int = 0
    # 建物に掛かる敷地メッシュの外形（平面 mm）。敷地境界線のポリラインが無いときの敷地境界に使う
    mesh_outlines: list = field(default_factory=list)
    plane_k: int = 6

    @property
    def is_flat(self) -> bool:
        return not self.points

    def _plane(self, x: float, y: float):
        """(x, y) の近くの点に当てた平面 z = a(x−x)+b(y−y)+c → (a, b, c)。当てられなければ None."""
        if len(self.points) < 3:
            return None
        near = sorted(self.points, key=lambda p: (p[0] - x) ** 2 + (p[1] - y) ** 2)[: max(3, self.plane_k)]
        # 重み付き最小二乗（重み 1/(d+1m)²）。原点を (x, y) に置いて解く
        sw = sxx = sxy = syy = sx = sy = sz = sxz = syz = 0.0
        for px, py, pz in near:
            dx, dy = px - x, py - y
            w = 1.0 / (math.hypot(dx, dy) + 1000.0) ** 2
            sw += w
            sx += w * dx
            sy += w * dy
            sz += w * pz
            sxx += w * dx * dx
            sxy += w * dx * dy
            syy += w * dy * dy
            sxz += w * dx * pz
            syz += w * dy * pz
        m = [[sxx, sxy, sx], [sxy, syy, sy], [sx, sy, sw]]
        r = [sxz, syz, sz]
        det = (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
               + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))
        scale = (sxx + syy) * sw
        if scale <= 0 or abs(det) < 1e-9 * scale * (sxx + syy + 1.0):
            return None

        def d3(a):
            return (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1]) - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
                    + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))
        cols = []
        for k in range(3):
            mk = [row[:] for row in m]
            for i in range(3):
                mk[i][k] = r[i]
            cols.append(d3(mk) / det)
        a, b, c = cols
        zs = [p[2] for p in near]
        span = max(zs) - min(zs)
        if not (min(zs) - span - 1.0 <= c <= max(zs) + span + 1.0):
            return None                      # 外挿が暴れる（点の並びが悪い）
        return a, b, c

    def slope_at(self, x: float, y: float) -> float:
        """(x, y) の地盤の勾配（高さ／水平。0.05＝5%）。平らか当てられなければ 0."""
        pl = self._plane(x, y)
        return math.hypot(pl[0], pl[1]) if pl else 0.0

    def elevation_at(self, x: float, y: float, default: float = 0.0) -> float:
        if not self.points:
            return default
        for px, py, pz in self.points:
            if (px - x) ** 2 + (py - y) ** 2 < 1e-6:
                return pz
        pl = self._plane(x, y)
        if pl is not None:
            # 点の高さの範囲に収める（メッシュの外へ勾配を延ばして、敷地より高い・低い地盤を作らない）
            near = sorted(self.points, key=lambda p: (p[0] - x) ** 2 + (p[1] - y) ** 2)[: max(3, self.plane_k)]
            return min(max(pl[2], min(p[2] for p in near)), max(p[2] for p in near))
        dists = []
        for px, py, pz in self.points:
            d2 = (px - x) ** 2 + (py - y) ** 2
            if d2 < 1e-6:          # サンプル点に一致
                return pz
            dists.append((d2, pz))
        dists.sort(key=lambda t: t[0])
        near = dists[: max(1, self.k_nearest)]
        wsum = 0.0
        zsum = 0.0
        for d2, pz in near:
            w = 1.0 / (math.sqrt(d2) ** self.power)
            wsum += w
            zsum += w * pz
        return zsum / wsum

    def range_mm(self) -> tuple[float, float]:
        if not self.points:
            return (0.0, 0.0)
        zs = [p[2] for p in self.points]
        return (min(zs), max(zs))


@dataclass
class PostFoot:
    """支柱1本の脚部（ジャッキ量と支柱構成）."""

    index: int
    x: float
    y: float
    gl_mm: float
    koma_offset: int          # 基準から何コマ下げるか
    jack_mm: float            # ジャッキ繰出し量
    posts: list[int]          # この位置の支柱構成（下から）
    base_plate_adjust_mm: float = 0.0   # 敷板で追加調整が必要な量
    warnings: list[str] = field(default_factory=list)
    row: int = 0              # 建地列（0＝内側（躯体側）、1＝外側）
    slope: float = 0.0        # 足元の地盤の勾配（高さ／水平）

    @property
    def jack_top_mm(self) -> float:
        return self.gl_mm + self.jack_mm + self.base_plate_adjust_mm

    @property
    def ok(self) -> bool:
        return not self.warnings


@dataclass
class TerrainResult:
    feet: list[PostFoot]
    reference_gl_mm: float
    gl_range_mm: tuple[float, float]
    deck_levels_abs_mm: list[float]    # 作業床の絶対標高（全周共通）
    # warnings は「対応が要るもの」だけ。何をどう解いたかの説明は notes へ分ける
    # （混ぜると、読む側がどれに手を打てばよいのか分からなくなる）
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    # ジャッキ繰出しが実務上限を超えたときの本文。法規チェック6と同じ事象なので、
    # 向こうにも同じ文面を使わせて、要確認一覧に二重で並ばないようにする
    over_jack_warning: str = ""
    # 帳票の呼び名（枠組は建枠）。ジャッキ量一覧の列名などに使う
    vertical_member_name: str = "支柱"
    # 下げ段数の刻み（くさび=コマピッチ、枠組=調整枠の高さ）mm
    step_mm: float = 0.0
    # 外側の建地列の脚（本足場。feet と同じ並び）。外側の列は躯体から建地列の間隔だけ外の地盤に立つので、
    # 内側の列の地盤高で描くと斜面で外側の脚が浮く・埋まる（利用者の指定 2026-10-21「足元はメッシュで高低差が
    # あるときの対応」）。一側足場は建地が外側の1列だけなので、feet がその列（row=1）で、ここは空
    feet_outer: list[PostFoot] = field(default_factory=list)

    @property
    def all_feet(self) -> list[PostFoot]:
        return list(self.feet) + list(self.feet_outer)

    @property
    def jack_min_mm(self) -> float:
        return min((f.jack_mm for f in self.all_feet), default=0.0)

    @property
    def jack_max_mm(self) -> float:
        return max((f.jack_mm for f in self.all_feet), default=0.0)

    @property
    def gl_difference_mm(self) -> float:
        return self.gl_range_mm[1] - self.gl_range_mm[0]

    @property
    def all_ok(self) -> bool:
        return all(f.ok for f in self.all_feet)

    def over_recommended(self) -> list[PostFoot]:
        return [f for f in self.all_feet if f.jack_mm > JACK_MAX_EXTENSION]


def solve_post_feet(
    model: ScaffoldModel,
    ground: Optional[GroundModel] = None,
    jack_min: int = JACK_MIN_EXTENSION,
    jack_recommended_max: int = JACK_MAX_EXTENSION,
    jack_hard_max: Optional[int] = None,
) -> TerrainResult:
    """各支柱位置のGL標高から、支柱ごとのジャッキ量と支柱構成を解く.

    作業床レベルを全周で通すため、各支柱の下端は基準からコマピッチの整数倍だけ下げる。
    残差をジャッキで吸収し、吸収しきれない分は敷板調整として明示する。
    """
    ground = ground or GroundModel()
    # 機械的な上限は系列で違う（枠組350・日建ND752SP 432・信和SE-6 450）
    if jack_hard_max is None:
        jack_hard_max = model.master.jack_hard_max_mm()
    inner = model.plan.post_positions()
    outer = outer_post_positions(model)
    if model.config.scaffold_form == "一側足場" or not ground.points:
        # 一側足場は外側の1列だけ。平坦なら内外とも同じなので内側の列だけで足りる
        positions, rows = (outer, [1] * len(outer)) if model.config.scaffold_form == "一側足場" else (inner, [0] * len(inner))
    else:
        positions, rows = inner + outer, [0] * len(inner) + [1] * len(outer)
    koma = model.master.koma_pitch
    # 枠組にコマは無い。段差の刻みは最小の建枠（調整枠）の高さになる
    step_name = "コマピッチ"
    # 調整支柱のある系列（ミレニューム P2.25G）は、その長さの刻みで最下段の下に入れる
    adj = adjust_post_mm(model.master)
    if adj:
        koma = adj
        step_name = "調整支柱"
    if koma <= 0:
        # 枠組はコマの概念がないので、建枠高さの最小値を刻みとする
        koma = min(model.master.frame_heights() or [model.master.floor_height])
        step_name = "調整枠の高さ"

    # 敷板で持ち上げる境目。実務上限（270）を超えても、その繰出しを許容する品（日建の
    # ロングジャッキ ND752SP 432 等）が系列にあればそれで受け、無ければ敷板で上限内に収める
    # （信和 SE-6 は「繰出し最大450 許容繰出し270」なので許容270が境目）
    rated: list[int] = []
    for p in model.master.by_category("ジャッキ"):
        if "アンダーベース" in p.note:
            continue
        mt = re.search(r"許容繰出し\s*(\d+)", p.note)
        v = int(mt.group(1)) if mt else p.max_extension_mm()
        if v:
            rated.append(int(v))
    shim_limit = max([jack_recommended_max] + rated)

    gls = [ground.elevation_at(x, y) for (x, y) in positions]
    gl_max = max(gls) if gls else 0.0
    gl_min = min(gls) if gls else 0.0

    # 基準面（全支柱の下端が乗る面）を全体シフトして、実務上限を超える支柱を最小化する。
    # 平面割付の「全体XYシフトで離れを最適化」と同じ考え方の垂直版。
    # ジャッキの可動域(30〜270)はコマピッチ(450)より狭いため、
    # 連続的な斜面では必ず収まらない支柱が出る。せめてその本数を最小にする。
    ref_jack = model.elevation.jack_extension
    ref_jack_top = _optimize_datum(gls, gl_max, ref_jack, koma, jack_min, shim_limit, jack_recommended_max)

    base_posts = list(model.elevation.posts)
    base_total = sum(base_posts)
    lengths = (
        model.master.frame_heights() if model.master.is_frame
        else model.master.post_lengths(include_negarami=True)
    )
    # 何コマ下げれば、ジャッキ量が可動域に収まるか（脚ごと）
    offsets = [
        _choose_koma_offset(ref_jack_top, gl, koma, jack_min, shim_limit, jack_recommended_max)
        for gl in gls
    ]
    # 継ぎ足しの構成表は、実際に必要な最大コマ数まで作る。8コマ（3.6m）で
    # 打ち切っていたときは、それを超える段差の脚が名目構成に戻され、数量の
    # 支柱が不足し、高さ判定も名目のままだった（脚ごとの備考にしか出なかった）
    # 全脚が同じ段数だけ下がっているなら、それは基準面が高すぎるだけ。
    # 基準面ごと下げれば同じジャッキ量のまま継ぎ足しが要らなくなる
    # （枠組は刻み900mmで、500mmの高低差に全58脚へ調整枠を足していた）
    # 枠組は建枠1枚が内外の脚を兼ねるので、外側の脚も内側と同じ段数（建枠の構成）。差はジャッキで受ける
    if model.master.is_frame and 0 in rows and 1 in rows:
        n0 = rows.count(0)
        offsets[n0:] = offsets[:len(offsets) - n0]
    min_offset = min(offsets) if offsets else 0
    if min_offset > 0:
        offsets = [m - min_offset for m in offsets]
        ref_jack_top -= min_offset * koma
    max_offset = max(offsets) if offsets else 0
    table = _compose_table(
        base_total + int(koma) * max(8, max_offset), sorted(set(lengths), reverse=True)
    )


    feet: list[PostFoot] = []
    warnings: list[str] = []
    for i, ((x, y), gl), m in zip(range(len(gls)), zip(positions, gls), offsets):
        # 支柱下端の目標位置は gl + jack_ideal。ジャッキで届かない分は地盤側で調整する。
        # 調整量は必ず adjust = jack_ideal - 実ジャッキ量 とする（符号を逆にすると
        # 支柱下端が目標からずれ、作業床が全周で通らなくなる）
        jack_ideal = ref_jack_top - m * koma - gl
        jack = jack_ideal
        foot_warnings: list[str] = []
        adjust = 0.0

        if jack_ideal < jack_min:
            jack = jack_min
            adjust = jack_ideal - jack_min          # 負＝床掘りで下げる
            foot_warnings.append(
                f"ジャッキ最小{jack_min}mmでも下端が高すぎます。"
                f"床掘り等で{-adjust:.0f}mm下げる必要があります"
            )
        elif jack > shim_limit:
            # 実務上限（270）または系列の許容繰出しを超える。敷板（厚35）を重ねて持ち上げ、
            # 繰出しを境目以下に収める。支柱下端（gl＋敷板＋ジャッキ）は変えないので
            # 作業床は通る。以前は警告だけで敷板調整が0のままだった（実機で7本が警告のまま）。
            # 可動域（最大350）も超える脚も同じ扱い。以前は繰出し350のまま端数の敷板（80mm 等）を
            # 書き、注記の「上限内にしています」と一覧の350が食い違っていた（枠組の見本で10本）
            n_shim = int(math.ceil((jack - shim_limit) / SHIM_UNIT_MM))
            adjust = n_shim * SHIM_UNIT_MM
            jack = jack_ideal - adjust
            beyond = f"（最大{jack_hard_max}mmも超える）" if jack_ideal > jack_hard_max else ""
            foot_warnings.append(
                f"ジャッキ繰出し{jack_ideal:.0f}mmは実務上限{shim_limit}mmを超える{beyond}ので、"
                f"敷板{n_shim}枚（厚{SHIM_UNIT_MM}mm）で{adjust:.0f}mm持ち上げて繰出し{jack:.0f}mmにしています"
            )
        elif jack > jack_recommended_max:
            foot_warnings.append(
                f"ジャッキ繰出し{jack:.0f}mmが実務上限{jack_recommended_max}mmを超えます"
            )

        # コマを下げた分だけ支柱を長くする
        posts = base_posts
        if m > 0 and adj:
            # 最下段の下に調整支柱（短い順に下から。カタログ Q12「MN-P2.25 | P13.5（左が下段）」）。上の支柱はそのまま
            extra = table.get(int(m * koma))
            posts = sorted(extra) + list(base_posts) if extra else base_posts
        elif m > 0:
            extra = table.get(base_total + int(m * koma))
            posts = sorted(extra, reverse=True) if extra else base_posts
            if extra is None:
                foot_warnings.append(
                    f"{m}コマ分（{m * koma:.0f}mm）延長した支柱構成を組めません"
                )

        feet.append(PostFoot(
            index=i, x=x, y=y, gl_mm=gl, koma_offset=m, jack_mm=jack,
            posts=posts, base_plate_adjust_mm=adjust, warnings=foot_warnings, row=rows[i],
        ))

    notes: list[str] = []
    diff = gl_max - gl_min
    if diff > 0:
        notes.append(
            f"敷地の高低差{diff:.0f}mmを支柱ごとのジャッキ・支柱長で吸収しました"
            f"（{len({f.koma_offset for f in feet})}種類の脚部構成）"
        )
    vm = model.master.vertical_member_name    # 支柱／建枠
    over_jack_warning = ""
    shimmed = [f for f in feet if f.base_plate_adjust_mm > 1e-6
               and any("実務上限" in w for w in f.warnings)]
    if shimmed:
        per_foot = [int(round(f.base_plate_adjust_mm / SHIM_UNIT_MM)) for f in shimmed]
        n_sheets = sum(per_foot)
        shim_msg = (
            f"ジャッキ繰出しが実務上限{shim_limit}mmを超える{vm}{len(shimmed)}本は、"
            f"敷板（厚{SHIM_UNIT_MM}mm）で持ち上げて上限内にしています（敷板 計{n_sheets}枚"
            + ("・内外の列の合計" if 1 in rows and 0 in rows else "・1列あたり")
            + (f"・1脚に最多{max(per_foot)}枚。" if max(per_foot) > 1 else "。")
            + "脚ごとの枚数はジャッキ量一覧の敷板調整欄）。床均しで高低差を縮めれば敷板は減らせます"
        )
        # 敷板を何枚も重ねた脚は据わりが悪い。重ねる枚数の多い脚は敷角か床均しに替える
        stacked = sum(1 for n in per_foot if n >= SHIM_STACK_WARN)
        if stacked:
            shim_msg += (f"。{SHIM_STACK_WARN}枚以上重ねる脚{stacked}本は、敷角に替えるか"
                         "その脚の周りを床均しして重ねる枚数を減らしてください")
        warnings.append(shim_msg)
        over_jack_warning = shim_msg
    over = [f for f in feet if f.jack_mm > jack_recommended_max]
    if over:
        window = jack_recommended_max - jack_min
        msg = (
            f"ジャッキ繰出しが実務上限{jack_recommended_max}mmを超える{vm}が"
            f"{len(over)}本あります（最大{max(f.jack_mm for f in over):.0f}mm）。"
        )
        if diff <= koma:
            # 高低差がコマピッチ以内なら、床均しで全数を上限内に収められる
            need = max(0.0, diff - window)
            msg += (
                f"高低差が{step_name}{koma:.0f}mm以内なので、"
                f"床均しで高低差を{need:.0f}mm縮めれば全{vm}が上限内に収まります"
            )
        else:
            msg += (
                f"ジャッキの可動域（{jack_min}〜{jack_recommended_max}mm＝{window}mm）は"
                f"{step_name}{koma:.0f}mmより狭いため、高低差が1段を超える敷地では"
                f"一定数が上限を超えます。該当{vm}の敷板調整または部分的な床均しで対応してください"
            )
        warnings.append(msg)
        over_jack_warning = msg
    cannot = [f for f in feet if any("組めません" in w for w in f.warnings)]
    if cannot:
        # 脚ごとの備考にしか出ないと、総合判定が成立のまま部材が足りない計画になる
        warnings.append(
            f"継ぎ足した{vm}構成を組めない脚が{len(cannot)}本あります"
            f"（最大{max(f.koma_offset for f in cannot)}{step_name}分）。"
            "マスタの支柱長で構成できない段差です。床均しか支柱規格の追加を検討してください"
        )
    # 敷板で上限内に収めた脚は上の注記で数えたので重ねない（同じ脚が「上限内にしています」と
    # 「吸収しきれない」の両方に数えられ、10本・12本・32本と食い違って見えた）
    shimmed_ids = {id(f) for f in shimmed}
    need_plate = [f for f in feet if abs(f.base_plate_adjust_mm) > 1e-6 and id(f) not in shimmed_ids]
    if need_plate:
        warnings.append(
            f"ジャッキを最小{jack_min}mmまで縮めても高すぎる{vm}が{len(need_plate)}本あります"
            f"（最大{-min(f.base_plate_adjust_mm for f in need_plate):.0f}mm。脚ごとに床掘りで下げる深さを一覧に明示しています）"
        )

    # 足元の勾配（脚ごと）。勾配のある脚はジャッキベースを傾斜に合わせ、敷板を勾配に沿わせて据える（利用者の指定
    # 2026-10-24: 足元の勾配に合わせるように配置）
    slopes = [(ground.slope_at(f.x, f.y), f) for f in feet] if not ground.is_flat else []
    for sl, f in slopes:
        f.slope = sl
    steep = [f for sl, f in slopes if sl > SLOPE_SHIM_LIMIT]
    if slopes:
        mx = max(sl for sl, _f in slopes)
        if steep:
            warnings.append(
                f"足元の勾配が {SLOPE_SHIM_LIMIT * 100:.0f}% を超える{vm}が{len(steep)}本あります（最大 {mx * 100:.1f}%）。"
                "敷板を段切りして水平に据えるか、傾斜対応のジャッキベース（自在ジャッキベース）で受けてください"
                "（ジャッキ量一覧の勾配の列）")
        elif mx > 0.005:
            notes.append(f"足元の勾配は最大 {mx * 100:.1f}%。敷板は勾配に沿わせて据え、ジャッキで高さを合わせます")
    deck_levels_abs = [
        ref_jack_top - ref_jack + lvl for lvl in model.elevation.level_heights
    ]
    n_in = sum(1 for r in rows if r == rows[0]) if rows and rows[0] == 0 else len(feet)
    return TerrainResult(
        feet=feet[:n_in],
        feet_outer=feet[n_in:],
        reference_gl_mm=gl_max,
        gl_range_mm=(gl_min, gl_max),
        deck_levels_abs_mm=deck_levels_abs,
        warnings=warnings,
        notes=notes,
        over_jack_warning=over_jack_warning,
        vertical_member_name=vm,
        step_mm=float(koma),
    )


def outer_post_positions(model: ScaffoldModel) -> list[tuple[float, float]]:
    """外側の建地列の支柱位置（post_positions と同じ並び。内側の列から外へ建地列の間隔だけ）."""
    row = float(model.post_row_spacing_mm)
    pts: list[tuple[float, float]] = []
    for ep in model.plan.edges:
        edge = model.plan.outline.edges[ep.edge_index]
        ox, oy = edge.outward
        dx, dy = edge.direction
        x, y = ep.start_post[0] + ox * row, ep.start_post[1] + oy * row
        acc = 0.0
        pts.append((x, y))
        for sp in ep.spans[:-1]:
            acc += sp
            pts.append((x + dx * acc, y + dy * acc))
    return pts


def _foot_cost(jack: float, jack_min: int, shim_limit: int) -> float:
    """その繰出しの脚の足元の手間（敷板・床掘り）を mm で量る. 解の選び方にだけ使う.

    敷板を重ねるのと床を掘り下げるのは、どちらも足元の手間で据わりにも響く。小さい方を選ぶ。
    敷板2枚（70mm）までは並べて敷くのと変わらないので軽く見て、床掘りより先に使う。3枚目からは
    重ねた厚さそのまま。以前は可動域（最大350〜450）に入ることを最優先したので、50mm 掘れば済む
    脚に敷板6枚（210mm）を重ねていた（傾斜地の見本）。
    """
    if jack > shim_limit:
        n = math.ceil((jack - shim_limit) / SHIM_UNIT_MM - 1e-9)
        return SHIM_UNIT_MM * (n if n > SHIM_LIGHT else n / 2)
    if jack < jack_min:
        return jack_min - jack
    return 0.0


def _optimize_datum(
    gls: list[float],
    gl_max: float,
    ref_jack: int,
    koma: float,
    jack_min: int,
    shim_limit: int,
    jack_recommended_max: int,
) -> float:
    """基準面（ジャッキ天端の基準標高）を決める.

    基準面をδずらすと全支柱のジャッキ量が一様にδ動く。δはコマピッチ周期なので
    [0, koma) を走査すれば十分。足元の手間（敷板・床掘り）の合計 → 実務上限超えの本数
    （ロングジャッキに頼る脚）→ 1脚の最大 の順に最小化する。
    """
    if not gls:
        return gl_max + ref_jack
    best = None
    step = 5
    # 5mm刻みの走査に、名目のジャッキ量そのもの（例: 建枠の86mm）も候補として加える
    nominal_delta = int(round((ref_jack - jack_min) % koma))
    for delta in sorted(set(range(0, int(koma), step)) | {nominal_delta}):
        top = gl_max + jack_min + delta
        costs = []
        n_over = 0
        for gl in gls:
            m = _choose_koma_offset(top, gl, koma, jack_min, shim_limit, jack_recommended_max)
            jack = top - m * koma - gl
            costs.append(_foot_cost(jack, jack_min, shim_limit))
            n_over += jack_recommended_max < jack <= shim_limit
        # 同点なら名目のジャッキ量（立面ソルバが端数吸収で決めた値）に最も近い基準面。
        # これが無いと平坦な敷地でも delta=0（ジャッキ30mm）が選ばれ、立面（名目100mm）と
        # ジャッキ量一覧（30mm）が食い違い、足場全体が70mm低く組まれることになる
        d = (jack_min + delta - ref_jack) % koma
        near = min(d, koma - d)
        score = (round(sum(costs), 3), n_over, round(max(costs), 3), near)
        if best is None or score < best[0]:
            best = (score, top)
    return best[1]


def _choose_koma_offset(
    ref_jack_top: float,
    gl: float,
    koma: float,
    jack_min: int,
    shim_limit: int,
    jack_recommended_max: int,
) -> int:
    """足元の手間（敷板・床掘り）がいちばん小さい下げコマ数を選ぶ.

    同じなら実務上限内（ロングジャッキに頼らない）、その次に下げの少ない方。
    """
    raw = (ref_jack_top - gl - shim_limit) / koma
    best = None
    for m in range(max(0, math.floor(raw) - 1), math.ceil(raw) + 3):
        if m < 0:
            continue
        jack = ref_jack_top - m * koma - gl
        score = (round(_foot_cost(jack, jack_min, shim_limit), 3), jack > jack_recommended_max, m)
        if best is None or score < best[0]:
            best = (score, m)
    return best[1] if best else 0


def jack_table_rows(result: TerrainResult) -> list[list]:
    """ジャッキ量一覧（帳票用の行データ）."""
    vm = result.vertical_member_name
    rows = [[
        "No", "列", "X(mm)", "Y(mm)", "GL標高(mm)", "下げ段数",
        "ジャッキ繰出し(mm)", "敷板調整(mm)", f"{vm}構成", "勾配(%)", "備考",
    ]]
    for f in result.all_feet:
        rows.append([
            f.index + 1, "外" if f.row == 1 else "内", round(f.x), round(f.y), round(f.gl_mm, 1), f.koma_offset,
            round(f.jack_mm, 1), round(f.base_plate_adjust_mm, 1),
            spans_text(f.posts),
            round(f.slope * 100.0, 1),
            " / ".join(f.warnings) if f.warnings else "",
        ])
    return rows


def adjust_post_mm(master) -> int:
    """斜面で最下段に入れる調整支柱の刻み（コマピッチを割り切れる、コマピッチより短い支柱。無ければ 0）.

    日建ミレニュームの斜面の組み方（カタログ Q12。利用者の資料 2026-10-25）: 地盤のいちばん高い所を基準に最下段の
    支柱（MN-P27）をそろえ、低い所は調整用の支柱（MN-P2.25・P4.5・P9・P13.5 の組み合わせ）を最下段の下に入れて、
    ジャッキの繰出し（50〜300）と合わせて補う。225 の調整支柱がある系列は 225 刻みで下げる."""
    koma = int(master.koma_pitch or 0)
    if koma <= 0:
        return 0
    shorts = [int(p.nominal_dim) for p in master.by_category("支柱")
              if 0 < p.nominal_dim < koma and "根がらみ" not in p.note and koma % int(p.nominal_dim) == 0
              and p.nominal_dim >= 200]
    return min(shorts) if shorts else 0


def terrain_step_mm(model: ScaffoldModel) -> float:
    """下げ段数の刻み。くさびはコマピッチ（調整支柱のある系列はその長さ）、枠組は調整枠（最小の建枠）の高さ."""
    koma = model.master.koma_pitch
    if koma <= 0:
        koma = min(model.master.frame_heights() or [model.master.floor_height])
    return float(adjust_post_mm(model.master) or koma)


def datum_first_ledger_mm(model: ScaffoldModel, terrain) -> float:
    """基準面から見た第一の布（根がらみ）の高さ（gl_ref 基準, mm）.

    名目の first_ledger_height は名目のジャッキ量を前提にしている。敷地を解く
    ときは基準面の最適化でジャッキ量が名目から動く（枠組でジャッキ86→205mm）
    ので、実際の脚から基準面を逆算する。脚の下端＝gl＋敷板調整＋ジャッキで、
    下げた段数ぶんを戻せばどの脚からも同じ基準面が出る。
    """
    feet = list(getattr(terrain, "feet", []) or [])
    e = model.elevation
    if not feet:
        return float(e.first_ledger_height)
    step = terrain_step_mm(model)
    gl_ref = max(f.gl_mm for f in feet)
    f0 = feet[0]
    ref_top = f0.gl_mm + f0.base_plate_adjust_mm + f0.jack_mm + f0.koma_offset * step
    # 名目の「ジャッキ天端から第一の布まで」（くさび=コマ1つ、枠組=0）はそのまま
    return (ref_top - gl_ref) + float(e.first_ledger_height - e.jack_extension)


def edge_foot_indices(model: ScaffoldModel, ep, n_feet: int) -> list[int]:
    """この辺の支柱位置（始点・中間・終点）が feet の何番目か.

    feet は post_positions() の順（各辺の始点＋中間支柱）。終点は次の辺の始点。
    """
    offset = sum(e.span_count for e in model.plan.edges if e.edge_index < ep.edge_index)
    idx = list(range(offset, offset + ep.span_count))
    nxt = offset + ep.span_count
    idx.append(nxt if nxt < n_feet else 0)
    return idx


def extra_negarami(model: ScaffoldModel, terrain) -> dict[int, list[tuple[int, float]]]:
    """継ぎ足した脚の区間に入れる根がらみ（辺 → [(スパン番号, 基準GLからの高さmm)]）.

    基準の根がらみは最も高い地盤に合わせた高さなので、下げた脚では地盤から
    離れる（地上第一の布2m以下＝安衛則571条、根がらみ＝570条）。区間の両端の
    脚のうち下げ段数の少ない方に合わせ、その段数ぶん下げた高さに1段入れる。
    くさびのコマ（緊結部）は全支柱で基準面の格子に揃うので、この高さは
    両端の支柱の緊結部に必ず乗る。図面（2D/3D）も同じ規則で描く。
    """
    feet = list(getattr(terrain, "feet", []) or [])
    out: dict[int, list[tuple[int, float]]] = {}
    if not feet:
        return out
    step = terrain_step_mm(model)
    nega = datum_first_ledger_mm(model, terrain)
    for ep in model.plan.edges:
        idx = edge_foot_indices(model, ep, len(feet))
        if max(idx) >= len(feet):
            continue
        rows = []
        half = step < float(model.master.koma_pitch or 0) - 0.5     # 調整支柱が半コマ（ミレニューム 225）
        for i in range(ep.span_count):
            ma, mb = feet[idx[i]].koma_offset, feet[idx[i + 1]].koma_offset
            m = min(ma, mb)
            if m >= 1 or (half and abs(ma - mb) % 2 == 1 and max(ma, mb) >= 1):
                # 半コマの調整支柱で下げ段数の偶奇が違う区間は、脚から脚へ斜めに渡す（3d.gdl と同じ。高さは浅い脚の側）
                rows.append((i, nega - m * step))
        if rows:
            out[ep.edge_index] = rows
    return out


def first_ledger_heights(model: ScaffoldModel, terrain) -> list[float]:
    """脚ごとの、その脚の地盤から最初の布（根がらみ）までの高さ（mm）.

    継ぎ足し部の根がらみ（extra_negarami）を含めて、脚に取り付く最も低い布で見る。
    """
    feet = list(getattr(terrain, "feet", []) or [])
    if not feet:
        return []
    gl_ref = max(f.gl_mm for f in feet)
    nega = datum_first_ledger_mm(model, terrain)
    levels: dict[int, list[float]] = {i: [nega] for i in range(len(feet))}
    extra = extra_negarami(model, terrain)
    for ep in model.plan.edges:
        idx = edge_foot_indices(model, ep, len(feet))
        if max(idx) >= len(feet):
            continue
        for i, lvl in extra.get(ep.edge_index, []):
            levels[idx[i]].append(lvl)
            levels[idx[i + 1]].append(lvl)
    # 支持面は敷板（正）・床掘り（負）の調整後。元の地盤で測ると、床掘りした脚で
    # 「地盤より下の布」という負の高さが出る（実際に-300mmと出た）
    return [
        min(levels[i]) - (f.gl_mm + f.base_plate_adjust_mm - gl_ref)
        for i, f in enumerate(feet)
    ]


def actual_max_height_mm(model: ScaffoldModel, terrain=None) -> tuple[float, float]:
    """判定・届出に使う足場高さと、敷地の低い側で伸びた分（mm）.

    高低差のある敷地では支柱を下へ継ぎ足すので、最も低い脚の実高さは名目の
    足場高さより大きい。31m/45m・朝顔の段数・届出要否・風の高さ補正は
    この実高さで見る（名目で見ると崖地の36mを16mとして通してしまう）。
    """
    nominal = float(model.scaffold_height_mm)
    feet = list(getattr(terrain, "feet", []) or [])
    if not feet:
        return nominal, 0.0
    tallest = max(sum(f.posts) + f.jack_mm for f in feet)
    return max(nominal, tallest), max(0.0, tallest - nominal)

