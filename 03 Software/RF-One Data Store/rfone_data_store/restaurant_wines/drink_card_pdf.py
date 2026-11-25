"""Wines > Drink card: page layout and PDF.

One implementation for both the preview and the export: the page shows
the very PDF this module produces, so the exported file always matches the
preview. The layout follows the approved Winter Park card (Product Owner
choice C, 2026-11-24): a double frame that follows the free corners of the
menu holder, the restaurant heading and the title in bold 18 pt, sections
with their G and B columns, each wine with producer · vintage on the next
line and its description (pairings included) under it, and the footer note.

Nothing is printed inside the free corner triangles: the frame, the text
and the decorations are kept on the visible side of each hypotenuse.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from decimal import Decimal

from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as pdf_canvas

INCH = 72.0

FONT = "Times-Roman"
FONT_BOLD = "Times-Bold"
FONT_ITALIC = "Times-Italic"

TITLE_SIZE = 18          # "Wine List", bold 18 pt (specification)
SECTION_SIZE = 16
NAME_SIZE = 13
PRICE_SIZE = 13
COLUMN_LETTER_SIZE = 9
DETAIL_SIZE = 10.5
FOOTER_SIZE = 10

NAME_LEAD = 14.5
PRODUCER_LEAD = 12.0
DESCRIPTION_LEAD = 12.0
ENTRY_GAP = 3.0          # the largest space is between one wine and the next
SECTION_HEAD = 30.0      # section title, its rule and the space under it
SECTION_GAP = 12.0
COLUMN_GAP = 28.0        # right edge of G to right edge of B
MAX_DESCRIPTION_LINES = 2

OUTER_INSET = 0.13 * INCH
INNER_INSET = 0.20 * INCH
CORNER_GAP = 0.06 * INCH


@dataclass
class Entry:
    name: str
    detail: str                 # "Producer · 2018" or "Sparkling · 750 mL"
    description: str
    bottle: Decimal | None
    glass: Decimal | None = None
    key: str = ""


@dataclass
class Section:
    title: str
    entries: list[Entry]
    glass_column: bool = True
    column_letters: bool = True    # "G" and "B" over the price columns (wines only)


@dataclass
class CardSpec:
    width_in: Decimal
    height_in: Decimal
    landscape: bool
    page_count: int
    corners: bool
    corner_leg_in: Decimal
    show_glass: bool
    title: str
    heading: str | None
    subheading: str | None
    footer_note: str | None
    ink: str
    accent: str
    line: str
    images: dict[str, bytes] = field(default_factory=dict)


@dataclass
class Layout:
    pages: list[list[tuple]]                    # drawing operations per page
    overflow: list[str]                         # entries that do not fit
    long_descriptions: list[str]                # descriptions over two lines
    pages_used: int


def _money(value: Decimal | None) -> str:
    if value is None:
        return ""
    value = Decimal(value)
    return str(int(value)) if value == value.to_integral_value() else f"{value:.2f}"


class _Geometry:
    def __init__(self, spec: CardSpec):
        w, h = float(spec.width_in) * INCH, float(spec.height_in) * INCH
        if spec.landscape:
            w, h = max(w, h), min(w, h)
        else:
            w, h = min(w, h), max(w, h)
        self.w, self.h = w, h
        self.leg = float(spec.corner_leg_in) * INCH if spec.corners else 0.0
        self.top_offset = 1.62 * INCH       # from the top edge to the first section
        self.bottom_offset = 1.25 * INCH    # from the bottom edge to the end of the text
        clear = self.leg + CORNER_GAP * 3 if self.leg else 0.0
        self.margin = max(0.5 * INCH, clear - self.top_offset, clear - self.bottom_offset)
        self.left = self.margin
        self.right = w - self.margin
        self.text_top = h - self.top_offset
        self.text_bottom = self.bottom_offset

    def clear_width(self, distance_from_edge: float) -> float:
        """Usable width of a centred line whose farthest point is at
        `distance_from_edge` from the top or bottom edge."""
        side = max(0.5 * INCH, self.leg + CORNER_GAP * 3 - distance_from_edge) if self.leg else 0.5 * INCH
        return self.w - 2 * side


def _fit(text: str, font: str, size: float, width: float, minimum: float) -> float:
    while size > minimum and stringWidth(text, font, size) > width:
        size -= 0.5
    return size


def _frame(g: _Geometry, inset: float, gap: float) -> list[tuple[float, float]]:
    w, h = g.w, g.h
    if not g.leg:
        return [(inset, inset), (w - inset, inset), (w - inset, h - inset), (inset, h - inset)]
    c = g.leg + gap - inset            # where the diagonal x + y = leg + gap meets the inset rectangle
    return [
        (inset + c, inset), (w - inset - c, inset), (w - inset, inset + c), (w - inset, h - inset - c),
        (w - inset - c, h - inset), (inset + c, h - inset), (inset, h - inset - c), (inset, inset + c),
    ]


def _image_box(g: _Geometry, slot: str) -> tuple[float, float, float, float] | None:
    """(x, y, width, height) of a decoration, kept out of the corners."""
    bw, bh = 0.8 * INCH, 0.95 * INCH
    off = max(0.42 * INCH, (g.leg + CORNER_GAP * 4) / 2 if g.leg else 0.0)
    if slot == "HEADER_LEFT":
        return off, g.h - off - bh, bw, bh
    if slot == "HEADER_RIGHT":
        return g.w - off - bw, g.h - off - bh, bw, bh
    if slot == "FOOTER_LEFT":
        return off, off, bw, bh
    if slot == "FOOTER_RIGHT":
        return g.w - off - bw, off, bw, bh
    if slot == "FOOTER_CENTER":
        width = g.clear_width(0.25 * INCH) - 2 * (bw + 0.05 * INCH) if g.leg else g.w - 2 * (off + bw)
        return (g.w - width) / 2, 0.25 * INCH, width, 0.8 * INCH
    if slot == "LOGO":
        width = g.clear_width(0.35 * INCH) - 2 * bw
        return (g.w - width) / 2, g.h - 1.08 * INCH, width, 0.7 * INCH
    return None


def _page_decor(g: _Geometry, spec: CardSpec) -> list[tuple]:
    ops: list[tuple] = [("frame", _frame(g, OUTER_INSET, CORNER_GAP), 1.0),
                        ("frame", _frame(g, INNER_INSET, CORNER_GAP * 2.6), 0.6)]
    for slot in ("HEADER_LEFT", "HEADER_RIGHT", "FOOTER_LEFT", "FOOTER_RIGHT", "FOOTER_CENTER"):
        if slot in spec.images:
            ops.append(("image", slot, _image_box(g, slot)))
    center = g.w / 2
    if "LOGO" in spec.images:
        ops.append(("image", "LOGO", _image_box(g, "LOGO")))
    else:
        if spec.heading:
            heading = spec.heading.upper()
            size = _fit(heading, FONT, 22, g.clear_width(0.45 * INCH) - 1.8 * INCH, 12)
            ops.append(("text", center, g.h - 0.72 * INCH, heading, FONT, size, "ink", "center", 1.2))
        if spec.subheading:
            sub = " ".join(spec.subheading.upper())
            size = _fit(sub, FONT, 10, g.clear_width(0.95 * INCH) - 2.6 * INCH, 7)
            y = g.h - 0.98 * INCH
            ops.append(("text", center, y, sub, FONT, size, "accent", "center", 0))
            half = stringWidth(sub, FONT, size) / 2
            ops.append(("rule", center - half - 0.42 * INCH, center - half - 0.08 * INCH, y + size * 0.3, "accent", 0.6))
            ops.append(("rule", center + half + 0.08 * INCH, center + half + 0.42 * INCH, y + size * 0.3, "accent", 0.6))
    title_size = _fit(spec.title, FONT_BOLD, TITLE_SIZE, g.clear_width(1.35 * INCH) - 1.8 * INCH, 12)
    ops.append(("text", center, g.h - 1.32 * INCH, spec.title, FONT_BOLD, title_size, "ink", "center", 0))
    if spec.footer_note:
        size = _fit(spec.footer_note, FONT_ITALIC, FOOTER_SIZE, g.clear_width(1.1 * INCH) - 1.9 * INCH, 7)
        ops.append(("text", center, 1.12 * INCH, spec.footer_note, FONT_ITALIC, size, "accent", "center", 0))
    return ops


def description_lines(spec: CardSpec, description: str) -> int:
    """How many printed lines a wine description takes on this card."""
    g = _Geometry(spec)
    return len(simpleSplit(description, FONT, DETAIL_SIZE, g.right - g.left)) if description else 0


def _entry_height(entry: Entry, width: float) -> tuple[float, list[str]]:
    lines = simpleSplit(entry.description, FONT, DETAIL_SIZE, width) if entry.description else []
    height = NAME_LEAD + (PRODUCER_LEAD if entry.detail else 0) + DESCRIPTION_LEAD * len(lines) + ENTRY_GAP
    return height, lines


def layout(spec: CardSpec, sections: list[Section]) -> Layout:
    g = _Geometry(spec)
    b_right = g.right
    g_right = g.right - COLUMN_GAP
    two_digits = stringWidth("00", FONT_BOLD, PRICE_SIZE)
    text_width = g.right - g.left

    pages: list[list[tuple]] = []
    overflow: list[str] = []
    long_descriptions: list[str] = []
    y = 0.0
    page: list[tuple] | None = None

    def new_page():
        nonlocal page, y
        page = []
        pages.append(page)
        y = g.text_top

    def section_head(section: Section):
        nonlocal y
        page.append(("text", g.left, y - SECTION_SIZE, section.title, FONT_BOLD, SECTION_SIZE, "ink", "left", 0))
        if section.column_letters:
            page.append(("text", b_right - two_digits / 2, y - SECTION_SIZE, "B", FONT_BOLD, COLUMN_LETTER_SIZE, "accent", "center", 0))
        if section.column_letters and section.glass_column and spec.show_glass:
            page.append(("text", g_right - two_digits / 2, y - SECTION_SIZE, "G", FONT_BOLD, COLUMN_LETTER_SIZE, "accent", "center", 0))
        page.append(("rule", g.left, g.right, y - SECTION_SIZE - 7, "line", 0.6))
        y -= SECTION_HEAD

    new_page()
    first_on_page = True
    for section in sections:
        if not section.entries:
            continue
        glass = section.glass_column and spec.show_glass
        for index, entry in enumerate(section.entries):
            height, lines = _entry_height(entry, text_width)
            if len(lines) > MAX_DESCRIPTION_LINES:
                long_descriptions.append(entry.name)
            need = height + (SECTION_HEAD + (0 if first_on_page else SECTION_GAP) if index == 0 else 0)
            if y - need < g.text_bottom:
                new_page()
                first_on_page = True
            if index == 0 or first_on_page:
                if not first_on_page:
                    y -= SECTION_GAP
                section_head(section)
                first_on_page = False
            if len(pages) > spec.page_count:
                overflow.append(entry.name)
                y -= height
                continue
            name_limit = (g_right - two_digits - 8 if glass else b_right - stringWidth("000", FONT_BOLD, PRICE_SIZE) - 8) - g.left
            size = _fit(entry.name, FONT_BOLD, NAME_SIZE, name_limit, 9.5)
            base = y - NAME_SIZE + 1
            page.append(("text", g.left, base, entry.name, FONT_BOLD, size, "ink", "left", 0))
            if entry.bottle is not None:
                page.append(("text", b_right, base, _money(entry.bottle), FONT_BOLD, PRICE_SIZE, "accent", "right", 0))
            if glass and entry.glass is not None:
                page.append(("text", g_right, base, _money(entry.glass), FONT_BOLD, PRICE_SIZE, "accent", "right", 0))
            cursor = y - NAME_LEAD
            if entry.detail:
                page.append(("text", g.left, cursor - DETAIL_SIZE + 1.5, entry.detail, FONT_ITALIC, DETAIL_SIZE, "ink", "left", 0))
                cursor -= PRODUCER_LEAD
            for line in lines:
                page.append(("text", g.left, cursor - DETAIL_SIZE + 1.5, line, FONT, DETAIL_SIZE, "ink", "left", 0))
                cursor -= DESCRIPTION_LEAD
            y -= height

    used = min(len(pages), spec.page_count)
    pages = pages[:spec.page_count]
    while len(pages) < spec.page_count:
        pages.append([])
    decor = _page_decor(g, spec)
    return Layout(pages=[decor + ops for ops in pages], overflow=overflow,
                  long_descriptions=long_descriptions, pages_used=used)


def render(spec: CardSpec, result: Layout) -> bytes:
    g = _Geometry(spec)
    colors = {"ink": HexColor(spec.ink), "accent": HexColor(spec.accent), "line": HexColor(spec.line)}
    readers = {}
    for slot, data in spec.images.items():
        try:
            readers[slot] = ImageReader(io.BytesIO(data))
        except Exception:  # an unreadable upload is skipped, never breaks the card
            continue
    buffer = io.BytesIO()
    c = pdf_canvas.Canvas(buffer, pagesize=(g.w, g.h), pageCompression=1)
    c.setTitle(spec.title)
    for ops in result.pages:
        for op in ops:
            kind = op[0]
            if kind == "frame":
                _, points, width = op
                c.setStrokeColor(colors["accent"])
                c.setLineWidth(width)
                path = c.beginPath()
                path.moveTo(*points[0])
                for point in points[1:]:
                    path.lineTo(*point)
                path.close()
                c.drawPath(path, stroke=1, fill=0)
            elif kind == "rule":
                _, x1, x2, y, color, width = op
                c.setStrokeColor(colors[color])
                c.setLineWidth(width)
                c.line(x1, y, x2, y)
            elif kind == "image":
                _, slot, box = op
                if slot in readers and box:
                    x, y, w, h = box
                    c.drawImage(readers[slot], x, y, w, h, preserveAspectRatio=True, anchor="c", mask="auto")
            elif kind == "text":
                _, x, y, value, font, size, color, align, spacing = op
                c.setFillColor(colors[color])
                if spacing:
                    c.saveState()
                    t = c.beginText()
                    t.setFont(font, size)
                    t.setCharSpace(spacing)
                    width = stringWidth(value, font, size) + spacing * (len(value) - 1)
                    t.setTextOrigin(x - width / 2 if align == "center" else x, y)
                    t.textOut(value)
                    c.drawText(t)
                    c.restoreState()
                else:
                    c.setFont(font, size)
                    if align == "center":
                        c.drawCentredString(x, y, value)
                    elif align == "right":
                        c.drawRightString(x, y, value)
                    else:
                        c.drawString(x, y, value)
        c.showPage()
    c.save()
    return buffer.getvalue()
