"""Builds one PDF per invoice of the extended direct-reading trial.

Input:  letture.json (the reading, written by hand from the rendered pages — this
        script reads no invoice content itself) and the original files under
        <AI-RF-ONE>/Documents/Invoices (or the folder given as first argument).
Output: one PDF per invoice in ./PDF/, plus controlli.json (the computed checks).

Each PDF: every original page (rendered, rotated upright), then the extracted
data, the missing/uncertain data and the outcome of the arithmetic checks.
No network call, no recognition service: pages are only rendered (pypdfium2).

Usage:  python make_pdfs.py [path-to-Documents/Invoices]
"""
from __future__ import annotations

import json
import pathlib
import shutil
import sys
import tempfile
from decimal import ROUND_HALF_UP, Decimal

import pypdfium2 as pdfium
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, Image, NextPageTemplate, PageBreak, PageTemplate,
                                Paragraph, Spacer, Table, TableStyle)

HERE = pathlib.Path(__file__).resolve().parent
SOURCE_ROOT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parents[3] / "Documents" / "Invoices"
OUT_DIR = HERE / "PDF"
TMP_DIR = pathlib.Path(tempfile.mkdtemp(prefix="prova_lettura_"))  # rendered pages, outside OneDrive
DATA = json.loads((HERE / "letture.json").read_text(encoding="utf-8"))

pdfmetrics.registerFont(TTFont("Arial", r"C:\Windows\Fonts\arial.ttf"))
pdfmetrics.registerFont(TTFont("Arial-Bold", r"C:\Windows\Fonts\arialbd.ttf"))
pdfmetrics.registerFont(TTFont("Arial-Italic", r"C:\Windows\Fonts\ariali.ttf"))
S = ParagraphStyle("s", fontName="Arial", fontSize=6.8, leading=8.2)
SB = ParagraphStyle("sb", parent=S, fontName="Arial-Bold")
SI = ParagraphStyle("si", parent=S, fontName="Arial-Italic", textColor=colors.HexColor("#1f4e9c"))
SC = ParagraphStyle("sc", parent=S, fontName="Arial-Italic", textColor=colors.HexColor("#8a4b00"))
N = ParagraphStyle("n", fontName="Arial", fontSize=8.5, leading=11)
H1 = ParagraphStyle("h1", fontName="Arial-Bold", fontSize=14, leading=17, spaceAfter=4)
H2 = ParagraphStyle("h2", fontName="Arial-Bold", fontSize=10.5, leading=13, spaceBefore=8, spaceAfter=3)
OK_C, KO_C, NA_C = colors.HexColor("#e3f3e3"), colors.HexColor("#f9dddd"), colors.HexColor("#eeeeee")

LAND_W = landscape(A4)[0] - 20 * mm
CENT = Decimal("0.01")


def esc(v) -> str:
    return "" if v is None else str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def P(text, style=S):
    return Paragraph(esc(text), style)


def D(v) -> Decimal | None:
    return None if v in (None, "") else Decimal(str(v).replace(",", ""))


def money(v: Decimal) -> str:
    return str(v.quantize(CENT, rounding=ROUND_HALF_UP))


# ----------------------------------------------------------------- effective values
def interp(line, field):
    for i in line["interpretations"]:
        if i["field"] == field:
            return i["value"]
    return None


def calc(line, field):
    for c in line["calculations"]:
        if c["field"] == field:
            return c["value"]
    return None


def cell(line, field, extra=None):
    """Read value as plain text; interpretation [i] in blue italics; calculation [c] in brown italics."""
    v = line.get(field)
    if v not in (None, ""):
        return P(f"{v}{extra or ''}")
    i = interp(line, field)
    if i is not None:
        return Paragraph("[i] " + esc(i), SI)
    c = calc(line, field)
    if c is not None:
        return Paragraph("[c] " + esc(c), SC)
    return P("—")


def eff_quantity(line):
    q = line.get("quantity") or interp(line, "quantity")
    try:
        return D(q)
    except Exception:
        return None


def eff_basis(line):
    return line.get("unit_price_basis") or interp(line, "unit_price_basis")


# ----------------------------------------------------------------- checks
def line_check(line):
    price, amount = D(line.get("unit_price")), D(line.get("amount"))
    basis = (eff_basis(line) or "").upper()
    weight = D(line.get("actual_weight_value"))
    if basis in ("LB", "LBS", "#") and weight is not None and line.get("quantity") not in (None,) and \
            (line.get("purchase_unit") or interp(line, "purchase_unit") or "").upper() not in ("LB", "LBS"):
        mult, label = weight, f"peso {weight}"
    else:
        mult, label = eff_quantity(line), f"quantità {eff_quantity(line)}"
    if price is None or amount is None or mult is None:
        if line.get("amount") is None and line.get("unit_price") is not None:
            return ("NON POSSIBILE", f"riga {line['ref']}: importo non stampato")
        if price is None and amount is not None:
            return ("NON APPLICABILE", f"riga {line['ref']}: prezzo unitario non stampato (importo = prezzo della riga)")
        return ("NON POSSIBILE", f"riga {line['ref']}: dati insufficienti")
    computed = (price * mult).quantize(CENT, rounding=ROUND_HALF_UP)
    exact = price * mult
    ok = computed == amount
    note = f"riga {line['ref']}: {label} x {price} = {exact.normalize():f} -> {computed}; stampato {amount}"
    return ("OK" if ok else "DIFFERENZA", note)


def total_check(inv, t):
    lines = inv["lines"] if t["lines"] == "all" else [l for l in inv["lines"] if l["ref"] in (t["lines"] or [])]
    charges = inv["charges"] if t["charges"] == "all" else [c for c in inv["charges"] if c["name"] in (t["charges"] or [])]
    printed = D(t["value"])
    kind = t["kind"]
    if kind == "amount":
        parts = [D(l["amount"]) for l in lines if l.get("amount") is not None] + [D(c["amount"]) for c in charges]
        s = sum(parts, Decimal("0"))
        what = f"{len([l for l in lines if l.get('amount') is not None])} righe" + (f" + {len(charges)} charge" if charges else "")
        return ("OK" if s == printed else "DIFFERENZA", f"{t['label']} (p.{t['page']}): somma {what} = {money(s)}; stampato {t['value']}")
    if kind == "weight":
        s = sum((D(l["actual_weight_value"]) or Decimal(0) for l in lines), Decimal("0"))
        return ("OK" if s == printed else "DIFFERENZA", f"{t['label']} (p.{t['page']}): somma pesi = {s}; stampato {t['value']}")
    if kind in ("quantity", "quantity_with_implicit_one"):
        s = sum(((eff_quantity(l) if eff_quantity(l) is not None else (Decimal(1) if kind.endswith("one") else Decimal(0))) for l in lines), Decimal("0"))
        return ("OK" if s == printed else "DIFFERENZA", f"{t['label']} (p.{t['page']}): somma quantità = {s.normalize():f}; stampato {t['value']}")
    if kind == "count_lines":
        return ("OK" if len(lines) == int(printed) else "DIFFERENZA", f"{t['label']}: righe lette = {len(lines)}; stampato {t['value']}")
    return ("NON POSSIBILE", t["label"])


def all_checks(inv):
    out = [("Riga",) + line_check(l) for l in inv["lines"]]
    out += [("Totale",) + total_check(inv, t) for t in inv["printed_totals"]]
    for c in inv.get("calculations", []):
        out.append(("Calcolo", "OK", c))
    for m in inv["pages_missing"]:
        out.append(("Completezza", "NON POSSIBILE", m))
    return out


# ----------------------------------------------------------------- rendering
def resolve(rel: str) -> pathlib.Path:
    """Some scanner file names contain a narrow no-break space (U+202F) before 'PM';
    letture.json uses a plain space, so match names with that difference ignored."""
    p = SOURCE_ROOT / rel
    if p.exists():
        return p
    norm = lambda s: s.replace(" ", " ").replace(" ", " ")
    for candidate in p.parent.iterdir():
        if norm(candidate.name) == norm(p.name):
            return candidate
    raise FileNotFoundError(p)


def render_pages(inv):
    flow = []
    for src in inv["sources"]:
        pdf = pdfium.PdfDocument(str(resolve(src["file"])))
        for n in src["pages"]:
            img = pdf[n - 1].render(scale=2.2).to_pil()
            if src.get("rotate"):
                img = img.rotate(src["rotate"], expand=True)
            TMP_DIR.mkdir(exist_ok=True)
            p = TMP_DIR / f"{inv['id'].replace('/', '_').replace(chr(39), '')}_{pathlib.Path(src['file']).stem}_p{n}.jpg"
            img.convert("RGB").save(p, quality=85)
            w, h = img.size
            # Frame size minus the frame's own 6 pt padding on each side, the caption and the spacer.
            frame_w, frame_h = (A4[0] - 16 * mm, A4[1] - 20 * mm) if h >= w else (LAND_W, landscape(A4)[1] - 20 * mm)
            box_w, box_h = frame_w - 14, frame_h - 14 - 12 * mm
            scale = min(box_w / w, box_h / h)
            tmpl = "portrait" if h >= w else "landscape_img"
            flow += [NextPageTemplate(tmpl), PageBreak(),
                     Paragraph(esc(f"Originale: {src['file']} — pagina {n} del file ({src.get('printed_page', '')})"
                                   + (f" — {src['role']}" if src.get("role") else "")), S),
                     Spacer(1, 2 * mm), Image(str(p), width=w * scale, height=h * scale)]
    return flow


def table(rows, widths, header_rows=1, styles=()):
    t = Table(rows, colWidths=[w * mm for w in widths], repeatRows=header_rows)
    base = [("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#999999")),
            ("BACKGROUND", (0, 0), (-1, header_rows - 1), colors.HexColor("#dde3ea")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]
    t.setStyle(TableStyle(base + list(styles)))
    return t


def data_section(inv, checks):
    f = [NextPageTemplate("landscape"), PageBreak()]
    f.append(Paragraph(esc(f"{inv['supplier_name']} — {inv['document_type']} {inv['document_number'] or '(senza numero)'}"), H1))
    ids = inv.get("identifiers")
    head = [
        ["Supplier", inv["supplier_name"]],
        ["Numero", inv["document_number"] or ("non stampato; identificativi: " + ", ".join(f"{k} {v}" for k, v in ids.items()) if ids else "non stampato")],
        ["Data", f"{inv['issue_date']['as_printed']} (ISO {inv['issue_date']['iso']})"],
        ["Tipo documento", inv["document_type"]],
        ["File e pagine", "; ".join(f"{s['file']} p.{','.join(map(str, s['pages']))} [{s.get('printed_page', '')}]" for s in inv["sources"])],
        ["Pagine mancanti", "; ".join(inv["pages_missing"]) or "nessuna rilevata"],
        ["Lettura", f"{DATA['reader']}, {DATA['read_on']}. Nessun completamento dalla scheda prodotto."],
    ]
    f.append(table([[P(a, SB), P(b)] for a, b in head], [38, LAND_W / mm - 38], header_rows=0))
    f.append(Spacer(1, 2 * mm))
    f.append(Paragraph("Legenda: valore normale = letto sul documento; <font color='#1f4e9c'><i>[i] = interpretazione</i></font>; "
                       "<font color='#8a4b00'><i>[c] = calcolato</i></font>; — = non stampato / non letto.", S))

    f.append(Paragraph("Righe articolo", H2))
    hdr = ["#", "Pag.", "Riga / Codice", "Descrizione", "Q.tà", "Unità", "Confezione (stampata)", "Pz/conf.",
           "Contenuto pezzo", "Peso effettivo", "Prezzo unit.", "Base prezzo", "Importo", "Sezione"]
    rows = [[P(h, SB) for h in hdr]]
    for l in inv["lines"]:
        code = " / ".join(x for x in (l.get("source_line_number"), l.get("supplier_item_code")) if x) or "—"
        content = (Paragraph(esc(f"{l['piece_content_value']} {l['piece_content_unit'] or ''}"), S)
                   if l.get("piece_content_value") else cell(l, "piece_content_value"))
        if l.get("piece_content_value") and not l.get("piece_content_unit") is None and interp(l, "piece_content_unit"):
            content = Paragraph(esc(f"{l['piece_content_value']} {l['piece_content_unit']}") + "<br/>" +
                                "<font color='#1f4e9c'><i>[i] " + esc(interp(l, 'piece_content_unit')) + "</i></font>", S)
        weight = "—"
        if l.get("actual_weight_value"):
            txt = esc(f"{l['actual_weight_value']} {l['actual_weight_unit'] or '(unità non stampata)'}")
            if interp(l, "actual_weight_unit"):
                txt += "<br/><font color='#1f4e9c'><i>[i] " + esc(interp(l, "actual_weight_unit")) + "</i></font>"
            if calc(l, "actual_weight_value"):
                txt += "<br/><font color='#8a4b00'><i>[c] " + esc(calc(l, "actual_weight_value")) + "</i></font>"
            weight = Paragraph(txt, S)
        else:
            weight = P("—")
        rows.append([P(l["ref"]), P(l["page"]), P(code), P(l["raw_description"]), cell(l, "quantity"), cell(l, "purchase_unit"),
                     cell(l, "pack_size"), cell(l, "pack_count"), content, weight, cell(l, "unit_price"),
                     cell(l, "unit_price_basis"), cell(l, "amount"), P(l.get("source_section") or "—")])
    widths = [7, 8, 20, 62, 11, 12, 21, 12, 20, 24, 15, 17, 15, 0]
    widths[-1] = LAND_W / mm - sum(widths[:-1])
    f.append(table(rows, widths))

    f.append(Paragraph("Charges (nome e importo con segno, come stampati)", H2))
    if inv["charges"]:
        crow = [[P(h, SB) for h in ("Nome", "Importo", "Tipo", "Pag.", "Riga stampata / nota")]]
        for c in inv["charges"]:
            crow.append([P(c["name"]), P(c["amount"]), P(c["kind"]), P(c["page"]), P(c.get("source_line") or "")])
        f.append(table(crow, [70, 25, 30, 15, LAND_W / mm - 140]))
    else:
        f.append(P("Nessun charge leggibile" + (" (pagina mancante)." if inv["pages_missing"] else ".")))

    f.append(Paragraph("Dati mancanti o incerti", H2))
    frows = [[P(h, SB) for h in ("Riga", "Campo", "Tipo", "Nota", "Risolvibile da")]]
    for l in inv["lines"]:
        for fl in l["flags"]:
            frows.append([P(l["ref"]), P(fl["field"]), P(fl["issue_type"]), P(fl["note"]),
                          P("scheda prodotto" if fl["resolvable_by"] == "PRODUCT_CARD" else "persona / documento")])
    for fl in inv.get("flags", []):
        frows.append([P("doc."), P(fl["field"]), P(fl["issue_type"]), P(fl["note"]), P("persona / documento")])
    for m in inv["pages_missing"]:
        frows.append([P("doc."), P("pagine"), P("MISSING"), P(m), P("persona / documento")])
    if len(frows) == 1:
        f.append(P("Nessuno."))
    else:
        f.append(table(frows, [12, 32, 24, LAND_W / mm - 108, 40]))

    irows = [[P(h, SB) for h in ("Riga", "Campo", "Interpretazione / calcolo", "Motivo")]]
    for l in inv["lines"]:
        for i in l["interpretations"]:
            irows.append([P(l["ref"]), P(i["field"]), Paragraph("[i] " + esc(i["value"]), SI), P(i["reason"])])
        for c in l["calculations"]:
            irows.append([P(l["ref"]), P(c["field"]), Paragraph("[c] " + esc(c["value"]), SC), P(c["formula"])])
    if len(irows) > 1:
        f.append(Paragraph("Interpretazioni e calcoli (non scritti nei campi letti)", H2))
        f.append(table(irows, [12, 32, 45, LAND_W / mm - 89]))

    notes = list(inv.get("notes", [])) + [f"Riga {l['ref']}: {n}" for l in inv["lines"] for n in l["notes"]]
    if notes:
        f.append(Paragraph("Note di lettura", H2))
        f.extend(P("• " + n) for n in notes)

    f.append(Paragraph("Esito dei controlli", H2))
    crow = [[P(h, SB) for h in ("Tipo", "Esito", "Dettaglio")]]
    st = []
    for i, (kind, res, det) in enumerate(checks, 1):
        crow.append([P(kind), P(res, SB), P(det)])
        st.append(("BACKGROUND", (1, i), (1, i), OK_C if res == "OK" else (KO_C if res == "DIFFERENZA" else NA_C)))
    f.append(table(crow, [22, 28, LAND_W / mm - 50], styles=st))
    f.append(Spacer(1, 2 * mm))
    f.append(P("Una somma che torna è un controllo di coerenza, non una garanzia assoluta della lettura. "
               "Arrotondamento: al centesimo, metà per eccesso."))
    return f


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Arial", 6.5)
    canvas.drawString(10 * mm, 6 * mm, f"{doc.title} — Prova estesa lettura diretta — pagina {doc.page}")
    canvas.restoreState()


def build(inv):
    checks = all_checks(inv)
    name = f"{inv['id'].replace('/', '-').replace(chr(39), '')} - {inv['issue_date']['iso']}.pdf"
    out = OUT_DIR / name
    doc = BaseDocTemplate(str(out), pagesize=A4, title=inv["id"], leftMargin=8 * mm, rightMargin=8 * mm,
                          topMargin=10 * mm, bottomMargin=12 * mm)
    lw, lh = landscape(A4)
    doc.addPageTemplates([
        PageTemplate("cover", [Frame(10 * mm, 12 * mm, A4[0] - 20 * mm, A4[1] - 22 * mm)], onPage=footer, pagesize=A4),
        PageTemplate("portrait", [Frame(8 * mm, 12 * mm, A4[0] - 16 * mm, A4[1] - 20 * mm)], onPage=footer, pagesize=A4),
        PageTemplate("landscape_img", [Frame(10 * mm, 12 * mm, lw - 20 * mm, lh - 20 * mm)], onPage=footer, pagesize=(lw, lh)),
        PageTemplate("landscape", [Frame(10 * mm, 12 * mm, lw - 20 * mm, lh - 20 * mm)], onPage=footer, pagesize=(lw, lh)),
    ])
    outcome = {r: sum(1 for c in checks if c[1] == r) for r in ("OK", "DIFFERENZA", "NON POSSIBILE", "NON APPLICABILE")}
    flags = sum(len(l["flags"]) for l in inv["lines"]) + len(inv.get("flags", [])) + len(inv["pages_missing"])
    story = [Paragraph(esc(f"{inv['supplier_name']}"), H1),
             Paragraph(esc(f"{inv['document_type']} {inv['document_number'] or '(senza numero)'} — {inv['issue_date']['as_printed']}"), H2),
             P(f"Righe articolo lette: {len(inv['lines'])}. Charges: {len(inv['charges'])}. Segnalazioni (mancanti/incerti): {flags}.", N),
             P(f"Controlli: {outcome['OK']} OK, {outcome['DIFFERENZA']} differenze, {outcome['NON POSSIBILE']} non possibili, "
               f"{outcome['NON APPLICABILE']} non applicabili.", N),
             P("Contenuto: pagine originali, poi dati estratti, dati mancanti o incerti, esito dei controlli.", N),
             P(f"Lettura diretta senza Textract, Bedrock o altre API di riconoscimento. {DATA['method']}", N)]
    story += render_pages(inv)
    story += data_section(inv, checks)
    doc.build(story)
    return out, checks


def main():
    OUT_DIR.mkdir(exist_ok=True)
    summary = {}
    for inv in DATA["invoices"]:
        out, checks = build(inv)
        summary[inv["id"]] = {"pdf": out.name, "checks": [dict(kind=k, result=r, detail=d) for k, r, d in checks]}
        bad = [c for c in checks if c[1] == "DIFFERENZA"]
        print(f"{out.name}: {len(checks)} controlli, {len(bad)} differenze")
    (HERE / "controlli.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    shutil.rmtree(TMP_DIR, ignore_errors=True)


if __name__ == "__main__":
    main()
