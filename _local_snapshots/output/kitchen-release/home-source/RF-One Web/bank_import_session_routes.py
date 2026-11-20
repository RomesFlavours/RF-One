"""RF-One Web — the two-pass Bank import session (BANK_TWO_PASS_IMPORT_001).

An uploaded file set is staged (`bank_import_staging`) and handled on ONE page,
`/bank/import/<token>`, in two passes:

  PASS 1  Sources — the account from the file name, the layout from the
          content; a name matching exactly one Source gets it. EVERY row has
          one action, "Complete Source" (BANK_COMPLETE_SOURCE_ALL_ROWS_001):
          the ONE Source modal, with the row's Source or, when it has none,
          what the file states — to create it or to choose an existing one.
          A Source is written only by the modal's Save, which also links it
          to the file; a cancelled modal writes nothing. Only Sources are
          written.
  FILES   A file this import cannot read (an unknown layout; a PayPal /
          Amazon file, whose importer does not exist yet) is never left out
          automatically: the person confirms it in the review log, before
          Confirm (BANK_FILE_LEAVE_OUT_001). PayPal / Amazon files left out
          are kept, with their Source, for a later import.
  PASS 2  Read and check — every row read, assigned to its file's Source, and
          checked for possible duplicates with date + description + amount
          only, against the stored transactions and the rest of the upload.
          Nothing is written; every row needing a decision is listed.

Confirm (`/bank/upload/<token>/confirm`, in `bank_routes`) then imports with
the person's decisions in one transaction. The session's state lives in the
staged set's manifest, so it survives every request until Confirm or Cancel.

Registered from `bank_routes.register_bank_routes`; never imports `app.py`.
"""

from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import import_session

import bank_import_staging

STATE_KEY = "two_pass"
PENDING, READY, AMBIGUOUS = "PENDING", "READY", "AMBIGUOUS"
IMPORTER_MISSING, HELD, UNRECOGNIZED, EXCLUDED = "IMPORTER_MISSING", "HELD", "UNRECOGNIZED", "EXCLUDED"


def file_entries(staged) -> list[dict]:
    """The staged files, in upload order, with their index."""
    return [{"index": i, "file_name": name, "content": content}
            for i, (name, content) in enumerate(staged.files())]


def ensure_state(staged) -> dict:
    """The session state; created on first view by recognising each file
    (read only).

    A file's `status` is what this BANK import does with it: a bank file is
    PENDING until it has its Source (READY). A file it cannot read waits
    for the person's confirmation in the review log — IMPORTER_MISSING (a
    PayPal / Amazon file) becomes HELD, kept for a later import;
    UNRECOGNIZED becomes EXCLUDED. Never automatically. Its Source
    (`source_id`) is separate: any row may have one, whatever its importer."""
    state = staged.manifest.get(STATE_KEY)
    if state is not None:
        return state
    files = []
    for entry in file_entries(staged):
        identity = import_session.identify_file(entry["file_name"], entry["content"])
        status = PENDING
        if identity.kind in import_session.DOCUMENT_KINDS:
            status = IMPORTER_MISSING
        elif identity.kind == import_session.KIND_UNRECOGNIZED:
            status = UNRECOGNIZED
        files.append({"index": entry["index"], "file_name": entry["file_name"], "kind": identity.kind,
                      "format": identity.detected_format, "institution": identity.institution,
                      "instrument_type": identity.instrument_type, "digits": identity.account_digits,
                      "note": identity.note, "status": status, "source_id": None, "created": False,
                      "candidates": []})
    state = {"files": files, "check": None, "decisions": {}}
    bank_import_staging.save_state(staged, STATE_KEY, state)
    return state


def match_sources(db, staged, state: dict) -> None:
    """Each bank file still without its Source gets the one Source its name
    matches — or the Source the person chose in the upload form, for every
    bank file. Several matches are only offered (AMBIGUOUS); no match leaves
    the file for Complete Source. Nothing is created here."""
    chosen = (staged.manifest.get("options") or {}).get("payment_instrument_id")
    chosen_source = db.get(m.PaymentInstrument, chosen) if chosen else None
    changed = False
    for f in state["files"]:
        if f["kind"] != import_session.KIND_BANK or f["status"] != PENDING or f["source_id"]:
            continue
        if chosen_source is not None and chosen_source.is_payment_source:
            f.update(status=READY, source_id=chosen_source.id)
            changed = True
            continue
        identity = import_session.FileIdentity(
            f["file_name"], f["kind"], detected_format=f["format"], institution=f["institution"],
            instrument_type=f["instrument_type"], account_digits=f["digits"])
        found = import_session.matching_sources(db, identity)
        if len(found) == 1:
            f.update(status=READY, source_id=found[0].id)
        elif found:
            f.update(status=AMBIGUOUS, candidates=[i.id for i in found])
        else:
            continue
        changed = True
    if changed:
        bank_import_staging.save_state(staged, STATE_KEY, state)


def link_file(staged, state: dict, index: int, source, *, created: bool = False) -> None:
    """THE association of a Source with a file — what the modal's Save does
    once the Source itself is saved. The session, the other files and the
    row decisions are kept; a check made with another Source is outdated
    (Confirm compares the Sources it was made with)."""
    f = next(x for x in state["files"] if x["index"] == index)
    if f["source_id"] != source.id:
        f.update(source_id=source.id, candidates=[], created=created)
    if f["kind"] == import_session.KIND_BANK:
        f["status"] = READY
    bank_import_staging.save_state(staged, STATE_KEY, state)


def check_link(f: dict | None, source) -> None:
    """Refuse a Source a file cannot take: a bank statement only goes to a
    bank account, card or PayPal Source (never a purchase platform)."""
    if f is None:
        raise ValueError("This file is no longer part of the import session: reload the page.")
    if f["kind"] == import_session.KIND_BANK and not source.is_payment_source:
        raise ValueError("A bank statement goes to a bank account, card or PayPal Source, "
                         "not to a purchase platform.")


def pass1_complete(state: dict) -> bool:
    """Every bank file has its Source. Files this import cannot read are
    not part of Pass 1: their leave-out is decided in the review log."""
    return all(f["status"] == READY for f in state["files"] if f["kind"] == import_session.KIND_BANK)


def unconfirmed_leave_outs(state: dict) -> list[dict]:
    """The files this import cannot read whose leave-out the person has not
    confirmed yet (BANK_FILE_LEAVE_OUT_001)."""
    return [f for f in state["files"] if f["status"] in (IMPORTER_MISSING, UNRECOGNIZED)]


def bank_files(state: dict) -> list[dict]:
    return [f for f in state["files"] if f["kind"] == import_session.KIND_BANK and f["status"] == READY]


def unresolved_issues(state: dict) -> list[dict]:
    check = state.get("check") or {}
    decisions = state.get("decisions") or {}
    out = []
    for issue in check.get("issues", []):
        # BANK_POSSIBLE_DUPLICATES_001 — a possible duplicate has a default
        # (imported, "Da verificare"); only an unreadable row must be decided.
        decision = import_session.effective_decision(issue, decisions)
        if decision is None or (issue.get("exclusion_only") and decision != import_session.DECISION_EXCLUDE):
            out.append(issue)
    return out


def incomplete_sources(db, state: dict) -> dict[int, list[str]]:
    """BANK_COMPLETE_SOURCE_001 — each Source of an included (READY) file
    that still lacks required data, with what it lacks. Read live, so a
    Source completed in the modal counts at once."""
    out = {}
    for source_id in {f["source_id"] for f in state["files"] if f["status"] == READY and f["source_id"]}:
        source = db.get(m.PaymentInstrument, source_id)
        missing = import_session.source_missing_fields(db, source) if source is not None else ["Source not found"]
        if missing:
            out[source_id] = missing
    return out


def ready_to_confirm(state: dict, *, incomplete: dict[int, list[str]]) -> tuple[bool, str]:
    if not pass1_complete(state):
        return False, "Pass 1 is not finished: every bank file needs its Source (Complete Source on its row)."
    if unconfirmed_leave_outs(state):
        return False, (f"{len(unconfirmed_leave_outs(state))} file(s) cannot be imported now: confirm in the "
                       "review log that they stay out of this upload.")
    if incomplete:
        return False, f"{len(incomplete)} Source(s) still miss required data: use Complete Source on their row."
    check = state.get("check")
    if check is None:
        return False, "Run Pass 2 (Read and check) first."
    if check.get("source_map") != {str(f["index"]): f["source_id"] for f in bank_files(state)}:
        return False, "The Sources changed after the check: run Read and check again."
    if unresolved_issues(state):
        return False, f"{len(unresolved_issues(state))} row(s) still need a decision."
    if not bank_files(state):
        return False, "No bank file to import."
    return True, ""


def register_bank_import_session_routes(app, *, gate, SessionFactory, require_csrf, current_account,
                                        staging_root, instruments, source_page_context):

    def _load(token: str):
        with SessionFactory() as db:
            account_id = current_account(db).id
        return bank_import_staging.load(staging_root(), token, account_id=account_id)

    def _back(token: str, anchor: str | None = None, **args):
        return redirect(url_for("bank_import_session", token=token, _anchor=anchor, **args))

    def _gone():
        flash("This import session no longer exists (confirmed, cancelled or expired). Upload the files again.",
              "error")
        return redirect(url_for("bank_home"))

    @app.route("/bank/import/<token>")
    @gate
    def bank_import_session(token: str):
        staged = _load(token)
        if staged is None:
            return _gone()
        state = ensure_state(staged)
        with SessionFactory() as db:
            match_sources(db, staged, state)
            all_instruments = instruments(db)
            by_id = {i.id: i for i in all_instruments}
            incomplete = incomplete_sources(db, state)
            # What every row's Source lacks — shown on every row; only the
            # Sources of the files THIS import includes block it.
            source_missing = {f["source_id"]: import_session.source_missing_fields(db, by_id[f["source_id"]])
                              for f in state["files"] if f["source_id"] in by_id}
            payment_ids = [i.id for i in all_instruments if i.is_payment_source]
            row_modal = {}
            for f in state["files"]:
                candidates = f.get("candidates") or (
                    [i.id for i in import_session.document_candidates(db, f["kind"])]
                    if f["kind"] in import_session.DOCUMENT_KINDS and not f["source_id"] else [])
                row_modal[f["index"]] = {
                    "index": f["index"], "file_name": f["file_name"],
                    "source_id": f["source_id"] if f["source_id"] in by_id else None,
                    "candidates": candidates,
                    "choices": payment_ids if f["kind"] == import_session.KIND_BANK else list(by_id),
                    "prefill": import_session.source_prefill(f["kind"], f["institution"], f["instrument_type"],
                                                             f["digits"]),
                }
            ready, why_not = ready_to_confirm(state, incomplete=incomplete)
            decisions = state.get("decisions") or {}
            issues = (state.get("check") or {}).get("issues", [])
            effective = [import_session.effective_decision(i, decisions) for i in issues]
            excluded = effective.count(import_session.DECISION_EXCLUDE)
            distinct = effective.count(import_session.DECISION_DISTINCT)
            to_verify = effective.count(import_session.DECISION_TO_VERIFY)
            total_rows = sum(f["rows"] for f in (state.get("check") or {}).get("files", []))
            return render_template(
                "bank_import_session.html", token=token, state=state, sources_by_id=by_id,
                kind_labels=import_session.KIND_LABELS, ready=ready, why_not=why_not,
                pass1_done=pass1_complete(state) and not incomplete, incomplete=incomplete,
                source_missing=source_missing, row_modal=row_modal, import_token=token,
                unresolved=len(unresolved_issues(state)), leave_outs_open=len(unconfirmed_leave_outs(state)),
                excluded_count=excluded, distinct_count=distinct, to_verify_count=to_verify, total_rows=total_rows,
                rows_to_import=total_rows - excluded, options=staged.manifest.get("options") or {},
                **source_page_context(db, all_instruments, open_source_id=request.args.get("edit", type=int)),
            )

    @app.route("/bank/import/<token>/assign", methods=["POST"])
    @gate
    def bank_import_assign(token: str):
        """An EXISTING Source for one file, as it is (the modal's Save links
        the Source it saves through the Source routes, `link_file`)."""
        require_csrf()
        staged = _load(token)
        if staged is None:
            return _gone()
        state = ensure_state(staged)
        index = request.form.get("file_index", type=int)
        f = next((x for x in state["files"] if x["index"] == index), None)
        with SessionFactory() as db:
            source = db.get(m.PaymentInstrument, request.form.get("source", type=int) or 0)
            try:
                if source is None:
                    raise ValueError("Choose the Source of this file.")
                check_link(f, source)
            except ValueError as exc:
                flash(str(exc), "error")
                return _back(token, "pass-1")
            link_file(staged, state, index, source)
        return _back(token, f"file-{index}")

    @app.route("/bank/import/<token>/leave-out", methods=["POST"])
    @gate
    def bank_import_leave_out(token: str):
        """The person's decision, in the review log, on a file this import
        cannot read: confirm it stays out of this upload (a PayPal / Amazon
        file is kept for a later import), or take the confirmation back."""
        require_csrf()
        staged = _load(token)
        if staged is None:
            return _gone()
        state = ensure_state(staged)
        index = request.form.get("file_index", type=int)
        leave_out = request.form.get("decision") == "LEAVE_OUT"
        for f in state["files"]:
            if f["index"] != index:
                continue
            if f["kind"] in import_session.DOCUMENT_KINDS:
                f["status"] = HELD if leave_out else IMPORTER_MISSING
            elif f["kind"] == import_session.KIND_UNRECOGNIZED:
                f["status"] = EXCLUDED if leave_out else UNRECOGNIZED
        bank_import_staging.save_state(staged, STATE_KEY, state)
        return _back(token, f"leave-out-{index}")

    @app.route("/bank/import/<token>/check", methods=["POST"])
    @gate
    def bank_import_check(token: str):
        """Pass 2: read every row and list what needs a decision. Writes
        nothing to the Bank data."""
        require_csrf()
        staged = _load(token)
        if staged is None:
            return _gone()
        state = ensure_state(staged)
        if not pass1_complete(state):
            flash("Finish Pass 1 first: every bank file needs its Source (Complete Source on its row).", "error")
            return _back(token, "pass-1")
        contents = {e["index"]: e["content"] for e in file_entries(staged)}
        files = [{"index": f["index"], "file_name": f["file_name"], "content": contents[f["index"]],
                  "source_id": f["source_id"]} for f in bank_files(state)]
        with SessionFactory() as db:
            if incomplete_sources(db, state):
                flash("Complete every Source first: use Complete Source on each row marked incomplete.", "error")
                return _back(token, "pass-1")
            check = import_session.check_rows(db, files)
        check["source_map"] = {str(f["index"]): f["source_id"] for f in bank_files(state)}
        keys = {i["key"] for i in check["issues"]}
        state["decisions"] = {k: v for k, v in (state.get("decisions") or {}).items() if k in keys}
        state["check"] = check
        bank_import_staging.save_state(staged, STATE_KEY, state)
        return _back(token, "pass-2")

    @app.route("/bank/import/<token>/decide", methods=["POST"])
    @gate
    def bank_import_decide(token: str):
        """The person's decision for one row, or for every row of a file /
        of the whole upload of one kind. An unreadable row can only be
        excluded: no generic override makes invalid data importable."""
        require_csrf()
        staged = _load(token)
        if staged is None:
            return _gone()
        state = ensure_state(staged)
        decision = request.form.get("decision")
        if decision not in (import_session.DECISION_EXCLUDE, import_session.DECISION_DISTINCT,
                            import_session.DECISION_TO_VERIFY):
            flash("Choose a decision.", "error")
            return _back(token, "pass-2")
        key = request.form.get("key")
        scope = request.form.get("scope")
        decisions = state.setdefault("decisions", {})
        changed = 0
        for issue in (state.get("check") or {}).get("issues", []):
            if key and issue["key"] != key:
                continue
            if scope and scope.startswith("file:") and str(issue["file_index"]) != scope[5:]:
                continue
            if not key and not scope:
                continue
            if issue.get("exclusion_only") and decision != import_session.DECISION_EXCLUDE:
                continue  # an unreadable row / a byte-identical file can only be excluded
            if scope and issue["kind"] == import_session.ISSUE_UNREADABLE:
                continue  # unreadable rows are decided one by one
            decisions[issue["key"]] = decision
            changed += 1
        bank_import_staging.save_state(staged, STATE_KEY, state)
        anchor = f"issue-{key.replace(':', '-')}" if key else "pass-2"
        return _back(token, anchor)
