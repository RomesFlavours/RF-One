import os
import uuid

from flask import Flask, abort, render_template, request, redirect, send_from_directory, session, url_for

import ocr_engine
import parser as invoice_parser
import excel_store
import human_review
import purchased_bridge
import review_authority
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
# Only needed for the Purchased Human Review "who is reviewing" session
# (review_authority.py) -- a signed cookie, not a secret protecting real
# data; see that module's own docstring for why there is no real
# authentication here (Identity & Access is frozen).
app.secret_key = os.environ.get("INVOICE_INTAKE_SECRET_KEY", "dev-only-not-a-real-secret")


def _current_reviewer() -> tuple[str | None, str | None]:
    return session.get("reviewer_name"), session.get("reviewer_role")


def _require_action(action: str):
    """Returns a Flask response to abort the request with if the current
    session's role cannot perform `action`; `None` when allowed. Task
    requirement 19: server-side enforcement, never a client-trusted flag."""

    _, role = _current_reviewer()
    if not review_authority.has_action(role, action):
        abort(403, description=f"Reviewer role {role!r} is not authorized for {action!r}.")
    return None


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
    raw_text = form.get("raw_text", "")

    # Canonical persistence (Align legacy Invoice Intake with Purchased): the
    # RF-One Data Store is the Purchase Fact source of truth from here on,
    # owned by Purchased (01 Domains/Shared Domains/Purchased/README.md).
    doc_id = purchased_bridge.save_purchase_document(header, lines, source_file, raw_text=raw_text)

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


# ---------------------------------------------------------------------------
# Purchased Human Review ("Purchased Human Review + Supplier Format
# Training UI") -- Purchased's own concern, never Purchasing/Accounting/
# Bank Reconciliation (Task requirement 1). See `human_review.py` and
# `review_authority.py` for the actual logic; these routes are thin.
# ---------------------------------------------------------------------------


@app.route("/review/login", methods=["GET", "POST"])
def review_login():
    """Not real authentication -- see `review_authority.py`'s own
    docstring for why (Identity & Access is frozen). Records who is acting
    for this browser session's audit trail and action-model role."""

    if request.method == "POST":
        name = request.form.get("reviewer_name", "").strip()
        role = request.form.get("reviewer_role", "").strip().upper()
        if name and role in review_authority.ROLES:
            session["reviewer_name"] = name
            session["reviewer_role"] = role
            return redirect(url_for("review_queue"))
        return render_template("review_login.html", roles=review_authority.ROLES, error="Nome e ruolo richiesti.")
    return render_template("review_login.html", roles=review_authority.ROLES, error=None)


@app.route("/review")
def review_queue():
    _require_action(review_authority.ACTION_VIEW_QUEUE)
    reviewer_name, reviewer_role = _current_reviewer()
    rows = human_review.get_review_queue()
    return render_template("review_queue.html", rows=rows, reviewer_name=reviewer_name, reviewer_role=reviewer_role)


@app.route("/review/<int:doc_id>")
def review_detail(doc_id):
    _require_action(review_authority.ACTION_VIEW_QUEUE)
    reviewer_name, reviewer_role = _current_reviewer()
    view = human_review.get_review_detail(doc_id)
    if view is None:
        abort(404)
    can_correct = review_authority.has_action(reviewer_role, review_authority.ACTION_CORRECT)
    return render_template(
        "review_detail.html",
        doc_id=doc_id,
        view=view,
        header_fields=human_review.HEADER_FIELDS,
        line_fields=human_review.LINE_FIELDS,
        reviewer_name=reviewer_name,
        reviewer_role=reviewer_role,
        can_correct=can_correct,
    )


@app.route("/review/<int:doc_id>/field", methods=["POST"])
def review_submit_field(doc_id):
    _require_action(review_authority.ACTION_CORRECT)
    reviewer_name, _ = _current_reviewer()
    field_name = request.form.get("field_name", "")
    classification = request.form.get("classification", "")
    purchase_line_id = request.form.get("purchase_line_id") or None
    corrected_value = request.form.get("corrected_value") or None
    human_review.submit_field_review(
        doc_id,
        field_name=field_name,
        classification=classification,
        reviewed_by=reviewer_name or "unknown",
        purchase_line_id=int(purchase_line_id) if purchase_line_id else None,
        corrected_value=corrected_value,
    )
    return redirect(url_for("review_detail", doc_id=doc_id))


@app.route("/review/<int:doc_id>/complete", methods=["POST"])
def review_complete(doc_id):
    _require_action(review_authority.ACTION_CORRECT)
    reviewer_name, _ = _current_reviewer()
    result = human_review.complete_review(doc_id, reviewed_by=reviewer_name or "unknown")
    return render_template("review_complete.html", doc_id=doc_id, result=result)


@app.route("/review/source/<path:filename>")
def review_source(filename):
    """Task requirement 16: the source PDF/image, served only to a
    reviewer with at least view access, only from within `uploads/`
    (`send_from_directory` rejects any `..`/absolute-path traversal
    attempt on its own). Never publicly reachable without a valid Human
    Review session."""

    _require_action(review_authority.ACTION_VIEW_QUEUE)
    try:
        return send_from_directory(UPLOAD_DIR, filename)
    except Exception:
        abort(404)


@app.route("/training")
def supplier_training_status():
    _require_action(review_authority.ACTION_VIEW_QUEUE)
    reviewer_name, reviewer_role = _current_reviewer()
    rows = human_review.list_supplier_training_status()
    can_validate = review_authority.has_action(reviewer_role, review_authority.ACTION_VALIDATE_FORMAT)
    return render_template(
        "supplier_training.html", rows=rows, reviewer_name=reviewer_name, reviewer_role=reviewer_role, can_validate=can_validate
    )


@app.route("/training/validate", methods=["POST"])
def supplier_training_validate():
    _require_action(review_authority.ACTION_VALIDATE_FORMAT)
    supplier_name = request.form.get("supplier_name", "")
    source_format = request.form.get("source_format", "")
    error = None
    try:
        human_review.validate_supplier_format(supplier_name, source_format)
    except ValueError as exc:
        error = str(exc)
    rows = human_review.list_supplier_training_status()
    reviewer_name, reviewer_role = _current_reviewer()
    can_validate = review_authority.has_action(reviewer_role, review_authority.ACTION_VALIDATE_FORMAT)
    return render_template(
        "supplier_training.html",
        rows=rows,
        reviewer_name=reviewer_name,
        reviewer_role=reviewer_role,
        can_validate=can_validate,
        error=error,
    )


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
