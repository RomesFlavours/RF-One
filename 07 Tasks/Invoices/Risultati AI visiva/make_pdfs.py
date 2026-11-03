"""Build one readable PDF per invoice from the saved model answers (no model calls)."""
import json
import pathlib
import re
import shutil
import sys

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

HERE = pathlib.Path(__file__).parent
IMG_DIR = pathlib.Path(sys.argv[1])
RAW = HERE / "Risposte modello"
SENT = HERE / "Immagini inviate"
SENT.mkdir(exist_ok=True)

pdfmetrics.registerFont(TTFont("Arial", r"C:\Windows\Fonts\arial.ttf"))
pdfmetrics.registerFont(TTFont("Arial-Bold", r"C:\Windows\Fonts\arialbd.ttf"))
S = ParagraphStyle("s", fontName="Arial", fontSize=7, leading=8.5)
SB = ParagraphStyle("sb", parent=S, fontName="Arial-Bold")
N = ParagraphStyle("n", fontName="Arial", fontSize=9, leading=11.5)
H1 = ParagraphStyle("h1", fontName="Arial-Bold", fontSize=14, leading=17, spaceAfter=4)
H2 = ParagraphStyle("h2", fontName="Arial-Bold", fontSize=11, leading=14, spaceBefore=8, spaceAfter=4)

INVOICES = {
    "Keith": {"model": "Claude Opus 4.6 (us.anthropic.claude-opus-4-6-v1)", "source": "2026-08-Keith PM.pdf", "short": "Opus 4.6"},
    "Gordon": {"model": "Claude Sonnet 4.6 (us.anthropic.claude-sonnet-4-6)", "source": "2026-08-Gordon.pdf", "short": "Sonnet 4.6 (incompleta)"},
    "Cheney": {"model": "Claude Sonnet 4.6 (us.anthropic.claude-sonnet-4-6)", "source": "2026-08-Cheney.pdf", "short": "Sonnet 4.6"},
}

# Presentation corrections made by the Mulo after checking the original. The model's raw answer
# (Risposte modello/*_answer.txt) is left untouched; the PDF shows both values.
CORRECTIONS = {
    "Cheney": {
        "20": {"actual_weight": ("65.00 [unità non determinata]",
                                 "Il modello ha restituito '65.00 lb'. Nell'originale la colonna WEIGHT riporta solo "
                                 "65.00: l'unità non è stampata, quindi resta non determinata.")},
        "10": {"actual_weight": ("16.08 [unità non stampata; lb = inferenza]",
                                 "Il modello ha restituito '16.08 lb'. Accanto al peso l'unità non è stampata; 'lb' è "
                                 "un'inferenza dal '#' stampato dopo il prezzo 8.98 e dal pack '003/2.5 # AVG'.")},
    },
}


def esc(v):
    if v is None:
        return "—"
    return str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def money(v):
    return "—" if v is None else (f"{v:,.2f}" if isinstance(v, (int, float)) else esc(v))


def load_answer(name):
    """Parse the model JSON; if the answer was cut by max_tokens, keep only complete items."""
    text = (RAW / f"{name}_answer.txt").read_text(encoding="utf-8")
    body = text[text.index("{"):]
    body = re.sub(r"```\s*$", "", body.strip())
    try:
        return json.loads(body), False
    except json.JSONDecodeError:
        # Keep the last, partially returned item up to its last complete field, flagged as truncated.
        # The answer ends right after a complete field and its trailing comma.
        return json.loads(body.rstrip().rstrip(",") +', "doubts": "[risposta del modello interrotta qui: campo non restituito]"}]}'), True


def build(name, meta):
    ans, truncated = load_answer(name)
    img = IMG_DIR / f"{name}_oriented.jpg"
    for part in ("oriented", "top", "bottom"):
        if (IMG_DIR / f"{name}_{part}.jpg").resolve() != (SENT / f"{name}_{part}.jpg").resolve():
            shutil.copy(IMG_DIR / f"{name}_{part}.jpg", SENT / f"{name}_{part}.jpg")
    date = (ans.get("invoice_date") or {}).get("as_printed")
    out = HERE / f"{name} - {(date or 'data non letta').replace('/', '-')} - Bedrock {meta['short']}.pdf"
    doc = SimpleDocTemplate(str(out), pagesize=landscape(A4), leftMargin=10 * mm, rightMargin=10 * mm,
                            topMargin=10 * mm, bottomMargin=10 * mm, title=f"{name} - lettura Bedrock")
    W, H = landscape(A4)[0] - 20 * mm, landscape(A4)[1] - 20 * mm
    story = []

    # 1. Original, oriented for reading
    story.append(Paragraph(f"{esc(name)} — originale orientato per la lettura", H2))
    from PIL import Image as PImage
    iw, ih = PImage.open(img).size
    scale = min(W / iw, (H - 12 * mm) / ih)
    story += [Image(str(img), iw * scale, ih * scale), PageBreak()]

    # 2. Compact table of requested data only
    story.append(Paragraph(f"{esc(name)} — lettura Bedrock (modello AI, lettura indipendente)", H1))
    story.append(Paragraph(
        f"<b>Supplier:</b> {esc(ans.get('supplier'))} &nbsp;&nbsp; <b>Data fattura:</b> {esc(date)} "
        f"(ISO {esc((ans.get('invoice_date') or {}).get('iso'))}) &nbsp;&nbsp; <b>Modello:</b> {esc(meta['model'])} "
        f"&nbsp;&nbsp; <b>Originale:</b> {esc(meta['source'])}", N))
    if truncated:
        story.append(Paragraph(
            "<b>ATTENZIONE: risposta del modello interrotta dal limite di token di output.</b> Sono riportate solo le "
            "righe restituite complete; righe successive, charges e segnalazioni sul documento NON sono stati "
            "restituiti dal modello (non significa che non esistano).", N))
    story.append(Spacer(1, 4))
    head = ["#", "Rif.", "Descrizione", "Q.tà ord.", "Q.tà cons.", "Unità", "Casse", "Pezzi",
            "Confezione", "Peso effettivo", "Costo unit.", "Base del prezzo", "Importo riga"]
    rows = [[Paragraph(h, SB) for h in head]]
    fixes = CORRECTIONS.get(name, {})
    CB = ParagraphStyle("cb", parent=S, textColor=colors.HexColor("#B00020"), fontName="Arial-Bold")

    def cell(it, k):
        fix = fixes.get(str(it.get("line_ref")), {}).get(k)
        return Paragraph(esc(fix[0]) + " *", CB) if fix else Paragraph(esc(it.get(k)), S)

    for i, it in enumerate(ans.get("items", []), 1):
        rows.append([Paragraph(str(i), S)] + [cell(it, k) for k in
                    ("line_ref", "description", "qty_ordered", "qty_delivered", "qty_unit", "cases", "pieces",
                     "pack_content", "actual_weight")] +
                    [Paragraph(money(it.get("unit_price")), S), Paragraph(esc(it.get("unit_price_basis")), S),
                     Paragraph(money(it.get("line_amount")), S)])
    cw = [7, 16, 48, 13, 13, 13, 13, 11, 20, 26, 16, 51, 18]
    t = Table(rows, colWidths=[c * mm for c in cw], repeatRows=1)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDE4EE")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (10, 1), (10, -1), "RIGHT"), ("ALIGN", (12, 1), (12, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F7FA")]),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    story.append(t)

    story.append(Paragraph("Charges (con segno)", H2))
    if truncated:
        story.append(Paragraph("Non restituiti dal modello (risposta interrotta).", N))
    elif ans.get("charges"):
        crow = [[Paragraph("Nome", SB), Paragraph("Importo", SB)]] + \
               [[Paragraph(esc(c.get("name")), S), Paragraph(money(c.get("amount")), S)] for c in ans["charges"]]
        ct = Table(crow, colWidths=[80 * mm, 25 * mm])
        ct.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDE4EE")),
                                ("ALIGN", (1, 1), (1, -1), "RIGHT")]))
        story.append(ct)
    else:
        story.append(Paragraph("Nessun charge indicato dal modello.", N))

    # 3. Ambiguities / unreadable information
    if fixes:
        story.append(Paragraph("* Correzioni di presentazione (del Mulo, non del modello)", H2))
        story.append(Paragraph("La risposta originale del modello resta intatta in 'Risposte modello/'. "
                               "In tabella, in rosso, il valore corretto; qui sotto il valore restituito dal modello.", N))
        for ref, flds in fixes.items():
            for k, (shown, why) in flds.items():
                story.append(Paragraph(f"• <b>Riga {esc(ref)}, {esc(k)}:</b> {esc(why)}", N))
    story.append(Paragraph("Ambiguità e informazioni non leggibili (testo del modello)", H2))
    issues = list(ans.get("document_issues") or [])
    if truncated:
        issues.insert(0, "[Nota di chi ha eseguito la prova, non del modello] La risposta è stata interrotta prima "
                         "delle sezioni 'document_issues' e 'general_doubts'. Nel ragionamento riassunto restituito "
                         "il modello aveva notato 'Page 1 of 2' con pagina 2 mancante e l'articolo Rinse Aid "
                         "(209.49), ma queste informazioni non sono arrivate nella risposta strutturata.")
    for x in issues:
        story.append(Paragraph("• <b>Documento:</b> " + esc(x), N))
    for x in ans.get("general_doubts") or []:
        story.append(Paragraph("• <b>Generale:</b> " + esc(x), N))
    for i, it in enumerate(ans.get("items", []), 1):
        if it.get("doubts"):
            story.append(Paragraph(f"• <b>Riga {i} ({esc(it.get('line_ref'))}):</b> {esc(it['doubts'])}", N))
    for c in ([] if truncated else ans.get("charges") or []):
        if c.get("doubts"):
            story.append(Paragraph(f"• <b>Charge {esc(c.get('name'))}:</b> {esc(c['doubts'])}", N))
    doc.build(story)
    return out


for n, m in INVOICES.items():
    print(build(n, m))
