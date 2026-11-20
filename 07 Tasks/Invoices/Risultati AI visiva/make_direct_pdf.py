"""PDF of the Mulo's direct reading of Gordon (no model or AWS call): original + table + ambiguities."""
import json
import pathlib

from PIL import Image as PImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

HERE = pathlib.Path(__file__).parent
DATA = json.loads((HERE / "Lettura diretta Mulo" / "Gordon_lettura_diretta_Mulo.json").read_text(encoding="utf-8"))
IMG = HERE / "Immagini inviate" / "Gordon_oriented.jpg"
OUT = HERE / "Gordon - 08-26-2026 - Lettura diretta Mulo.pdf"

pdfmetrics.registerFont(TTFont("Arial", r"C:\Windows\Fonts\arial.ttf"))
pdfmetrics.registerFont(TTFont("Arial-Bold", r"C:\Windows\Fonts\arialbd.ttf"))
pdfmetrics.registerFont(TTFont("Arial-Italic", r"C:\Windows\Fonts\ariali.ttf"))
S = ParagraphStyle("s", fontName="Arial", fontSize=7, leading=8.5)
SI = ParagraphStyle("si", parent=S, fontName="Arial-Italic", textColor=colors.HexColor("#555555"))
SB = ParagraphStyle("sb", parent=S, fontName="Arial-Bold")
N = ParagraphStyle("n", fontName="Arial", fontSize=9, leading=11.5)
H1 = ParagraphStyle("h1", fontName="Arial-Bold", fontSize=14, leading=17, spaceAfter=4)
H2 = ParagraphStyle("h2", fontName="Arial-Bold", fontSize=11, leading=14, spaceBefore=8, spaceAfter=4)


def esc(v):
    return "—" if v is None else str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def src(field, label_if_missing="non stampato"):
    """Printed values in normal text; inferences in grey italics marked (inf.); missing values explained."""
    if field["value"] is None:
        return Paragraph(label_if_missing, SI)
    if field["source"].startswith("inference"):
        return Paragraph(f"{esc(field['value'])} (inf.)", SI)
    return Paragraph(esc(field["value"]), S)


doc = SimpleDocTemplate(str(OUT), pagesize=landscape(A4), leftMargin=10 * mm, rightMargin=10 * mm,
                        topMargin=10 * mm, bottomMargin=10 * mm, title="Gordon - lettura diretta Mulo")
W, H = landscape(A4)[0] - 20 * mm, landscape(A4)[1] - 20 * mm
story = [Paragraph("Gordon — originale (già orientato per la lettura)", H2)]
iw, ih = PImage.open(IMG).size
sc = min(W / iw, (H - 12 * mm) / ih)
story += [Image(str(IMG), iw * sc, ih * sc), PageBreak()]

story.append(Paragraph("Gordon — LETTURA DIRETTA DEL MULO", H1))
story.append(Paragraph(
    "Lettura eseguita dal Mulo (Claude, nella sessione Claude Code) guardando direttamente l'immagine originale, "
    "senza chiamate AWS o ad altri servizi. <b>Non</b> è la lettura Bedrock: quella, incompleta, resta nel file "
    "separato 'Gordon - 08-26-2026 - Bedrock Sonnet 4.6 (incompleta).pdf'.", N))
story.append(Paragraph(
    f"<b>Supplier:</b> {esc(DATA['supplier']['value'])} &nbsp;&nbsp; <b>Data fattura:</b> "
    f"{esc(DATA['invoice_date']['value'])} (ISO {DATA['invoice_date']['iso']}) &nbsp;&nbsp; "
    "<b>Legenda:</b> testo normale = stampato; <i>grigio corsivo (inf.)</i> = inferenza; "
    "<i>non stampato</i> = dato assente nell'originale.", N))
story.append(Spacer(1, 4))

head = ["#", "Codice", "Descrizione", "Q.tà ord.", "Q.tà cons.", "Unità", "Casse", "Pezzi", "Confezione",
        "Peso effettivo", "Costo unit.", "Base del prezzo", "Importo riga"]
rows = [[Paragraph(h, SB) for h in head]]
for i, it in enumerate(DATA["items"], 1):
    rows.append([Paragraph(str(i), S), Paragraph(it["item_code"], S), Paragraph(esc(it["description"]), S),
                 Paragraph(str(it["qty_ordered"]), S), Paragraph(str(it["qty_delivered"]), S),
                 src(it["unit"]), src(it["cases"]), src(it["pieces"]), Paragraph(esc(it["pack_content"]), S),
                 src(it["actual_weight"]), Paragraph(f"{it['unit_price']:,.2f}", S),
                 src(it["unit_price_basis"]), Paragraph(f"{it['line_amount']:,.2f}", S)])
t = Table(rows, colWidths=[c * mm for c in [7, 14, 58, 13, 13, 11, 12, 16, 20, 18, 16, 41, 18]], repeatRows=1)
t.setStyle(TableStyle([
    ("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E3EEDD")),
    ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (10, 1), (10, -1), "RIGHT"), ("ALIGN", (12, 1), (12, -1), "RIGHT"),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F7FA")]),
    ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
story.append(t)
story.append(Paragraph("Base del prezzo (inf.) per tutte le righe: la colonna Unit è CS e Q.tà cons. × Costo unit. = "
                       "Importo riga; l'intestazione 'Unit Price' non dichiara la base.", SI))

story.append(Paragraph("Charges", H2))
story.append(Paragraph("Nessun charge stampato a pagina 1. " + esc(DATA["charges_note"].split(". ", 1)[1]
                       if ". " in DATA["charges_note"] else ""), N))
story.append(Paragraph("Non sono articoli né charges: " + "; ".join(DATA["not_items_or_charges"]) + ".", N))

story.append(Paragraph("Ambiguità, pagine mancanti, note", H2))
for x in DATA["document_issues"]:
    story.append(Paragraph("• <b>Documento:</b> " + esc(x), N))
for it in DATA["items"]:
    if it["note"]:
        story.append(Paragraph(f"• <b>{it['item_code']}:</b> {esc(it['note'])}", N))
for x in DATA["ambiguities"]:
    story.append(Paragraph("• " + esc(x), N))
story.append(Paragraph("• <i>Controlli aritmetici (calcoli, non dati stampati):</i> "
                       + esc(DATA["arithmetic_checks_not_data"]), N))
doc.build(story)
print(OUT)
