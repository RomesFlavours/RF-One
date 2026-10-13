"""Bank transfer: AWS history + the local 2026 Bank work (BANK_AWS_DATA_TRANSFER_PLAN_001).

    # preview (default): a disposable rfone_pgval_* database or the live one, nothing written
    python transfer_bank_2026_to_aws.py --local <copy of the local rfone.db> --target live
    # rehearsal on a disposable database (it must already hold a copy of live)
    python transfer_bank_2026_to_aws.py --local <copy> --target rfone_pgval_x --apply
    # the transfer itself
    python transfer_bank_2026_to_aws.py --local <copy> --target live --apply --confirm-live

AWS stays the base: nothing on it is deleted. The local work is ADDED (Sources, WHO, WHY, the 130
September movements with their files and raw rows, every decision, the AI work) and the matched
AWS movements get the local decisions as their new current decision (the AWS one stays as history).
Mappings follow the plan (§2–§3): Legal Entities 1→2, 2→1, 3→3 (names not changed); Reporting
Entities by Legal Entity (the AWS row takes the local code and name); Sources by account number,
the local 3144 card split by each row's `Card` column; WHO by name; WHY, groups, WHAT by code.

Possible duplicates (Product Owner, 2026-10-13): nothing is deleted or merged; the AWS repeats that
no balance proves distinct become CANDIDATE_DUPLICATE ("Da verificare"), linked to the first row.

Matched movement (Product Owner, 2026-10-13): the LOCAL state prevails, also when its WHO or WHY is
empty and when it has no decision at all; the AWS decision stays in the history, never deleted. The
local value wins a conflict. `--fill-from-aws` (not the Product Owner's choice) is kept only to compare.

Safety: AWS account, database and Alembic revision checked; the local file is read from a COPY that
this tool upgrades itself; one transaction; every check below must hold before COMMIT, otherwise
ROLLBACK; a second run is refused (AI rules already present).
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from urllib.parse import urlsplit, urlunsplit

import sqlalchemy as sa

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

EXPECTED_ACCOUNT = "418674484214"
PROFILE, REGION, SECRET = "rfone-dev-login", "us-east-1", "rfone-tips/database-url"
LIVE_DB, DISPOSABLE_PREFIX = "rfone", "rfone_pgval_"
REVISION = "7b1d4f9a2c6e"

# Plan §2 — local id -> AWS id.
LEGAL_ENTITY_MAP = {1: 2, 2: 1, 3: 3}
REPORTING_ENTITY_MAP = {3: 1, 2: 3, 4: 2}          # RE_RFWP, RE_RFMD_LLC, RE_RFCO; RE_PINO_PERSONAL is added
LOCAL_ADMIN_TO_AWS_ACCOUNT = ("admin", "rfone")      # the only local account (the Product Owner) -> AWS account
# Plan §3 — local Source -> AWS Source (None: added); the local 3144 card is split by `Card`.
SOURCE_MAP = {1: 11, 2: 10, 3: 9, 4: 8, 5: 2, 6: 6, 7: 5, 8: 13, 10: 3, 11: 1, 12: 12, 13: None}
SPLIT_SOURCE, SPLIT_BY_CARD, SPLIT_DEFAULT = 9, {"2270": 12}, 7
SOURCE_DIGITS = {1: "0214", 2: "0336", 3: "1057", 4: "1562", 5: "9318", 6: "3376", 7: "3583", 8: "2915",
                 9: "3144", 10: "8076", 11: "7470", 12: "2270"}
CUTOFF = "2026-01-01"


class Refusal(Exception):
    pass


def norm(text):
    return re.sub(r"\s+", " ", (text or "").upper()).strip()


# --------------------------------------------------------------------------- connections

def secret_url() -> str:
    import boto3
    s = boto3.Session(profile_name=PROFILE, region_name=REGION)
    if s.client("sts").get_caller_identity()["Account"] != EXPECTED_ACCOUNT:
        raise Refusal("not the expected AWS account")
    raw = s.client("secretsmanager").get_secret_value(SecretId=SECRET)["SecretString"].strip()
    try:
        d = json.loads(raw)
        raw = d.get("url") or d.get("DATABASE_URL") or next(v for v in d.values() if isinstance(v, str) and "://" in v)
    except (ValueError, StopIteration):
        pass
    return raw.strip()


def target_url(target: str) -> str:
    live = secret_url()
    if urlsplit(live).path != "/" + LIVE_DB:
        raise Refusal("the secret does not name the live database")
    if target == "live":
        return live
    if not target.startswith(DISPOSABLE_PREFIX):
        raise Refusal("target must be 'live' or a disposable rfone_pgval_* database")
    return urlunsplit(urlsplit(live)._replace(path="/" + target))


def local_copy(path: str) -> str:
    """A private copy of the local database, upgraded to the release's revision. The working
    database itself is never opened for writing."""
    tmp = os.path.join(tempfile.mkdtemp(prefix="bank_transfer_"), "local_copy.db")
    src = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    dst = sqlite3.connect(tmp)
    src.backup(dst)
    src.close()
    dst.close()
    from rfone_data_store.database import run_migrations_to_head
    run_migrations_to_head(f"sqlite:///{tmp.replace(os.sep, '/')}")
    return tmp


# --------------------------------------------------------------------------- helpers

def rows(conn, sql, **params):
    return [dict(r._mapping) for r in conn.execute(sa.text(sql), params)]


def insert(conn, table, row: dict) -> int:
    cols = [c for c in row if c != "id"]
    sql = f'INSERT INTO "{table}" ({",".join(chr(34) + c + chr(34) for c in cols)}) ' \
          f'VALUES ({",".join(":" + c for c in cols)}) RETURNING id'
    return conn.execute(sa.text(sql), {c: row[c] for c in cols}).scalar()


def table_hash(conn, table, where="") -> str:
    h = hashlib.sha256()
    for r in conn.execute(sa.text(f'SELECT * FROM "{table}" {where} ORDER BY 1')):
        h.update(repr(tuple(r)).encode())
    return h.hexdigest()


def coerce(conn, table, row: dict) -> dict:
    """SQLite gives booleans as 0/1 and timestamps as text; let PostgreSQL see real types."""
    types = TYPES.setdefault(table, {c["name"]: str(c["type"]).upper() for c in sa.inspect(conn).get_columns(table)})
    out = {}
    for k, v in row.items():
        if k not in types:
            continue
        if v is not None and "BOOL" in types[k]:
            v = bool(v)
        out[k] = v
    return out


TYPES: dict[str, dict[str, str]] = {}


# --------------------------------------------------------------------------- the transfer

def run(local_path: str, target: str, apply: bool, fill_from_aws: bool) -> dict:
    copy = local_copy(local_path)
    L = sqlite3.connect(copy)
    L.row_factory = sqlite3.Row
    lq = lambda sql, *a: [dict(r) for r in L.execute(sql, a)]  # noqa: E731
    if lq("select version_num from alembic_version")[0]["version_num"] != REVISION:
        raise Refusal("the local copy is not at the release revision")

    engine = sa.create_engine(target_url(target))
    report: dict = {"target": target, "applied": False, "checks": []}
    with engine.connect() as A:
        trans = A.begin()
        try:
            if [r["version_num"] for r in rows(A, "select version_num from alembic_version")] != [REVISION]:
                raise Refusal("the AWS database is not at the release revision")
            if rows(A, "select count(*) n from bank_ai_rules")[0]["n"]:
                raise Refusal("AI rules already present on AWS: the transfer already ran")

            other_tables = [t for t in sa.inspect(A).get_table_names() if not t.startswith(("bank_",))
                            and t not in ("financial_transactions", "raw_bank_transactions", "payment_instruments",
                                          "reporting_entities", "alembic_version")]
            before_other = {t: table_hash(A, t) for t in other_tables}
            before_history = (table_hash(A, "financial_transactions", f"WHERE posting_date < '{CUTOFF}'"),
                              rows(A, f"select count(*) n from financial_transactions where posting_date < '{CUTOFF}'")[0]["n"])
            aws_ft_before = rows(A, "select count(*) n from financial_transactions")[0]["n"]
            aws_expl_before = rows(A, "select count(*) n from bank_transaction_explanations")[0]["n"]

            # ---- accounts
            local_admin = lq("select id, username from rfone_accounts")
            if [a["username"] for a in local_admin] != [LOCAL_ADMIN_TO_AWS_ACCOUNT[0]]:
                raise Refusal("the local accounts are not the expected single 'admin'")
            aws_admin = rows(A, "select id from rfone_accounts where username=:u", u=LOCAL_ADMIN_TO_AWS_ACCOUNT[1])[0]["id"]
            acc = lambda v: None if v is None else aws_admin  # noqa: E731

            # ---- Legal / Reporting Entities (plan §2)
            le = lambda v: None if v is None else LEGAL_ENTITY_MAP[v]  # noqa: E731
            re_map = dict(REPORTING_ENTITY_MAP)
            for lr in lq("select * from reporting_entities"):
                if lr["id"] in re_map:
                    aws_re = rows(A, "select legal_entity_id from reporting_entities where id=:i", i=re_map[lr["id"]])[0]
                    if aws_re["legal_entity_id"] != le(lr["legal_entity_id"]):
                        raise Refusal(f"reporting entity {lr['code']}: Legal Entity does not match the map")
                    A.execute(sa.text("update reporting_entities set code=:c, name=:n, updated_at=now() where id=:i"),
                              {"c": lr["code"], "n": lr["name"], "i": re_map[lr["id"]]})
                else:
                    re_map[lr["id"]] = insert(A, "reporting_entities", coerce(A, "reporting_entities", dict(
                        lr, legal_entity_id=le(lr["legal_entity_id"]), reporting_group_id=None)))
            rem = lambda v: None if v is None else re_map[v]  # noqa: E731

            # ---- Sources (plan §3)
            aws_src = {r["id"]: r for r in rows(A, "select * from payment_instruments")}
            src_map: dict[int, int] = {}
            for ls in lq("select * from payment_instruments order by id"):
                target_id = SOURCE_MAP.get(ls["id"], "missing")
                if target_id == "missing" and ls["id"] != SPLIT_SOURCE:
                    raise Refusal(f"local Source #{ls['id']} has no mapping")
                if ls["id"] == SPLIT_SOURCE:
                    src_map[ls["id"]] = SPLIT_DEFAULT
                    continue
                if target_id is None:
                    src_map[ls["id"]] = None  # inserted below, after the links are known
                    continue
                digits = SOURCE_DIGITS.get(ls["id"])
                if digits and ls["last_four"] not in (digits, None) and ls["external_account_identifier"] != digits:
                    raise Refusal(f"local Source #{ls['id']} digits changed")
                src_map[ls["id"]] = target_id
            for ls in lq("select * from payment_instruments where id=?", 13):
                src_map[13] = insert(A, "payment_instruments", coerce(A, "payment_instruments", dict(
                    ls, legal_entity_id=le(ls["legal_entity_id"]), linked_instrument_id=None,
                    owner_reporting_entity_id=rem(ls["owner_reporting_entity_id"]),
                    replaced_by_instrument_id=None, source_system_id=None)))
            sm = lambda v: None if v is None else src_map[v]  # noqa: E731
            for ls in lq("select * from payment_instruments order by id"):
                ids = [SPLIT_DEFAULT, *SPLIT_BY_CARD.values()] if ls["id"] == SPLIT_SOURCE else [src_map[ls["id"]]]
                for aid in ids:
                    fields = {"display_name": ls["display_name"], "legal_entity_id": le(ls["legal_entity_id"]),
                              "owner_reporting_entity_id": rem(ls["owner_reporting_entity_id"]),
                              "linked_instrument_id": sm(ls["linked_instrument_id"]), "status": ls["status"],
                              "institution": ls["institution"] or aws_src.get(aid, {}).get("institution"),
                              "external_account_identifier": ls["external_account_identifier"]
                              or aws_src.get(aid, {}).get("external_account_identifier")}
                    if ls["id"] == SPLIT_SOURCE:  # the AWS split cards keep their own names and digits
                        fields.pop("display_name")
                    else:
                        fields["last_four"] = ls["last_four"] or aws_src.get(aid, {}).get("last_four")
                    A.execute(sa.text("update payment_instruments set " + ", ".join(f"{k}=:{k}" for k in fields)
                                      + ", updated_at=now() where id=:id"), dict(fields, id=aid))
            # settlement accounts: AWS rows kept (same pairs, earlier start); the local-only card gets its own
            for s in lq("select * from bank_card_settlement_accounts where credit_card_payment_instrument_id=13"):
                insert(A, "bank_card_settlement_accounts", coerce(A, "bank_card_settlement_accounts", dict(
                    s, credit_card_payment_instrument_id=src_map[13],
                    settlement_bank_account_id=sm(s["settlement_bank_account_id"]),
                    created_by_account_id=acc(s["created_by_account_id"]))))
            for h in lq("select * from bank_card_holder_assignments"):
                card = h["credit_card_payment_instrument_id"]
                insert(A, "bank_card_holder_assignments", coerce(A, "bank_card_holder_assignments", dict(
                    h, credit_card_payment_instrument_id=SPLIT_DEFAULT if card == SPLIT_SOURCE else sm(card),
                    holder_acting_identity_id=None, holder_employee_id=None,
                    created_by_account_id=acc(h["created_by_account_id"]))))

            # ---- catalogues: WHAT and groups by code (identical), WHY by code, WHO by name
            ac_map = {r["id"]: r["code"] for r in lq("select id, code from bank_accounting_classifications")}
            aws_ac = {r["code"]: r["id"] for r in rows(A, "select id, code from bank_accounting_classifications")}
            acm = lambda v: None if v is None else aws_ac[ac_map[v]]  # noqa: E731
            grp = {r["id"]: r["code"] for r in lq("select id, code from bank_reason_groups")}
            aws_grp = {r["code"]: r["id"] for r in rows(A, "select id, code from bank_reason_groups")}
            aws_why = {r["code"]: r["id"] for r in rows(A, "select id, code from bank_transaction_reasons")}
            why_map = {}
            for w in lq("select * from bank_transaction_reasons"):
                fields = dict(name=w["name"], description=w["description"], status=w["status"],
                              accounting_classification_id=acm(w["accounting_classification_id"]),
                              reason_group_id=None if w["reason_group_id"] is None else aws_grp[grp[w["reason_group_id"]]])
                if w["code"] in aws_why:
                    why_map[w["id"]] = aws_why[w["code"]]
                    A.execute(sa.text("update bank_transaction_reasons set " + ", ".join(f"{k}=:{k}" for k in fields)
                                      + ", updated_at=now() where id=:id"), dict(fields, id=why_map[w["id"]]))
                else:
                    why_map[w["id"]] = insert(A, "bank_transaction_reasons", coerce(A, "bank_transaction_reasons",
                                                                                    dict(w, **fields)))
            wm = lambda v: None if v is None else why_map[v]  # noqa: E731
            types = {r["id"]: r["code"] for r in lq("select id, code from bank_occurrence_types")}
            aws_types = {r["code"]: r["id"] for r in rows(A, "select id, code from bank_occurrence_types")}
            aws_who = collections.defaultdict(list)
            for r in rows(A, "select id, canonical_name from bank_occurrences order by id"):
                aws_who[norm(r["canonical_name"])].append(r["id"])
            who_map = {}
            for o in lq("select * from bank_occurrences"):
                fields = dict(status=o["status"], manual_only=bool(o["manual_only"]),
                              category_capability=o["category_capability"],
                              default_transaction_reason_id=wm(o["default_transaction_reason_id"]),
                              occurrence_type_id=aws_types[types[o["occurrence_type_id"]]])
                if aws_who.get(norm(o["canonical_name"])):
                    who_map[o["id"]] = aws_who[norm(o["canonical_name"])][0]
                    A.execute(sa.text("update bank_occurrences set " + ", ".join(f"{k}=:{k}" for k in fields)
                                      + ", updated_at=now() where id=:id"), dict(fields, id=who_map[o["id"]]))
                else:
                    who_map[o["id"]] = insert(A, "bank_occurrences", coerce(A, "bank_occurrences", dict(o, **fields)))
            om = lambda v: None if v is None else who_map[v]  # noqa: E731

            # ---- movements: match the local 2026 movements on the mapped Source
            card_of = {r["normalized_transaction_id"]: (json.loads(r["raw_fields"]) or {}).get("Card")
                       for r in lq("select normalized_transaction_id, raw_fields from raw_bank_transactions")}

            def aws_source(t):
                if t["payment_instrument_id"] == SPLIT_SOURCE:
                    return SPLIT_BY_CARD.get(card_of.get(t["id"]) or "", SPLIT_DEFAULT)
                return sm(t["payment_instrument_id"])

            key = lambda src, t: (src, str(t["posting_date"])[:10], t["amount_minor"], norm(t["description_original"]))  # noqa: E731
            aws_by_key = collections.defaultdict(list)
            for t in rows(A, f"select * from financial_transactions where posting_date >= '{CUTOFF}' order by id"):
                aws_by_key[key(t["payment_instrument_id"], t)].append(t)
            local_ft = lq(f"select * from financial_transactions where posting_date >= '{CUTOFF}' order by id")
            if len(local_ft) != len(lq("select id from financial_transactions")):
                raise Refusal("the local Bank holds movements before 2026: not in this plan")
            ft_map, new_local, matched = {}, [], {}
            for t in local_ft:
                bucket = aws_by_key.get(key(aws_source(t), t))
                if bucket:
                    a = bucket.pop(0)
                    ft_map[t["id"]] = a["id"]
                    matched[t["id"]] = a
                else:
                    new_local.append(t)

            # the 130 new movements: their files, their raw rows, the movements
            batch_map = {}
            for b in lq("select * from bank_import_batches where id in (%s)" % ",".join(
                    str(i) for i in {t["import_batch_id"] for t in new_local if t["import_batch_id"]} or {0})):
                existing = rows(A, "select id from bank_import_batches where sha256=:s", s=b["sha256"])
                batch_map[b["id"]] = existing[0]["id"] if existing else insert(
                    A, "bank_import_batches", coerce(A, "bank_import_batches", dict(
                        b, payment_instrument_id=SPLIT_DEFAULT if b["payment_instrument_id"] == SPLIT_SOURCE
                        else sm(b["payment_instrument_id"]), uploaded_by_account_id=acc(b["uploaded_by_account_id"]))))
            for t in new_local:
                ft_map[t["id"]] = insert(A, "financial_transactions", coerce(A, "financial_transactions", dict(
                    t, payment_instrument_id=aws_source(t), import_batch_id=batch_map.get(t["import_batch_id"]),
                    accounting_settlement_account_id=sm(t["accounting_settlement_account_id"]),
                    accounting_canonical_transaction_id=None, duplicate_of_transaction_id=None,
                    explanation_id=None, source_system_id=None)))
                for r in lq("select * from raw_bank_transactions where normalized_transaction_id=?", t["id"]):
                    insert(A, "raw_bank_transactions", coerce(A, "raw_bank_transactions", dict(
                        r, import_batch_id=batch_map.get(r["import_batch_id"]),
                        normalized_transaction_id=ft_map[t["id"]])))

            # ---- decisions: every local explanation, re-pointed; the current one becomes current on AWS
            expl_map, filled, conflicts = {}, collections.Counter(), []
            aws_current = {a["id"]: a for a in rows(A, "select e.* from bank_transaction_explanations e join "
                                                     "financial_transactions t on t.explanation_id = e.id")}
            current_local = {t["id"]: t["explanation_id"] for t in local_ft if t["explanation_id"]}
            for e in lq("select * from bank_transaction_explanations order by id"):
                ft_local = e["financial_transaction_id"]
                row = dict(e, financial_transaction_id=ft_map[ft_local], occurrence_id=om(e["occurrence_id"]),
                           transaction_reason_id=wm(e["transaction_reason_id"]), recognition_rule_id=None,
                           reconciliation_standard_id=None, confirmed_by_account_id=acc(e["confirmed_by_account_id"]),
                           accounting_classification_id=acm(e["accounting_classification_id"]))
                is_current = current_local.get(ft_local) == e["id"]
                aws_now = aws_current.get(matched[ft_local]["explanation_id"]) if ft_local in matched and \
                    matched[ft_local]["explanation_id"] else None
                if is_current and aws_now is not None:
                    if row["occurrence_id"] and aws_now["occurrence_id"] and row["occurrence_id"] != aws_now["occurrence_id"]:
                        conflicts.append(("WHO", ft_map[ft_local]))
                    if row["transaction_reason_id"] and aws_now["transaction_reason_id"] and \
                            row["transaction_reason_id"] != aws_now["transaction_reason_id"]:
                        conflicts.append(("WHY", ft_map[ft_local]))
                    if fill_from_aws and row["occurrence_id"] is None and aws_now["occurrence_id"]:
                        row.update(occurrence_id=aws_now["occurrence_id"],
                                   occurrence_name_snapshot=aws_now["occurrence_name_snapshot"])
                        filled["WHO"] += 1
                    if fill_from_aws and row["transaction_reason_id"] is None and aws_now["transaction_reason_id"]:
                        for k in ("transaction_reason_id", "transaction_reason_name_snapshot",
                                  "accounting_classification_id", "accounting_classification_code_snapshot",
                                  "accounting_classification_name_snapshot", "accounting_statement_type_snapshot",
                                  "food_cost_snapshot", "operative_snapshot", "deductible_snapshot", "what_label_snapshot",
                                  "accounting_destination_source"):
                            row[k] = aws_now.get(k)
                        filled["WHY"] += 1
                    if (row["occurrence_id"] != om(e["occurrence_id"])
                            or row["transaction_reason_id"] != wm(e["transaction_reason_id"])):
                        row["explanation_notes"] = ((e["explanation_notes"] or "") +
                                                    f" [BANK_AWS_001 transfer: value kept from AWS decision #{aws_now['id']}]").strip()
                expl_map[e["id"]] = insert(A, "bank_transaction_explanations",
                                           coerce(A, "bank_transaction_explanations", row))
                if is_current:
                    A.execute(sa.text("update financial_transactions set explanation_id=:e where id=:t"),
                              {"e": expl_map[e["id"]], "t": ft_map[ft_local]})
            # Local state prevails, also when it is empty (Product Owner, 2026-10-13): a matched AWS movement the
            # local Bank has not decided gets no current decision; its AWS decision stays in the history.
            cleared = 0
            if not fill_from_aws:
                for lt_id, a in matched.items():
                    if lt_id not in current_local and a["explanation_id"] is not None:
                        A.execute(sa.text("update financial_transactions set explanation_id=NULL where id=:t"),
                                  {"t": a["id"]})
                        cleared += 1
            report["matched_aws_decision_kept_as_history_only"] = cleared

            # ---- possible duplicates on AWS: kept; those no balance proves distinct are "Da verificare"
            from rfone_data_store.bank_reconciliation.service import distinct_proof
            flagged = 0
            groups = collections.defaultdict(list)
            for t in rows(A, f"select * from financial_transactions where posting_date >= '{CUTOFF}' order by id"):
                groups[key(t["payment_instrument_id"], t)].append(t)
            for g in groups.values():
                for t in g[1:]:
                    if t["duplicate_status"] in (None, "NONE") and distinct_proof(
                            t["balance_minor"], t["reference"], g[0]["balance_minor"], g[0]["reference"]) is None:
                        A.execute(sa.text("update financial_transactions set duplicate_status='CANDIDATE_DUPLICATE', "
                                          "duplicate_of_transaction_id=:o where id=:i"), {"o": g[0]["id"], "i": t["id"]})
                        flagged += 1

            # ---- AI work: instructions, interpretations, rules, versions, applications and their items
            for i in lq("select * from bank_ai_instructions"):
                insert(A, "bank_ai_instructions", coerce(A, "bank_ai_instructions",
                                                         dict(i, created_by_account_id=acc(i["created_by_account_id"]))))
            # A local reset (BANK_RULES_RESET_001) suffixed invalidated keys beyond the 64 characters PostgreSQL
            # holds. Kept as history under a key that can never match a lookup (lookups are 64 hex digits).
            def interp_row(i):
                if len(i["cache_key"]) > 64:
                    i = dict(i, cache_key="x" + hashlib.sha256(i["cache_key"].encode()).hexdigest()[:63])
                    report["interpretations_rekeyed_as_history"] = report.get("interpretations_rekeyed_as_history", 0) + 1
                return coerce(A, "bank_ai_rule_interpretations", i)
            interp_map = {i["id"]: insert(A, "bank_ai_rule_interpretations", interp_row(i))
                          for i in lq("select * from bank_ai_rule_interpretations")}
            rule_map = {r["id"]: insert(A, "bank_ai_rules", coerce(A, "bank_ai_rules", dict(
                r, origin_transaction_id=ft_map.get(r["origin_transaction_id"]),
                created_by_account_id=acc(r["created_by_account_id"]),
                deleted_by_account_id=acc(r["deleted_by_account_id"])))) for r in lq("select * from bank_ai_rules")}
            version_map = {v["id"]: insert(A, "bank_ai_rule_versions", coerce(A, "bank_ai_rule_versions", dict(
                v, rule_id=rule_map[v["rule_id"]], interpretation_id=interp_map.get(v["interpretation_id"]),
                created_by_account_id=acc(v["created_by_account_id"])))) for v in lq("select * from bank_ai_rule_versions")}
            app_map = {a["id"]: insert(A, "bank_ai_rule_applications", coerce(A, "bank_ai_rule_applications", dict(
                a, rule_id=rule_map[a["rule_id"]], version_id=version_map.get(a["version_id"]), preview_id=None,
                import_batch_id=batch_map.get(a["import_batch_id"]),
                created_by_account_id=acc(a["created_by_account_id"])))) for a in lq("select * from bank_ai_rule_applications")}
            for it in lq("select * from bank_ai_rule_application_items"):
                insert(A, "bank_ai_rule_application_items", coerce(A, "bank_ai_rule_application_items", dict(
                    it, application_id=app_map[it["application_id"]],
                    financial_transaction_id=ft_map.get(it["financial_transaction_id"]),
                    explanation_id=expl_map.get(it["explanation_id"]))))

            # ---- checks (all must hold before COMMIT)
            def check(name, ok, detail=""):
                report["checks"].append({"check": name, "ok": bool(ok), "detail": str(detail)[:300]})

            check("every local 2026 movement is on AWS (matched or added)", len(ft_map) == len(local_ft),
                  f"{len(ft_map)}/{len(local_ft)}")
            check("matched / added", True, f"{len(matched)} matched, {len(new_local)} added")
            check("AWS history before 2026 unchanged",
                  (table_hash(A, "financial_transactions", f"WHERE posting_date < '{CUTOFF}'"),
                   rows(A, f"select count(*) n from financial_transactions where posting_date < '{CUTOFF}'")[0]["n"])
                  == before_history)
            check("no AWS movement deleted", rows(A, "select count(*) n from financial_transactions")[0]["n"]
                  == aws_ft_before + len(new_local))
            check("no AWS decision deleted", rows(A, "select count(*) n from bank_transaction_explanations")[0]["n"]
                  == aws_expl_before + len(expl_map))
            mismatch = []
            for lt, ae in ((t, ft_map[t["id"]]) for t in local_ft if t["explanation_id"]):
                cur = rows(A, "select e.occurrence_id, e.transaction_reason_id from financial_transactions t "
                              "join bank_transaction_explanations e on e.id=t.explanation_id where t.id=:i", i=ae)
                le_ = lq("select occurrence_id, transaction_reason_id from bank_transaction_explanations where id=?",
                         lt["explanation_id"])[0]
                want_who, want_why = om(le_["occurrence_id"]), wm(le_["transaction_reason_id"])
                if not cur or (want_who and cur[0]["occurrence_id"] != want_who) or \
                        (want_why and cur[0]["transaction_reason_id"] != want_why):
                    mismatch.append(ae)
            check("every local current decision is the current decision on AWS", not mismatch, mismatch[:10])
            if not fill_from_aws:
                exact = []
                for lt_id, a in matched.items():
                    cur = rows(A, "select e.occurrence_id o, e.transaction_reason_id r from financial_transactions t "
                                  "left join bank_transaction_explanations e on e.id=t.explanation_id where t.id=:i", i=a["id"])[0]
                    le_ = lq("select occurrence_id o, transaction_reason_id r from bank_transaction_explanations where id=?",
                             current_local[lt_id])[0] if lt_id in current_local else {"o": None, "r": None}
                    if (cur["o"], cur["r"]) != (om(le_["o"]), wm(le_["r"])):
                        exact.append(a["id"])
                check("matched movements: WHO and WHY exactly the local ones, empty included", not exact, exact[:10])
                prev = {a["explanation_id"] for a in matched.values() if a["explanation_id"]}
                kept = rows(A, "select count(*) n from bank_transaction_explanations where id = any(:ids)", ids=list(prev))[0]["n"]
                check("the previous AWS decisions of the matched movements are kept as history", kept == len(prev),
                      f"{kept}/{len(prev)}")
            aws_only_ids = [t["id"] for b in aws_by_key.values() for t in b]
            check("AWS-only 2026 movements keep their decision",
                  all(rows(A, "select explanation_id e from financial_transactions where id=:i", i=i)[0]["e"] == t_e
                      for i, t_e in ((t["id"], t["explanation_id"]) for b in aws_by_key.values() for t in b)),
                  len(aws_only_ids))
            check("other Domains' tables unchanged",
                  all(table_hash(A, t) == h for t, h in before_other.items()),
                  [t for t, h in before_other.items() if table_hash(A, t) != h][:10])
            check("AI work transferred", (len(rule_map), len(version_map), len(interp_map), len(app_map)) ==
                  (len(lq("select id from bank_ai_rules")), len(lq("select id from bank_ai_rule_versions")),
                   len(lq("select id from bank_ai_rule_interpretations")), len(lq("select id from bank_ai_rule_applications"))))
            report.update(filled_from_aws=dict(filled), conflicts=conflicts, flagged_possible_duplicates=flagged,
                          source_map={str(k): v for k, v in src_map.items()},
                          reporting_entity_map={str(k): v for k, v in re_map.items()},
                          who_added=sum(1 for k, v in who_map.items() if v not in sum(aws_who.values(), [])),
                          why_added=sum(1 for v in why_map.values() if v not in aws_why.values()))
            # sequences past the rows written
            for t in ("reporting_entities", "payment_instruments", "bank_card_settlement_accounts",
                      "bank_card_holder_assignments", "bank_transaction_reasons", "bank_occurrences",
                      "bank_import_batches", "financial_transactions", "raw_bank_transactions",
                      "bank_transaction_explanations", "bank_ai_instructions", "bank_ai_rule_interpretations",
                      "bank_ai_rules", "bank_ai_rule_versions", "bank_ai_rule_applications",
                      "bank_ai_rule_application_items"):
                A.execute(sa.text(f"select setval(pg_get_serial_sequence('{t}','id'), "
                                  f"coalesce((select max(id) from \"{t}\"), 0) + 1, false)"))
            if not all(c["ok"] for c in report["checks"]):
                raise Refusal("a check failed: " + "; ".join(c["check"] for c in report["checks"] if not c["ok"]))
            if apply:
                trans.commit()
                report["applied"] = True
            else:
                trans.rollback()
        except Exception:
            trans.rollback()
            raise
    shutil.rmtree(os.path.dirname(copy), ignore_errors=True)
    return report


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--local", required=True, help="path of a COPY of the local Bank rfone.db (read only)")
    p.add_argument("--target", required=True, help="'live' or a disposable rfone_pgval_* database")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--confirm-live", action="store_true")
    p.add_argument("--fill-from-aws", action="store_true",
                   help="NOT the Product Owner's choice (2026-10-13): kept only for comparison")
    a = p.parse_args()
    if a.target == "live" and a.apply and not a.confirm_live:
        print("REFUSED: writing to the live database also requires --confirm-live.")
        return 2
    try:
        report = run(a.local, a.target, a.apply, fill_from_aws=a.fill_from_aws)
    except Refusal as exc:
        print("REFUSED:", exc)
        return 2
    print(json.dumps(report, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
