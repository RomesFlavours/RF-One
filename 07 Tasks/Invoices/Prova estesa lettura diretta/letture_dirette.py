"""Prova estesa lettura diretta — what was READ on the original pages.

Read directly by the Claude Code session (model claude-opus-5-5) from the 300 dpi renders in pagine/ (whole page,
then zoomed / rotated crops), 2026-10-11. No recognition service, no earlier transcription used.

Only values printed on the page are recorded here. Field names follow the Invoice Intake schema
(purchase_documents / purchase_lines / purchase_document_sources, PURCHASING.md §13):
  supplier_item_code, raw_description, brand, source_section, supplier_category_code, quantity, purchase_unit,
  pack_size (as printed), pack_count, piece_content_value/unit, actual_weight_value/unit,
  unit_price + unit_price_basis, source_amount (signed; the schema stores *_minor cents).
`uncertain`: fields whose reading or meaning is an interpretation, with the reason.
Checks and every computed value are produced by make_pdfs.py, never stored here as read.
"""

from __future__ import annotations


def L(page, n, code, desc, qty, unit, pack, count, piece, piece_unit, price, basis, amount, *, brand=None,
      section=None, cat=None, weight=None, weight_unit=None, extra=None, uncertain=None, notes=None,
      line_type="PRODUCT"):
    return {"line_type": line_type, "page": page, "source_line_number": n, "supplier_item_code": code,
            "raw_description": desc, "brand": brand, "source_section": section, "supplier_category_code": cat,
            "quantity": qty, "purchase_unit": unit, "pack_size": pack, "pack_count": count,
            "piece_content_value": piece, "piece_content_unit": piece_unit,
            "actual_weight_value": weight, "actual_weight_unit": weight_unit,
            "unit_price": price, "unit_price_basis": basis, "source_amount": amount,
            "extra": extra or {}, "uncertain": uncertain or {}, "notes": notes or []}


def C(page, name, amount, *, kind="SURCHARGE", n=None, notes=None):
    """A charge: name and signed amount as printed (kind SURCHARGE / DISCOUNT / TAX)."""
    return {"page": page, "name": name, "amount": amount, "kind": kind, "source_line_number": n, "notes": notes or []}


def T(page, label, value):
    """A total printed on the page (used only for checks)."""
    return {"page": page, "label": label, "value": value}


INVOICES = []

# ---------------------------------------------------------------------------------------------- Cheney Brothers
INVOICES.append({
    "key": "cheney_05-9100355806",
    "supplier_name": "Cheney Brothers, Inc. (Ocala, FL)",
    "document_number": "05-9100355806",
    "document_date": "2026-08-19",
    "date_as_printed": "MO 08 / DAY 19 / YR 26",
    "pages": [{"render": "Cheney_b7e2e8ba1c23_p1", "label": "scan A, page 1", "rotated": 90},
              {"render": "Cheney_6a0100477cb0_p1", "label": "scan B (rescan of the same invoice), page 1", "rotated": 90}],
    "page_marking": "PAGE 1; TOTAL QTY THIS PAGE 6 = TOTAL QTY THIS INVOICE 6",
    "missing_pages": [],
    "lines": [
        L(1, 20, "114047", "OIL OLIVE EXTRA VIRGIN ITALY TINS ITALY RETAIL READY - NEW 10180584", 4, "CS",
          "002/1 GAL", 2, 1, "GAL", 120.88, "CS", 483.52, brand="FRONTE", section="01-DRY GOODS",
          weight=65.00, weight_unit=None, extra={"location": "DW-177-1"},
          uncertain={"actual_weight_unit": "colonna WEIGHT 65.00 senza unità stampata (probabilmente lb); su una riga "
                                            "prezzata a cassa è un peso di spedizione, non un peso variabile"}),
        L(1, 10, "10038378", "SALAMI SOPRESSATA SPICY CALABRIAN", 2, "CS", "003/2.5 # AVG", 3, 2.5, "LB",
          8.98, "LB", 144.40, brand="VOLPI", section="02-COOLER", weight=16.08, weight_unit="LB",
          extra={"location": "CJ-126-2C", "case_weights_printed": [8.15, 7.93]},
          uncertain={"piece_content_value": "2.5 # è una MEDIA (\"AVG\"), non un contenuto fisso",
                     "actual_weight_unit": "unità ricavata dalla base prezzo \"#\" (= lb) stampata accanto all'importo"}),
    ],
    "charges": [C(1, "FUEL SURCHARGE", 7.00, n=1, notes=["prezzo unitario stampato 0.00"])],
    "printed_totals": [T(1, "01-DRY GOODS", 483.52), T(1, "02-COOLER", 144.40),
                       T(1, "TOTAL DISCOUNT/SURCHARGE", 7.00), T(1, "Estimated Total", 634.92),
                       T(1, "TOTAL QTY THIS INVOICE", 6), T(1, "unlabelled value near signature", 81.08)],
    "document_notes": ["Due scansioni in file diversi (SHA-256 b7e2e8ba1c23…, presente anche in due copie identiche, "
                       "e 6a0100477cb0…) mostrano la STESSA fattura: una sola fattura, letta una volta.",
                       "Scadenza 08/27/2026, termini 1 WK DUE, cliente 60024539."],
})

# ---------------------------------------------------------------------------------------------- Gordon Food Service
_G_SECTIONS = {"Cooler": "Total Cooler Pieces", "Grocery": "Total Grocery Pieces", "Misc": "Total Miscellaneous Pieces"}
_G_NOTE = "Colonna Unit = CS: quantità e Unit Price sono per cassa; Inv Value = prezzo per pezzo interno (stampato)."

INVOICES.append({
    "key": "gordon_9039354564",
    "supplier_name": "Gordon Food Service Inc. (Plant City Distribution Ctr)",
    "document_number": "9039354564",
    "document_date": "2026-08-26",
    "date_as_printed": "08/26/2026",
    "pages": [{"render": "Gordon_1050699ac5f2_p1", "label": "page 1 of 2"}],
    "page_marking": "Page 1 of 2",
    "missing_pages": ["Pagina 2 di 2 (riepilogo categorie, fuel charge, tasse, totale fattura) assente in tutti i file"],
    "lines": [
        L(1, 1, "106632", "ARUGULA WILD", 1, "CS", "2x2 LB", 2, 2, "LB", 17.38, "CS", 17.38, brand="Ready-", section="Cooler", cat="PR", extra={"inv_value": 8.69}),
        L(1, 2, "732478", "BROCCOLI FLORET REG CUT", 1, "CS", "4x3 LB", 4, 3, "LB", 31.29, "CS", 31.29, brand="Ready-", section="Cooler", cat="PR", extra={"inv_value": 7.82}),
        L(1, 3, "556528", "JUICE STRAWB LEMND", 3, "CS", "6x12 FOZ", 6, 12, "FL OZ", 11.07, "CS", 33.21, brand="Natali", section="Cooler", cat="BV", extra={"inv_value": 1.85}),
        L(1, 4, "521520", "PARSLEY ITAL FRESH", 2, "CS", "1x1 LB", 1, 1, "LB", 11.32, "CS", 22.64, brand="Markon", section="Cooler", cat="PR", extra={"inv_value": 11.32}),
        L(1, 5, "560715", "PEPPERS RED", 1, "CS", "1x23 LB", 1, 23, "LB", 38.11, "CS", 38.11, brand="Markon", section="Cooler", cat="PR", extra={"inv_value": 38.11}),
        L(1, 6, "152222", "SPRING MIX HERITAGE", 1, "CS", "4x3 LB", 4, 3, "LB", 31.23, "CS", 31.23, brand="Ready-", section="Cooler", cat="PR", extra={"inv_value": 7.81}),
        L(1, 7, "165431", "THYME FRESH", 2, "CS", "1x1 LB", 1, 1, "LB", 12.00, "CS", 24.00, brand="Markon", section="Cooler", cat="PR", extra={"inv_value": 12.00}),
        L(1, 8, "403872", "BEAN CANNELINI WHT KIDNY", 1, "CS", "24x15.5 OZ", 24, 15.5, "OZ", 34.66, "CS", 34.66, brand="Furman", section="Grocery", cat="GR", extra={"inv_value": 1.44}),
        L(1, 9, "115642", "CONT PLAS 38Z RECT BLK W/LID VERSA", 1, "CS", "1x150 CO", 1, 150, "CT", 83.29, "CS", 83.29, brand="Versat", section="Grocery", cat="DS", extra={"inv_value": 83.29, "tax_code": "12"},
          uncertain={"pack_count": "\"1x150 CO\": letto come 1 confezione da 150 pezzi (CO = count); 150 pezzi per cassa è un'interpretazione"}),
        L(1, 10, "672312", "CUP PLAS CLD 16Z CLR", 1, "CS", "12x70 CO", 12, 70, "CT", 59.99, "CS", 59.99, brand="Gordon", section="Grocery", cat="DS", extra={"inv_value": 5.00, "tax_code": "12", "spec": "P"},
          notes=["Stampato: \"The above line item includes a promotional discount of $ 34.65 ($34.65/CS)\" — già incluso in 59.99, non è una charge separata"],
          uncertain={"pack_count": "\"12x70 CO\": 12 confezioni da 70 bicchieri (CO = count) — interpretazione di CO"}),
        L(1, 11, "811601", "FLOUR PIZZA \"00\"", 1, "CS", "1x55 LB", 1, 55, "LB", 51.34, "CS", 51.34, brand="Caputo", section="Grocery", cat="GR", extra={"inv_value": 51.34}),
        L(1, 12, "579590", "SODA BTL COKE MEX", 3, "CS", "24x12 FOZ", 24, 12, "FL OZ", 38.39, "CS", 115.17, brand="Coca-C", section="Grocery", cat="BV", extra={"inv_value": 1.60, "tax_code": "12"}),
        L(1, 13, "358914", "TOMATO PLUM I/JCE", 5, "CS", "6x10 CSZ", 6, 10, "CSZ", 37.13, "CS", 185.65, brand="Alta C", section="Grocery", cat="GR", extra={"inv_value": 6.19},
          uncertain={"piece_content_value": "\"10 CSZ\" = formato lattina #10, non un peso o volume: il peso netto per lattina non è stampato"}),
        L(1, 14, "556163", "TOWEL C-FLD 11.42X10\" WHT", 1, "CS", "12x198 CO", 12, 198, "CT", 24.80, "CS", 24.80, brand="Empres", section="Grocery", cat="DS", extra={"inv_value": 2.07, "tax_code": "12"},
          uncertain={"pack_count": "\"12x198 CO\": 12 pacchi da 198 salviette — interpretazione di CO"}),
        L(1, 15, "169641", "TOWEL ROLL NAT 800'", 1, "CS", "6x800 FT", 6, 800, "FT", 42.05, "CS", 42.05, brand="Array", section="Grocery", cat="DS", extra={"inv_value": 7.01, "tax_code": "12"}),
        L(1, 16, "256463", "RINSE AID DSHMCH CRYSTDRI", 1, "CS", "1x5 GAL", 1, 5, "GAL", 209.49, "CS", 209.49, brand="Array", section="Misc", cat="CP", extra={"inv_value": 209.49, "tax_code": "12"}),
    ],
    "charges": [],
    "printed_totals": [T(1, "Total Cooler Pieces", 197.86), T(1, "Total Grocery Pieces", 596.95),
                       T(1, "Total Miscellaneous Pieces", 209.49), T(1, "Page Total", 1004.30),
                       T(1, "Totals Qty Ship Cooler", 11), T(1, "Totals Qty Ship Grocery", 14), T(1, "Totals Qty Ship Misc", 1)],
    "document_notes": [_G_NOTE, "Le righe con Tax 12 sono tassabili; tasse, fuel charge e totale fattura "
                       "sono sulla pagina 2 mancante."],
})

INVOICES.append({
    "key": "gordon_9040450678",
    "supplier_name": "Gordon Food Service Inc. (Plant City Distribution Ctr)",
    "document_number": "9040450678",
    "document_date": "2026-09-23",
    "date_as_printed": "09/23/2026",
    "pages": [{"render": "Gordon_7fd998cffd9b_p1", "label": "page 1 of 2"},
              {"render": "Gordon_7fd998cffd9b_p2", "label": "page 2 of 2"}],
    "page_marking": "Page 1 of 2, Page 2 of 2",
    "missing_pages": [],
    "lines": [
        L(1, 1, "106632", "ARUGULA WILD", 2, "CS", "2x2 LB", 2, 2, "LB", 17.38, "CS", 34.76, brand="Ready-", section="Cooler", cat="PR", extra={"inv_value": 8.69}),
        L(1, 2, "732478", "BROCCOLI FLORET REG CUT", 1, "CS", "4x3 LB", 4, 3, "LB", 35.29, "CS", 35.29, brand="Ready-", section="Cooler", cat="PR", extra={"inv_value": 8.82}),
        L(1, 3, "306712", "CHEESE MOZZ 3% SHRD FTHR", 1, "CS", "6x5 LB", 6, 5, "LB", 97.62, "CS", 97.62, brand="Grande", section="Cooler", cat="DY", extra={"inv_value": 16.27}),
        L(1, 4, "556528", "JUICE STRAWB LEMND", 3, "CS", "6x12 FOZ", 6, 12, "FL OZ", 11.07, "CS", 33.21, brand="Natali", section="Cooler", cat="BV", extra={"inv_value": 1.85}),
        L(1, 5, "521520", "PARSLEY ITAL FRESH", 1, "CS", "1x1 LB", 1, 1, "LB", 11.32, "CS", 11.32, brand="Markon", section="Cooler", cat="PR", extra={"inv_value": 11.32}),
        L(1, 6, "560715", "PEPPERS RED", 1, "CS", "1x23 LB", 1, 23, "LB", 27.83, "CS", 27.83, brand="Markon", section="Cooler", cat="PR", extra={"inv_value": 27.83}),
        L(1, 7, "152222", "SPRING MIX HERITAGE", 1, "CS", "4x3 LB", 4, 3, "LB", 31.80, "CS", 31.80, brand="Ready-", section="Cooler", cat="PR", extra={"inv_value": 7.95}),
        L(1, 8, "165431", "THYME FRESH", 1, "CS", "1x1 LB", 1, 1, "LB", 12.00, "CS", 12.00, brand="Markon", section="Cooler", cat="PR", extra={"inv_value": 12.00}),
        L(1, 9, "811601", "FLOUR PIZZA \"00\"", 2, "CS", "1x55 LB", 1, 55, "LB", 51.34, "CS", 102.68, brand="Caputo", section="Grocery", cat="GR", extra={"inv_value": 51.34}),
        L(1, 10, "324157", "FLOUR SEMOLINA", 1, "CS", "1x50 LB", 1, 50, "LB", 28.46, "CS", 28.46, brand="Gold M", section="Grocery", cat="GR", extra={"inv_value": 28.46}),
        L(1, 11, "348637", "GLOVE NITRILE LRG PWDFR BLK", 1, "CS", "10x100 CO", 10, 100, "CT", 34.53, "CS", 34.53, brand="Gordon", section="Grocery", cat="DS", extra={"inv_value": 3.45, "tax_code": "12", "spec": "P"},
          notes=["Stampato: \"The above line item includes a promotional discount of $ 27.29 ($27.29/CS)\" — già incluso in 34.53, non è una charge separata"],
          uncertain={"pack_count": "\"10x100 CO\": 10 scatole da 100 guanti — interpretazione di CO"}),
        L(1, 12, "579590", "SODA BTL COKE MEX", 1, "CS", "24x12 FOZ", 24, 12, "FL OZ", 38.39, "CS", 38.39, brand="Coca-C", section="Grocery", cat="BV", extra={"inv_value": 1.60, "tax_code": "12"}),
        L(1, 13, "358914", "TOMATO PLUM I/JCE", 5, "CS", "6x10 CSZ", 6, 10, "CSZ", 37.17, "CS", 185.85, brand="Alta C", section="Grocery", cat="GR", extra={"inv_value": 6.20},
          uncertain={"piece_content_value": "\"10 CSZ\" = formato lattina #10, non un peso o volume: il peso netto per lattina non è stampato"}),
        L(1, 14, "169641", "TOWEL ROLL NAT 800'", 2, "CS", "6x800 FT", 6, 800, "FT", 42.07, "CS", 84.14, brand="Array", section="Grocery", cat="DS", extra={"inv_value": 7.01, "tax_code": "12"}),
        L(1, 15, "260226", "DETRGNT POT & PAN ORIG", 1, "CS", "4x1 GAL", 4, 1, "GAL", 78.81, "CS", 78.81, brand="Dawn P", section="Misc", cat="CP", extra={"inv_value": 19.70, "tax_code": "12"}),
    ],
    "charges": [C(2, "Fuel Charge (Misc)", 11.25),
                C(2, "Tax - 6.00", 14.15, kind="TAX"), C(2, "Tax - 0.50", 1.18, kind="TAX")],
    "printed_totals": [T(1, "Total Cooler Pieces", 283.83), T(1, "Total Grocery Pieces", 474.05),
                       T(1, "Total Miscellaneous Pieces", 78.81), T(1, "Page Total", 836.69),
                       T(1, "Totals Qty Ship Cooler", 11), T(1, "Totals Qty Ship Grocery", 12), T(1, "Totals Qty Ship Misc", 1),
                       T(2, "Product Total", 836.69), T(2, "Misc", 11.25), T(2, "SubTotal", 847.94),
                       T(2, "Invoice Total", 863.27), T(2, "Category recap Total CS", 24),
                       T(2, "Recap PR subtotal", 153.00), T(2, "Recap GR subtotal", 316.99), T(2, "Recap DY subtotal", 97.62),
                       T(2, "Recap DS subtotal", 118.67), T(2, "Recap CP subtotal", 78.81), T(2, "Recap BV subtotal", 71.60),
                       T(2, "Recap DS tax", 7.71), T(2, "Recap CP tax", 5.13), T(2, "Recap BV tax", 2.49), T(2, "Recap tax total", 15.33)],
    "document_notes": [_G_NOTE, "Pagina 2: \"You saved $27.29 today with GFS Promotions\" (= la promozione già inclusa nella riga 11). "
                       "Due Date 09/25/2026, Pay This Amount $863.27."],
})

# ---------------------------------------------------------------------------------------------- Ben E. Keith
_K_NOTE = ("Quantità nella colonna Cases (CS) o, per una cassa aperta, nella colonna Pkgs (PKG); Unit Price è per quell'unità, "
           "salvo le righe a peso variabile (\"Total Weight …#\"). La colonna \"*\" è stampata senza "
           "legenda. Totali di sezione, fuel charge e riepilogo TAX per sezione sono a pagina 1; il totale fattura "
           "è a pagina 2.")
_K_OZ = {"piece_content_unit": "\"OZ\" come stampato: non è indicato se once di peso o fluide (scheda prodotto)"}


def K(page, n, code, brand, desc, cases, pkgs, pack, count, piece, unit, price, amount, *, section, mfg, location,
      weight=None, uncertain=None, notes=None, basis=None):
    qty, purchase_unit = (cases, "CS") if cases is not None else (pkgs, "PKG")
    extra = {"location": location, "manufacturer_code": mfg}
    unc = dict(uncertain or {})
    if purchase_unit == "PKG":
        unc.setdefault("unit_price_basis", "cassa aperta: prezzo per confezione (colonna PKG), base non stampata")
    return L(page, n, code, desc, qty, purchase_unit, pack, count, piece, unit, price, basis or purchase_unit, amount,
             brand=brand, section=section, weight=weight, weight_unit="LB" if weight else None, extra=extra,
             uncertain=unc, notes=notes)


_BEEF_UNC = {"unit_price_basis": "base per LB non stampata: dedotta da \"Total Weight …#\" e da peso × prezzo = importo"}

INVOICES.append({
    "key": "keith_57978854",
    "supplier_name": "Ben E. Keith Co.",
    "document_number": "57978854",
    "document_date": "2026-08-26",
    "date_as_printed": "08/26/2026",
    "pages": [{"render": "Keith_792a82fc0b00_p1", "label": "page 1 of 2", "rotated": 90}],
    "page_marking": "Page 1 of 2; Total Qty This Invoice / Tax / Total Invoice = \"Continued\"",
    "missing_pages": ["Pagina 2 di 2 (tax, Total Invoice) assente in tutti i file"],
    "lines": [
        K(1, 1, "170274", "MARJAC", "Chicken Breast 8oz Butterfly", 2, None, "2/10 LB", 2, 10, "LB", 80.00, 160.00, section="Cooler", mfg="64840", location="801721"),
        K(1, 7, "556283", "DAIRYSTR", "Cream Heavy Whipping 40%", 1, None, "12/32 OZ", 12, 32, "OZ", 60.15, 60.15, section="Cooler", mfg="1003196", location="813211", uncertain=_K_OZ, notes=["marcata \"*\""]),
        K(1, 6, "302845", "PACKER", "Egg Shell Large Grade Aa", 3, None, "1/15 DZN", 1, 15, "DZN", 24.90, 74.70, section="Cooler", mfg="316780", location="838611"),
        K(1, 9, "697002", "FLEISCHM", "Yeast Fresh Compressed", None, 1, "24/1 LB", 24, 1, "LB", 2.00, 2.00, section="Cooler", mfg="2117", location="816331", notes=["\"*\" marcata; 1 confezione di una cassa 24/1 LB"]),
        K(1, 4, "213888", "ESSNTIAL", "Box Pizza 12 In Eleo Kk", 1, None, "1/50 CT", 1, 50, "CT", 23.30, 23.30, section="Dry", mfg="784505", location="175512"),
        K(1, 8, "660356", "ROLAND", "Glaze Balsamic", 1, None, "6/12.9 OZ", 6, 12.9, "OZ", 39.21, 39.21, section="Dry", mfg="70442", location="191556", uncertain=_K_OZ),
        K(1, 5, "301638", "MOTTS", "Juice Apple Bottle 100%", 1, None, "24/10 OZ", 24, 10, "OZ", 21.18, 21.18, section="Dry", mfg="91130", location="195721", uncertain=_K_OZ),
        K(1, 2, "202991", "COCACOLA", "Soda Coke Diet Slim Can", 1, None, "24/12 OZ", 24, 12, "OZ", 21.00, 21.00, section="Dry", mfg="154818", location="170812", uncertain=_K_OZ),
        K(1, 3, "202992", "COKEZERO", "Soda Coke Zero Slim Can", 1, None, "24/12 OZ", 24, 12, "OZ", 21.00, 21.00, section="Dry", mfg="155852", location="192811", uncertain=_K_OZ),
    ],
    "charges": [C(1, "Fuel Charge $", 8.75)],
    "printed_totals": [T(1, "Section Total -Cooler", 296.85), T(1, "Section Total -Dry", 125.69),
                       T(1, "Section Total -Cooler cases", 6), T(1, "Section Total -Cooler pkgs", 1),
                       T(1, "Section Total -Dry cases", 5), T(1, "Total Qty This Page cases", 11),
                       T(1, "Total Qty This Page pkgs", 1), T(1, "Recap TAX Cooler", 0.00), T(1, "Recap TAX Dry", 0.00)],
    "document_notes": [_K_NOTE, "Order No 02995407, Customer 00880244, Terms NET 07."],
})

INVOICES.append({
    "key": "keith_58049702",
    "supplier_name": "Ben E. Keith Co.",
    "document_number": "58049702",
    "document_date": "2026-09-02",
    "date_as_printed": "09/02/2026",
    "pages": [{"render": "Keith_57d864d7605a_p2", "label": "page 1 of 2 (file page 2)", "rotated": 270}],
    "page_marking": "Page 1 of 2; totals \"Continued\"",
    "missing_pages": ["Pagina 2 di 2 (tax, Total Invoice) assente in tutti i file"],
    "lines": [
        K(1, 13, "506601", "IBP", "Beef Ground Fine 80/20", 1, None, "4/10 LB", 4, 10, "LB", 4.29, 175.89, section="Cooler", mfg="D0231BHK", location="806111", weight=41.00, basis="LB", uncertain=_BEEF_UNC,
          notes=["Stampato sotto la riga: \"41.00#\" e \"Total Weight 41.00#\""]),
        K(1, 1, "098016", "PACKER", "Carrot Jumbo", 1, None, "1/25 LB", 1, 25, "LB", 20.80, 20.80, section="Cooler", mfg="15510", location="833421"),
        K(1, 5, "170274", "MARJAC", "Chicken Breast 8oz Butterfly", 2, None, "2/10 LB", 2, 10, "LB", 80.00, 160.00, section="Cooler", mfg="64840", location="801721"),
        K(1, 14, "556283", "DAIRYSTR", "Cream Heavy Whipping 40%", 1, None, "12/32 OZ", 12, 32, "OZ", 59.90, 59.90, section="Cooler", mfg="1003196", location="813211", uncertain=_K_OZ, notes=["marcata \"*\""]),
        K(1, 12, "302845", "PACKER", "Egg Shell Large Grade Aa", 3, None, "1/15 DZN", 1, 15, "DZN", 18.62, 55.86, section="Cooler", mfg="316780", location="838611"),
        K(1, 3, "151009", "MRKN/FC", "Onion Red Jumbo Us#1", 1, None, "1/25 LB", 1, 25, "LB", 28.50, 28.50, section="Cooler", mfg="95500", location="901812"),
        K(1, 4, "170044", "MRKN/FC", "Potato Russet 40 Ct Ida", 1, None, "1/50 LB", 1, 50, "LB", 39.22, 39.22, section="Cooler", mfg="92410", location="832511"),
        K(1, 2, "109343", "PACKER", "Tomato Heirloom Cherry Mixed", 1, None, "12/10 OZ", 12, 10, "OZ", 29.70, 29.70, section="Cooler", mfg="13636", location="901122", uncertain=_K_OZ),
        K(1, 17, "697002", "FLEISCHM", "Yeast Fresh Compressed", None, 2, "24/1 LB", 24, 1, "LB", 2.00, 4.00, section="Cooler", mfg="2117", location="816331", notes=["\"*\" marcata; 2 confezioni di una cassa 24/1 LB"]),
        K(1, 6, "198057", "HOLLYS", "Box Pizza 8in Plain", 1, None, "1/50 CT", 1, 50, "CT", 16.92, 16.92, section="Dry", mfg="9083511", location="182811"),
        K(1, 11, "302249", "VIGO", "Bread Crumbs Italian", 1, None, "2/5 LB", 2, 5, "LB", 16.97, 16.97, section="Dry", mfg="1317", location="136721"),
        K(1, 15, "620161", "DOLE", "Juice Pineapple 100%unswtnd", 2, None, "48/6 OZ", 48, 6, "OZ", 37.51, 75.02, section="Dry", mfg="00914", location="172311", uncertain=_K_OZ),
        K(1, 10, "302013", "RON SON", "Olive Ripe Medium Black Pitted", 1, None, "6/#10 CAN", 6, 10, "#10 CAN", 57.10, 57.10, section="Dry", mfg="4037RS", location="164922",
          uncertain={"piece_content_value": "\"#10 CAN\" è un formato lattina: peso netto o sgocciolato non stampato"}),
        K(1, 8, "202991", "COCACOLA", "Soda Coke Diet Slim Can", 2, None, "24/12 OZ", 24, 12, "OZ", 21.00, 42.00, section="Dry", mfg="154818", location="170812", uncertain=_K_OZ),
        K(1, 9, "202992", "COKEZERO", "Soda Coke Zero Slim Can", 2, None, "24/12 OZ", 24, 12, "OZ", 21.00, 42.00, section="Dry", mfg="155852", location="192811", uncertain=_K_OZ),
        K(1, 16, "650491", "HUNTS", "Tomato Paste Fancy", 1, None, "24/12 OZ", 24, 12, "OZ", 59.30, 59.30, section="Dry", mfg="2700038811", location="103021"),
        K(1, 7, "198521", "ELLINGTN", "Bacon Applewood Layout 13/17", 1, None, "1/15 LB", 1, 15, "LB", 68.52, 68.52, section="Frozen", mfg="02026", location="437211"),
    ],
    "charges": [C(1, "Fuel Charge $", 8.75)],
    "printed_totals": [T(1, "Section Total -Cooler", 573.87), T(1, "Section Total -Dry", 309.31),
                       T(1, "Section Total -Frozen", 68.52), T(1, "Section Total -Cooler cases", 11),
                       T(1, "Section Total -Cooler pkgs", 2), T(1, "Section Total -Dry cases", 10),
                       T(1, "Section Total -Frozen cases", 1), T(1, "Total Qty This Page cases", 22),
                       T(1, "Total Qty This Page pkgs", 2)],
    "document_notes": [_K_NOTE, "Questa fattura è la SECONDA pagina del file Keith/2026-10-10_093150.pdf; la prima pagina "
                       "di quel file è un'altra fattura (58188774). Order No 03088690."],
})

INVOICES.append({
    "key": "keith_58188774",
    "supplier_name": "Ben E. Keith Co.",
    "document_number": "58188774",
    "document_date": "2026-09-16",
    "date_as_printed": "09/16/2026",
    "pages": [{"render": "Keith_57d864d7605a_p1", "label": "page 1 of 2 (file page 1)", "rotated": 270}],
    "page_marking": "Page 1 of 2; totals \"Continued\"",
    "missing_pages": ["Pagina 2 di 2 (tax, Total Invoice) assente in tutti i file"],
    "lines": [
        K(1, 1, "098016", "PACKER", "Carrot Jumbo", 1, None, "1/25 LB", 1, 25, "LB", 20.80, 20.80, section="Cooler", mfg="15510", location="833421"),
        K(1, 13, "762124", "GRANDE", "Cheese Ricotta Sopraffina", 1, None, "6/3 LB", 6, 3, "LB", 46.07, 46.07, section="Cooler", mfg="00139", location="825211", notes=["marcata \"*\""]),
        K(1, 10, "556283", "DAIRYSTR", "Cream Heavy Whipping 40%", 1, None, "12/32 OZ", 12, 32, "OZ", 59.90, 59.90, section="Cooler", mfg="1003196", location="813211", uncertain=_K_OZ, notes=["marcata \"*\""]),
        K(1, 9, "302845", "PACKER", "Egg Shell Large Grade Aa", 2, None, "1/15 DZN", 1, 15, "DZN", 16.94, 33.88, section="Cooler", mfg="316780", location="838611"),
        K(1, 4, "151009", "MRKN/FC", "Onion Red Jumbo Us#1", 1, None, "1/25 LB", 1, 25, "LB", 28.50, 28.50, section="Cooler", mfg="95500", location="901812"),
        K(1, 2, "109343", "PACKER", "Tomato Heirloom Cherry Mixed", 1, None, "12/10 OZ", 12, 10, "OZ", 29.70, 29.70, section="Cooler", mfg="13636", location="901122", uncertain=_K_OZ),
        K(1, 12, "697002", "FLEISCHM", "Yeast Fresh Compressed", None, 2, "24/1 LB", 24, 1, "LB", 2.00, 4.00, section="Cooler", mfg="2117", location="816331", notes=["\"*\" marcata; 2 confezioni di una cassa 24/1 LB"]),
        K(1, 7, "213888", "ESSNTIAL", "Box Pizza 12 In Eleo Kk", 1, None, "1/50 CT", 1, 50, "CT", 23.30, 23.30, section="Dry", mfg="784505", location="175512"),
        K(1, 8, "302249", "VIGO", "Bread Crumbs Italian", 1, None, "2/5 LB", 2, 5, "LB", 16.97, 16.97, section="Dry", mfg="1317", location="136721"),
        K(1, 11, "660356", "ROLAND", "Glaze Balsamic", 1, None, "6/12.9 OZ", 6, 12.9, "OZ", 39.21, 39.21, section="Dry", mfg="70442", location="191556", uncertain=_K_OZ),
        K(1, 3, "112409", "DOMINO", "Sugar Pure Cane", 1, None, "10/4 LB", 10, 4, "LB", 37.64, 37.64, section="Dry", mfg="400368", location="173212"),
        K(1, 6, "198521", "ELLINGTN", "Bacon Applewood Layout 13/17", 1, None, "1/15 LB", 1, 15, "LB", 68.52, 68.52, section="Frozen", mfg="02026", location="437211"),
    ],
    "not_shipped": [{"page": 1, "source_line_number": 5, "supplier_item_code": "170274",
                     "raw_description": "Chicken Breast 8oz Butterfly", "pack_size": "2/10 LB",
                     "printed": "Cases OUT, Unit Price 0.00, Amount *-OUT-*"}],
    "charges": [C(1, "Fuel Charge $", 8.75)],
    "printed_totals": [T(1, "Section Total -Cooler", 222.85), T(1, "Section Total -Dry", 117.12),
                       T(1, "Section Total -Frozen", 68.52), T(1, "Section Total -Cooler cases", 7),
                       T(1, "Section Total -Cooler pkgs", 2), T(1, "Section Total -Dry cases", 4),
                       T(1, "Section Total -Frozen cases", 1), T(1, "Total Qty This Page cases", 12),
                       T(1, "Total Qty This Page pkgs", 2)],
    "document_notes": [_K_NOTE, "Prima pagina del file Keith/2026-10-10_093150.pdf; la seconda pagina del file è la fattura "
                       "58049702. Order No 03228269, Driver 166."],
})

INVOICES.append({
    "key": "keith_58263737",
    "supplier_name": "Ben E. Keith Co.",
    "document_number": "58263737",
    "document_date": "2026-09-23",
    "date_as_printed": "09/23/2026",
    "pages": [{"render": "Keith_ba80244b0f5b_p1", "label": "page 1 of 2", "rotated": 270},
              {"render": "Keith_ba80244b0f5b_p2", "label": "page 2 of 2", "rotated": 270}],
    "page_marking": "Page 1 of 2, Page 2 of 2",
    "missing_pages": [],
    "lines": [
        K(1, 6, "506601", "IBP", "Beef Ground Fine 80/20", 1, None, "4/10 LB", 4, 10, "LB", 4.07, 160.77, section="Cooler", mfg="D0231BHK", location="806111", weight=39.50, basis="LB", uncertain=_BEEF_UNC,
          notes=["Stampato sotto la riga: \"39.50#\" e \"Total Weight 39.50#\""]),
        K(1, 10, "762124", "GRANDE", "Cheese Ricotta Sopraffina", 1, None, "6/3 LB", 6, 3, "LB", 47.00, 47.00, section="Cooler", mfg="00139", location="825211", notes=["marcata \"*\""]),
        K(1, 3, "170274", "MARJAC", "Chicken Breast 8oz Butterfly", 2, None, "2/10 LB", 2, 10, "LB", 81.00, 162.00, section="Cooler", mfg="64840", location="801721"),
        K(1, 7, "556283", "DAIRYSTR", "Cream Heavy Whipping 40%", 1, None, "12/32 OZ", 12, 32, "OZ", 59.90, 59.90, section="Cooler", mfg="1003196", location="813211", uncertain=_K_OZ, notes=["marcata \"*\""]),
        K(1, 5, "302845", "PACKER", "Egg Shell Large Grade Aa", 1, None, "1/15 DZN", 1, 15, "DZN", 17.00, 17.00, section="Cooler", mfg="316780", location="838611"),
        K(1, 2, "170044", "MRKN/FC", "Potato Russet 40 Ct Ida", 1, None, "1/50 LB", 1, 50, "LB", 42.00, 42.00, section="Cooler", mfg="92410", location="832511"),
        K(1, 1, "109343", "PACKER", "Tomato Heirloom Cherry Mixed", 1, None, "12/10 OZ", 12, 10, "OZ", 28.00, 28.00, section="Cooler", mfg="13636", location="901122", uncertain=_K_OZ),
        K(1, 9, "697002", "FLEISCHM", "Yeast Fresh Compressed", None, 2, "24/1 LB", 24, 1, "LB", 2.40, 4.80, section="Cooler", mfg="2117", location="816331", notes=["\"*\" marcata; 2 confezioni di una cassa 24/1 LB"]),
        K(1, 8, "676182", "MORTON", "Salt Kosher Coarse Box", 1, None, "12/3 LB", 12, 3, "LB", 40.55, 40.55, section="Dry", mfg="14710", location="194455"),
        K(1, 4, "202992", "COKEZERO", "Soda Coke Zero Slim Can", 1, None, "24/12 OZ", 24, 12, "OZ", 21.00, 21.00, section="Dry", mfg="155852", location="192811", uncertain=_K_OZ),
    ],
    "charges": [C(1, "Fuel Charge $", 8.75), C(2, "Tax", 0.00, kind="TAX")],
    "printed_totals": [T(1, "Section Total -Cooler", 521.47), T(1, "Section Total -Dry", 61.55),
                       T(1, "Section Total -Cooler cases", 8), T(1, "Section Total -Cooler pkgs", 2),
                       T(1, "Section Total -Dry cases", 2), T(1, "Total Qty This Page cases", 10),
                       T(1, "Total Qty This Page pkgs", 2), T(2, "Total Qty This Invoice cases", 10),
                       T(2, "Total Qty This Invoice pkgs", 2), T(2, "Total Invoice", 591.77)],
    "document_notes": [_K_NOTE, "Order No 03301552. La pagina 2 riporta solo i totali (Tax 0.00, Total Invoice 591.77) e "
                       "\"Shipped From: 5201 N.E. 40th Terrace, Gainesville, FL\"."],
})

# ---------------------------------------------------------------------------------------------- Prime Line
_P_NOTE = ("Quantity + UOM (CASE / PC. / JAR) è ciò che è stato acquistato; \"Billing Units\" è la quantità a cui si applica lo Unit Price"
           ": casse, oppure libbre quando il prezzo è stampato con \"lb\" (il peso è ripetuto anche sotto la "
           "descrizione). Pack Size come stampato (oz sulle bevande = once fluide, per i 500ml / 1.5L nel nome).")


def P(page, code, qty, uom, desc, pack, count, piece, unit, billing, price, per_lb, amount, *, section, uncertain=None,
      notes=None):
    basis = "LB" if per_lb else {"CASE": "CS", "PC.": "PC", "JAR": "JAR"}[uom]
    weight = billing if per_lb else None
    unc = dict(uncertain or {})
    if not per_lb:
        unc.setdefault("unit_price_basis", f"base non stampata: Billing Units {billing} = quantità in {uom}")
    return L(page, None, code, desc, qty, {"CASE": "CS", "PC.": "PC", "JAR": "JAR"}[uom], pack, count, piece, unit,
             price, basis, amount, section=section, weight=weight, weight_unit="LB" if weight else None,
             extra={"billing_units": billing}, uncertain=unc, notes=notes)


_P_BEV = {"piece_content_unit": "\"oz\" letto come once FLUIDE perché il nome dice 500ml / 1.5L (16.9 fl oz = 500 ml)"}

INVOICES.append({
    "key": "primeline_1648163",
    "supplier_name": "Prime Line Distributors Inc. (Orlando, FL)",
    "document_number": "1648163",
    "document_date": "2026-09-03",
    "date_as_printed": "09/03/26 (Order Date 09/02/26)",
    "pages": [{"render": "Primeline_ec6e782d8305_p1", "label": "page 1 of 1"}],
    "page_marking": "Page No: 1 of 1",
    "missing_pages": [],
    "lines": [
        P(1, "BM40", 6, "CASE", "SAN BENEDETTO SPARKLING GLASS 500ml", "20/16.9 oz", 20, 16.9, "FL OZ", 6, 34.99, False, 209.94, section="DRY ITEMS", uncertain=_P_BEV),
        P(1, "BM41", 4, "CASE", "SAN BENEDETTO NATURAL GLASS 500ml", "20/16.9 oz", 20, 16.9, "FL OZ", 4, 34.99, False, 139.96, section="DRY ITEMS", uncertain=_P_BEV),
        P(1, "BM43", 6, "CASE", "SAN BENEDETTO NATURAL PET 1.5L", "6/50.7 oz", 6, 50.7, "FL OZ", 6, 14.50, False, 87.00, section="DRY ITEMS", uncertain=_P_BEV),
        P(1, "BI08", 1, "CASE", "VICENZI LADYFINGERS VICENZOVO 400gr", "6/14 oz.", 6, 14, "OZ", 1, 33.00, False, 33.00, section="DRY ITEMS"),
        P(1, "TF41", 1, "JAR", "SAVINI TRUFFLE GATHERER SAUCE 500gr", "17.6 oz.", 1, 17.6, "OZ", 1, 35.50, False, 35.50, section="DRY ITEMS"),
        P(1, "MU15", 1, "CASE", "PORCINI FROZEN 1st QUALITY", "6/2.2 lbs.", 6, 2.2, "LB", 13.23, 17.49, True, 231.39, section="FROZEN ITEMS",
          notes=["peso 13.23 stampato solo in Billing Units (non ripetuto sotto la descrizione)"]),
        P(1, "CI57", 1, "CASE", "PECORINO w/TRUFFLES BOSKETTO", "6/1.2 lbs.", 6, 1.2, "LB", 8.73, 19.50, True, 170.24, section="REFRIGERATED ITEMS"),
        P(1, "SS34", 1, "CASE", "PESTO SAUCE MAGRINI ITALY BULK", "2/4.6 lbs.", 2, 4.6, "LB", 1, 108.00, False, 108.00, section="REFRIGERATED ITEMS"),
        P(1, "MP33", 1, "PC.", "BIELLESE GUANCIALE", "4 lbs.", 1, 4, "LB", 6.10, 22.49, True, 137.19, section="REFRIGERATED ITEMS",
          uncertain={"piece_content_value": "\"4 lbs.\" nominale; il pezzo pesava 6.10 lb"}),
        P(1, "CI17", 3, "CASE", "MOZZARELLA DI BUFALA 250 gr. ROSE", "12/8.8 oz.", 12, 8.8, "OZ", 3, 117.00, False, 351.00, section="REFRIGERATED ITEMS"),
        P(1, "MP01", 1, "CASE", "PROSCIUTTO DI PARMA DOP BERETTA", "16 lbs.", None, 16, "LB", 18.23, 13.50, True, 246.11, section="REFRIGERATED ITEMS",
          uncertain={"pack_count": "\"16 lbs.\" senza numero di pezzi: pezzi per cassa non stampati; 16 lb può riferirsi alla cassa o al pezzo"}),
        P(1, "CI28P", 1, "CASE", "GRANA PADANO 18 MONTH AGED QUARTER", "20 lbs.", None, 20, "LB", 19.94, 11.49, True, 229.11, section="REFRIGERATED ITEMS",
          uncertain={"pack_count": "\"20 lbs.\" senza numero di pezzi: quarti per cassa non stampati"}),
        P(1, "CI19", 1, "CASE", "MASCARPONE GALBANI ITALY 500gr.", "24/17.6 oz", 24, 17.6, "OZ", 1, 234.00, False, 234.00, section="REFRIGERATED ITEMS"),
    ],
    "charges": [C(1, "SURCHARGE", 8.50), C(1, "TAX", 0.00, kind="TAX")],
    "printed_totals": [T(1, "SUBTOTAL", 2212.44), T(1, "TOTAL", 2220.94)],
    "document_notes": [_P_NOTE, "Payment Due by 09/10/26; Terms ACH-NET 7 DAYS; Account 6287; ricevuta firmata."],
})

INVOICES.append({
    "key": "primeline_1652976",
    "supplier_name": "Prime Line Distributors Inc. (Orlando, FL)",
    "document_number": "1652976",
    "document_date": "2026-09-24",
    "date_as_printed": "09/24/26 (Order Date 09/23/26)",
    "pages": [{"render": "Primeline_042e90f8cf6f_p1", "label": "page 1 of 1"}],
    "page_marking": "Page No: 1 of 1",
    "missing_pages": [],
    "lines": [
        P(1, "BM40", 3, "CASE", "SAN BENEDETTO SPARKLING GLASS 500ml", "20/16.9 oz", 20, 16.9, "FL OZ", 3, 34.99, False, 104.97, section="DRY ITEMS", uncertain=_P_BEV),
        P(1, "BM41", 2, "CASE", "SAN BENEDETTO NATURAL GLASS 500ml", "20/16.9 oz", 20, 16.9, "FL OZ", 2, 34.99, False, 69.98, section="DRY ITEMS", uncertain=_P_BEV),
        P(1, "BM43", 7, "CASE", "SAN BENEDETTO NATURAL PET 1.5L", "6/50.7 oz", 6, 50.7, "FL OZ", 7, 14.50, False, 101.50, section="DRY ITEMS", uncertain=_P_BEV),
        P(1, "OL17", 1, "CASE", "TAGGIASCA OLIVES PITTED IN OIL 950g", "6/34 oz.", 6, 34, "OZ", 1, 165.00, False, 165.00, section="DRY ITEMS",
          notes=["il nome dice 950g, la confezione 34 oz (≈ 964 g): entrambi stampati, non conciliati"]),
        P(1, "MP30", 1, "CASE", "SPECK PROSCIUTTO ALTO ADIGE IGP", "2/5 lbs.", 2, 5, "LB", 10.36, 11.99, True, 124.22, section="REFRIGERATED ITEMS"),
        P(1, "CI51P", 1, "PC.", "PECORINO TOSCANO w/RED PEPPER", "2.8 lbs.", 1, 2.8, "LB", 2.92, 15.50, True, 45.26, section="REFRIGERATED ITEMS"),
        P(1, "SS34", 1, "CASE", "PESTO SAUCE MAGRINI ITALY BULK", "2/4.6 lbs.", 2, 4.6, "LB", 1, 108.00, False, 108.00, section="REFRIGERATED ITEMS"),
        P(1, "MP33", 1, "PC.", "BIELLESE GUANCIALE", "4 lbs.", 1, 4, "LB", 4.80, 22.49, True, 107.95, section="REFRIGERATED ITEMS",
          uncertain={"piece_content_value": "\"4 lbs.\" nominale; il pezzo pesava 4.80 lb"}),
        P(1, "CI17", 3, "CASE", "MOZZARELLA DI BUFALA 250 gr. ROSE", "12/8.8 oz.", 12, 8.8, "OZ", 3, 117.00, False, 351.00, section="REFRIGERATED ITEMS"),
        P(1, "CI28P", 1, "CASE", "GRANA PADANO 18 MONTH AGED QUARTER", "20 lbs.", None, 20, "LB", 21.04, 11.49, True, 241.75, section="REFRIGERATED ITEMS",
          uncertain={"pack_count": "\"20 lbs.\" senza numero di pezzi: quarti per cassa non stampati"}),
        P(1, "CI19", 1, "CASE", "MASCARPONE GALBANI ITALY 500gr.", "24/17.6 oz", 24, 17.6, "OZ", 1, 234.00, False, 234.00, section="REFRIGERATED ITEMS"),
    ],
    "charges": [C(1, "SURCHARGE", 8.50), C(1, "TAX", 0.00, kind="TAX")],
    "printed_totals": [T(1, "SUBTOTAL", 1653.63), T(1, "TOTAL", 1662.13)],
    "document_notes": [_P_NOTE, "Payment Due by 10/01/26. Copia rosa spiegazzata: leggibile, nessun valore coperto."],
})

# ---------------------------------------------------------------------------------------------- Samuels Seafood
_S_W = {"actual_weight_value": "QTY SHIPPED è in libbre (colonna UNIT LB/LBS): la quantità È il peso spedito"}
INVOICES.append({
    "key": "samuels_532747",
    "supplier_name": "Samuels Seafood Co. - South Coast (Samuels & Son)",
    "document_number": "532747",
    "document_date": "2026-09-26",
    "date_as_printed": "09/26/26",
    "pages": [{"render": "Samuel_941cf27bada7_p1", "label": "page 1"}],
    "page_marking": "PAGE 1 (no \"of N\"); BALANCE printed on the page",
    "missing_pages": [],
    "lines": [
        L(1, None, None, "BRONZINO 1.25-1.5 S & G / 6 EA 600-800 (WW)", 8.12, "LB", "6 EA", 6, None, None, 10.240, "LB", 83.15,
          weight=8.12, weight_unit="LB", extra={"origin": "F/TUR", "price_flag": "*"}, uncertain=dict(_S_W, piece_content_value="\"1.25-1.5\" and \"600-800\" sono intervalli di pezzatura (lb per pesce / grammi?) senza unità stampata: non un contenuto nominale")),
        L(1, None, None, "SALMON H/C PORT 8oz C/C SQ/BL S/OFF PBO", 7.80, "LB", None, None, 8, "OZ", 15.990, "LB", 124.72,
          weight=7.80, weight_unit="LB", extra={"origin": "F/FO", "price_flag": "*", "unit_as_printed": "LBS"},
          uncertain=dict(_S_W, piece_content_value="\"8oz\" è la porzione indicata nella descrizione, non un contenuto della confezione")),
        L(1, None, None, "SHRIMP U/12 BLUES 6/5 PRIME SELECTA BLUES!17", 10.00, "LB", "6/5", 6, 5, None, 14.990, "LB", 149.90,
          weight=10.00, weight_unit="LB", extra={"origin": "W/MEX", "price_flag": "*"},
          uncertain=dict(_S_W, piece_content_unit="\"6/5\" senza unità (probabilmente 6 × 5 lb); sono state vendute 10 lb, cioè parte di una cassa")),
    ],
    "charges": [C(1, "DELIVERY CHARGE (1.00 EA × 2.990)", 2.99)],
    "printed_totals": [T(1, "BALANCE", 360.76)],
    "document_notes": ["Nessun codice articolo stampato. \"*\" davanti a ogni prezzo unitario, senza legenda. Order 463789, customer "
                       "ROM90, terms VISA NET1 D. Scritto a mano \"351\" (?) in FINAL CHECKER, non usato."],
})

# ---------------------------------------------------------------------------------------------- Trader Joe's
INVOICES.append({
    "key": "traderjoes_2026-09-04_43964",
    "supplier_name": "Trader Joe's #0765 (Winter Park, FL)",
    "document_number": "TRANS 43964 (store 0765, till 1)",
    "document_date": "2026-09-04",
    "date_as_printed": "09-04-2026 10:16",
    "pages": [{"render": "TraderJoes_380088afca76_p1", "label": "receipt"}],
    "page_marking": "till receipt",
    "missing_pages": [],
    "lines": [
        L(1, None, None, "LEEK? TRIMMED 2CT", 3, "EA", "2CT", 2, None, None, 2.99, "EA", 8.97,
          uncertain={"raw_description": "stampa termica sbiadita: \"LEEK\" in parte illeggibile", "unit_price_basis": "\"3 @ $2 99\": prezzo per articolo, base non nominata"}),
        L(1, None, None, "R-HERB MINT ORGANIC 1 OZ", 1, "EA", "1 OZ", 1, 1, "OZ", 1.99, "EA", 1.99,
          uncertain={"quantity": "nessuna quantità stampata: un articolo per riga stampata"}),
        L(1, None, None, "R-HERB ROSEMARY ORG 1 OZ", 1, "EA", "1 OZ", 1, 1, "OZ", 1.99, "EA", 1.99,
          uncertain={"quantity": "nessuna quantità stampata: un articolo per riga stampata"}),
        L(1, None, None, "HERB BASI? ORGANIC 2.5 O", 6, "EA", "2.5 O", 1, 2.5, "OZ", 2.99, "EA", 17.94,
          uncertain={"raw_description": "sbiadito: \"BASIL\" in parte illeggibile", "piece_content_unit": "stampato \"2.5 O\" (troncato): OZ per analogia con le altre righe"}),
    ],
    "charges": [],
    "printed_totals": [T(1, "Items in Transaction", 11), T(1, "Balance to pay", 30.89), T(1, "Visa Debit", 30.89)],
    "document_notes": ["Scontrino di cassa, non fattura: nessun codice articolo; il numero di transazione sostituisce il numero "
                       "fattura. Nessuna riga di tassa stampata. Numero di carta mascherato sullo scontrino e non registrato qui."],
})

INVOICES.append({
    "key": "traderjoes_2026-09-18_69793",
    "supplier_name": "Trader Joe's #0765 (Winter Park, FL)",
    "document_number": "TRANS 69793 (store 0765, till 3)",
    "document_date": "2026-09-18",
    "date_as_printed": "09-18-2026 10:00",
    "pages": [{"render": "TraderJoes_59fc4ff13d62_p1", "label": "receipt"}],
    "page_marking": "till receipt",
    "missing_pages": [],
    "lines": (
        [L(1, None, None, "T HOLD THE CONE! STRAWBERR", 1, "EA", None, None, None, None, 3.99, "EA", 3.99,
           extra={"taxable_flag": "T"}, uncertain={"quantity": "un articolo per riga stampata"}) for _ in range(2)]
        + [L(1, None, None, "T HOLD THE CONE! CHOC CHIP", 1, "EA", None, None, None, None, 3.99, "EA", 3.99,
             extra={"taxable_flag": "T"}, uncertain={"quantity": "un articolo per riga stampata"}) for _ in range(2)]
        + [L(1, None, None, "HERB BASIL ORGANIC 2.5 0", 1, "EA", "2.5 O", 1, 2.5, "OZ", 2.99, "EA", 2.99,
             uncertain={"quantity": "un articolo per riga stampata", "piece_content_unit": "stampato \"2.5 0\" (troncato): OZ per analogia con le altre righe"}) for _ in range(6)]
        + [L(1, None, None, "R-HERB ROSEMARY ORG 1 OZ", 1, "EA", "1 OZ", 1, 1, "OZ", 1.99, "EA", 1.99, uncertain={"quantity": "un articolo per riga stampata"}),
           L(1, None, None, "R-HERB MINT ORGANIC 1 OZ", 1, "EA", "1 OZ", 1, 1, "OZ", 1.99, "EA", 1.99, uncertain={"quantity": "un articolo per riga stampata"})]),
    "charges": [C(1, "Tax: $15.96 @ 6.5%", 1.04, kind="TAX")],
    "printed_totals": [T(1, "Items in Transaction", 12), T(1, "Balance to pay", 38.92), T(1, "TOTAL PURCHASE", 38.92),
                       T(1, "Tax base", 15.96)],
    "document_notes": ["Scontrino di cassa: una riga stampata per articolo (12 righe). \"T\" davanti a HOLD THE CONE! indica gli "
                       "articoli tassabili (imponibile $15.96 = 4 × 3.99). Numero di carta mascherato, non registrato."],
})
