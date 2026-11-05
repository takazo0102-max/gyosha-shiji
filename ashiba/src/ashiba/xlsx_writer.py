"""依存ゼロの最小XLSXライタ.

openpyxl等の外部依存を避ける（Archicad同梱Pythonでも動かすため）。
必要十分な機能に絞る: 複数シート・文字列/数値セル・太字・セル結合・列幅・数式。

xlsxはOOXMLのzip。ここでは共有文字列を使わずインラインstrで書く（実装が単純で堅い）。
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

Value = Union[str, int, float, None]

# スタイルID（styles.xml の cellXfs の並び順と一致させること）
STYLE_DEFAULT = 0
STYLE_BOLD = 1
STYLE_TITLE = 2
STYLE_NUM2 = 3      # 小数2桁
STYLE_HEADER = 4    # 太字＋背景＋罫線
STYLE_BORDER = 5
STYLE_SMALL = 6     # 8pt・中央・罫線（工程表の日付）
STYLE_OFF = 7       # 8pt・中央・罫線・灰（休みの日）
STYLE_TEXT = 8      # 9pt・左・罫線・折り返し（工程表の作業名）
# 工程表の線（塗り）。BAR_COLORS の順に STYLE_BAR + i
BAR_COLORS = ("FF8EA9DB", "FFC9A36B", "FFF4B183", "FFFF7C80", "FFD9D9D9", "FF5B9BD5", "FF70AD47", "FFE7E6E6", "FFB4A7D6")
STYLE_BAR = 9
STYLE_YEN = STYLE_BAR + len(BAR_COLORS)      # 3桁区切りの整数・罫線（仮設の金額）


@dataclass
class Cell:
    value: Value = None
    style: int = STYLE_DEFAULT
    formula: Optional[str] = None


@dataclass
class Sheet:
    name: str
    rows: list[list[Cell]] = field(default_factory=list)
    col_widths: dict[int, float] = field(default_factory=dict)  # 0-based列→幅
    merges: list[str] = field(default_factory=list)             # 例 "A1:D1"
    freeze: tuple = ()                                          # (行, 列) より上・左を固定（工程表の見出しと作業名）
    landscape_a3: bool = False                                  # 印刷は A3 横・幅を1ページに
    row_heights: dict[int, float] = field(default_factory=dict)  # 0-based行→高さ pt

    def add(self, values: list[Value], style: int = STYLE_DEFAULT) -> None:
        self.rows.append([Cell(v, style) for v in values])

    def add_cells(self, cells: list[Cell]) -> None:
        self.rows.append(cells)

    def add_blank(self, n: int = 1) -> None:
        for _ in range(n):
            self.rows.append([])

    def add_title(self, text: str, span: int = 6) -> None:
        r = len(self.rows) + 1
        self.rows.append([Cell(text, STYLE_TITLE)])
        if span > 1:
            self.merges.append(f"A{r}:{_col_name(span - 1)}{r}")

    def add_header(self, values: list[Value]) -> None:
        self.rows.append([Cell(v, STYLE_HEADER) for v in values])

    def set_width(self, col: int, width: float) -> None:
        self.col_widths[col] = width


class Workbook:
    def __init__(self) -> None:
        self.sheets: list[Sheet] = []

    def sheet(self, name: str) -> Sheet:
        s = Sheet(name=name)
        self.sheets.append(s)
        return s

    def save(self, path: Path) -> None:
        path = Path(path)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", self._content_types())
            z.writestr("_rels/.rels", _RELS_ROOT)
            z.writestr("xl/workbook.xml", self._workbook_xml())
            z.writestr("xl/_rels/workbook.xml.rels", self._workbook_rels())
            z.writestr("xl/styles.xml", _STYLES_XML)
            for i, s in enumerate(self.sheets, start=1):
                z.writestr(f"xl/worksheets/sheet{i}.xml", _sheet_xml(s))

    def _content_types(self) -> str:
        overrides = "".join(
            f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.'
            'spreadsheetml.worksheet+xml"/>'
            for i in range(1, len(self.sheets) + 1)
        )
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.'
            'relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.'
            'openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.'
            'openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            f"{overrides}</Types>"
        )

    def _workbook_xml(self) -> str:
        sheets = "".join(
            f'<sheet name="{_esc(s.name)}" sheetId="{i}" r:id="rId{i}"/>'
            for i, s in enumerate(self.sheets, start=1)
        )
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f"<sheets>{sheets}</sheets></workbook>"
        )

    def _workbook_rels(self) -> str:
        rels = "".join(
            f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/'
            'officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{i}.xml"/>'
            for i in range(1, len(self.sheets) + 1)
        )
        style_id = len(self.sheets) + 1
        rels += (
            f'<Relationship Id="rId{style_id}" Type="http://schemas.openxmlformats.org/'
            'officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        )
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
            f'relationships">{rels}</Relationships>'
        )


def _col_name(idx: int) -> str:
    """0-based列インデックス → A, B, ... Z, AA"""
    name = ""
    idx += 1
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        name = chr(65 + rem) + name
    return name


def _is_finite(v) -> bool:
    return not isinstance(v, float) or (v == v and v not in (float("inf"), float("-inf")))


def _esc(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _sheet_xml(sheet: Sheet) -> str:
    cols = ""
    if sheet.col_widths:
        items = "".join(
            f'<col min="{c + 1}" max="{c + 1}" width="{w}" customWidth="1"/>'
            for c, w in sorted(sheet.col_widths.items())
        )
        cols = f"<cols>{items}</cols>"

    rows_xml = []
    for r, row in enumerate(sheet.rows, start=1):
        cells = []
        for c, cell in enumerate(row):
            ref = f"{_col_name(c)}{r}"
            st = f' s="{cell.style}"' if cell.style else ""
            if cell.formula:
                cells.append(f'<c r="{ref}"{st}><f>{_esc(cell.formula)}</f></c>')
            elif cell.value is None or cell.value == "":
                if cell.style:
                    cells.append(f'<c r="{ref}"{st}/>')
            elif isinstance(cell.value, bool):
                cells.append(f'<c r="{ref}"{st} t="inlineStr"><is><t>'
                             f'{_esc(str(cell.value))}</t></is></c>')
            elif isinstance(cell.value, (int, float)) and _is_finite(cell.value):
                cells.append(f'<c r="{ref}"{st}><v>{cell.value}</v></c>')
            elif isinstance(cell.value, float):
                # inf / nan を数値セルに書くとブックが開けなくなる。
                # 検定比は許容耐力0のとき inf になり得るので、文字で残す
                cells.append(f'<c r="{ref}"{st} t="inlineStr"><is><t>'
                             f'{_esc("計算不能(" + str(cell.value) + ")")}</t></is></c>')
            else:
                cells.append(f'<c r="{ref}"{st} t="inlineStr"><is><t xml:space="preserve">'
                             f"{_esc(cell.value)}</t></is></c>")
        ht = sheet.row_heights.get(r - 1)
        hx = f' ht="{ht}" customHeight="1"' if ht else ""
        rows_xml.append(f'<row r="{r}"{hx}>{"".join(cells)}</row>')

    merges = ""
    if sheet.merges:
        items = "".join(f'<mergeCell ref="{m}"/>' for m in sheet.merges)
        merges = f'<mergeCells count="{len(sheet.merges)}">{items}</mergeCells>'

    pr = views = page = ""
    if sheet.freeze:
        fr, fc = sheet.freeze
        top = f"{_col_name(fc)}{fr + 1}"
        attrs = (f' xSplit="{fc}"' if fc else "") + (f' ySplit="{fr}"' if fr else "")
        pane = "bottomRight" if fr and fc else ("bottomLeft" if fr else "topRight")
        views = (f'<sheetViews><sheetView workbookViewId="0"><pane{attrs} topLeftCell="{top}" activePane="{pane}" '
                 f'state="frozen"/></sheetView></sheetViews>')
    if sheet.landscape_a3:
        pr = '<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>'
        page = ('<pageMargins left="0.4" right="0.4" top="0.5" bottom="0.5" header="0.2" footer="0.2"/>'
                '<pageSetup paperSize="8" orientation="landscape" fitToWidth="1" fitToHeight="0"/>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'{pr}{views}{cols}<sheetData>{"".join(rows_xml)}</sheetData>{merges}{page}</worksheet>'
    )


_RELS_ROOT = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
    'relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'
)

# fonts: 0=標準 1=太字 2=タイトル(14pt太字)
# fills: 0=none 1=gray125(必須) 2=ヘッダ背景
# borders: 0=なし 1=細罫
# cellXfs の並びが STYLE_* 定数に対応
_STYLES_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    '<fonts count="5">'
    '<font><sz val="11"/><name val="ＭＳ Ｐゴシック"/></font>'
    '<font><b/><sz val="11"/><name val="ＭＳ Ｐゴシック"/></font>'
    '<font><b/><sz val="14"/><name val="ＭＳ Ｐゴシック"/></font>'
    '<font><sz val="8"/><name val="ＭＳ Ｐゴシック"/></font>'
    '<font><sz val="9"/><name val="ＭＳ Ｐゴシック"/></font>'
    "</fonts>"
    f'<fills count="{4 + len(BAR_COLORS)}">'
    '<fill><patternFill patternType="none"/></fill>'
    '<fill><patternFill patternType="gray125"/></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFD9E1F2"/>'
    '<bgColor indexed="64"/></patternFill></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFEDEDED"/><bgColor indexed="64"/></patternFill></fill>'
    + "".join(f'<fill><patternFill patternType="solid"><fgColor rgb="{c}"/><bgColor indexed="64"/></patternFill></fill>'
              for c in BAR_COLORS)
    + "</fills>"
    '<borders count="2">'
    "<border><left/><right/><top/><bottom/><diagonal/></border>"
    '<border><left style="thin"/><right style="thin"/><top style="thin"/>'
    '<bottom style="thin"/><diagonal/></border>'
    "</borders>"
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>'
    "</cellStyleXfs>"
    f'<cellXfs count="{10 + len(BAR_COLORS)}">'
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    '<xf numFmtId="2" fontId="0" fillId="0" borderId="1" xfId="0" '
    'applyNumberFormat="1" applyBorder="1"/>'
    '<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" '
    'applyFont="1" applyFill="1" applyBorder="1"/>'
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1"/>'
    '<xf numFmtId="0" fontId="3" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1">'
    '<alignment horizontal="center" vertical="center"/></xf>'
    '<xf numFmtId="0" fontId="3" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" '
    'applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>'
    '<xf numFmtId="0" fontId="4" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1">'
    '<alignment vertical="center" wrapText="1"/></xf>'
    + "".join(f'<xf numFmtId="0" fontId="3" fillId="{4 + i}" borderId="1" xfId="0" applyFont="1" applyFill="1" '
              'applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>'
              for i in range(len(BAR_COLORS)))
    + '<xf numFmtId="3" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"/>'
    + "</cellXfs>"
    '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
    "</styleSheet>"
)
