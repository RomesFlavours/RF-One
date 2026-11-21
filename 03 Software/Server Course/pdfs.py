"""The PDFs people download: course guides, the menu guide, the wine list and
the certificate of completion. Built on request with ReportLab, from the same
content the AI Trainer and the tests use, so they never drift apart.
"""

from __future__ import annotations

import hashlib
import io
import re
from datetime import date
from functools import lru_cache
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (Image, KeepTogether, ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

from content.guides import EXTRA_TITLES, GUIDES
from content.modules import MODULES

BASE = Path(__file__).resolve().parent
LOGO = BASE / "static" / "rf-one-logo.png"
DISH_CARDS = BASE / "content" / "winter_park_dish_cards.md"

OLIVE = colors.HexColor("#5d6d2f")
OLIVE_DARK = colors.HexColor("#3f4b1e")
OLIVE_SOFT = colors.HexColor("#e8edd9")
INK = colors.HexColor("#1d221d")
MUTED = colors.HexColor("#5b655b")
TOMATO = colors.HexColor("#b23a26")
GOLD = colors.HexColor("#c99a22")

ACADEMY = "Rome's Flavours Academy"

_S = {
    "tag": ParagraphStyle("tag", fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=OLIVE, spaceAfter=2),
    "title": ParagraphStyle("title", fontName="Times-Roman", fontSize=26, leading=30, textColor=INK, spaceAfter=4),
    "intro": ParagraphStyle("intro", fontName="Helvetica", fontSize=10.5, leading=15, textColor=MUTED, spaceAfter=10),
    "h2": ParagraphStyle("h2", fontName="Times-Roman", fontSize=16, leading=20, textColor=OLIVE_DARK, spaceBefore=10,
                         spaceAfter=4),
    "h3": ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=10.5, leading=14, textColor=INK, spaceBefore=6),
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=10, leading=14, textColor=INK),
    "small": ParagraphStyle("small", fontName="Helvetica", fontSize=8.5, leading=12, textColor=MUTED),
    "warn": ParagraphStyle("warn", fontName="Helvetica-Oblique", fontSize=8.5, leading=12, textColor=TOMATO),
}


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _bullets(items):
    return ListFlowable([ListItem(Paragraph(_esc(t), _S["body"]), leftIndent=12, value="circle") for t in items],
                        bulletType="bullet", start="•", bulletColor=OLIVE, leftIndent=12, bulletFontSize=9)


def _header(tag: str, title: str, intro: str):
    logo = Image(str(LOGO), width=0.62 * inch, height=0.62 * inch)
    text = [Paragraph(_esc(tag.upper()), _S["tag"]), Paragraph(_esc(title), _S["title"])]
    t = Table([[logo, text]], colWidths=[0.8 * inch, None])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    return [t, Spacer(1, 4), Paragraph(_esc(intro), _S["intro"])]


def _footer(label: str):
    def draw(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(OLIVE_SOFT)
        canvas.line(doc.leftMargin, 0.6 * inch, doc.pagesize[0] - doc.rightMargin, 0.6 * inch)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(doc.leftMargin, 0.42 * inch, f"{ACADEMY} · The Server Course · {label}")
        canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, 0.42 * inch, f"Page {doc.page}")
        canvas.restoreState()
    return draw


def _build(story, label: str, title: str) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.8 * inch, rightMargin=0.8 * inch,
                            topMargin=0.7 * inch, bottomMargin=0.85 * inch, title=title, author=ACADEMY)
    doc.build(story, onFirstPage=_footer(label), onLaterPages=_footer(label))
    return buf.getvalue()


def course_number(course_id: str) -> int:
    return [m["id"] for m in MODULES].index(course_id) + 1


@lru_cache(maxsize=None)
def course_guide(course_id: str) -> bytes:
    course = next(m for m in MODULES if m["id"] == course_id)
    g = GUIDES[course_id]
    n = course_number(course_id)
    story = _header(f"Course {n} guide", course["title"], g["intro"])
    for heading, items in g["sections"]:
        story.append(KeepTogether([Paragraph(_esc(heading), _S["h2"]), _bullets(items)]))
    if course.get("safety_critical"):
        story += [Spacer(1, 10), Paragraph("Allergen notes are a guide only. The kitchen confirms, every time.", _S["warn"])]
    return _build(story, f"Course {n}: {course['title']}", f"Course {n} guide: {course['title']}")


# ---------- the unit guides: the unit's own section of the master course ----------

def _inline(text: str) -> str:
    """Escape, then keep the master text's **bold** and *italic* as PDF markup."""
    text = _esc(text.replace("\u2014", ", ").replace("\u2013", "-"))
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    return re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", text)


@lru_cache(maxsize=None)
def unit_guide(uid: str) -> bytes:
    from content import course as _course
    u = _course.UNIT_BY_ID[uid]
    story = _header(f"Unit {uid} guide · Level {u['level']}, {u['level_title']}", u["title"],
                    f"{u['objective']} Essential evidence: {u['evidence']}")
    # For the new hire first: what they'll be able to do, and the situations.
    story.append(Paragraph("What you'll be able to do", _S["h2"]))
    story.append(ListFlowable([ListItem(Paragraph(f"<b>{_esc(m['title'])}.</b> {_esc(m['known'])}", _S["body"]), leftIndent=12, value="circle")
                               for m in u["pills"]], bulletType="bullet", start="•", bulletColor=OLIVE, leftIndent=12, bulletFontSize=9))
    story.append(Paragraph("Situations to think through", _S["h2"]))
    story.append(_bullets([m["scenario"] for m in u["pills"]]))
    if "answers" in (u.get("sources") or []):
        story.append(Paragraph("Rome's Flavours answers: safety, allergies, alcohol, hygiene, Clover", _S["h2"]))
        _markdown(story, (BASE / "content" / "courses" / "server-company-answers.md").read_text(encoding="utf-8"), skip_intro=True)
    story.append(Paragraph("From the master course (the instructor's text)", _S["h2"]))
    lines = _course.unit_text(uid).splitlines()[1:]  # the heading is the title above
    bullets, header_row = [], None

    def flush():
        nonlocal bullets
        if bullets:
            story.append(ListFlowable([ListItem(Paragraph(b, _S["body"]), leftIndent=12, value="circle") for b in bullets],
                                      bulletType="bullet", start="\u2022", bulletColor=OLIVE, leftIndent=12,
                                      bulletFontSize=9))
            bullets = []

    for raw in lines:
        line = raw.strip()
        if not line:
            flush(); header_row = None
            continue
        if line.startswith("#### "):
            flush(); story.append(Paragraph(_inline(line[5:]), _S["h2"]))
        elif line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):
                continue
            if header_row is None:
                header_row = cells
                continue
            bullets.append(_inline("; ".join(f"<b>{_esc(h)}:</b> {c}" if h else c for h, c in zip(header_row, cells))
                                   .replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>")))
        elif re.match(r"^(- |\d+\. )", line):
            bullets.append(_inline(re.sub(r"^(- |\d+\. )", "", line)))
        else:
            flush(); story.append(Paragraph(_inline(line), _S["body"])); story.append(Spacer(1, 5))
    flush()
    if u.get("practical"):
        story.append(Paragraph("Practical checks with your lead, in person", _S["h2"]))
        story.append(_bullets([f"{x['title']}: {x['visible']}" for x in u["practical"]]))
    if u.get("safety_critical"):
        story += [Spacer(1, 10), Paragraph("Allergen and emergency answers are confirmed by the kitchen and the manager on shift, every time.", _S["warn"])]
    return _build(story, f"Unit {uid}: {u['title']}", f"Unit {uid} guide: {u['title']}")


def _markdown(story, text: str, skip_intro: bool = False) -> None:
    """A simple markdown file: ## and ### headings, bullets, tables as bullets, paragraphs."""
    bullets, header_row, started = [], None, not skip_intro
    def flush():
        nonlocal bullets
        if bullets:
            story.append(ListFlowable([ListItem(Paragraph(b, _S["body"]), leftIndent=12, value="circle") for b in bullets],
                                      bulletType="bullet", start="•", bulletColor=OLIVE, leftIndent=12, bulletFontSize=9))
            bullets = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("# "):
            continue
        if line.startswith("## "):
            started = True
            flush(); header_row = None
            story.append(Paragraph(_esc(line[3:]), _S["h3"]))
            continue
        if not started:
            continue
        if not line:
            flush(); header_row = None
        elif line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):
                continue
            if header_row is None:
                header_row = cells
                continue
            bullets.append(f"<b>{_inline(cells[0])}:</b> " + "; ".join(_inline(c) for c in cells[1:]))
        elif re.match(r"^(- |\d+\. )", line):
            bullets.append(_inline(re.sub(r"^(- |\d+\. )", "", line)))
        else:
            flush(); story.append(Paragraph(_inline(line), _S["body"])); story.append(Spacer(1, 4))
    flush()


def safety_card() -> bytes:
    story = _header("Rome's Flavours · keep it with you", "Safety card",
                    "What we do every time, from the restaurant's own answers. Roles, not names: the leads on each shift are told at the start of the shift.")
    _markdown(story, (BASE / "content" / "courses" / "server-company-answers.md").read_text(encoding="utf-8"), skip_intro=True)
    story += [Spacer(1, 8), Paragraph("Not sure? Stop, say you'll check, and ask the lead on shift. In an emergency: the manager on shift now, 911 if you're alone.", _S["warn"])]
    return _build(story, "Safety card", "Rome's Flavours safety card")


# ---------- the dish cards, for the menu guide and the wine list ----------

SECTION_ORDER = ["Appetizers", "Soups", "Bruschetta", "Salads", "Pasta", "Pizzas", "Meat & Fish", "Sides", "Desserts"]
SECTION_NOTES = {"Soups": "Served with homemade bread.", "Bruschetta": "Served with a small side salad.",
                 "Meat & Fish": "Every main is served with the guest's choice of one side."}
# From Pino's FAQ (3 November 2026), where the dish card's allergen line is
# empty or incomplete. Still to confirm with the kitchen, like the rest.
ADDED_NOTES = {
    "Homemade Meatballs": "The recipe includes pesto: pine nuts and cheese. Bread: wheat. Pino's FAQ also lists dairy. Contains pork.",
    "Campo dei Fiori": "Nutella: hazelnuts and milk. Dough: wheat.",
    "Tiramisu": "Ladyfingers: wheat and eggs. Pino's FAQ lists amaretto and marsala in the cream: alcohol, and the amaretto needs checking for a nut allergy.",
    "Pannacotta": "Nutella topping: hazelnuts and milk.",
    "Cannoli Siciliani": "Shell: wheat.",
    "Fettuccine Bolognese": "Beef and pork; red wine.",
    "Fettuccine Carbonara": "Guanciale is pork.",
    "Fettuccine Shrimp & Pistacchio": "White wine.",
    "Fettuccine Alfredo": "White wine.",
    "Vegetable Festival": "White wine.",
    "Lemon Butter Asparagus": "White wine.",
    "Homemade Gnocchi in Basil Pesto": "Gnocchi contain flour: not gluten free. The pesto is made ahead: nothing can be taken out.",
    "Homemade Gnocchi Sorrento": "Gnocchi contain flour: not gluten free. White wine.",
    "Bolognese Pizza": "The Bolognese sauce has pork.",
    "Dolomiti": "Speck is pork.",
    "Tuscany Cutting Board": "Prosciutto, speck and soppressata are pork.",
    "Garnished Focaccia": "Focaccia: wheat. Prosciutto is pork.",
}
# Added to every dish in a section (also to confirm with the kitchen).
SECTION_ALLERGENS = {
    "Pasta": "House egg pasta: eggs and wheat.",
    "Pizzas": "Pizza dough: wheat.",
    "Bruschetta": "Bread: wheat.",
    "Soups": "Served with bread: wheat.",
}
REGION = {
    "Vermentino di Gallura": "Sardinia", "Gavi": "Piedmont", "Soave Classico": "Veneto",
    "Montepulciano d'Abruzzo": "Abruzzo", "Primitivo di Manduria": "Puglia", "Brunello di Montalcino": "Tuscany",
    "Sangue di Giuda": "Lombardy", "Grillo": "Sicily", "Nero d'Avola": "Sicily", "Primitivo Rosato": "Puglia",
}
KIND = [("Rosato", "Rosé"), ("Moscato", "Sweet"), ("Sangue di Giuda", "Sweet"),
        ("Pinot Grigio", "White"), ("Vermentino", "White"), ("Gavi", "White"), ("Grillo", "White"), ("Soave", "White"),
        ("Chardonnay", "White"), ("Pinot Nero", "Red"), ("Montepulciano", "Red"), ("Nero d'Avola", "Red"),
        ("Primitivo", "Red"), ("Brunello", "Red")]


def _section(name: str) -> str:
    n = name.strip()
    return {"Appetizer": "Appetizers"}.get(n, n)


@lru_cache(maxsize=1)
def dishes() -> list[dict]:
    """Every Winter Park dish card: section, name, one line, ingredients, allergen notes, wines."""
    return _parse_cards(DISH_CARDS)


def _parse_cards(path) -> list[dict]:
    out, section, cur = [], "", None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            section = _section(line[3:])
        elif line.startswith("### "):
            cur = {"section": section, "name": line[4:].strip(), "line": "", "ingredients": "", "allergens": "",
                   "wines": []}
            out.append(cur)
        elif cur:
            m = re.match(r"\*\*(.+?):\*\*\s*(.*)", line)
            if not m:
                continue
            key, val = m.group(1).lower(), m.group(2).strip()
            if key == "in one line":
                cur["line"] = val
            elif key == "ingredients":
                cur["ingredients"] = val.replace(" ,", ",")
            elif key.startswith("allergen notes"):
                cur["allergens"] = val.replace(" ,", ":")
            elif key == "wines":
                for w in re.split(r"\)\s*/\s*|\s+/\s+(?=[A-Z])", val):
                    w = re.sub(r"\s*\(.*$", "", w).strip()
                    if " , " in w:
                        name, producer = w.split(" , ", 1)
                        cur["wines"].append((name.strip(), producer.strip()))
    return out


@lru_cache(maxsize=1)
def menu_guide() -> bytes:
    story = _header("Support document", "Winter Park menu guide",
                    "Every dish on the Winter Park menu, from the dish cards: what it is, its components and its "
                    "allergen notes. Allergen notes are a guide only: the kitchen confirms every time.")
    by = {}
    for d in dishes():
        by.setdefault(d["section"], []).append(d)
    for section in SECTION_ORDER + [s for s in by if s not in SECTION_ORDER]:
        if section not in by:
            continue
        story.append(Paragraph(_esc(section), _S["h2"]))
        if section in SECTION_NOTES:
            story.append(Paragraph(_esc(SECTION_NOTES[section]), _S["small"]))
        for d in by[section]:
            section_note = "" if "Gnocchi" in d["name"] else SECTION_ALLERGENS.get(section, "")
            parts = (d["allergens"], section_note, ADDED_NOTES.get(d["name"], ""))
            notes = ". ".join(x.strip().rstrip(";.") for x in parts if x.strip().rstrip(";.")) + "."
            block = [Paragraph(_esc(d["name"]), _S["h3"]), Paragraph(_esc(d["line"]), _S["body"])]
            if d["ingredients"]:
                block.append(Paragraph("<b>Components:</b> " + _esc(d["ingredients"]), _S["small"]))
            if notes != ".":
                block.append(Paragraph("<b>Allergen notes, to confirm:</b> " + _esc(notes), _S["small"]))
            story.append(KeepTogether(block))
    return _build(story, "Winter Park menu guide", "Winter Park menu guide")


def _kind(name: str) -> str:
    return next((k for key, k in KIND if key.lower() in name.lower()), "Other")


@lru_cache(maxsize=1)
def wine_list() -> bytes:
    wines = {}
    for d in dishes():
        for name, producer in d["wines"]:
            w = wines.setdefault((name, producer), [])
            if d["name"] not in w:
                w.append(d["name"])
    story = _header("Support document", "Our wine list",
                    "The Italian wines our dish cards suggest, with the dishes each one goes with. All from small "
                    "importers. Check the current list in the restaurant for what's open and available.")
    for kind in ("White", "Rosé", "Red", "Sweet", "Other"):
        rows = sorted((k, v) for k, v in wines.items() if _kind(k[0]) == kind)
        if not rows:
            continue
        story.append(Paragraph(_esc({"Sweet": "Dessert wines"}.get(kind, kind + " wines")), _S["h2"]))
        for (name, producer), dish_names in rows:
            region = next((r for key, r in REGION.items() if name.startswith(key)), "")
            head = _esc(name) + f' <font color="#5b655b" size="9">· {_esc(producer)}' + (
                f" · {_esc(region)}" if region else "") + "</font>"
            story.append(KeepTogether([Paragraph(head, _S["h3"]),
                                       Paragraph("Goes with: " + _esc(", ".join(dish_names)), _S["small"])]))
    story += [Spacer(1, 8), Paragraph(
        "How to suggest: red or white? For red, dry or fruity, and light, medium or full-bodied? For white, sweeter "
        "or more acidic? Then suggest two or three wines.", _S["body"])]
    return _build(story, "Our wine list", "Our wine list")


MD_DISH_CARDS = BASE / "content" / "mount_dora_dish_cards.md"
MD_SECTION_ORDER = ["Antipasti", "Zuppe e Insalate", "Pasta Fresca", "Pizza Gourmet", "Secondi", "Contorni"]


@lru_cache(maxsize=1)
def mount_dora_dishes() -> list[dict]:
    return _parse_cards(MD_DISH_CARDS)


@lru_cache(maxsize=1)
def mount_dora_menu_guide() -> bytes:
    """The Mount Dora draft dish cards: built from the menu's own ingredients, every
    allergen note to confirm with the kitchen, until the kitchen's recipes exist."""
    story = _header("Support document", "Mount Dora menu guide",
                    "Every dish on the Mount Dora menu: what it is, its components and its allergen notes. These are "
                    "draft cards built from the menu, so every allergen note is a guide only: the kitchen confirms "
                    "every time. A star (*) marks a Rome's Flavours signature dish.")
    by = {}
    for d in mount_dora_dishes():
        by.setdefault(d["section"], []).append(d)
    for section in MD_SECTION_ORDER + [x for x in by if x not in MD_SECTION_ORDER]:
        if section not in by:
            continue
        story.append(Paragraph(_esc(section), _S["h2"]))
        for d in by[section]:
            block = [Paragraph(_esc(d["name"]), _S["h3"]), Paragraph(_esc(d["line"]), _S["body"])]
            if d["ingredients"]:
                block.append(Paragraph("<b>Components:</b> " + _esc(d["ingredients"]), _S["small"]))
            if d["allergens"]:
                block.append(Paragraph("<b>Allergen notes, to confirm:</b> " + _esc(d["allergens"]), _S["small"]))
            story.append(KeepTogether(block))
    story += [Spacer(1, 8), Paragraph("Desserts and wines for Mount Dora aren't on the menu yet.", _S["small"])]
    return _build(story, "Mount Dora menu guide", "Mount Dora menu guide")


def extra_guide(key: str, location: str = "") -> bytes:
    if key == "menu" and location == "Mount Dora":
        return mount_dora_menu_guide()
    return {"menu": menu_guide, "wines": wine_list, "safety": safety_card}[key]()


def extra_title(key: str, location: str = "") -> str:
    if key == "menu" and location == "Mount Dora":
        return "Mount Dora menu guide"
    return EXTRA_TITLES[key]


# ---------- the certificate ----------

def certificate_id(name: str, done: date, location: str) -> str:
    h = hashlib.sha256(f"{name.strip().lower()}|{done.isoformat()}|{location}".encode()).hexdigest()[:6].upper()
    return f"RFA-ST-{done:%Y%m%d}-{h}"


def certificate(name: str, done: date, location: str = "") -> bytes:
    buf = io.BytesIO()
    W, H = landscape(letter)
    from reportlab.pdfgen import canvas as rl_canvas
    c = rl_canvas.Canvas(buf, pagesize=(W, H))
    c.setTitle(f"Certificate of Completion: {name}")
    c.setAuthor(ACADEMY)

    # Background and double border
    c.setFillColor(colors.HexColor("#fbfaf4"))
    c.rect(0, 0, W, H, stroke=0, fill=1)
    c.setStrokeColor(OLIVE)
    c.setLineWidth(3)
    c.rect(0.45 * inch, 0.45 * inch, W - 0.9 * inch, H - 0.9 * inch)
    c.setLineWidth(0.8)
    c.rect(0.58 * inch, 0.58 * inch, W - 1.16 * inch, H - 1.16 * inch)
    # Corner marks
    c.setFillColor(GOLD)
    for x, y in ((0.58, 0.58), (W / inch - 0.58, 0.58), (0.58, H / inch - 0.58), (W / inch - 0.58, H / inch - 0.58)):
        c.circle(x * inch, y * inch, 4, stroke=0, fill=1)

    cx = W / 2
    # The logo file has a white square around the circle: clip it to the circle.
    c.saveState()
    clip = c.beginPath()
    clip.circle(cx, H - 1.4 * inch, 0.5 * inch)
    c.clipPath(clip, stroke=0, fill=0)
    c.drawImage(str(LOGO), cx - 0.55 * inch, H - 1.95 * inch, width=1.1 * inch, height=1.1 * inch, mask="auto")
    c.restoreState()

    c.setFillColor(OLIVE)
    c.setFont("Helvetica-Bold", 11)
    _spaced(c, cx, H - 2.3 * inch, ACADEMY.upper(), 2.2)

    c.setFillColor(INK)
    c.setFont("Times-Roman", 40)
    c.drawCentredString(cx, H - 2.95 * inch, "Certificate of Completion")

    c.setFillColor(MUTED)
    c.setFont("Helvetica", 12)
    c.drawCentredString(cx, H - 3.45 * inch, "This certifies that")

    size = 34
    while size > 18 and c.stringWidth(name, "Times-Italic", size) > W - 3 * inch:
        size -= 2
    c.setFillColor(OLIVE_DARK)
    c.setFont("Times-Italic", size)
    c.drawCentredString(cx, H - 4.1 * inch, name)
    c.setStrokeColor(GOLD)
    c.setLineWidth(1)
    c.line(cx - 3 * inch, H - 4.25 * inch, cx + 3 * inch, H - 4.25 * inch)

    c.setFillColor(MUTED)
    c.setFont("Helvetica", 12)
    c.drawCentredString(cx, H - 4.7 * inch, "has successfully completed the")
    c.setFillColor(INK)
    c.setFont("Times-Roman", 24)
    c.drawCentredString(cx, H - 5.15 * inch, "Server Training Program")
    n_courses = len(MODULES)
    n_modules = sum(len(m["pills"]) for m in MODULES)
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 10.5)
    c.drawCentredString(cx, H - 5.5 * inch,
                        f"{n_courses} courses and {n_modules} modules with the AI Trainer, and every course test passed")

    # Date and signature lines
    y = 1.35 * inch
    c.setStrokeColor(INK)
    c.setLineWidth(0.6)
    for x0 in (1.6 * inch, W - 4.6 * inch):
        c.line(x0, y, x0 + 3 * inch, y)
    c.setFillColor(INK)
    c.setFont("Times-Roman", 14)
    c.drawCentredString(1.6 * inch + 1.5 * inch, y + 0.12 * inch, f"{done:%B} {done.day}, {done.year}")
    c.setFont("Helvetica", 9)
    c.setFillColor(MUTED)
    c.drawCentredString(1.6 * inch + 1.5 * inch, y - 0.2 * inch, "Date of completion")
    c.drawCentredString(W - 4.6 * inch + 1.5 * inch, y - 0.2 * inch, ACADEMY)
    c.setFont("Helvetica", 7.5)
    c.drawCentredString(cx, 0.78 * inch, f"Certificate {certificate_id(name, done, location)}"
                        + (f" · Rome's Flavours {location}" if location else ""))
    c.showPage()
    c.save()
    return buf.getvalue()


def _spaced(c, cx, y, text, gap):
    width = sum(c.stringWidth(ch, "Helvetica-Bold", 11) for ch in text) + gap * (len(text) - 1)
    x = cx - width / 2
    for ch in text:
        c.drawString(x, y, ch)
        x += c.stringWidth(ch, "Helvetica-Bold", 11) + gap
