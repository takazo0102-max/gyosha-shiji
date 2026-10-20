"""足場ラインを部材（1本＝1部品 ashiba_member）に分解する（利用者の指定 2026-10-21: 部材を分解できるコマンドを Tapir に）.

足場ライン（面ごとに1部品）が描いている支柱・ジャッキ・布材（根がらみ・腕木・手すり・中桟）・先行手すり・
踏板・幅木・ブレースを、足場ラインの GDL パラメータから同じ規則で並べ直し、1本ずつの部品にする。
分解した足場ラインは explodeMask=1 で、それらの部材を描かない（階段・朝顔・出隅・開口部の梁枠・ステージ・
壁つなぎなどは足場ラインのまま）。「分解を戻す」で部品を消して足場ラインに戻す。

座標: 足場ラインの局所座標（x＝面に沿う向き、y＝躯体側が＋、外側建地列は y=-rowW、z＝足場の立つ面から）を、
足場ラインの原点・回転で平面の座標に直す。

くさび式は支柱を1本ずつ、枠組（serType W）は建枠を1枚ずつ（脚2本・横架材・鳥居の縦材）と交差筋違にする。
敷地の高低差（脚ごとの地盤高）、荷受けステージ・昇降機の乗り込み口・ブラケット区間で手すりを外す升目は
考えず、全部の升目に手すりを置く（分解後にその部材を消す）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

MEMBER_OBJECT = "ashiba_member"
KIND = {"支柱": 1, "布材": 2, "踏板": 3, "幅木": 4, "先行手すり": 5, "ブレース": 6, "ジャッキ": 7, "建枠": 8, "交差筋違": 9}
R_NUNO = 0.0427 / 2


@dataclass
class Member:
    kind: int
    x: float              # 局所 m
    y: float
    z: float
    ang: float = 0.0      # 局所の向き（度。0＝+x）
    L: float = 0.0
    W: float = 0.0
    H: float = 0.0
    koma: list = field(default_factory=list)   # 支柱のコマ（下端から mm）
    name: str = ""
    flags: int = 0        # 建枠: 1＝下の建枠との継ぎ目、2＝躯体側の脚を描かない


def _nums(v) -> list[float]:
    out = []
    for t in str(v or "").replace(" ", "").split(","):
        if t == "":
            continue
        try:
            out.append(float(t))
        except ValueError:
            pass
    return out


def _f(p: dict, k: str, d: float = 0.0) -> float:
    try:
        return float(p.get(k, d))
    except (TypeError, ValueError):
        return d


def _i(p: dict, k: str, d: int = 0) -> int:
    try:
        return int(round(float(p.get(k, d))))
    except (TypeError, ValueError):
        return d


def koma_offsets(length_m: float, pitch: float, gap: float, nega: float, nega_lens_mm: list) -> list[int]:
    """支柱1本のコマの高さ（下端から mm）。足場ライン 3d.gdl の kzAll と同じ規則（master.post_koma_offsets）."""
    if pitch <= 0:
        return []
    out = set()
    z = length_m - gap
    while z >= 0.1 - 0.0001:
        out.add(round(z * 1000))
        z -= pitch
    if nega > 0.001 and any(abs(v / 1000 - length_m) < 0.0005 for v in nega_lens_mm):
        out.add(round(nega * 1000))
        zm = length_m - gap
        while zm - pitch > nega + 0.001:
            zm -= pitch
        if zm > nega + 0.75 * pitch + 0.001 and pitch - gap < length_m:
            out.add(round((pitch - gap) * 1000))
    return sorted(out)


def _edits(p: dict) -> list[tuple]:
    v = [int(round(x)) for x in _nums(p.get("editList"))]
    return [tuple(v[i:i + 5]) for i in range(0, len(v) - 4, 5)]


def _edit_bit(edits, ip: int, level: int, bit: int) -> bool:
    return any(a <= ip <= b and c <= level <= d and (e >> bit) & 1 for a, b, c, d, e in edits)


def line_members(p: dict) -> list[Member]:
    """足場ラインの GDL パラメータ → 局所座標の部材の並び（3d.gdl の支柱・水平材・踏板・幅木・ブレースと同じ規則）."""
    frame = str(p.get("serType", "A")).strip() == "W"
    spans = [v / 1000 for v in _nums(p.get("spanList")) + _nums(p.get("spanList2"))]
    posts = [v / 1000 for v in _nums(p.get("postList"))]
    if not spans or not posts:
        raise ValueError("足場ラインのスパン・支柱構成が読めません")
    row_w = _f(p, "rowW", 0.61)
    jack = _f(p, "jackOut", 0.2)
    n_rows = _i(p, "nRows", 2)
    row_start = 1 if n_rows < 2 else 0
    pitch, gap = _f(p, "komaPitch", 0.45), _f(p, "komaGap")
    nega, nega_lens = _f(p, "komaNega"), _nums(p.get("negaLens"))
    r_sic = (_f(p, "postDia", 0.0427) or 0.0427) / 2
    post_top = jack + sum(posts)
    levels = [v / 1000 for v in _nums(p.get("levelList"))]
    lv = [_f(p, "negaH") or (jack + pitch)] + levels
    rail_top = _f(p, "railH") or 2 * pitch
    rail_mid = _f(p, "midH") or pitch
    rail_adv = _i(p, "railAdv") == 1
    rail_in = _i(p, "railIn") == 1 and n_rows >= 2
    deck_w1, deck_w2 = _f(p, "deckW1", 0.5), _f(p, "deckW2")
    ev_s, ev_l = max(1, _i(p, "braceEveryS", 1)), max(1, _i(p, "braceEveryL", 1))
    skip_s, skip_e = _i(p, "skipInS"), _i(p, "skipInE")
    st_out = _i(p, "stOut") == 1
    st = _nums(p.get("stairList"))
    towers = [(st[i] / 1000, st[i + 1] / 1000) for i in range(0, len(st) - 1, 2)]
    bm = _nums(p.get("beamList"))
    beams = [(bm[i] / 1000, bm[i + 1] / 1000, bm[i + 2] / 1000) for i in range(0, len(bm) - 2, 3)]
    edits = _edits(p)
    xs = [0.0]
    for s in spans:
        xs.append(xs[-1] + s)
    n_span, n_lv = len(spans), len(lv)
    out: list[Member] = []

    def under_beam(x0, x1, z):
        return any(x0 >= s - 0.001 and x1 <= s + ln + 0.001 and z < h - 0.001 for s, ln, h in beams)

    # ---- 支柱とジャッキ（各スパン境界に内外1対。隅の内側建地は隣の面が持つ。梁枠の内側は梁枠の上から） ----
    for ip, x in enumerate(xs):
        b_base = 0.0
        for s, ln, h in beams:
            if s + 0.001 < x < s + ln - 0.001:
                b_base = h
        for row in range(row_start, 2):
            if row == 0 and ((ip == 0 and skip_s) or (ip == n_span and skip_e)):
                continue
            y = -row * row_w
            if b_base:
                out.append(Member(1, x, y, b_base, L=post_top - b_base, name=f"支柱（梁枠上）{(post_top - b_base) * 1000:.0f}"))
                continue
            out.append(Member(7, x, y, 0.0, H=jack, name=f"ジャッキベース 繰出し{jack * 1000:.0f}"))
            if frame:
                continue                  # 建枠は内外の脚を1枚で（下でまとめて置く）
            z = jack
            for pl in posts:
                out.append(Member(1, x, y, z, L=pl, koma=koma_offsets(pl, pitch, gap, nega, nega_lens),
                                  name=f"支柱 {pl * 1000:.0f}"))
                z += pl

    # ---- 建枠（枠組。支柱位置ごとに段数ぶん積む。隅で隣の面と共有する躯体側の脚は描かない） ----
    if frame:
        for ip, x in enumerate(xs):
            if any(s + 0.001 < x < s + ln - 0.001 for s, ln, h in beams):
                continue
            shared = (ip == 0 and skip_s) or (ip == n_span and skip_e)
            z = jack
            for j, pl in enumerate(posts):
                out.append(Member(8, x, 0.0, z, L=pl, W=row_w, flags=(1 if j else 0) | (2 if shared else 0),
                                  name=f"建枠 {row_w * 1000:.0f}×{pl * 1000:.0f}"))
                z += pl

    # ---- 水平材（根がらみ・腕木・外側の手すり・中桟／先行手すり・内側の手すり・中桟） ----
    for il in range(n_lv):
        z = lv[il]
        for ip in range(n_span):
            x, sp = xs[ip], spans[ip]
            k = il                     # 作業床の層（1始まり。根がらみは0）
            skip_h = under_beam(x, x + sp, z)
            if il == 0 and not skip_h:
                for row in range(row_start, 2):
                    out.append(Member(2, x, -row * row_w, z, L=sp, name=f"布材（根がらみ）{sp * 1000:.0f}"))
            in_sg = st_out and any(abs(x - s) < 0.001 or abs(x + sp - s - ln) < 0.001 for s, ln in towers)
            # 枠組の中間層の手すりは1つ上の建枠が兼ねる（最上層だけ布材）
            fr_mid = frame and il < n_lv - 1
            if il > 0 and not skip_h and not in_sg and not fr_mid and not _edit_bit(edits, ip + 1, k, 1):
                if rail_adv:
                    out.append(Member(5, x, -row_w, z, L=sp, H=rail_top, name=f"先行手すり {sp * 1000:.0f}"))
                else:
                    out.append(Member(2, x, -row_w, z + rail_top, L=sp, name=f"布材（手すり）{sp * 1000:.0f}"))
                    out.append(Member(2, x, -row_w, z + rail_mid, L=sp, name=f"布材（中桟）{sp * 1000:.0f}"))
            if il > 0 and not skip_h and rail_in and not _edit_bit(edits, ip + 1, k, 4):
                out.append(Member(2, x, 0.0, z + rail_top, L=sp, name=f"布材（躯体側の手すり）{sp * 1000:.0f}"))
                out.append(Member(2, x, 0.0, z + rail_mid, L=sp, name=f"布材（躯体側の中桟）{sp * 1000:.0f}"))
        # 腕木（支柱位置ごと、内外の建地列の間。梁枠の内側の支柱を抜いた位置には無い）。枠組は建枠の横架材
        if n_rows >= 2 and not frame:
            for ip, x in enumerate(xs):
                if any(s + 0.001 < x < s + ln - 0.001 and z < h - 0.001 for s, ln, h in beams):
                    continue
                out.append(Member(2, x, 0.0, z, ang=-90.0, L=row_w, name=f"布材（腕木）{row_w * 1000:.0f}"))

    # ---- 踏板・幅木 ----
    for il in range(1, n_lv):
        z, k = lv[il], il
        for ip in range(n_span):
            x, sp = xs[ip], spans[ip]
            if under_beam(x, x + sp, z):
                continue
            skip_deck = False
            for s, ln in towers:
                if not st_out and x >= s - 0.001 and x + sp <= s + ln + 0.001:
                    if ln <= sp + 0.001:
                        skip_deck = True
                    else:
                        odd = k % 2 == 1
                        if abs(x - s) < 0.001:
                            skip_deck = skip_deck or odd
                        elif ip > 0 and abs(x - spans[ip - 1] - s) < 0.001:
                            skip_deck = skip_deck or not odd
            # 足場の中の階段室の区間は踏板の編集を効かせない（数量・足場ラインの 3D と同じ）
            in_tower = not st_out and any(x >= s - 0.001 and x + sp <= s + ln + 0.001 for s, ln in towers)
            if _edit_bit(edits, ip + 1, k, 0) and not in_tower:
                skip_deck = True
            if not skip_deck:
                if in_tower or not _edit_bit(edits, ip + 1, k, 5):
                    out.append(Member(3, x, -row_w + 0.05, z, L=sp, W=deck_w1 - 0.01,
                                      name=f"踏板 {deck_w1 * 1000:.0f}×{sp * 1000:.0f}"))
                if deck_w2 > 0 and (in_tower or not _edit_bit(edits, ip + 1, k, 6)):
                    out.append(Member(3, x, -row_w + 0.05 + deck_w1 + 0.02, z, L=sp, W=deck_w2 - 0.01,
                                      name=f"踏板 {deck_w2 * 1000:.0f}×{sp * 1000:.0f}"))
            in_sg = st_out and any(abs(x - s) < 0.001 or abs(x + sp - s - ln) < 0.001 for s, ln in towers)
            if not rail_adv and not in_sg and not _edit_bit(edits, ip + 1, k, 2):
                out.append(Member(4, x - 0.035, -row_w + r_sic + 0.004, z + R_NUNO + 0.045, L=sp + 0.07,
                                  name=f"幅木 {sp * 1000:.0f}"))

    # ---- 出隅の升目（くさび式。始点側の外側コーナー支柱と、隣の面の外側列の延長・この面の外側列の手前） ----
    if not frame and _i(p, "cornerS") == 1:
        cx = cy = -row_w
        out.append(Member(7, cx, cy, 0.0, H=jack, name=f"ジャッキベース（出隅）繰出し{jack * 1000:.0f}"))
        z = jack
        for pl in posts:
            out.append(Member(1, cx, cy, z, L=pl, koma=koma_offsets(pl, pitch, gap, nega, nega_lens),
                              name=f"支柱（出隅）{pl * 1000:.0f}"))
            z += pl
        for il in range(n_lv):
            heights = [lv[il]] + ([lv[il] + rail_top, lv[il] + rail_mid] if il > 0 else [])
            for zz in heights:
                tag = "根がらみ" if il == 0 else ("床" if zz == lv[il] else "手すり・中桟")
                # 前の面の外側列の延長（この面の内側建地列の位置から -Y へ）と、この面の外側列の手前（+X へ）
                out.append(Member(2, cx, 0.0, zz, ang=-90.0, L=row_w, name=f"布材（出隅・{tag}）{row_w * 1000:.0f}"))
                out.append(Member(2, cx, cy, zz, ang=0.0, L=row_w, name=f"布材（出隅・{tag}）{row_w * 1000:.0f}"))
            if il > 0:
                out.append(Member(3, cx + 0.025, cy + 0.05, lv[il], L=row_w - 0.025, W=row_w - 0.05,
                                  name="踏板（出隅）"))
                if not rail_adv:
                    tz = lv[il] + R_NUNO + 0.045
                    out.append(Member(4, cx + r_sic + 0.004, cy + r_sic + 0.004, tz, L=row_w - r_sic,
                                      name="幅木（出隅）"))
                    out.append(Member(4, cx + r_sic + 0.004, 0.0, tz, ang=-90.0, L=row_w - r_sic + 0.004,
                                      name="幅木（出隅）"))

    # ---- 開放端（一部の面だけの足場で隣の面を掛けない端）: 妻側の手すり・中桟・幅木 ----
    line_len = xs[-1]
    for xe, flag in ((0.0, _i(p, "endOpenS")), (line_len, _i(p, "endOpenE"))):
        if flag != 1:
            continue
        for il in range(1, n_lv):
            z = lv[il]
            for zz in (z + rail_top, z + rail_mid):
                out.append(Member(2, xe, 0.0, zz, ang=-90.0, L=row_w, name=f"布材（妻側の手すり）{row_w * 1000:.0f}"))
            # 幅木は板が足場の内側に来る向き（始点の端は +X、終点の端は -X）
            if xe == 0.0:
                out.append(Member(4, xe, 0.0, z + R_NUNO + 0.045, ang=-90.0, L=row_w, name="幅木（妻側）"))
            else:
                out.append(Member(4, xe, -row_w, z + R_NUNO + 0.045, ang=90.0, L=row_w, name="幅木（妻側）"))

    # ---- 交差筋違（枠組。全構面の両面、建枠の脚の筋違ピンに掛ける） ----
    if frame:
        for il in range(n_lv - 1):
            z1, z2 = lv[il], lv[il + 1]
            bpz = 0.24 if z2 - z1 >= 0.9 else 0.10
            for ip in range(n_span):
                if _edit_bit(edits, ip + 1, il + 1, 3):
                    continue
                x, sp = xs[ip], spans[ip]
                for bf in (0, 1):
                    yb = -row_w - 0.035 if bf == 0 else 0.035
                    leg = -row_w if bf == 0 else 0.0
                    out.append(Member(9, x, yb, z1 + bpz, L=sp, H=z2 - z1 - 2 * bpz, W=leg - yb,
                                      name=f"交差筋違 {sp * 1000:.0f}"))
        return out

    # ---- ブレース（外側構面、bEvS スパン・bEvL 層ごとに交さ2方向） ----
    br_z = 0.10
    for il in range(n_lv - 1):
        if il % ev_l:
            continue
        z1, z2 = lv[il], lv[il + 1]
        for ip in range(n_span):
            if ip % ev_s or _edit_bit(edits, ip + 1, il + 1, 3):
                continue
            x, sp = xs[ip], spans[ip]
            for bf in (0, 1):
                yb = -row_w - r_sic - 0.0214 - 0.004 - bf * 0.046
                reach = -row_w - yb       # クランプからこの面の外側建地列の芯まで
                if bf == 0:
                    out.append(Member(6, x, yb, z1 + br_z, ang=0.0, L=sp, W=reach, H=z2 - z1 - 2 * br_z,
                                      name=f"ブレース {sp * 1000:.0f}"))
                else:
                    out.append(Member(6, x + sp, yb, z1 + br_z, ang=180.0, L=sp, W=-reach, H=z2 - z1 - 2 * br_z,
                                      name=f"ブレース {sp * 1000:.0f}"))
    return out


def to_world(members: list[Member], origin_m: tuple, angle_rad: float, base_z_m: float = 0.0) -> list[dict]:
    """局所の部材 → 部品を置く位置（平面 m）と GDL パラメータ."""
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    deg = math.degrees(angle_rad)
    out = []
    for m in members:
        wx = origin_m[0] + m.x * c - m.y * s
        wy = origin_m[1] + m.x * s + m.y * c
        out.append({
            "x": wx, "y": wy,
            "params": {
                "kind": int(m.kind), "faceAng": (deg + m.ang) % 360.0, "zH": base_z_m + m.z,
                "memL": float(m.L), "memW": float(m.W), "memH": float(m.H),
                "komaList": ",".join(str(v) for v in m.koma), "partName": m.name, "frFlags": int(m.flags),
            },
        })
    return out


def member_counts(members: list[Member]) -> dict[str, int]:
    """部材名ごとの本数（分解の結果の確認用）."""
    out: dict[str, int] = {}
    for m in members:
        out[m.name] = out.get(m.name, 0) + 1
    return out
