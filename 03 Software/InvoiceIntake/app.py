import os
import uuid

from flask import Flask, render_template, request, redirect, url_for

import ocr_engine
import parser as invoice_parser
import excel_store
import purchased_bridge
from mailbox_acquisition.acquisition_store import AcquisitionStore
from mailbox_acquisition.acquisition_service import DEFAULT_DB_PATH as MAILBOX_DB_PATH
from mailbox_acquisition.config import MailboxConfigError, load_config as load_mailbox_config

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
    for line in lines:
        line["line_type"] = purchased_bridge.guess_line_type(line.get("description", ""))

    # Always offer a handful of blank extra rows for manual entry, since
    # automatic line-item parsing is unreliable on noisy/photographed
    # invoices.
    blank_rows_to_add = max(0, 8 - len(lines))
    for _ in range(blank_rows_to_add):
        lines.append({"description": "", "quantity": "", "unit_price": "", "line_amount": "", "line_type": "PRODUCT"})

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
    line_types = request.form.getlist("line_type")

    lines = []
    for desc, qty, unit, price, amount, line_type in zip(
        descriptions, quantities, units, unit_prices, line_amounts, line_types
    ):
        lines.append(
            {
                "description": desc.strip(),
                "quantity": qty.strip(),
                "unit": unit.strip(),
                "unit_price": price.strip(),
                "line_amount": amount.strip(),
                "line_type": (line_type or "PRODUCT").strip().upper(),
            }
        )

    source_file = form.get("source_file", "")

    # Canonical persistence (Align legacy Invoice Intake with Purchased): the
    # RF-One Data Store is the Purchase Fact source of truth from here on,
    # owned by Purchased (01 Domains/Shared Domains/Purchased/README.md).
    doc_id = purchased_bridge.save_purchase_document(header, lines, source_file)

    # Excel remains available only as a secondary export/debugging capability
    # (Purchased was never canonical there; it was only ever this
    # prototype's storage). A failure here must never lose the canonical
    # save above.
    excel_ok = True
    try:
        excel_store.save_purchase_document(EXCEL_PATH, header, lines, source_file)
    except Exception:
        excel_ok = False

    functional_status = purchased_bridge.get_saved_document_functional_status(doc_id)

    return render_template(
        "success.html", doc_id=doc_id, excel_path=EXCEL_PATH, excel_ok=excel_ok, functional_status=functional_status
    )


@app.route("/mailbox")
def mailbox_acquisitions():
    """Simple admin view over the Aruba mailbox acquisition's own local
    state (`mailbox_acquisition/acquisition_store.py`) — not a dashboard,
    just enough to see what was acquired, its status, and any failure/retry
    (Task requirement 11, "Human visibility")."""

    store = AcquisitionStore(MAILBOX_DB_PATH)
    try:
        records = store.list_recent(limit=200)
    finally:
        store.close()

    rows = []
    for record in records:
        supplier_name = None
        if record.purchase_document_id is not None:
            try:
                supplier_name = purchased_bridge.get_saved_document_supplier_name(record.purchase_document_id)
            except Exception:
                supplier_name = None
        rows.append(
            {
                "received_at": record.received_at,
                "sender": record.sender,
                "attachment_filename": record.attachment_filename,
                "supplier_name": supplier_name,
                "status": record.status,
                "functional_status": record.functional_status,
                "failure_reason": record.failure_reason,
                "retry_count": record.retry_count,
            }
        )

    try:
        mailbox_label = load_mailbox_config().username
    except MailboxConfigError:
        mailbox_label = "(non configurata — vedi mailbox_acquisition/README.md)"

    return render_template("mailbox.html", records=rows, mailbox=mailbox_label)


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
