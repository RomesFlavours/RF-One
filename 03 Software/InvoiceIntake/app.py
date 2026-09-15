import os
import uuid

from flask import Flask, abort, render_template, request, redirect, send_from_directory, session, url_for

import ocr_engine
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
    """Task "Close Purchased Human Review Reliability Gaps" §2: a manually
    uploaded file uses the exact same split path the mailbox acquisition
    pipeline already uses (`mailbox_acquisition/acquisition_service.py`'s
    `deliver_to_invoice_intake()`) — one saved file becomes 1..N
    `PurchaseDocument`s via `invoice_splitter.split_into_invoices()` +
    `purchased_bridge.save_purchase_documents_from_batch()`, never a second,
    duplicated split implementation. A 4-invoice Prime Line batch now
    produces 4 documents here exactly like it already does through the
    mailbox; when the split is genuinely uncertain, `invoice_splitter`
    itself falls back to one document (never an invented boundary), which
    then goes through the normal NORMALIZED/HUMAN check like before.

    There is no more pre-save manual header/lines editing step (the old
    single-document `review.html` form this route used to render) — every
    resulting document, split or not, is saved directly and any correction
    happens afterward through Purchased Human Review (`/review/<id>`),
    exactly as it already does for mailbox-acquired documents. This makes
    manual upload and mailbox acquisition literally the same pipeline from
    here on, not two independently-maintained ones."""

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
        pages, method = ocr_engine.extract_pages_from_pdf(saved_path)
    else:
        pages = [ocr_engine.extract_from_image(saved_path)]
        method = "OCR"

    document_ids = purchased_bridge.save_purchase_documents_from_batch(pages, unique_name, method)
    results = [
        {"doc_id": doc_id, "functional_status": purchased_bridge.get_saved_document_functional_status(doc_id)}
        for doc_id in document_ids
    ]

    return render_template("success.html", results=results, original_name=file.filename)


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
        error=request.args.get("error"),
    )


@app.route("/review/<int:doc_id>/field", methods=["POST"])
def review_submit_field(doc_id):
    _require_action(review_authority.ACTION_CORRECT)
    reviewer_name, _ = _current_reviewer()
    field_name = request.form.get("field_name", "")
    classification = request.form.get("classification", "")
    purchase_line_id = request.form.get("purchase_line_id") or None
    corrected_value = request.form.get("corrected_value") or None
    try:
        human_review.submit_field_review(
            doc_id,
            field_name=field_name,
            classification=classification,
            reviewed_by=reviewer_name or "unknown",
            purchase_line_id=int(purchase_line_id) if purchase_line_id else None,
            corrected_value=corrected_value,
        )
    except ValueError as exc:
        return redirect(url_for("review_detail", doc_id=doc_id, error=str(exc)))
    return redirect(url_for("review_detail", doc_id=doc_id))


@app.route("/review/<int:doc_id>/line/add", methods=["POST"])
def review_add_line(doc_id):
    """Task "Close Purchased Human Review Reliability Gaps" §3: lets a
    reviewer add a Purchase Line the original OCR/parser extraction never
    created at all — gated behind the same `ACTION_CORRECT` permission as
    any other field correction (adding a missing line is itself a
    correction, not a new action tier)."""

    _require_action(review_authority.ACTION_CORRECT)
    reviewer_name, _ = _current_reviewer()
    form = request.form
    try:
        human_review.add_missing_line(
            doc_id,
            added_by=reviewer_name or "unknown",
            line_type=(form.get("line_type") or "PRODUCT").strip().upper(),
            description=form.get("description", ""),
            normalized_item=form.get("normalized_item") or None,
            quantity=form.get("quantity") or None,
            unit_of_measure=form.get("unit_of_measure") or None,
            unit_price=form.get("unit_price") or None,
            line_amount=form.get("line_amount") or None,
        )
    except ValueError as exc:
        return redirect(url_for("review_detail", doc_id=doc_id, error=str(exc)))
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
