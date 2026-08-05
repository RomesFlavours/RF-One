import os
import uuid

from flask import Flask, render_template, request, redirect, url_for

import ocr_engine
import parser as invoice_parser
import excel_store

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
DATA_DIR = os.path.join(BASE_DIR, "data")
EXCEL_PATH = os.path.join(DATA_DIR, "PurchaseDocuments.xlsx")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".pdf", ".webp", ".bmp", ".tiff"}

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("upload.html", excel_path=EXCEL_PATH)


@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("invoice_file")
    if not file or file.filename == "":
        return render_template("upload.html", error="Seleziona un file.", excel_path=EXCEL_PATH)

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        return render_template(
            "upload.html",
            error=f"Formato non supportato: {ext}. Usa jpg, png, pdf.",
            excel_path=EXCEL_PATH,
        )

    unique_name = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    saved_path = os.path.join(UPLOAD_DIR, unique_name)
    file.save(saved_path)

    if ext == ".pdf":
        text, method = ocr_engine.extract_from_pdf(saved_path)
    else:
        text = ocr_engine.extract_from_image(saved_path)
        method = "OCR"

    header = invoice_parser.parse_header(text)
    header["acquisition_method"] = method
    lines = invoice_parser.parse_lines(text)

    # Always offer a handful of blank extra rows for manual entry, since
    # automatic line-item parsing is unreliable on noisy/photographed
    # invoices.
    blank_rows_to_add = max(0, 8 - len(lines))
    for _ in range(blank_rows_to_add):
        lines.append({"description": "", "quantity": "", "unit_price": "", "line_amount": ""})

    return render_template(
        "review.html",
        header=header,
        lines=lines,
        raw_text=text,
        source_file=unique_name,
        original_name=file.filename,
    )


@app.route("/save", methods=["POST"])
def save():
    form = request.form

    header = {
        "supplier_name": form.get("supplier_name", "").strip(),
        "document_number": form.get("document_number", "").strip(),
        "document_type": form.get("document_type", "Invoice").strip(),
        "issue_date": form.get("issue_date", "").strip(),
        "acquisition_method": form.get("acquisition_method", "OCR").strip(),
        "currency": form.get("currency", "").strip(),
        "total_amount": form.get("total_amount", "").strip(),
    }

    descriptions = request.form.getlist("line_description")
    quantities = request.form.getlist("line_quantity")
    units = request.form.getlist("line_unit")
    unit_prices = request.form.getlist("line_unit_price")
    line_amounts = request.form.getlist("line_amount")

    lines = []
    for desc, qty, unit, price, amount in zip(
        descriptions, quantities, units, unit_prices, line_amounts
    ):
        lines.append(
            {
                "description": desc.strip(),
                "quantity": qty.strip(),
                "unit": unit.strip(),
                "unit_price": price.strip(),
                "line_amount": amount.strip(),
            }
        )

    source_file = form.get("source_file", "")
    doc_id = excel_store.save_purchase_document(EXCEL_PATH, header, lines, source_file)

    return render_template("success.html", doc_id=doc_id, excel_path=EXCEL_PATH)


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
