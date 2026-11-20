"""Prova estesa lettura diretta — step 3: checks, structured data and one PDF per invoice.

Input:  letture_dirette.py (what was READ), pagine/*.png (render_pages.py), campione.json.
Output: fatture.json        structured data (schema field names) + checks + gaps, with page references
        PDF/<supplier> <number> - <date>.pdf   original pages, extracted data, missing/uncertain data, checks

Every value computed here (expected amounts, sums, tax) is labelled CALCULATED, never stored as read.
The PDFs are printed by headless Chrome from HTML (tables wrap, never cut). No recognition service is called.
Run:  python make_pdfs.py
"""

from __future__ import annotations

import html
import json
import shutil
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path

from PIL import Image

import letture_dirette as data

HERE = Path(__file__).resolve().parent
PAGES = HERE / "pagine"
OUT = HERE / "PDF"
CHROME = [Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
          Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")]
TOL = 0.011          # one cent of rounding

# Which reader of each uncertainty can resolve it (PO request: product card vs. person).
PRODUCT_CARD = "scheda prodotto"
PERSON = "persona"
NONE_NEEDED = "nessuna (confermato dai controlli)"
RESOLVER = {
    "piece_content_unit": PRODUCT_CARD, "piece_content_value": PRODUCT_CARD, "pack_count": PRODUCT_CARD,
    "unit_price_basis": PRODUCT_CARD, "actual_weight_unit": PERSON, "raw_description": PERSON,
    "quantity": NONE_NEEDED, "actual_weight_value": NONE_NEEDED,
}
FIELD_IT = {
    "piece_content_unit": "unità del contenuto", "piece_content_value": "contenuto nominale", "pack_count": "pezzi per confezione",
    "unit_price_basis": "base del prezzo", "actual_weight_unit": "unità del peso", "raw_description": "descrizione",
    "quantity": "quantità", "actual_weight_value": "peso effettivo", "supplier_item_code": "codice articolo",
}


def fmt(v, nd=2):
    if v is None:
        return "—"
    if isinstance(v, float) or isinstance(v, int):
        return f"{v:,.{nd}f}" if isinstance(v, float) or nd else str(v)
    return str(v)


def num(v):
    return f"{v:g}" if isinstance(v, (int, float)) else ("—" if v is None else str(v))


# ------------------------------------------------------------------------------------------------ checks

class Checks:
    def __init__(self):
        self.items = []

    def add(self, name, expected, printed, page=None, *, kind="sum", note=None):
        ok = None if printed is None or expected is None else abs(expected - printed) <= TOL * (1 if kind != "qty" else 0.001)
        self.items.append({"check": name, "calculated": round(expected, 4) if expected is not None else None,
                           "printed": printed, "page": page, "result": "OK" if ok else ("NON VERIFICABILE" if ok is None else "DIFFERENZA"),
                           "note": note})


def printed(inv, label):
    for t in inv["printed_totals"]:
        if t["label"] == label:
            return t["value"], t["page"]
    return None, None


def line_expected(line):
    """The amount the line's own numbers give (CALCULATED)."""
    if line["unit_price_basis"] == "LB" and line["actual_weight_value"] is not None:
        return line["actual_weight_value"] * line["unit_price"], f"{num(line['actual_weight_value'])} lb × {num(line['unit_price'])}"
    return line["quantity"] * line["unit_price"], f"{num(line['quantity'])} {line['purchase_unit']} × {num(line['unit_price'])}"


def run_checks(inv):
    c = Checks()
    lines = inv["lines"]
    for i, ln in enumerate(lines, 1):
        exp, how = line_expected(ln)
        c.add(f"Riga {ln['source_line_number'] or i} {ln['supplier_item_code'] or ''} — {how}", exp, ln["source_amount"], page=ln["page"], kind="line")
    products = sum(ln["source_amount"] for ln in lines)
    charges = sum(ch["amount"] for ch in inv["charges"])
    key = inv["key"]
    sec = defaultdict(float)
    sec_qty = defaultdict(lambda: defaultdict(float))
    for ln in lines:
        sec[ln["source_section"]] += ln["source_amount"]
        sec_qty[ln["source_section"]][ln["purchase_unit"]] += ln["quantity"]

    if key.startswith("cheney"):
        for s, label in (("01-DRY GOODS", "01-DRY GOODS"), ("02-COOLER", "02-COOLER")):
            c.add(f"Totale sezione {s}", sec[s], *printed(inv, label))
        c.add("Charges = TOTAL DISCOUNT/SURCHARGE", charges, *printed(inv, "TOTAL DISCOUNT/SURCHARGE"))
        c.add("Articoli + charges = Estimated Total", products + charges, *printed(inv, "Estimated Total"))
        c.add("Casse fatturate = TOTAL QTY THIS INVOICE", sum(ln["quantity"] for ln in lines), *printed(inv, "TOTAL QTY THIS INVOICE"), kind="qty")
        sal = lines[1]
        c.add("Pesi dei colli salame 8.15 + 7.93 = peso riga", sum(sal["extra"]["case_weights_printed"]), sal["actual_weight_value"], page=1)
        c.add("Somma colonna WEIGHT = valore non etichettato 81.08", sum(ln["actual_weight_value"] for ln in lines),
              *printed(inv, "unlabelled value near signature"), note="interpretazione: il valore 81.08 è il peso totale")
    elif key.startswith("gordon"):
        for s in ("Cooler", "Grocery", "Misc"):
            label = {"Cooler": "Total Cooler Pieces", "Grocery": "Total Grocery Pieces", "Misc": "Total Miscellaneous Pieces"}[s]
            c.add(f"Totale sezione {s}", sec[s], *printed(inv, label))
            c.add(f"Qty Ship sezione {s}", sec_qty[s]["CS"], *printed(inv, f"Totals Qty Ship {s}"), kind="qty")
        c.add("Somma articoli = Page Total", products, *printed(inv, "Page Total"))
        if inv["missing_pages"]:
            c.add("Totale fattura (tasse, fuel)", None, None, note="pagina 2 mancante: totale fattura, tasse e fuel non stampati su questa pagina")
        else:
            c.add("Product Total", products, *printed(inv, "Product Total"))
            cats = defaultdict(float)
            for ln in lines:
                cats[ln["supplier_category_code"]] += ln["source_amount"]
            for cat in ("PR", "GR", "DY", "DS", "CP", "BV"):
                c.add(f"Riepilogo categoria {cat}", cats[cat], *printed(inv, f"Recap {cat} subtotal"))
            c.add("Casse totali riepilogo", sum(ln["quantity"] for ln in lines), *printed(inv, "Category recap Total CS"), kind="qty")
            base = sum(ln["source_amount"] for ln in lines if ln["extra"].get("tax_code") == "12")
            c.add(f"Tassa 6.00% su imponibile {base:.2f} (righe Tax 12)", base * 0.06, inv["charges"][1]["amount"], page=2)
            c.add(f"Tassa 0.50% su imponibile {base:.2f}", base * 0.005, inv["charges"][2]["amount"], page=2)
            c.add("Product Total + Misc = SubTotal", products + inv["charges"][0]["amount"], *printed(inv, "SubTotal"))
            c.add("SubTotal + tasse = Invoice Total", products + charges, *printed(inv, "Invoice Total"))
    elif key.startswith("keith"):
        for s in ("Cooler", "Dry", "Frozen"):
            p = printed(inv, f"Section Total -{s}")
            if p[0] is not None:
                c.add(f"Totale sezione {s}", sec[s], *p)
                c.add(f"Casse sezione {s}", sec_qty[s]["CS"], *printed(inv, f"Section Total -{s} cases"), kind="qty")
                if printed(inv, f"Section Total -{s} pkgs")[0] is not None:
                    c.add(f"Pkgs sezione {s}", sec_qty[s]["PKG"], *printed(inv, f"Section Total -{s} pkgs"), kind="qty")
        c.add("Casse pagina", sum(ln["quantity"] for ln in lines if ln["purchase_unit"] == "CS"), *printed(inv, "Total Qty This Page cases"), kind="qty")
        c.add("Pkgs pagina", sum(ln["quantity"] for ln in lines if ln["purchase_unit"] == "PKG"), *printed(inv, "Total Qty This Page pkgs"), kind="qty")
        if inv["missing_pages"]:
            c.add("Totale fattura", None, None, note="pagina 2 mancante: Tax e Total Invoice stampati \"Continued\"")
        else:
            c.add("Articoli + Fuel + Tax = Total Invoice", products + charges, *printed(inv, "Total Invoice"))
    elif key.startswith("primeline"):
        c.add("Somma articoli = SUBTOTAL", products, *printed(inv, "SUBTOTAL"))
        c.add("SUBTOTAL + SURCHARGE + TAX = TOTAL", products + charges, *printed(inv, "TOTAL"))
    elif key.startswith("samuels"):
        c.add("Articoli + Delivery Charge = BALANCE", products + charges, *printed(inv, "BALANCE"))
    elif key.startswith("traderjoes"):
        c.add("Articoli = Items in Transaction", sum(ln["quantity"] for ln in lines), *printed(inv, "Items in Transaction"), kind="qty")
        if printed(inv, "Tax base")[0] is not None:
            base = sum(ln["source_amount"] for ln in lines if ln["extra"].get("taxable_flag") == "T")
            c.add("Imponibile righe \"T\" = base stampata", base, *printed(inv, "Tax base"))
            c.add("Tassa 6.5% sull'imponibile", base * 0.065, inv["charges"][0]["amount"], page=1)
        c.add("Articoli + tasse = Balance to pay", products + charges, *printed(inv, "Balance to pay"))
    return c.items, products, charges


def gaps(inv):
    """Missing or uncertain data, and who can resolve them."""
    out = []
    for p in inv["missing_pages"]:
        out.append({"scope": "documento", "field": "pagina", "issue": p, "resolver": PERSON})
    grouped: dict[tuple, list] = {}           # identical issue on several lines -> one entry, "#" listed
    for i, ln in enumerate(inv["lines"], 1):
        what = ln["supplier_item_code"] or ln["raw_description"][:30]
        issues = [("supplier_item_code", "codice articolo non stampato")] if not ln["supplier_item_code"] else []
        issues += list(ln["uncertain"].items())
        for field, why in issues:
            grouped.setdefault((what, field, why), []).append(i)
    for (what, field, why), rows in grouped.items():
        out.append({"scope": f"#{', #'.join(map(str, rows))} {what}", "field": field, "issue": why,
                    "resolver": PERSON if field == "supplier_item_code" else RESOLVER.get(field, PERSON), "rows": rows})
    for ns in inv.get("not_shipped", []):
        out.append({"scope": f"riga {ns['source_line_number']} {ns['supplier_item_code']}", "field": "riga OUT",
                    "issue": f"non consegnato ({ns['printed']}): esclusa dagli articoli", "resolver": NONE_NEEDED})
    return out


# ------------------------------------------------------------------------------------------------ HTML / PDF

CSS = """
@page { size: A4 landscape; margin: 10mm; }
body { font-family: Arial, Helvetica, sans-serif; font-size: 8.6pt; color: #111; }
h1 { font-size: 14pt; margin: 0 0 4px; } h2 { font-size: 11pt; margin: 10px 0 4px; border-bottom: 1px solid #999; }
table { border-collapse: collapse; width: 100%; table-layout: fixed; page-break-inside: auto; }
tr { page-break-inside: avoid; } thead { display: table-header-group; }
th, td { border: 1px solid #aaa; padding: 2px 3px; vertical-align: top; overflow-wrap: anywhere; }
th { background: #e8edf2; font-weight: bold; text-align: left; }
td.n { text-align: right; } .u { background: #fff4d6; } .ok { color: #106010; font-weight: bold; }
.ko { color: #b00000; font-weight: bold; } .nv { color: #8a5a00; font-weight: bold; }
.meta td { border: none; padding: 1px 6px 1px 0; } .legend { font-size: 7.6pt; color: #444; }
.page { page-break-before: always; page-break-inside: avoid; text-align: center; }
.page p { margin: 0 0 2mm; } .page img { display: block; margin: 0 auto; max-width: 100%; max-height: 168mm; border: 1px solid #ccc; }
.small { font-size: 7.6pt; }
"""


def e(v):
    return html.escape("" if v is None else str(v))


def build_html(inv, checks, products, charges, gap_list, page_images):
    rows = []
    for i, ln in enumerate(inv["lines"], 1):
        piece = (f"{num(ln['piece_content_value'])} {ln['piece_content_unit'] or ''}".strip()
                 if ln["piece_content_value"] is not None else "—")
        weight = (f"{num(ln['actual_weight_value'])} {ln['actual_weight_unit'] or '(unità?)'}"
                  if ln["actual_weight_value"] is not None else "—")
        piece_u = "piece_content_value" in ln["uncertain"] or "piece_content_unit" in ln["uncertain"]
        weight_u = "actual_weight_value" in ln["uncertain"] or "actual_weight_unit" in ln["uncertain"]
        desc = e(ln["raw_description"]) + (f'<br><span class="small">{e(ln["brand"])}</span>' if ln["brand"] else "")
        rows.append(
            "<tr>"
            f'<td class="n">{i}</td>'
            f'<td class="n">{e(ln["source_line_number"] or "")}</td>'
            f'<td>{e(ln["supplier_item_code"] or "—")}</td>'
            f'<td class="{"u" if "raw_description" in ln["uncertain"] else ""}">{desc}</td>'
            f'<td class="n{" u" if "quantity" in ln["uncertain"] else ""}">{num(ln["quantity"])} {e(ln["purchase_unit"])}</td>'
            f'<td>{e(ln["pack_size"] or "—")}</td>'
            f'<td class="n{" u" if "pack_count" in ln["uncertain"] else ""}">{num(ln["pack_count"])}</td>'
            f'<td class="n{" u" if piece_u else ""}">{e(piece)}</td>'
            f'<td class="n{" u" if weight_u else ""}">{e(weight)}</td>'
            f'<td class="n{" u" if "unit_price_basis" in ln["uncertain"] else ""}">{ln["unit_price"]:,.3f} / {e(ln["unit_price_basis"])}</td>'
            f'<td class="n">{ln["source_amount"]:,.2f}</td>'
            f'<td class="n">{ln["page"]}</td>'
            "</tr>")
    charge_rows = "".join(
        f'<tr><td>{e(ch["name"])}</td><td>{e(ch["kind"])}</td><td class="n">{ch["amount"]:+,.2f}</td><td class="n">{ch["page"]}</td>'
        f'<td>{e("; ".join(ch["notes"]))}</td></tr>' for ch in inv["charges"]) or '<tr><td colspan="5">Nessuna charge su queste pagine.</td></tr>'
    ns_rows = "".join(f"<li>Riga {e(n['source_line_number'])} {e(n['supplier_item_code'])} {e(n['raw_description'])} — {e(n['printed'])}</li>"
                      for n in inv.get("not_shipped", []))
    gap_rows = "".join(f'<tr><td>{e(g["scope"])}</td><td>{e(FIELD_IT.get(g["field"], g["field"]))}</td><td>{e(g["issue"])}</td>'
                       f'<td>{e(g["resolver"])}</td></tr>' for g in gap_list) or '<tr><td colspan="4">Nessuno.</td></tr>'

    def res(r):
        cls = {"OK": "ok", "DIFFERENZA": "ko"}.get(r, "nv")
        return f'<span class="{cls}">{r}</span>'

    check_rows = "".join(
        f'<tr><td>{e(c["check"])}</td><td class="n">{fmt(c["calculated"])}</td><td class="n">{fmt(c["printed"])}</td>'
        f'<td class="n">{e(c["page"] or "")}</td><td>{res(c["result"])}</td><td>{e(c["note"] or "")}</td></tr>' for c in checks)
    n_ok = sum(1 for c in checks if c["result"] == "OK")
    n_ko = sum(1 for c in checks if c["result"] == "DIFFERENZA")
    n_nv = sum(1 for c in checks if c["result"] == "NON VERIFICABILE")
    notes = "".join(f"<li>{e(n)}</li>" for n in inv["document_notes"])
    line_notes = "".join(f"<li>Riga {i} ({e(ln['supplier_item_code'] or ln['raw_description'][:30])}): {e(n)}</li>"
                         for i, ln in enumerate(inv["lines"], 1) for n in ln["notes"])
    pages_html = "".join(f'<div class="page"><p><b>Pagina originale — {e(lbl)}</b></p><img src="{src}"></div>'
                         for src, lbl in page_images)
    return f"""<!doctype html><html lang="it"><head><meta charset="utf-8"><title>{e(inv['supplier_name'])} {e(inv['document_number'])}</title>
<style>{CSS}</style></head><body>
<h1>{e(inv['supplier_name'])} — fattura {e(inv['document_number'])} — {e(inv['document_date'])}</h1>
<table class="meta"><tr><td><b>Data stampata</b> {e(inv['date_as_printed'])}</td><td><b>Pagine</b> {e(inv['page_marking'])}</td>
<td><b>Pagine mancanti</b> {e('; '.join(inv['missing_pages']) or 'nessuna')}</td></tr>
<tr><td colspan="3"><b>Fonte</b> {e('; '.join(p['label'] + ' — ' + p['render'] for p in inv['pages']))}</td></tr></table>
<p class="legend">Lettura diretta degli originali (sessione Claude Code, claude-opus-5-5, 2026-10-11), senza servizi di riconoscimento e senza
trascrizioni precedenti; nessun completamento dalla scheda prodotto. <span class="u">&nbsp;Celle evidenziate&nbsp;</span> = lettura o
significato incerti (dettaglio nella sezione «Dati mancanti o incerti»). I valori calcolati compaiono solo nei controlli.</p>
<h2>Righe articolo ({len(inv['lines'])}) — dati letti</h2>
<table><colgroup><col style="width:3%"><col style="width:3.5%"><col style="width:6.5%"><col style="width:24%"><col style="width:7%">
<col style="width:8%"><col style="width:5.5%"><col style="width:8%"><col style="width:8%"><col style="width:10.5%"><col style="width:8%"><col style="width:3.5%"></colgroup>
<thead><tr><th>#</th><th>Riga doc.</th><th>Codice</th><th>Descrizione / marca</th><th>Q.tà fatturata</th><th>Confezione stampata</th>
<th>Pezzi per conf.</th><th>Contenuto nominale</th><th>Peso effettivo</th><th>Prezzo unitario / base</th><th>Importo riga</th><th>Pag.</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<h2>Charges (con segno)</h2>
<table><colgroup><col style="width:30%"><col style="width:10%"><col style="width:12%"><col style="width:6%"><col style="width:42%"></colgroup>
<thead><tr><th>Nome</th><th>Tipo</th><th>Importo</th><th>Pag.</th><th>Note</th></tr></thead><tbody>{charge_rows}</tbody></table>
{('<h2>Righe non consegnate (non conteggiate)</h2><ul>' + ns_rows + '</ul>') if ns_rows else ''}
<h2>Dati mancanti o incerti ({len(gap_list)})</h2>
<table><colgroup><col style="width:20%"><col style="width:13%"><col style="width:52%"><col style="width:15%"></colgroup>
<thead><tr><th>Dove</th><th>Campo</th><th>Problema</th><th>Chi può risolverlo</th></tr></thead><tbody>{gap_rows}</tbody></table>
<h2>Esito dei controlli — {n_ok} OK, {n_ko} differenze, {n_nv} non verificabili</h2>
<p class="legend">«Calcolato» = valore ottenuto dai dati letti; «Stampato» = valore letto sul documento. Tolleranza: 1 centesimo (arrotondamento).
Una somma che torna è un controllo, non una garanzia assoluta.</p>
<table><colgroup><col style="width:42%"><col style="width:11%"><col style="width:11%"><col style="width:5%"><col style="width:11%"><col style="width:20%"></colgroup>
<thead><tr><th>Controllo</th><th>Calcolato</th><th>Stampato</th><th>Pag.</th><th>Esito</th><th>Nota</th></tr></thead><tbody>{check_rows}</tbody></table>
<p><b>Totale righe articolo (calcolato)</b> {products:,.2f} · <b>Totale charges (calcolato)</b> {charges:+,.2f}</p>
<h2>Note sul documento</h2><ul>{notes}{line_notes}</ul>
{pages_html}
</body></html>"""


def page_image(render: str, rotated: int | None, tmp: Path) -> str:
    """Upright JPEG of an original page (rotated only to be readable; content untouched)."""
    im = Image.open(PAGES / f"{render}.png").convert("RGB")
    if rotated:
        im = im.rotate(rotated, expand=True)
    im.thumbnail((2200, 2200))
    out = tmp / f"{render}.jpg"
    im.save(out, "JPEG", quality=82)
    return out.as_uri()


def chrome() -> Path:
    for path in CHROME:
        if path.exists():
            return path
    raise SystemExit("Chrome / Edge not found")


def main() -> None:
    OUT.mkdir(exist_ok=True)
    sample = json.loads((HERE / "campione.json").read_text(encoding="utf-8"))
    by_render = {}
    for d in sample["distinct"]:
        for n, r in enumerate(d["renders"], 1):
            by_render[r.removesuffix(".png")] = {"content_hash": d["sha256"], "original_filenames": d["files"],
                                                 "file_page": n, "file_page_count": d["pages"]}
    results = []
    tmp = Path(tempfile.mkdtemp(prefix="prova_lettura_"))
    try:
        for inv in data.INVOICES:
            checks, products, charges = run_checks(inv)
            gap_list = gaps(inv)
            sources = [{"sequence": i, **by_render[p["render"]], "page_label": p["label"],
                        "rotated_for_reading": p.get("rotated")} for i, p in enumerate(inv["pages"], 1)]
            images = [(page_image(p["render"], p.get("rotated"), tmp), p["label"]) for p in inv["pages"]]
            name = f"{inv['supplier_name'].split(' (')[0].split(',')[0]} {inv['document_number'].split(' (')[0]} - {inv['document_date']}"
            name = name.replace("/", "-").replace(":", "")
            html_path = tmp / f"{inv['key']}.html"
            html_path.write_text(build_html(inv, checks, products, charges, gap_list, images), encoding="utf-8")
            pdf = OUT / f"{name}.pdf"
            subprocess.run([str(chrome()), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                            f"--print-to-pdf={pdf}", html_path.as_uri()], check=True, capture_output=True, timeout=180)
            results.append({
                "key": inv["key"], "pdf": f"PDF/{pdf.name}",
                "purchase_document": {"supplier_name": inv["supplier_name"], "document_number": inv["document_number"],
                                      "document_date": inv["document_date"], "date_as_printed": inv["date_as_printed"],
                                      "page_marking": inv["page_marking"], "missing_pages": inv["missing_pages"]},
                "purchase_document_sources": sources,
                "purchase_lines": [dict(ln, source_amount_minor=round(ln["source_amount"] * 100),
                                        unit_price_minor=round(ln["unit_price"] * 100) if ln["unit_price"] * 100 == round(ln["unit_price"] * 100, 6) else None)
                                   for ln in inv["lines"]],
                "charges": [dict(ch, line_type=ch["kind"] if ch["kind"] != "TAX" else "TAX (not a purchase_lines type)",
                                 source_amount_minor=round(ch["amount"] * 100)) for ch in inv["charges"]],
                "not_shipped": inv.get("not_shipped", []),
                "printed_totals": inv["printed_totals"],
                "calculated": {"products_total": round(products, 2), "charges_total": round(charges, 2)},
                "checks": checks, "gaps": gap_list, "document_notes": inv["document_notes"],
            })
            print(f"{pdf.name}: {len(inv['lines'])} lines, checks "
                  f"{sum(c['result'] == 'OK' for c in checks)} OK / {sum(c['result'] == 'DIFFERENZA' for c in checks)} diff / "
                  f"{sum(c['result'] == 'NON VERIFICABILE' for c in checks)} n.v., gaps {len(gap_list)}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    (HERE / "fatture.json").write_text(json.dumps({
        "method": "lettura diretta degli originali, sessione Claude Code (claude-opus-5-5), 2026-10-11; nessun servizio "
                  "di riconoscimento; nessuna trascrizione precedente; nessun completamento da scheda prodotto",
        "schema_note": "nomi dei campi di purchase_documents / purchase_lines / purchase_document_sources (PURCHASING.md §13); "
                       "gli importi *_minor sono in centesimi; 'uncertain' = campi interpretati; 'checks.calculated' = valori calcolati",
        "invoices": results}, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
