#!/usr/bin/env python
"""HTTP test for the real Bank Configuration page (BANK_CONFIGURATION_001).

Thirty numbered points, as specified by the Product Owner:

   1-5   schema: the SQLite migration, the PostgreSQL path, existing rules
         surviving, a WHO-only rule with no WHY, WHO/entity pair uniqueness;
   6-7   WHAT: add/edit with metadata derived from the group; refusals;
   8-11  WHY: add/edit, unique generated code, stable code, exactly one WHAT;
  12-18  WHO: COUNTERPARTY creation, possible WHYs, default WHY, WHO never
         determines WHY, entities served, recognition rules, nothing inferred;
  19-21  Accounts & Cards: bank account entity, derived card entity,
         lifecycle and reference rules;
  22-27  Support: entities, source rules, control months, card settlement,
         cardholder, deduplication action;
  28-30  security: BANK access, CSRF, fixed redirects.

Plus the later Product Owner decisions: D10 (COUNTERPARTY seeded by
migration, idempotently) and D11 (WHAT = P&L WHAT only; an existing WHY on a
Balance Sheet destination is labelled truthfully and never reclassified).
D9 (WHO search) is a client-side filter, exercised by the browser test.

Runs against DISPOSABLE SQLite databases created here and deleted at the end.
"""

from __future__ import annotations

import io
import os
import re
import sqlite3
import sys
import tempfile
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_bank_config_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-config-test-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import card_configuration  # noqa: E402
from rfone_data_store.bank_reconciliation import recognition  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
NEW_REVISION = "e5b1d7c3a9f2"
HEAD_REVISION = "b9e4c2a7d5f3"
PREVIOUS_REVISION = "d4a8c2e6f1b3"


def _alembic_config(url: str, buffer=None):
    from alembic.config import Config
    cfg = Config(os.path.join(_DATA_STORE_DIR, "alembic.ini"), output_buffer=buffer)
    cfg.set_main_option("script_location", os.path.join(_DATA_STORE_DIR, "migrations"))
    os.environ["ALEMBIC_DATABASE_URL_OVERRIDE"] = url
    return cfg


def _upgrade(url: str, target: str, *, sql: bool = False, buffer=None) -> None:
    from alembic import command
    try:
        command.upgrade(_alembic_config(url, buffer), target, sql=sql)
    finally:
        os.environ.pop("ALEMBIC_DATABASE_URL_OVERRIDE", None)


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []
    extra_paths: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            passed.append(description)
            print(f"  PASS  {description}")
        else:
            failed.append(description)
            print(f"  FAIL  {description}" + (f"   [{str(detail)[:300]}]" if detail else ""))

    try:
        # ------------------------------------------------------------ fixture
        with SessionFactory() as db:
            for username, bank in (("cfg_operator", True), ("cfg_outsider", False)):
                account_service.create_account(
                    db, username=username, display_name=username, password="OperatorPass123!",
                    status="ACTIVE", is_admin=False,
                )
                db.commit()
                account = db.query(m.RFOneAccount).filter_by(username=username).one()
                if bank:
                    account_service.set_domain_access(
                        db, account_id=account.id, domain_code="BANK", enabled=True, role_code=None,
                    )
            le_alpha = m.LegalEntity(legal_name="Alpha Foods, LLC", status="ACTIVE")
            le_beta = m.LegalEntity(legal_name="Beta Gelato, LLC", status="ACTIVE")
            le_gamma = m.LegalEntity(legal_name="Gamma Old, LLC", status="ACTIVE")
            db.add_all([le_alpha, le_beta, le_gamma])
            db.flush()
            re_alpha = m.ReportingEntity(code="RE_ALPHA", name="Alpha", entity_type="LEGAL",
                                         legal_entity_id=le_alpha.id, status="ACTIVE")
            re_beta = m.ReportingEntity(code="RE_BETA", name="Beta", entity_type="LEGAL",
                                        legal_entity_id=le_beta.id, status="ACTIVE")
            re_gamma = m.ReportingEntity(code="RE_GAMMA", name="Gamma", entity_type="LEGAL",
                                         legal_entity_id=le_gamma.id, status="INACTIVE")
            re_brand = m.ReportingEntity(code="RE_BRAND", name="Brand X", entity_type="VIRTUAL",
                                         legal_entity_id=None, status="ACTIVE")
            db.add_all([re_alpha, re_beta, re_gamma, re_brand])
            checking = m.PaymentInstrument(
                display_name="Alpha Checking", instrument_type="BANK_ACCOUNT", institution="CHASE",
                last_four="1111", legal_entity_id=le_alpha.id, status="ACTIVE",
            )
            operating = m.PaymentInstrument(
                display_name="Beta Operating", instrument_type="BANK_ACCOUNT", institution="CHASE",
                last_four="2222", legal_entity_id=le_beta.id, status="ACTIVE",
            )
            # The card's OWN legal entity is Beta; nothing may ever read it (D3).
            card = m.PaymentInstrument(
                display_name="Ink Card", instrument_type="CREDIT_CARD", institution="CHASE",
                last_four="3333", legal_entity_id=le_beta.id, status="ACTIVE",
            )
            db.add_all([checking, operating, card])
            db.commit()
            ids = {
                "alpha": re_alpha.id, "beta": re_beta.id, "gamma": re_gamma.id, "brand": re_brand.id,
                "le_alpha": le_alpha.id, "le_beta": le_beta.id,
                "checking": checking.id, "operating": operating.id, "card": card.id,
            }
            pl_group = db.scalars(select(m.BankAccountingClassification).where(
                m.BankAccountingClassification.node_type == "GROUP",
                m.BankAccountingClassification.statement_type == "PROFIT_LOSS",
                m.BankAccountingClassification.normal_balance == "DEBIT",
                m.BankAccountingClassification.active.is_(True),
            ).order_by(m.BankAccountingClassification.code.desc())).first()
            bs_group = db.scalars(select(m.BankAccountingClassification).where(
                m.BankAccountingClassification.node_type == "GROUP",
                m.BankAccountingClassification.statement_type == "BALANCE_SHEET",
            )).first()
            posting = db.scalars(select(m.BankAccountingClassification).where(
                m.BankAccountingClassification.node_type == "POSTING",
                m.BankAccountingClassification.statement_type == "PROFIT_LOSS",
                m.BankAccountingClassification.active.is_(True),
            ).order_by(m.BankAccountingClassification.code)).first()
            # A group that cannot give a WHAT its meaning (no normal balance).
            bare_group = m.BankAccountingClassification(
                code="9990", name="Bare Group", statement_type="PROFIT_LOSS", node_type="GROUP",
                normal_balance=None, active=True,
            )
            db.add(bare_group)
            db.commit()
            ids.update(pl_group=pl_group.id, bs_group=bs_group.id, posting=posting.id,
                       bare_group=bare_group.id)
            baseline_whys = {
                r.id: (r.code, r.name, r.description, r.status, r.accounting_classification_id)
                for r in db.scalars(select(m.BankTransactionReason))
            }

        client = web_app.app.test_client()
        client.post("/login", data={
            "username": "cfg_operator", "password": "OperatorPass123!",
            "csrf_token": CSRF_RE.search(client.get("/login").data.decode("utf-8")).group(1),
        })
        page = client.get("/bank/configuration")
        html = page.data.decode("utf-8")
        token = CSRF_RE.search(html).group(1)

        def post(path: str, data: dict | list, *, with_token: bool = True, who=None):
            pairs = list(data.items()) if isinstance(data, dict) else list(data)
            if with_token:
                pairs.append(("csrf_token", token))
            from werkzeug.datastructures import MultiDict
            return (who or client).post(path, data=MultiDict(pairs))

        def flashes(response) -> str:
            return client.get("/bank/configuration").data.decode("utf-8") if response.status_code == 302 else ""

        # ---------------------------------------------------- page structure
        order = [html.index(f'id="{s}"') for s in ("cp-what", "cp-why", "cp-who", "cp-accounts", "cp-support")]
        check("0. /bank/configuration responds 200 with the approved block order WHAT, WHY, WHO, "
              "Accounts & Cards, Support", page.status_code == 200 and order == sorted(order))
        check("0. the Reconciliation button leads to the real Reconciliation page",
              'href="/bank/reconciliation"' in html and "/bank/review" not in html)

        # ================================================================ 1-5
        conn = sqlite3.connect(_TEST_DB_PATH)
        revision = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        notnull = {row[1]: row[3] for row in conn.execute("PRAGMA table_info(bank_recognition_rules)")}
        rules_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='bank_recognition_rules'").fetchone()[0]
        table_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='bank_occurrence_reporting_entities'").fetchone()
        conn.close()
        with SessionFactory() as db:
            counterparty = db.scalars(select(m.BankOccurrenceType).where(
                m.BankOccurrenceType.code == "COUNTERPARTY")).all()
        check("D10. a fresh migrated database holds exactly one COUNTERPARTY WHO type, seeded by migration",
              len(counterparty) == 1 and counterparty[0].name == "Counterparty"
              and counterparty[0].status == "ACTIVE" and "Supplier is only one possible kind" in (counterparty[0].description or ""))
        check("1. SQLite migration reaches e5b1d7c3a9f2, creates the WHO/entity table and relaxes "
              "the rule WHY to NULL, keeping every named CHECK",
              revision == HEAD_REVISION and table_sql is not None
              and notnull.get("transaction_reason_id") == 0 and notnull.get("occurrence_id") == 1
              and all(name in rules_sql for name in (
                  "ck_bank_recognition_rule_match_type", "ck_bank_recognition_rule_match_field",
                  "ck_bank_recognition_rule_purpose_scope", "ck_bank_recognition_rule_direction",
                  "ck_bank_recognition_rule_status")),
              f"{revision} {notnull} {rules_sql[:200]}")

        buffer = io.StringIO()
        pg_error = ""
        try:
            _upgrade("postgresql://rfone:x@localhost/rfone", f"{PREVIOUS_REVISION}:{HEAD_REVISION}",
                     sql=True, buffer=buffer)
        except Exception as exc:  # noqa: BLE001
            pg_error = repr(exc)
        pg_sql = buffer.getvalue()
        check("2. PostgreSQL path renders: CREATE TABLE with the unique pair and FKs, and "
              "ALTER COLUMN ... DROP NOT NULL (no SQLite batch rebuild)",
              not pg_error and "CREATE TABLE bank_occurrence_reporting_entities" in pg_sql
              and "uq_bank_occurrence_reporting_entity" in pg_sql
              and "ALTER TABLE bank_recognition_rules ALTER COLUMN transaction_reason_id DROP NOT NULL" in pg_sql
              and "_alembic_tmp" not in pg_sql
              and "WHERE NOT EXISTS (SELECT 1 FROM bank_occurrence_types WHERE code = 'COUNTERPARTY')" in pg_sql,
              pg_error or pg_sql[-600:])

        # 3 — a DB at the previous revision, holding a learned rule, upgraded.
        fd, old_path = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_bank_config_old_")
        os.close(fd)
        os.remove(old_path)
        extra_paths.append(old_path)
        old_url = f"sqlite:///{old_path.replace(os.sep, '/')}"
        _upgrade(old_url, PREVIOUS_REVISION)
        conn = sqlite3.connect(old_path)
        conn.execute("INSERT INTO bank_occurrence_types (id, code, name) VALUES (1, 'COUNTERPARTY', 'Counterparty')")
        conn.execute("INSERT INTO bank_occurrences (id, canonical_name, occurrence_type_id, status) VALUES (1, 'Legacy Who', 1, 'ACTIVE')")
        why_id = conn.execute("SELECT MIN(id) FROM bank_transaction_reasons").fetchone()[0]
        conn.execute(
            "INSERT INTO bank_recognition_rules (id, match_type, normalized_pattern, match_field, "
            "determines_purpose, occurrence_id, transaction_reason_id, priority, status, "
            "auto_apply_enabled, human_confirmations, human_contradictions) VALUES "
            "(7, 'PREFIX', 'LEGACY WHO', 'DESCRIPTION', 0, 1, ?, 3, 'ACTIVE', 1, 4, 1)", (why_id,))
        conn.commit()
        before = conn.execute("SELECT * FROM bank_recognition_rules").fetchall()
        conn.close()
        _upgrade(old_url, "head")
        conn = sqlite3.connect(old_path)
        after = conn.execute("SELECT * FROM bank_recognition_rules").fetchall()
        who_entities = conn.execute("SELECT COUNT(*) FROM bank_occurrence_reporting_entities").fetchone()[0]
        types_after_upgrade = conn.execute("SELECT id, code, name, description FROM bank_occurrence_types").fetchall()
        conn.close()
        from alembic import command
        try:
            command.downgrade(_alembic_config(old_url), NEW_REVISION)
        finally:
            os.environ.pop("ALEMBIC_DATABASE_URL_OVERRIDE", None)
        _upgrade(old_url, "head")
        conn = sqlite3.connect(old_path)
        types_after_rerun = conn.execute("SELECT id, code, name, description FROM bank_occurrence_types").fetchall()
        conn.close()
        check("D10. an existing COUNTERPARTY is left unchanged (no duplicate), and re-running the seed "
              "after a downgrade still leaves exactly one",
              types_after_upgrade == [(1, "COUNTERPARTY", "Counterparty", None)]
              and types_after_rerun == types_after_upgrade, f"{types_after_upgrade} {types_after_rerun}")
        check("3. an existing rule survives the upgrade unchanged, WHY included; the new "
              "WHO/entity table starts empty",
              before == after and after[0][0] == 7 and why_id in after[0] and who_entities == 0,
              f"{before} -> {after}")

        response = post("/bank/configuration/who", [
            ("name", "Cintas"), ("active", "1"), ("default_why_id", ""),
            ("rule_id", ""), ("rule_pattern", "cintas corp #22"), ("rule_match", "CONTAINS"), ("rule_active", "1"),
        ])
        with SessionFactory() as db:
            cintas = db.scalar(select(m.BankOccurrence).where(m.BankOccurrence.canonical_name == "Cintas"))
            rule = db.scalar(select(m.BankRecognitionRule).where(m.BankRecognitionRule.occurrence_id == cintas.id)) if cintas else None
            matched = recognition.find_candidate_rules(
                db, normalized_description=recognition.normalize_description_for_recognition(
                    "POS DEBIT CINTAS CORP 22 ORLANDO"),
                payment_instrument_id=ids["checking"], direction="DEBIT",
            ) if rule else []
            ids["cintas"] = cintas.id if cintas else None
        check("4. a WHO-only rule is stored with NO WHY (NULL), description scope, never "
              "determining purpose — and it still recognises its WHO",
              rule is not None and rule.transaction_reason_id is None and rule.match_field == "DESCRIPTION"
              and rule.determines_purpose is False and rule.normalized_pattern == "CINTAS CORP 22"
              and [r.id for r in matched] == [rule.id],
              f"{response.status_code} {rule and (rule.transaction_reason_id, rule.normalized_pattern)}")

        with SessionFactory() as db:
            db.add(m.BankOccurrenceReportingEntity(occurrence_id=ids["cintas"], reporting_entity_id=ids["alpha"]))
            db.commit()
            db.add(m.BankOccurrenceReportingEntity(occurrence_id=ids["cintas"], reporting_entity_id=ids["alpha"]))
            try:
                db.commit()
                duplicate_refused = False
            except IntegrityError:
                db.rollback()
                duplicate_refused = True
            db.query(m.BankOccurrenceReportingEntity).delete()
            db.commit()
        check("5. the WHO/ReportingEntity pair is unique in the database", duplicate_refused)

        # ================================================================ 6-7
        response = post("/bank/configuration/what", {
            "code": "7995", "name": "Linen Service", "group_id": ids["pl_group"], "active": "1"})
        with SessionFactory() as db:
            linen = db.scalar(select(m.BankAccountingClassification).where(m.BankAccountingClassification.code == "7995"))
            group = db.get(m.BankAccountingClassification, ids["pl_group"])
            ok_create = (linen is not None and linen.parent_id == group.id and linen.node_type == "POSTING"
                         and linen.statement_type == group.statement_type
                         and linen.normal_balance == group.normal_balance
                         and not linen.is_contra and not linen.review_sensitive and linen.active)
            ids["linen"] = linen.id if linen else None
        edit = post(f"/bank/configuration/what/{ids['linen']}", {
            "code": "HACKED", "name": "Linen & Uniforms", "group_id": ids["pl_group"], "active": "0"})
        with SessionFactory() as db:
            linen = db.get(m.BankAccountingClassification, ids["linen"])
            ok_edit = linen.code == "7995" and linen.name == "Linen & Uniforms" and linen.active is False
        check("6. Add WHAT derives statement type and normal balance from its group; Edit renames "
              "and deactivates, the code never changes; the page lists it with its group",
              response.status_code == 302 and ok_create and ok_edit
              and "Linen &amp; Uniforms" in client.get("/bank/configuration").data.decode("utf-8"),
              f"{ok_create} {ok_edit}")

        refused = []
        for data in (
            {"code": "7996", "name": "No meaning", "group_id": ids["bare_group"], "active": "1"},
            {"code": "7997", "name": "Under posting", "group_id": ids["posting"], "active": "1"},
            {"code": "7998", "name": "No group", "group_id": "", "active": "1"},
            {"code": "7995", "name": "Duplicate code", "group_id": ids["pl_group"], "active": "1"},
        ):
            post("/bank/configuration/what", data)
        with SessionFactory() as db:
            created = db.scalars(select(m.BankAccountingClassification.code).where(
                m.BankAccountingClassification.code.in_(["7996", "7997", "7998"]))).all()
            refused.append(not created)
            refused.append(db.scalar(select(func.count()).where(m.BankAccountingClassification.code == "7995")) == 1)
        cross = post(f"/bank/configuration/what/{ids['linen']}", {
            "name": "Linen & Uniforms", "group_id": ids["bs_group"], "active": "0"})
        cross_page = client.get("/bank/configuration").data.decode("utf-8")
        with SessionFactory() as db:
            refused.append(db.get(m.BankAccountingClassification, ids["linen"]).parent_id == ids["pl_group"])
        check("7. a group that cannot give a valid meaning, a non-group, no group and a duplicate "
              "code are refused; a WHAT cannot move to another statement",
              all(refused) and "Balance Sheet group" in cross_page, str(refused))

        # ================================================================ 8-11
        post("/bank/configuration/what/%d" % ids["linen"], {
            "name": "Linen & Uniforms", "group_id": ids["pl_group"], "active": "1"})
        response = post("/bank/configuration/why", {
            "name": "Linen rental", "description": "Weekly linen", "what_id": ids["linen"], "active": "1"})
        with SessionFactory() as db:
            linen_why = db.scalar(select(m.BankTransactionReason).where(m.BankTransactionReason.name == "Linen rental"))
            ids["linen_why"] = linen_why.id if linen_why else None
            created_ok = linen_why is not None and linen_why.accounting_classification_id == ids["linen"] \
                and linen_why.status == "ACTIVE" and linen_why.description == "Weekly linen"
        post(f"/bank/configuration/why/{ids['linen_why']}", {
            "name": "Linen & towel rental", "description": "", "what_id": ids["posting"], "active": "0"})
        with SessionFactory() as db:
            edited = db.get(m.BankTransactionReason, ids["linen_why"])
            edit_ok = (edited.name == "Linen & towel rental" and edited.description is None
                       and edited.accounting_classification_id == ids["posting"] and edited.status == "INACTIVE")
            first_code = edited.code
        check("8. Add WHY with name, description, status and its WHAT; Edit changes all four",
              response.status_code == 302 and created_ok and edit_ok)

        post("/bank/configuration/why", {"name": "Linen rental", "description": "", "what_id": ids["linen"], "active": "1"})
        post("/bank/configuration/why", {"name": "Café & crêpes!", "description": "", "what_id": ids["linen"], "active": "1"})
        with SessionFactory() as db:
            codes = sorted(db.scalars(select(m.BankTransactionReason.code).where(
                m.BankTransactionReason.code.like("LINEN_RENTAL%"))).all())
            cafe = db.scalar(select(m.BankTransactionReason.code).where(m.BankTransactionReason.name == "Café & crêpes!"))
        check("9. the WHY code is generated and unique (existing UPPER_SNAKE convention)",
              codes == ["LINEN_RENTAL", "LINEN_RENTAL_2"] and cafe == "CAFE_CREPES", f"{codes} {cafe}")
        check("10. renaming a WHY never changes its code", first_code == "LINEN_RENTAL", first_code)

        with SessionFactory() as db:
            before_count = db.scalar(select(func.count(m.BankTransactionReason.id)))
        for data in (
            {"name": "No what", "description": "", "what_id": "", "active": "1"},
            {"name": "On a group", "description": "", "what_id": ids["pl_group"], "active": "1"},
            {"name": "On inactive", "description": "", "what_id": ids["bare_group"], "active": "1"},
        ):
            post("/bank/configuration/why", data)
        with SessionFactory() as db:
            after_count = db.scalar(select(func.count(m.BankTransactionReason.id)))
            view_html = client.get("/bank/configuration").data.decode("utf-8")
            assignable_groups = re.findall(r'"assignable": true, "code": "[^"]*", "group"[^}]*"id": %d' % ids["pl_group"], view_html)
        check("11. a WHY needs exactly one valid posting WHAT: none, a group or an unusable WHAT "
              "is refused; groups are never offered as assignable",
              before_count == after_count and not assignable_groups, f"{before_count}->{after_count}")

        # ================================================================ D11
        import json

        def view_data():
            body = client.get("/bank/configuration").data.decode("utf-8")
            return json.loads(re.search(r'<script type="application/json" id="cp-data">(.*?)</script>', body, re.S).group(1))

        with SessionFactory() as db:
            bs_why = db.scalars(select(m.BankTransactionReason).join(
                m.BankAccountingClassification,
                m.BankAccountingClassification.id == m.BankTransactionReason.accounting_classification_id,
            ).where(m.BankAccountingClassification.statement_type == "BALANCE_SHEET")
             .order_by(m.BankTransactionReason.id)).first()
            bs_destination = db.get(m.BankAccountingClassification, bs_why.accounting_classification_id)
            ids.update(bs_why=bs_why.id, bs_destination=bs_destination.id)
            bs_why_before = (bs_why.code, bs_why.name, bs_why.accounting_classification_id, bs_why.status)
        data = view_data()
        what_ids = {w["id"] for w in data["whats"]}
        with SessionFactory() as db:
            statements = set(db.scalars(select(m.BankAccountingClassification.statement_type).where(
                m.BankAccountingClassification.id.in_(what_ids))).all())
        shown = next(y for y in data["whys"] if y["id"] == ids["bs_why"])
        check("D11. the WHAT block holds only P&L posting WHAT; groups offered for a WHAT are P&L only",
              statements == {"PROFIT_LOSS"} and ids["bs_destination"] not in what_ids
              and all(g["statement"] == "P&L" for g in data["groups"]), str(statements))
        check("D11. an existing WHY on a Balance Sheet destination is shown as "
              "\"Balance Sheet destination — <name>\", not as a WHAT; loading changes nothing",
              shown["destination"] == {"kind": "BALANCE_SHEET",
                                       "label": f"Balance Sheet destination — {bs_destination.name}"}
              and ids["bs_destination"] in {d["id"] for d in data["balance_sheet_destinations"]},
              str(shown["destination"]))
        new_on_bs = post("/bank/configuration/why", {
            "name": "Should not exist", "description": "", "what_id": ids["bs_destination"], "active": "1"})
        new_on_bs_msg = flashes(new_on_bs)
        post(f"/bank/configuration/why/{ids['bs_why']}", {
            "name": bs_why_before[1] + " (renamed)", "description": "edited",
            "what_id": ids["bs_destination"], "active": "1"})
        with SessionFactory() as db:
            kept = db.get(m.BankTransactionReason, ids["bs_why"])
            kept_state = (kept.accounting_classification_id, kept.name, kept.code)
            created_on_bs = db.scalar(select(func.count()).where(m.BankTransactionReason.name == "Should not exist"))
        check("D11. a new WHY must take a P&L WHAT (a Balance Sheet destination is refused); editing "
              "only the name of an existing Balance Sheet WHY keeps its destination",
              created_on_bs == 0 and "not a WHAT" in new_on_bs_msg
              and kept_state == (ids["bs_destination"], bs_why_before[1] + " (renamed)", bs_why_before[0]),
              f"{kept_state} {new_on_bs_msg[-300:] if not created_on_bs else ''}")
        post(f"/bank/configuration/why/{ids['bs_why']}", {
            "name": bs_why_before[1], "description": "", "what_id": ids["posting"], "active": "1"})
        with SessionFactory() as db:
            moved = db.get(m.BankTransactionReason, ids["bs_why"]).accounting_classification_id
        check("D11. only an explicit choice of a P&L WHAT changes such a WHY's destination",
              moved == ids["posting"], str(moved))

        # ================================================================ 12-18
        response = post("/bank/configuration/who", {"name": "Gordon Food Service", "active": "1", "default_why_id": ""})
        with SessionFactory() as db:
            gfs = db.scalar(select(m.BankOccurrence).where(m.BankOccurrence.canonical_name == "Gordon Food Service"))
            gfs_type = db.get(m.BankOccurrenceType, gfs.occurrence_type_id).code if gfs else None
            ids["gfs"] = gfs.id if gfs else None
        check("12. Add WHO creates a COUNTERPARTY, active, with no WHY, no default and no entity",
              response.status_code == 302 and gfs is not None and gfs_type == "COUNTERPARTY"
              and gfs.default_transaction_reason_id is None and gfs.status == "ACTIVE")

        with SessionFactory() as db:
            food, cleaning = db.scalars(select(m.BankTransactionReason.id).where(
                m.BankTransactionReason.status == "ACTIVE").order_by(m.BankTransactionReason.id).limit(2)).all()
        ids.update(food=food, cleaning=cleaning)
        gfs_url = f"/bank/configuration/who/{ids['gfs']}"
        post(gfs_url, [("name", "Gordon Food Service"), ("active", "1"), ("default_why_id", food),
                       ("why_ids", food), ("why_ids", cleaning)])
        post(gfs_url, [("name", "Gordon Food Service"), ("active", "1"), ("default_why_id", food),
                       ("why_ids", food)])
        with SessionFactory() as db:
            assoc = {a.transaction_reason_id: a.active for a in db.scalars(select(m.BankOccurrenceReasonAssociation).where(
                m.BankOccurrenceReasonAssociation.occurrence_id == ids["gfs"]))}
            default_now = db.get(m.BankOccurrence, ids["gfs"]).default_transaction_reason_id
        check("13. possible WHYs are stored as WHO↔WHY associations; a withdrawn WHY is "
              "deactivated, never deleted", assoc == {food: True, cleaning: False}, str(assoc))

        bad_default = post(gfs_url, [("name", "Gordon Food Service"), ("active", "1"),
                                     ("default_why_id", cleaning), ("why_ids", food)])
        with SessionFactory() as db:
            unchanged = db.get(m.BankOccurrence, ids["gfs"]).default_transaction_reason_id == food
        check("14. the default WHY must be one of the WHO's active possible WHYs (otherwise refused, "
              "nothing changed)", default_now == food and unchanged
              and "must be one of this WHO" in flashes(bad_default))

        post(gfs_url, [("name", "Gordon Food Service"), ("active", "1"), ("default_why_id", "")])
        with SessionFactory() as db:
            gfs_row = db.get(m.BankOccurrence, ids["gfs"])
            whys_now = {r.id: (r.code, r.name, r.description, r.status, r.accounting_classification_id)
                        for r in db.scalars(select(m.BankTransactionReason))
                        if r.id in baseline_whys and r.id != ids["bs_why"]}
            rule_whys = db.scalars(select(m.BankRecognitionRule.transaction_reason_id)).all()
        check("15. a WHO may have no WHY at all; saving WHOs never creates, changes or implies a "
              "WHY (existing WHYs untouched, rules carry no WHY)",
              gfs_row.default_transaction_reason_id is None
              and whys_now == {k: v for k, v in baseline_whys.items() if k != ids["bs_why"]}
              and all(w is None for w in rule_whys), str(rule_whys))

        post(gfs_url, [("name", "Gordon Food Service"), ("active", "1"), ("default_why_id", ""),
                       ("entity_ids", ids["alpha"]), ("entity_ids", ids["brand"])])
        post(gfs_url, [("name", "Gordon Food Service"), ("active", "1"), ("default_why_id", ""),
                       ("entity_ids", ids["alpha"])])
        inactive_entity = post(gfs_url, [("name", "Gordon Food Service"), ("active", "1"), ("default_why_id", ""),
                                         ("entity_ids", ids["alpha"]), ("entity_ids", ids["gamma"])])
        missing_entity = post(gfs_url, [("name", "Gordon Food Service Renamed"), ("active", "1"),
                                        ("default_why_id", ""), ("entity_ids", "99999")])
        with SessionFactory() as db:
            served = {r.reporting_entity_id: r.active for r in db.scalars(select(m.BankOccurrenceReportingEntity).where(
                m.BankOccurrenceReportingEntity.occurrence_id == ids["gfs"]))}
            name_kept = db.get(m.BankOccurrence, ids["gfs"]).canonical_name == "Gordon Food Service"
        check("16. entities served are ReportingEntities; withdrawn = inactive; an inactive or "
              "unknown entity is refused and the whole save is rolled back",
              served == {ids["alpha"]: True, ids["brand"]: False} and name_kept
              and inactive_entity.status_code == 302 and missing_entity.status_code == 302, str(served))

        post(gfs_url, [
            ("name", "Gordon Food Service"), ("active", "1"), ("default_why_id", ""),
            ("rule_id", ""), ("rule_pattern", "gordon food service"), ("rule_match", "PREFIX"), ("rule_active", "1"),
            ("rule_id", ""), ("rule_pattern", "GFS STORE 0123"), ("rule_match", "EXACT"), ("rule_active", "1"),
            ("rule_id", ""), ("rule_pattern", "gfs mkt"), ("rule_match", "CONTAINS"), ("rule_active", "0"),
        ])
        with SessionFactory() as db:
            rules = {r.normalized_pattern: r for r in db.scalars(select(m.BankRecognitionRule).where(
                m.BankRecognitionRule.occurrence_id == ids["gfs"]))}
            created = {p: (r.match_type, r.status, r.transaction_reason_id) for p, r in rules.items()}
            prefix_id = rules["GORDON FOOD SERVICE"].id if "GORDON FOOD SERVICE" in rules else None
            exact_id = rules["GFS STORE 0123"].id if "GFS STORE 0123" in rules else None
        post(gfs_url, [
            ("name", "Gordon Food Service"), ("active", "1"), ("default_why_id", ""),
            ("rule_id", prefix_id), ("rule_pattern", "GORDON FOOD SVC"), ("rule_match", "PREFIX"), ("rule_active", "1"),
        ])
        clash = post(f"/bank/configuration/who/{ids['cintas']}", [
            ("name", "Cintas"), ("active", "1"), ("default_why_id", ""),
            ("rule_id", ""), ("rule_pattern", "GORDON FOOD SVC"), ("rule_match", "PREFIX"), ("rule_active", "1"),
        ])
        bad_match = post(gfs_url, [("name", "Gordon Food Service"), ("active", "1"), ("default_why_id", ""),
                                   ("rule_id", ""), ("rule_pattern", "X"), ("rule_match", "REGEX"), ("rule_active", "1")])
        with SessionFactory() as db:
            after_rules = {r.id: (r.normalized_pattern, r.status) for r in db.scalars(select(m.BankRecognitionRule).where(
                m.BankRecognitionRule.occurrence_id == ids["gfs"]))}
            cintas_rules = db.scalar(select(func.count()).where(m.BankRecognitionRule.occurrence_id == ids["cintas"]))
        check("17. recognition rules: Exact / Contains / Prefix created WHY-less, patterns "
              "normalised, edited in place, removed = INACTIVE (never deleted); a text another "
              "WHO recognises and an unknown match are refused",
              created.get("GORDON FOOD SERVICE") == ("PREFIX", "ACTIVE", None)
              and created.get("GFS STORE 0123") == ("EXACT_NORMALIZED_DESCRIPTION", "ACTIVE", None)
              and created.get("GFS MKT") == ("CONTAINS_TEXT", "INACTIVE", None)
              and after_rules.get(prefix_id) == ("GORDON FOOD SVC", "ACTIVE")
              and after_rules.get(exact_id) == ("GFS STORE 0123", "INACTIVE")
              and len(after_rules) == 3 and cintas_rules == 1
              and "already recognises WHO" in flashes(clash) and bad_match.status_code == 302,
              f"{created} {after_rules}")

        with SessionFactory() as db:
            inferred = db.scalar(select(func.count()).select_from(m.BankOccurrenceReportingEntity).where(
                m.BankOccurrenceReportingEntity.occurrence_id != ids["gfs"]))
        check("18. nothing is inferred: only the entities a person ticked exist; Cintas (no entity "
              "chosen) serves none, even though accounts of Alpha exist",
              inferred == 0 and "Gordon Food Service" in client.get("/bank/configuration").data.decode("utf-8"))

        # ================================================================ 19-21
        response = post("/bank/configuration/account", {
            "label": "Gamma Payroll", "instrument_type": "BANK_ACCOUNT", "entity_id": ids["beta"],
            "reference": "4444", "active": "1"})
        with SessionFactory() as db:
            payroll = db.scalar(select(m.PaymentInstrument).where(m.PaymentInstrument.display_name == "Gamma Payroll"))
            ids["payroll"] = payroll.id if payroll else None
            created_ok = payroll is not None and payroll.legal_entity_id == ids["le_beta"] and payroll.last_four == "4444"
        post(f"/bank/configuration/account/{ids['payroll']}", {
            "label": "Beta Payroll", "instrument_type": "BANK_ACCOUNT", "entity_id": ids["alpha"], "reference": "4445"})
        with SessionFactory() as db:
            payroll = db.get(m.PaymentInstrument, ids["payroll"])
            edit_ok = payroll.display_name == "Beta Payroll" and payroll.legal_entity_id == ids["le_alpha"] \
                and payroll.last_four == "4445"
        check("19. a Bank Account's owning entity is chosen by ReportingEntity name and stored as "
              "PaymentInstrument.legal_entity_id; label, type and reference edit",
              response.status_code == 302 and created_ok and edit_ok)

        def account_row(account_id):
            import json
            body = client.get("/bank/configuration").data.decode("utf-8")
            data = json.loads(re.search(r'<script type="application/json" id="cp-data">(.*?)</script>', body, re.S).group(1))
            return next(a for a in data["accounts"] if a["id"] == account_id)

        unconfigured = account_row(ids["card"])
        with_entity = post(f"/bank/configuration/account/{ids['card']}", {
            "label": "Ink Card", "instrument_type": "CREDIT_CARD", "entity_id": ids["alpha"], "reference": "3333"})
        with_entity_msg = flashes(with_entity)
        post(f"/bank/configuration/card/{ids['card']}", {
            "settlement_account_id": ids["checking"], "settlement_valid_from": "2026-01-01",
            "holder_kind": "", "holder_valid_from": ""})
        derived = account_row(ids["card"])
        post(f"/bank/configuration/account/{ids['card']}", {
            "label": "Ink Business", "instrument_type": "CREDIT_CARD", "reference": "3333"})
        with SessionFactory() as db:
            own = db.get(m.PaymentInstrument, ids["card"])
        check("20. a Credit Card's owning entity is DERIVED from its settlement account (none "
              "before one exists, never its own value); setting it on the card is refused; "
              "editing the card leaves its own legal entity untouched",
              unconfigured["entity_name"] is None and unconfigured["derived"] is True
              and derived["entity_name"] == "Alpha" and derived["derived"] is True
              and "comes from its settlement account" in with_entity_msg
              and own.display_name == "Ink Business" and own.legal_entity_id == ids["le_beta"],
              f"{unconfigured} {derived}")

        status_attempt = post(f"/bank/configuration/account/{ids['operating']}", {
            "label": "Beta Operating", "instrument_type": "BANK_ACCOUNT", "entity_id": ids["beta"],
            "reference": "2222", "active": "0"})
        virtual_owner = post(f"/bank/configuration/account/{ids['operating']}", {
            "label": "Beta Operating", "instrument_type": "BANK_ACCOUNT", "entity_id": ids["brand"], "reference": "2222"})
        virtual_msg = flashes(virtual_owner)
        bad_reference = post(f"/bank/configuration/account/{ids['operating']}", {
            "label": "Beta Operating", "instrument_type": "BANK_ACCOUNT", "entity_id": ids["beta"], "reference": "22x"})
        with SessionFactory() as db:
            operating = db.get(m.PaymentInstrument, ids["operating"])
        check("21. the Active state is not edited here (lifecycle belongs to Monthly Sources); a "
              "virtual entity cannot own an account; a reference must be four digits",
              status_attempt.status_code == 302 and operating.status == "ACTIVE"
              and operating.legal_entity_id == ids["le_beta"] and operating.last_four == "2222"
              and "virtual entity" in virtual_msg and bad_reference.status_code == 302)

        # ================================================================ 22-27
        post("/bank/configuration/entity", {"name": "Delta", "legal_name": "Delta Pizza, LLC", "active": "1"})
        post("/bank/configuration/entity", {"name": "Pop-up Brand", "legal_name": "", "active": "1"})
        with SessionFactory() as db:
            delta = db.scalar(select(m.ReportingEntity).where(m.ReportingEntity.name == "Delta"))
            popup = db.scalar(select(m.ReportingEntity).where(m.ReportingEntity.name == "Pop-up Brand"))
            ids.update(delta=delta.id, popup=popup.id)
            delta_legal = db.get(m.LegalEntity, delta.legal_entity_id)
            ok_new = (delta.entity_type == "LEGAL" and delta_legal.legal_name == "Delta Pizza, LLC"
                      and popup.entity_type == "VIRTUAL" and popup.legal_entity_id is None
                      and delta.code == "RE_DELTA")
            legal_link = delta.legal_entity_id
        post(f"/bank/configuration/entity/{ids['delta']}", {"name": "Delta Pizza", "legal_name": "Delta Pizza Holdings, LLC", "active": "0"})
        virtual_legal = post(f"/bank/configuration/entity/{ids['popup']}", {"name": "Pop-up Brand", "legal_name": "Popup LLC", "active": "1"})
        with SessionFactory() as db:
            delta = db.get(m.ReportingEntity, ids["delta"])
            ok_edit = (delta.name == "Delta Pizza" and delta.status == "INACTIVE" and delta.legal_entity_id == legal_link
                       and db.get(m.LegalEntity, legal_link).legal_name == "Delta Pizza Holdings, LLC"
                       and db.get(m.ReportingEntity, ids["popup"]).legal_entity_id is None)
        check("22. Entities are ReportingEntities: an LLC keeps its LegalEntity link (legal name "
              "editable), a virtual entity never becomes an LLC",
              ok_new and ok_edit and "never becomes an LLC" in flashes(virtual_legal))

        post("/bank/configuration/source", {"detected_format": "FIRST_CITIZENS", "file_name_key": "AccountHistory",
                                            "account_hint": "", "payment_instrument_id": ids["checking"], "active": "1"})
        with SessionFactory() as db:
            profile = db.scalar(select(m.BankSourceInstrumentProfile))
            ids["profile"] = profile.id
            created_ok = profile.file_name_key == "accounthistory" and profile.payment_instrument_id == ids["checking"]
        post(f"/bank/configuration/source/{ids['profile']}", {"detected_format": "FIRST_CITIZENS", "file_name_key": "accounthistory",
                                                              "account_hint": "x-1111", "payment_instrument_id": ids["operating"], "active": "0"})
        unknown = post("/bank/configuration/source", {"detected_format": "MADE_UP", "file_name_key": "a",
                                                      "account_hint": "", "payment_instrument_id": ids["checking"], "active": "1"})
        post("/bank/configuration/source", {"detected_format": "FIRST_CITIZENS", "file_name_key": "accounthistory",
                                            "account_hint": "x-1111", "payment_instrument_id": ids["checking"], "active": "1"})
        with SessionFactory() as db:
            profiles = db.scalars(select(m.BankSourceInstrumentProfile)).all()
            p = profiles[0]
            edit_ok = (len(profiles) == 1 and p.account_hint == "x-1111" and p.payment_instrument_id == ids["operating"]
                       and p.status == "INACTIVE")
        check("23. source rules: add, edit, deactivate; an unknown format and a duplicate are refused",
              created_ok and edit_ok and unknown.status_code == 302)

        post("/bank/configuration/control", {"control_start": "2026-01", "validated_through": "2026-03"})
        post("/bank/configuration/control", {"control_start": "2026-01", "validated_through": "2026-05"})
        bad = post("/bank/configuration/control", {"control_start": "2026-13", "validated_through": "2026-05"})
        with SessionFactory() as db:
            config = db.get(m.BankReconciliationControlConfig, 1)
        check("24. Control start / Validated through are applied through the monthly services; a "
              "malformed month is refused",
              config is not None and config.control_start_month == "2026-01"
              and config.validated_through_month == "2026-05" and "YYYY-MM" in flashes(bad))

        second = post(f"/bank/configuration/card/{ids['card']}", {
            "settlement_account_id": ids["operating"], "settlement_valid_from": "2026-06-01",
            "holder_kind": "", "holder_valid_from": ""})
        second_msg = flashes(second)
        earlier = post(f"/bank/configuration/card/{ids['card']}", {
            "settlement_account_id": ids["checking"], "settlement_valid_from": "2025-12-01",
            "holder_kind": "", "holder_valid_from": ""})
        with SessionFactory() as db:
            history = [(h.settlement_bank_account_id, h.valid_from, h.valid_to)
                       for h in card_configuration.settlement_history(db, ids["card"])]
        check("25. card settlement keeps its history with Valid from: the new account opens a "
              "period and closes the previous one; an earlier date is refused; dedup recomputed",
              history == [(ids["operating"], date(2026, 6, 1), None),
                          (ids["checking"], date(2026, 1, 1), date(2026, 6, 1))]
              and "deduplication recomputed" in second_msg
              and "must start after" in flashes(earlier), str(history))

        post(f"/bank/configuration/card/{ids['card']}", {
            "settlement_account_id": ids["operating"], "settlement_valid_from": "2026-06-01",
            "holder_kind": "UNLINKED_PERSON", "holder_name": "Tatiana Ceban", "holder_valid_from": "2026-02-01"})
        post(f"/bank/configuration/card/{ids['card']}", {
            "settlement_account_id": ids["operating"], "settlement_valid_from": "2026-06-01",
            "holder_kind": "UNLINKED_PERSON", "holder_name": "Pino Miraglia", "holder_valid_from": "2026-07-01"})
        bad_kind = post(f"/bank/configuration/card/{ids['card']}", {
            "settlement_account_id": ids["operating"], "holder_kind": "ROBOT", "holder_valid_from": "2026-08-01"})
        bad_kind_msg = flashes(bad_kind)
        with SessionFactory() as db:
            holders = [(h.holder_kind, h.holder_display_name, h.valid_from, h.valid_to)
                       for h in card_configuration.cardholder_history(db, ids["card"])]
        page_now = client.get("/bank/configuration").data.decode("utf-8")
        check("26. cardholder with holder type, holder and Valid from: history kept, previous "
              "holder closed; the table shows \"Surname I.\"; an unknown type is refused",
              holders == [("UNLINKED_PERSON", "Pino Miraglia", date(2026, 7, 1), None),
                          ("UNLINKED_PERSON", "Tatiana Ceban", date(2026, 2, 1), date(2026, 7, 1))]
              and '"cardholder": "Miraglia P."' in page_now and "Holder kind must be" in bad_kind_msg,
              str(holders))

        get_attempt = client.get("/bank/configuration/dedup/recompute")
        action = post("/bank/configuration/dedup/recompute", {})
        check("27. deduplication recompute is an ACTION (POST only) with its outcome reported",
              get_attempt.status_code == 405 and action.status_code == 302
              and "Accounting deduplication recomputed" in flashes(action))

        # ================================================================ 28-30
        anonymous = web_app.app.test_client()
        outsider = web_app.app.test_client()
        outsider.post("/login", data={
            "username": "cfg_outsider", "password": "OperatorPass123!",
            "csrf_token": CSRF_RE.search(outsider.get("/login").data.decode("utf-8")).group(1)})
        with SessionFactory() as db:
            whos_before = db.scalar(select(func.count(m.BankOccurrence.id)))
        anon_get = anonymous.get("/bank/configuration")
        outsider_get = outsider.get("/bank/configuration")
        outsider_post = outsider.post("/bank/configuration/who", data={"name": "Intruder", "active": "1"})
        with SessionFactory() as db:
            whos_after = db.scalar(select(func.count(m.BankOccurrence.id)))
        check("28. BANK access is required: anonymous is sent to login, an account without BANK "
              "is refused, and nothing is written",
              anon_get.status_code in (302, 401, 403) and outsider_get.status_code in (302, 403)
              and outsider_post.status_code in (302, 400, 403) and whos_before == whos_after,
              f"{anon_get.status_code} {outsider_get.status_code} {outsider_post.status_code}")

        no_token = post("/bank/configuration/who", {"name": "No Token", "active": "1"}, with_token=False)
        with SessionFactory() as db:
            no_token_written = db.scalar(select(func.count()).where(m.BankOccurrence.canonical_name == "No Token"))
        check("29. every change requires the CSRF token (refused without it, nothing written)",
              no_token.status_code in (400, 403) and no_token_written == 0, str(no_token.status_code))

        hostile = post("/bank/configuration/why?next=https://evil.example/", {
            "name": "Redirect probe", "description": "", "what_id": ids["posting"], "active": "1",
            "return_to": "https://evil.example/", "next": "https://evil.example/"})
        refused_hostile = post("/bank/configuration/why", {"name": "", "what_id": "", "return_to": "//evil.example"})
        locations = [hostile.headers.get("Location", ""), refused_hostile.headers.get("Location", "")]
        check("30. success and refusal both redirect to /bank/configuration (fixed section), never "
              "to an address supplied by the request",
              all(re.fullmatch(r"(http://localhost)?/bank/configuration#cp-why", loc) for loc in locations),
              str(locations))
    finally:
        for path in [_TEST_DB_PATH] + extra_paths:
            try:
                os.remove(path)
            except OSError:
                pass

    print(f"\n{len(passed)} passed, {len(failed)} failed.")
    if failed:
        print("FAILED CHECKS:")
        for description in failed:
            print(f" - {description}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
