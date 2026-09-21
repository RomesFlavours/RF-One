#!/usr/bin/env python
"""HTTP-level regression test for BANK_RECONCILIATION_INSTRUMENT_ASSIGNMENT_001
— the corrections that came out of the local web collaudo of Bank
Reconciliation.

Same convention as `test_bank_reconciliation_http.py`, which it sits
beside and does not replace: a throwaway SQLite database created BEFORE
`app.py` is imported (via `RFONE_DATABASE_URL`), migrated explicitly,
Werkzeug's Flask test client, `main()` returning an exit code. Every CSV
here is synthetic; no real bank file, no AWS, no production database is
ever touched.

Covers: the three-tab module navigation and its active state, the absence
of the misleading back-link, Payment Instrument editing (including the
Legal Entity that unblocks the export), batch and single-transaction
reassignment with audit, absence of duplication after a reprocess, Chase
file-name recognition (ignoring the date and Windows `(1)`/`(2)`
suffixes), per-row recognition through the `Card` column, First Citizens
with one and with several accounts, reuse and disabling of a saved source
rule, the concrete explanation of `REQUIRES_REVIEW`, and the responsive
markup.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_bank_assign_test_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "http-test-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import service as bank_service  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')

CHASE_BANK_HEADER = "Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"
CHASE_CARD_HEADER = "Card,Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"
FIRST_CITIZENS_HEADER = "Account Number,Post Date,Check,Description,Debit,Credit,Status,Balance\n"


def chase_bank_csv(*rows: str) -> bytes:
    return (CHASE_BANK_HEADER + "".join(rows)).encode("utf-8")


def chase_card_csv(*rows: str) -> bytes:
    return (CHASE_CARD_HEADER + "".join(rows)).encode("utf-8")


def first_citizens_csv(*rows: str) -> bytes:
    return (FIRST_CITIZENS_HEADER + "".join(rows)).encode("utf-8")


def extract_csrf(html: bytes) -> str:
    match = CSRF_RE.search(html.decode("utf-8"))
    assert match, "csrf_token not found in response HTML"
    return match.group(1)


def main() -> int:  # noqa: C901 — one linear scenario, deliberately readable top to bottom
    checks_passed: list[str] = []
    checks_failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            checks_passed.append(description)
        else:
            checks_failed.append(description)
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    try:
        # -----------------------------------------------------------------
        # Fixture: one operator with BANK access, two Legal Entities.
        # -----------------------------------------------------------------
        with SessionFactory() as s:
            operator = account_service.create_account(
                s, username="bank_ops", display_name="Bank Operator", password="OperatorPass123!",
                status="ACTIVE", is_admin=False,
            )
            s.flush()
            account_service.set_domain_access(
                s, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None,
            )
            entity_a = m.LegalEntity(legal_name="RF Winter Park", status="ACTIVE")
            entity_b = m.LegalEntity(legal_name="RF Corporate", status="ACTIVE")
            s.add_all([entity_a, entity_b])
            s.commit()
            entity_a_id, entity_b_id = entity_a.id, entity_b.id

        client = web_app.app.test_client()
        resp = client.get("/login")
        client.post("/login", data={
            "username": "bank_ops", "password": "OperatorPass123!",
            "csrf_token": extract_csrf(resp.data),
        })

        def csrf_from(path: str) -> str:
            return extract_csrf(client.get(path).data)

        # =================================================================
        # 1. Three-tab navigation, active state, and no misleading link.
        # =================================================================
        pages = {
            "/bank": "import", "/bank/review": "review", "/bank/export": "export",
        }
        tab_labels = ("Import &amp; Instruments", "Review Transactions", "Monthly Export")
        for path in pages:
            html = client.get(path).data.decode("utf-8")
            check(
                f"{path} shows all three module tabs",
                all(label in html for label in tab_labels),
                f"missing: {[l for l in tab_labels if l not in html]}",
            )
            check(
                f"{path} links every tab to its own section",
                'href="/bank"' in html and 'href="/bank/review"' in html and 'href="/bank/export"' in html,
            )
            check(
                f"{path} offers an unambiguous RF-One Home link",
                'class="module-home-link"' in html and ">RF-One Home<" in html,
            )
            check(
                f"{path} no longer shows the misleading back-link",
                "&larr; Bank Reconciliation" not in html and "← Bank Reconciliation" not in html,
            )
            check(
                f"{path} presents Bank Reconciliation as a title, not a link",
                '<h1 class="module-title">Bank Reconciliation</h1>' in html,
            )

        # Tab order must be identical on every page. Compared inside the
        # nav block itself, since "Monthly Export" also appears in <title>.
        for path in pages:
            html = client.get(path).data.decode("utf-8")
            nav = html[html.index('<nav class="module-tabs"'):html.index("</nav>")]
            positions = [nav.index(label) for label in tab_labels]
            check(f"{path} keeps the tabs in the same order", positions == sorted(positions))

        # Exactly the current page's tab is active.
        for path, key in pages.items():
            html = client.get(path).data.decode("utf-8")
            active_tabs = re.findall(r'module-tab is-active"[^>]*href="([^"]+)"', html)
            check(
                f"{path} marks exactly one tab active",
                len(active_tabs) == 1, f"active={active_tabs}",
            )
            check(
                f"{path} marks the CURRENT section's tab active",
                active_tabs == [path], f"active={active_tabs}",
            )
            check(
                f"{path} exposes aria-current on the active tab",
                'aria-current="page"' in html,
            )

        # =================================================================
        # 2. Responsive markup.
        # =================================================================
        for path in pages:
            html = client.get(path).data.decode("utf-8")
            check(f"{path} opts into the wide module container", 'class="wrap wrap-wide"' in html)
            check(
                f"{path} declares no fixed pixel width that could force page scrolling",
                not re.search(r'style="[^"]*width:\s*\d{3,}px', html),
            )
        css_path = os.path.join(APP_DIR, "static", "css", "rf-one.css")
        with open(css_path, encoding="utf-8") as fh:
            css = fh.read()
        check("stylesheet defines the wide container", ".wrap-wide" in css)
        check("stylesheet keeps the default container narrow for text pages",
              ".wrap { max-width: 780px" in css)
        check("stylesheet stacks table rows on narrow viewports",
              "@media (max-width: 900px)" in css and ".table-stack td::before" in css)
        check("stylesheet lets descriptions wrap instead of stretching the table",
              ".col-description" in css and "white-space: normal" in css)
        stacked_block = css[css.index("@media (max-width: 900px)"):]
        stacked_block = stacked_block[:stacked_block.index("\n}\n", stacked_block.index(".table-stack td::before"))]
        hidden_selectors = [
            line.split("{")[0].strip()
            for line in stacked_block.splitlines() if "display: none" in line
        ]
        check(
            "the narrow layout keeps every cell carrying data visible",
            "display: block" in stacked_block
            and all(":empty" in selector for selector in hidden_selectors),
            f"hidden: {hidden_selectors}",
        )
        check(
            "the narrow layout replaces column headers with a per-cell label",
            'content: attr(data-label)' in stacked_block,
        )
        check(
            "the narrow layout does not shrink text below the desktop size",
            "font-size: .82rem" in stacked_block,
        )

        # =================================================================
        # 3. Payment Instrument creation, editing, and conflict refusal.
        # =================================================================
        csrf = csrf_from("/bank")
        client.post("/bank/instruments/new", data={
            "institution": "Chase", "display_name": "Chase Card 2915",
            "instrument_type": "CREDIT_CARD", "last_four": "2915", "csrf_token": csrf,
        })
        client.post("/bank/instruments/new", data={
            "institution": "Chase", "display_name": "Chase Card 3144",
            "instrument_type": "CREDIT_CARD", "last_four": "3144", "csrf_token": csrf,
        })
        client.post("/bank/instruments/new", data={
            "institution": "Chase", "display_name": "Chase Checking 0214",
            "instrument_type": "BANK_ACCOUNT", "csrf_token": csrf,
        })
        with SessionFactory() as s:
            card_2915 = s.scalars(select(m.PaymentInstrument).where(
                m.PaymentInstrument.display_name == "Chase Card 2915")).first()
            card_3144 = s.scalars(select(m.PaymentInstrument).where(
                m.PaymentInstrument.display_name == "Chase Card 3144")).first()
            checking = s.scalars(select(m.PaymentInstrument).where(
                m.PaymentInstrument.display_name == "Chase Checking 0214")).first()
            card_2915_id, card_3144_id, checking_id = card_2915.id, card_3144.id, checking.id
            check("instrument creation persisted all three instruments",
                  None not in (card_2915, card_3144, checking))
            check("a new instrument starts with no Legal Entity", card_2915.legal_entity_id is None)

        resp = client.get(f"/bank/instruments/{card_2915_id}/edit")
        check("an Edit page exists for a Payment Instrument", resp.status_code == 200)
        edit_html = resp.data.decode("utf-8")
        check("the Edit page warns that a missing Company blocks the export",
              "Monthly Export" in edit_html and "blocked" in edit_html)

        # Now that tables actually have rows, check the responsive markup
        # the stacked narrow-viewport layout depends on.
        home_html = client.get("/bank").data.decode("utf-8")
        check("/bank lists an Edit button per instrument",
              f'href="/bank/instruments/{card_2915_id}/edit"' in home_html)
        check(
            "/bank tables use the compact + stackable table classes",
            'class="table-compact table-stack"' in home_html,
        )
        check("/bank table cells carry a data-label for the stacked layout",
              home_html.count("data-label=") >= 9)

        # Edit every editable field at once, including the Legal Entity.
        csrf = csrf_from(f"/bank/instruments/{card_2915_id}/edit")
        client.post(f"/bank/instruments/{card_2915_id}/edit", data={
            "display_name": "Chase Visa ··2915", "institution": "CHASE",
            "instrument_type": "CREDIT_CARD", "last_four": "2915",
            "external_account_identifier": "", "legal_entity_id": str(entity_a_id),
            "currency": "usd", "linked_instrument_id": str(checking_id),
            "status": "ACTIVE", "csrf_token": csrf,
        })
        with SessionFactory() as s:
            edited = s.get(m.PaymentInstrument, card_2915_id)
            check("editing renamed the instrument", edited.display_name == "Chase Visa ··2915")
            check("editing assigned the Legal Entity", edited.legal_entity_id == entity_a_id,
                  f"legal_entity_id={edited.legal_entity_id}")
            check("editing normalized and stored the currency", edited.currency == "USD")
            check("editing stored the linked settlement instrument",
                  edited.linked_instrument_id == checking_id)
            check("editing never created a second instrument row",
                  s.scalar(select(m.PaymentInstrument.id).where(
                      m.PaymentInstrument.display_name == "Chase Card 2915")) is None)

        # Changing the Legal Entity again is a normal edit.
        csrf = csrf_from(f"/bank/instruments/{card_2915_id}/edit")
        client.post(f"/bank/instruments/{card_2915_id}/edit", data={
            "display_name": "Chase Visa ··2915", "institution": "CHASE",
            "instrument_type": "CREDIT_CARD", "last_four": "2915",
            "external_account_identifier": "", "legal_entity_id": str(entity_b_id),
            "currency": "USD", "linked_instrument_id": str(checking_id),
            "status": "ACTIVE", "csrf_token": csrf,
        })
        with SessionFactory() as s:
            check("the Legal Entity can be changed again",
                  s.get(m.PaymentInstrument, card_2915_id).legal_entity_id == entity_b_id)

        # A conflicting configuration is refused, not silently accepted.
        csrf = csrf_from(f"/bank/instruments/{card_3144_id}/edit")
        resp = client.post(f"/bank/instruments/{card_3144_id}/edit", data={
            "display_name": "Chase Card 3144", "institution": "Chase",
            "instrument_type": "CREDIT_CARD", "last_four": "2915",
            "external_account_identifier": "", "legal_entity_id": "",
            "currency": "", "linked_instrument_id": "", "status": "ACTIVE",
            "csrf_token": csrf,
        }, follow_redirects=True)
        with SessionFactory() as s:
            check(
                "an ambiguity-creating duplicate last-four is refused",
                s.get(m.PaymentInstrument, card_3144_id).last_four == "3144",
                f"last_four={s.get(m.PaymentInstrument, card_3144_id).last_four}",
            )
        check("the refusal is explained to the operator",
              b"could not tell the two apart" in resp.data)

        # CSRF is enforced on the edit endpoint.
        bare = web_app.app.test_client()
        r = bare.get("/login")
        bare.post("/login", data={
            "username": "bank_ops", "password": "OperatorPass123!", "csrf_token": extract_csrf(r.data),
        })
        resp = bare.post(f"/bank/instruments/{card_3144_id}/edit", data={
            "display_name": "No CSRF", "instrument_type": "CREDIT_CARD",
        })
        check("the Edit endpoint rejects a request with no CSRF token", resp.status_code == 400)

        # The full account number is never rendered.
        csrf = csrf_from(f"/bank/instruments/{checking_id}/edit")
        client.post(f"/bank/instruments/{checking_id}/edit", data={
            "display_name": "Chase Checking 0214", "institution": "Chase",
            "instrument_type": "BANK_ACCOUNT", "last_four": "",
            "external_account_identifier": "000123456789214",
            "legal_entity_id": str(entity_a_id), "currency": "USD",
            "linked_instrument_id": "", "status": "ACTIVE", "csrf_token": csrf,
        })
        listing = client.get("/bank").data.decode("utf-8")
        check("the instrument list never shows a full account number",
              "000123456789214" not in listing)
        check("the instrument list shows only the last four digits", ">9214<" in listing.replace(" ", "").replace("\n", ""))

        # =================================================================
        # 4. Chase recognition by file name: date and (1)/(2) ignored.
        # =================================================================
        check("file name key drops the export date and the Windows copy suffix",
              bank_service.file_name_key("Chase2915_Activity_20260920 (1).csv") == "chase2915_activity")
        check("file name key of a constant-name source is the name itself",
              bank_service.file_name_key("AccountHistory.csv") == "accounthistory")
        for name in (
            "Chase2915_Activity_20260920.csv",
            "Chase2915_Activity_20260920 (1).csv",
            "Chase2915_Activity_20261130 (2).csv",
        ):
            check(
                f"Chase last four is recognized in {name!r}",
                bank_service.chase_last_four_from_file_name(name) == "2915",
                bank_service.chase_last_four_from_file_name(name) or "None",
            )
        check("a non-Chase file name yields no last four",
              bank_service.chase_last_four_from_file_name("AccountHistory.csv") is None)

        # A Chase credit-card export WITHOUT a Card column resolves by name.
        no_card_csv = (
            "Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"
            "05/02/2026,05/03/2026,SYNTHETIC MERCHANT A,Food,Sale,-25.00,\n"
            "05/04/2026,05/05/2026,SYNTHETIC MERCHANT B,Food,Sale,-31.50,\n"
        ).encode("utf-8")
        csrf = csrf_from("/bank")
        client.post("/bank/upload", data={
            "csrf_token": csrf,
            "files": (io.BytesIO(no_card_csv), "Chase2915_Activity_20260920 (1).csv"),
        }, content_type="multipart/form-data")
        with SessionFactory() as s:
            batch = s.scalars(select(m.BankImportBatch).order_by(m.BankImportBatch.id.desc())).first()
            check(
                "a Chase file with no in-file identifier resolves from its name, ignoring date and (1)",
                batch.payment_instrument_id == card_2915_id,
                f"instrument={batch.payment_instrument_id} expected={card_2915_id}",
            )
            check("its rows were normalized onto that instrument",
                  s.scalar(select(m.BankImportBatch.row_count).where(m.BankImportBatch.id == batch.id)) == 2)
            name_batch_id = batch.id

        # =================================================================
        # 5. Per-row recognition through the `Card` column.
        # =================================================================
        mixed_card_csv = chase_card_csv(
            "XXXX XXXX XXXX 2915,05/06/2026,05/07/2026,SYNTHETIC CARD A ROW,Food,Sale,-10.00,\n",
            "XXXX XXXX XXXX 3144,05/06/2026,05/07/2026,SYNTHETIC CARD B ROW,Food,Sale,-20.00,\n",
            "XXXX XXXX XXXX 3144,05/08/2026,05/09/2026,SYNTHETIC CARD B ROW TWO,Food,Sale,-30.00,\n",
        )
        csrf = csrf_from("/bank")
        client.post("/bank/upload", data={
            "csrf_token": csrf,
            "files": (io.BytesIO(mixed_card_csv), "Chase9999_Activity_20260920.csv"),
        }, content_type="multipart/form-data")
        with SessionFactory() as s:
            batch = s.scalars(select(m.BankImportBatch).order_by(m.BankImportBatch.id.desc())).first()
            mixed_batch_id = batch.id
            txns = s.scalars(select(m.FinancialTransaction).where(
                m.FinancialTransaction.import_batch_id == batch.id)).all()
            by_instrument = {}
            for t in txns:
                by_instrument.setdefault(t.payment_instrument_id, []).append(t)
            check("a multi-card file is NOT attributed to one instrument",
                  batch.payment_instrument_id is None,
                  f"batch instrument={batch.payment_instrument_id}")
            check("every row of a multi-card file is resolved by its own Card value",
                  sorted(by_instrument) == sorted([card_2915_id, card_3144_id]),
                  f"instruments={sorted(by_instrument)}")
            check("the Card column wins over the file name",
                  len(by_instrument.get(card_3144_id, [])) == 2)
            mixed_txn_id = by_instrument[card_2915_id][0].id

        # Assigning such a batch as a whole is refused with a usable message.
        csrf = csrf_from("/bank")
        resp = client.post(f"/bank/batches/{mixed_batch_id}/resolve-instrument", data={
            "payment_instrument_id": str(card_2915_id), "reason": "trying to collapse it",
            "csrf_token": csrf,
        }, follow_redirects=True)
        check("a file carrying several cards cannot be assigned as a whole",
              b"not a single account or card" in resp.data)

        # =================================================================
        # 6. First Citizens: one account, then several.
        # =================================================================
        fc_rows = (
            "XXXXXX7470,05/10/2026,,SYNTHETIC FC PAYMENT,120.00,,Posted,5000.00\n",
            "XXXXXX7470,05/12/2026,,SYNTHETIC FC DEPOSIT,,340.00,Posted,5340.00\n",
        )
        csrf = csrf_from("/bank")
        client.post("/bank/instruments/new", data={
            "institution": "First Citizens", "display_name": "First Citizens Operating",
            "instrument_type": "BANK_ACCOUNT", "csrf_token": csrf,
        })
        client.post("/bank/upload", data={
            "csrf_token": csrf,
            "files": (io.BytesIO(first_citizens_csv(*fc_rows)), "AccountHistory.csv"),
        }, content_type="multipart/form-data")
        with SessionFactory() as s:
            fc_one = s.scalars(select(m.PaymentInstrument).where(
                m.PaymentInstrument.display_name == "First Citizens Operating")).first()
            fc_one_id = fc_one.id
            batch = s.scalars(select(m.BankImportBatch).order_by(m.BankImportBatch.id.desc())).first()
            check(
                "First Citizens with exactly one compatible account resolves automatically",
                batch.payment_instrument_id == fc_one_id,
                f"instrument={batch.payment_instrument_id}",
            )

        # A second First Citizens account makes an identical source ambiguous.
        csrf = csrf_from("/bank")
        client.post("/bank/instruments/new", data={
            "institution": "First Citizens", "display_name": "First Citizens Payroll",
            "instrument_type": "BANK_ACCOUNT", "csrf_token": csrf,
        })
        ambiguous_csv = first_citizens_csv(
            "XXXXXX7470,06/02/2026,,SYNTHETIC FC SECOND MONTH,75.00,,Posted,5265.00\n",
        )
        client.post("/bank/upload", data={
            "csrf_token": csrf,
            "files": (io.BytesIO(ambiguous_csv), "AccountHistory.csv"),
        }, content_type="multipart/form-data")
        with SessionFactory() as s:
            fc_two_id = s.scalar(select(m.PaymentInstrument.id).where(
                m.PaymentInstrument.display_name == "First Citizens Payroll"))
            ambiguous_batch = s.scalars(
                select(m.BankImportBatch).order_by(m.BankImportBatch.id.desc())).first()
            ambiguous_batch_id = ambiguous_batch.id
            check(
                "First Citizens with several compatible accounts asks a human instead of guessing",
                ambiguous_batch.payment_instrument_id is None,
                f"instrument={ambiguous_batch.payment_instrument_id}",
            )
            state = bank_service.compute_batch_review_state(s, ambiguous_batch)
            check("the ambiguous batch asks for the instrument, with a reason",
                  state.action == bank_service.ACTION_RESOLVE_INSTRUMENT and bool(state.reasons),
                  f"action={state.action} reasons={state.reasons}")

        # The human's one-off choice is saved and reused.
        csrf = csrf_from("/bank")
        client.post(f"/bank/batches/{ambiguous_batch_id}/resolve-instrument", data={
            "payment_instrument_id": str(fc_one_id),
            "save_as_source_profile": "1",
            "csrf_token": csrf,
        })
        with SessionFactory() as s:
            profile = s.scalars(select(m.BankSourceInstrumentProfile)).first()
            check("the human's choice was saved as a reusable source rule",
                  profile is not None and profile.payment_instrument_id == fc_one_id)
            check("the saved rule is keyed on evidence, not on the bare file name alone",
                  profile is not None and (profile.account_hint or profile.file_name_key))
            profile_id = profile.id if profile else None
            check("resolving the ambiguous batch normalized its rows",
                  s.scalar(select(m.BankImportBatch.payment_instrument_id).where(
                      m.BankImportBatch.id == ambiguous_batch_id)) == fc_one_id)

        reuse_csv = first_citizens_csv(
            "XXXXXX7470,07/02/2026,,SYNTHETIC FC THIRD MONTH,60.00,,Posted,5205.00\n",
        )
        csrf = csrf_from("/bank")
        client.post("/bank/upload", data={
            "csrf_token": csrf,
            "files": (io.BytesIO(reuse_csv), "AccountHistory.csv"),
        }, content_type="multipart/form-data")
        with SessionFactory() as s:
            reused_batch = s.scalars(
                select(m.BankImportBatch).order_by(m.BankImportBatch.id.desc())).first()
            check("a later import of the same source reuses the saved rule",
                  reused_batch.payment_instrument_id == fc_one_id,
                  f"instrument={reused_batch.payment_instrument_id}")

        # The rule can be re-pointed and disabled.
        csrf = csrf_from("/bank")
        client.post(f"/bank/source-profiles/{profile_id}", data={
            "payment_instrument_id": str(fc_two_id), "csrf_token": csrf,
        })
        with SessionFactory() as s:
            check("a saved rule can be re-pointed at another instrument",
                  s.get(m.BankSourceInstrumentProfile, profile_id).payment_instrument_id == fc_two_id)
        csrf = csrf_from("/bank")
        client.post(f"/bank/source-profiles/{profile_id}", data={
            "status": "INACTIVE", "csrf_token": csrf,
        })
        with SessionFactory() as s:
            disabled = s.get(m.BankSourceInstrumentProfile, profile_id)
            check("a saved rule can be disabled", disabled.status == "INACTIVE")
            check("disabling a rule never deletes it", disabled is not None)

        disabled_csv = first_citizens_csv(
            "XXXXXX7470,08/02/2026,,SYNTHETIC FC FOURTH MONTH,45.00,,Posted,5160.00\n",
        )
        csrf = csrf_from("/bank")
        client.post("/bank/upload", data={
            "csrf_token": csrf,
            "files": (io.BytesIO(disabled_csv), "AccountHistory.csv"),
        }, content_type="multipart/form-data")
        with SessionFactory() as s:
            after_disable = s.scalars(
                select(m.BankImportBatch).order_by(m.BankImportBatch.id.desc())).first()
            check("a disabled rule is no longer applied",
                  after_disable.payment_instrument_id is None,
                  f"instrument={after_disable.payment_instrument_id}")

        # =================================================================
        # 7. REQUIRES_REVIEW is explained, and offers the RIGHT action.
        # =================================================================
        # Named after the checking account's own last four (9214, derived from its
        # external account identifier) — a Chase source carries no in-file identifier,
        # so the file name prefix is the only automatic evidence there is.
        dup_csv = chase_bank_csv(
            "DEBIT,05/05/2026,SYNTHETIC IDENTICAL ROW,-42.00,ACH_DEBIT,9000.00,\n",
            "DEBIT,05/05/2026,SYNTHETIC IDENTICAL ROW,-42.00,ACH_DEBIT,9000.00,\n",
        )
        csrf = csrf_from("/bank")
        client.post("/bank/upload", data={
            "csrf_token": csrf,
            "files": (io.BytesIO(dup_csv), "Chase9214_Activity_20260920.csv"),
        }, content_type="multipart/form-data")
        with SessionFactory() as s:
            dup_batch = s.scalars(select(m.BankImportBatch).order_by(m.BankImportBatch.id.desc())).first()
            dup_batch_id = dup_batch.id
            state = bank_service.compute_batch_review_state(s, dup_batch)
            check("a fully normalized batch holding a candidate duplicate REQUIRES_REVIEW",
                  state.status == "REQUIRES_REVIEW", state.status)
            check("the reason names the candidate duplicates concretely",
                  any("candidate duplicate" in r for r in state.reasons), str(state.reasons))
            check("the item count is the number of things to review", state.item_count == 1,
                  str(state.item_count))
            check("its action is Review issues, NOT a fake Normalize",
                  state.action == bank_service.ACTION_REVIEW_ISSUES, str(state.action))
            check("nothing is left to normalize in that batch", state.unnormalized_row_count == 0)

        html = client.get("/bank").data.decode("utf-8")
        check("the batch list shows the concrete reason next to the status",
              "candidate duplicate" in html)
        check("the batch list links straight to the rows needing review",
              f"/bank/review?batch_id={dup_batch_id}" in html.replace("&amp;", "&"))
        resp = client.get(f"/bank/review?batch_id={dup_batch_id}&status=CANDIDATE_DUPLICATE")
        check("the deep link reaches exactly those rows",
              resp.status_code == 200 and b"CANDIDATE_DUPLICATE" in resp.data)

        # =================================================================
        # 8. Batch reassignment: audited, idempotent, no duplication.
        # =================================================================
        with SessionFactory() as s:
            before_total = s.scalar(select(func.count(m.FinancialTransaction.id)))
            before_batch = [
                t.id for t in s.scalars(select(m.FinancialTransaction).where(
                    m.FinancialTransaction.import_batch_id == name_batch_id)).all()
            ]
            before_raw = s.scalar(select(m.BankImportBatch.raw_file_bytes).where(
                m.BankImportBatch.id == name_batch_id))

        csrf = csrf_from("/bank")
        resp = client.post(f"/bank/batches/{name_batch_id}/resolve-instrument", data={
            "payment_instrument_id": str(card_3144_id),
            "reason": "Collaudo: the export actually belongs to card 3144.",
            "csrf_token": csrf,
        }, follow_redirects=True)
        with SessionFactory() as s:
            after_total = s.scalar(select(func.count(m.FinancialTransaction.id)))
            after_batch = s.scalars(select(m.FinancialTransaction).where(
                m.FinancialTransaction.import_batch_id == name_batch_id)).all()
            check("batch reassignment moved the batch to the new instrument",
                  s.scalar(select(m.BankImportBatch.payment_instrument_id).where(
                      m.BankImportBatch.id == name_batch_id)) == card_3144_id)
            check("batch reassignment moved its transactions",
                  all(t.payment_instrument_id == card_3144_id for t in after_batch))
            check("batch reassignment created no new transaction row",
                  after_total == before_total, f"{before_total} -> {after_total}")
            check("batch reassignment deleted no transaction row",
                  sorted(t.id for t in after_batch) == sorted(before_batch))
            check("batch reassignment recomputed the identity fingerprint",
                  all(t.fingerprint for t in after_batch))
            check("the raw file is byte-for-byte unchanged",
                  s.scalar(select(m.BankImportBatch.raw_file_bytes).where(
                      m.BankImportBatch.id == name_batch_id)) == before_raw)

            audit = s.scalars(
                select(m.BankInstrumentAssignmentAudit)
                .where(m.BankInstrumentAssignmentAudit.scope == "BATCH",
                       m.BankInstrumentAssignmentAudit.import_batch_id == name_batch_id)
                .order_by(m.BankInstrumentAssignmentAudit.id.desc())
            ).first()
            check("the batch reassignment was audited", audit is not None)
            check("the audit records the previous instrument",
                  audit is not None and audit.previous_payment_instrument_id == card_2915_id)
            check("the audit records the new instrument",
                  audit is not None and audit.new_payment_instrument_id == card_3144_id)
            check("the audit records the stated reason",
                  audit is not None and "card 3144" in audit.reason)
            check("the audit records who changed it",
                  audit is not None and audit.changed_by_account_id is not None)
            check("the audit records when it changed",
                  audit is not None and audit.changed_at is not None)
            check("the audit records how many transactions moved",
                  audit is not None and audit.affected_transaction_count == len(after_batch))

        check("the current assignment is shown after the change",
              b"Chase Card 3144" in client.get("/bank").data)
        html = client.get("/bank").data.decode("utf-8")
        check("the assignment history is visible in the UI",
              "Instrument assignment history" in html and "card 3144" in html)

        # A reassignment with no reason is refused.
        csrf = csrf_from("/bank")
        resp = client.post(f"/bank/batches/{name_batch_id}/resolve-instrument", data={
            "payment_instrument_id": str(card_2915_id), "csrf_token": csrf,
        }, follow_redirects=True)
        check("changing an existing assignment without a reason is refused",
              b"reason is required" in resp.data)

        # =================================================================
        # 9. Single-transaction reassignment.
        # =================================================================
        with SessionFactory() as s:
            before_total = s.scalar(select(func.count(m.FinancialTransaction.id)))
        csrf = csrf_from("/bank/review")
        resp = client.post(f"/bank/transactions/{mixed_txn_id}/reassign-instrument", data={
            "payment_instrument_id": str(card_3144_id),
            "reason": "Collaudo: this row's card was misread.",
            "csrf_token": csrf,
        }, follow_redirects=True)
        with SessionFactory() as s:
            txn = s.get(m.FinancialTransaction, mixed_txn_id)
            check("a single transaction can be reassigned",
                  txn.payment_instrument_id == card_3144_id)
            check("single-transaction reassignment created no new row",
                  s.scalar(select(func.count(m.FinancialTransaction.id))) == before_total)
            audit = s.scalars(
                select(m.BankInstrumentAssignmentAudit)
                .where(m.BankInstrumentAssignmentAudit.financial_transaction_id == mixed_txn_id)
            ).first()
            check("the single-transaction reassignment was audited", audit is not None)
            check("its audit scope is TRANSACTION", audit is not None and audit.scope == "TRANSACTION")
            check("its audit keeps the previous instrument",
                  audit is not None and audit.previous_payment_instrument_id == card_2915_id)
            raw = s.scalars(select(m.RawBankTransaction).where(
                m.RawBankTransaction.normalized_transaction_id == mixed_txn_id)).first()
            check("the raw row still points at the same normalized transaction",
                  raw is not None and raw.normalized_transaction_id == mixed_txn_id)

        resp = client.post(f"/bank/transactions/{mixed_txn_id}/reassign-instrument", data={
            "payment_instrument_id": str(card_2915_id), "csrf_token": csrf_from("/bank/review"),
        }, follow_redirects=True)
        check("reassigning a transaction without a reason is refused",
              b"reason" in resp.data.lower())

        review_html = client.get("/bank/review").data.decode("utf-8")
        check("Review shows the current instrument and that it was reassigned",
              "Reassigned" in review_html)
        check("Review's transaction table is compact and stackable",
              'class="table-compact table-stack"' in review_html)
        check("Review's table cells carry a data-label for the stacked layout",
              review_html.count("data-label=") >= 9)
        check("Review lets a description wrap instead of stretching the table",
              'class="col-description"' in review_html)

        # =================================================================
        # 10. Reprocess is idempotent — never duplicates.
        # =================================================================
        with SessionFactory() as s:
            before_total = s.scalar(select(func.count(m.FinancialTransaction.id)))
            before_matches = s.scalar(select(func.count(
                m.FinancialTransactionMatch.transaction_a_id)))
            before_ids = sorted(t.id for t in s.scalars(select(m.FinancialTransaction)).all())
        for _ in range(3):
            csrf = csrf_from("/bank")
            client.post(f"/bank/batches/{dup_batch_id}/reprocess", data={"csrf_token": csrf})
        with SessionFactory() as s:
            after_total = s.scalar(select(func.count(m.FinancialTransaction.id)))
            after_ids = sorted(t.id for t in s.scalars(select(m.FinancialTransaction)).all())
            after_matches = s.scalar(select(func.count(
                m.FinancialTransactionMatch.transaction_a_id)))
            check("repeated reprocess creates no transaction", after_total == before_total,
                  f"{before_total} -> {after_total}")
            check("repeated reprocess deletes no transaction", after_ids == before_ids)
            check("repeated reprocess creates no duplicate match", after_matches == before_matches)
            state = bank_service.compute_batch_review_state(s, s.get(m.BankImportBatch, dup_batch_id))
            check("reprocess left the candidate duplicate still awaiting a human",
                  state.candidate_duplicate_count == 1, str(state.candidate_duplicate_count))

        # Re-uploading the identical file is still idempotent after all this.
        csrf = csrf_from("/bank")
        client.post("/bank/upload", data={
            "csrf_token": csrf,
            "files": (io.BytesIO(dup_csv), "Chase9214_Activity_20260920.csv"),
        }, content_type="multipart/form-data")
        with SessionFactory() as s:
            check("re-uploading identical bytes still creates no second batch",
                  s.scalar(select(func.count(m.BankImportBatch.id)).where(
                      m.BankImportBatch.sha256 == hashlib.sha256(dup_csv).hexdigest())) == 1)

        # =================================================================
        # 11. Domain gating still holds on every new endpoint.
        # =================================================================
        outsider = web_app.app.test_client()
        with SessionFactory() as s:
            other = account_service.create_account(
                s, username="no_bank", display_name="No Bank", password="NoBankPass123!",
                status="ACTIVE", is_admin=False,
            )
            s.commit()
        r = outsider.get("/login")
        outsider.post("/login", data={
            "username": "no_bank", "password": "NoBankPass123!", "csrf_token": extract_csrf(r.data),
        })
        for path in (
            f"/bank/instruments/{card_2915_id}/edit",
            f"/bank/batches/{dup_batch_id}/reprocess",
            f"/bank/transactions/{mixed_txn_id}/reassign-instrument",
            f"/bank/source-profiles/{profile_id}",
        ):
            resp = outsider.get(path) if path.endswith("/edit") else outsider.post(path)
            check(f"{path} is refused without BANK domain access", resp.status_code == 403,
                  f"status={resp.status_code}")

    finally:
        pass

    print(f"\n{len(checks_passed)} passed, {len(checks_failed)} failed.")
    if checks_failed:
        print("FAILURES:")
        for description in checks_failed:
            print(f"  - {description}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
