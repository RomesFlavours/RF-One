"""The engine's records, in the ONE operational Bank database (Bank unification Phase 3A).

Since Phase 3A there is no separate store: the engine writes only its own records into the Bank database —
runs and per-movement results (`bank_engine_runs`, `bank_engine_results`, migration e3a120261024), matched
transfers and card settlements (`financial_transaction_matches`, method ENGINE) and AI investigations and
conversations (`bank_flow_artifacts`). It never writes a classification: a human decision is recorded only
through Bank's own manual decision service (`legacy.record_human_decision`), and Bank's human decisions are
read from `bank_transaction_explanations`.

`connect(":memory:")` gives tests the same tables in memory.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from . import config

INVESTIGATION, CONVERSATION = "ENGINE_INVESTIGATION", "ENGINE_CONVERSATION"

# The engine's tables as the migration creates them (only the columns the engine uses), for in-memory tests.
MEMORY_SCHEMA = """
create table bank_engine_runs (
  id integer primary key, created_at text not null, label text not null, scope_json text not null,
  summary_json text, origin text not null default 'ENGINE', origin_run_id integer);
create table bank_engine_results (
  run_id integer not null, financial_transaction_id integer not null, status text not null,
  payload_json text not null, primary key (run_id, financial_transaction_id));
create table financial_transaction_matches (
  id integer primary key, transaction_a_id integer not null, transaction_b_id integer not null,
  match_type text not null, match_method text not null, match_basis text, matched_amount_minor integer not null,
  confirmed_by text, created_at text default current_timestamp, relationship text, posting_transaction_id integer,
  first_engine_run_id integer, last_engine_run_id integer, unique (transaction_a_id, transaction_b_id));
create table bank_flow_artifacts (
  id integer primary key, kind text not null, payload text not null, account_id integer,
  created_at text default current_timestamp);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path=None) -> sqlite3.Connection:
    path = str(path or config.BANK_DB)
    con = sqlite3.connect(path, check_same_thread=False, timeout=30)
    con.row_factory = sqlite3.Row
    if path == ":memory:":
        con.executescript(MEMORY_SCHEMA)
    else:
        con.execute("PRAGMA busy_timeout = 30000")
    return con


# -- runs / results ---------------------------------------------------------

def _insert_results(con, run_id: int, results: list[dict]) -> None:
    con.executemany("insert into bank_engine_results(run_id,financial_transaction_id,status,payload_json) "
                    "values(?,?,?,?)",
                    [(run_id, r["txn_id"], r["status"], json.dumps(r, default=str)) for r in results])


def save_run(con, label: str, scope: dict, results: list[dict], summary: dict) -> int:
    cur = con.execute("insert into bank_engine_runs(created_at,label,scope_json,summary_json,origin) "
                      "values(?,?,?,?,'ENGINE')", (now(), label, json.dumps(scope), json.dumps(summary)))
    run_id = cur.lastrowid
    _insert_results(con, run_id, results)
    con.commit()
    return run_id


def update_summary(con, run_id: int, summary: dict) -> None:
    con.execute("update bank_engine_runs set summary_json=? where id=?", (json.dumps(summary), run_id))
    con.commit()


def replace_results(con, run_id: int, results: list[dict], summary: dict) -> None:
    """A re-evaluation of one run (decision 46): its results and summary, in one transaction."""
    con.execute("delete from bank_engine_results where run_id=?", (run_id,))
    _insert_results(con, run_id, results)
    con.execute("update bank_engine_runs set summary_json=? where id=?", (json.dumps(summary), run_id))
    con.commit()


def runs(con) -> list[dict]:
    return [dict(r) | {"summary": json.loads(r["summary_json"] or "{}")}
            for r in con.execute("select * from bank_engine_runs order by id desc limit 50")]


def run(con, run_id: int) -> dict | None:
    r = con.execute("select * from bank_engine_runs where id=?", (run_id,)).fetchone()
    return dict(r) | {"summary": json.loads(r["summary_json"] or "{}"),
                      "scope": json.loads(r["scope_json"])} if r else None


def results(con, run_id: int) -> list[dict]:
    return [json.loads(r["payload_json"]) for r in con.execute(
        "select payload_json from bank_engine_results where run_id=? order by financial_transaction_id", (run_id,))]


def previous_full_run(con, before_id: int | None = None) -> dict | None:
    row = con.execute("select * from bank_engine_runs where json_extract(scope_json,'$.kind')='all'"
                      + (" and id<?" if before_id else "") + " order by id desc limit 1",
                      ((before_id,) if before_id else ())).fetchone()
    return dict(row) | {"scope": json.loads(row["scope_json"])} if row else None


# -- matched legs (CARD_SETTLEMENT_001): one row per pair, idempotent -------

def record_matches(con, run_id: int, results: list[dict]) -> int:
    """Upsert every matched pair of this run (ordered pair = the existing unique key), keeping the run that
    first saw it; returns how many pairs are new. Re-running on the same data adds nothing and changes only
    `last_engine_run_id`. A pair recorded by another method (a person, the old matcher) is never touched."""
    new = 0
    for r in results:
        mt = r.get("match") or {}
        if mt.get("state") != "MATCHED":
            continue
        a, b = sorted((r["txn_id"], mt["counterpart_id"]))
        posting = r["txn_id"] if mt.get("posting") == "POSTED" else (mt["counterpart_id"] if mt.get("posting") else None)
        cur = con.execute(
            "insert or ignore into financial_transaction_matches(transaction_a_id,transaction_b_id,match_type,"
            "match_method,match_basis,matched_amount_minor,relationship,posting_transaction_id,first_engine_run_id,"
            "last_engine_run_id) values(?,?,?,'ENGINE',?,?,?,?,?,?)",
            (a, b, mt["kind"], mt["basis"], abs(r["amount_minor"]), mt.get("relationship"), posting, run_id, run_id))
        if cur.rowcount:
            new += 1
        else:
            con.execute("update financial_transaction_matches set last_engine_run_id=?, relationship=coalesce(?, relationship),"
                        " posting_transaction_id=coalesce(?, posting_transaction_id)"
                        " where transaction_a_id=? and transaction_b_id=? and match_method='ENGINE'",
                        (run_id, mt.get("relationship"), posting, a, b))
    con.commit()
    return new


def matched_pairs(con) -> list[dict]:
    return [dict(r) for r in con.execute(
        "select transaction_a_id txn_a, transaction_b_id txn_b, match_type kind, match_basis basis, relationship,"
        " posting_transaction_id posting_txn, first_engine_run_id first_run_id, last_engine_run_id last_run_id"
        " from financial_transaction_matches where match_method='ENGINE' order by 1, 2")]


# -- human decisions: Bank's own (one source) --------------------------------

def human_decisions(con) -> dict[int, dict]:
    """The movements whose CURRENT Bank decision was made by a person (one source of human decisions)."""
    from . import legacy
    return legacy.current_human_decisions()


def save_human_decision(con, txn_id: int, *, who_name, beneficiary_id, why_id, category_id, note,
                        associate: bool = False) -> int:
    """A person's decision, recorded through Bank's manual decision service (the same as Review). The WHAT
    derives from the WHY; the accounting subject is the Source owner (decision 86), so a management
    destination is not stored."""
    from . import legacy
    return legacy.record_human_decision(txn_id, who_name=who_name, why_id=why_id, category_id=category_id,
                                        note=note, associate=associate, beneficiary_id=beneficiary_id)


def decision_history(con, txn_id: int) -> list[dict]:
    from . import legacy
    return legacy.human_decision_history(txn_id)


# -- AI investigations and conversations (bank_flow_artifacts) -------------

def _artifact(con, kind: str, payload: dict) -> int:
    cur = con.execute("insert into bank_flow_artifacts(kind,payload,created_at) values(?,?,?)",
                      (kind, json.dumps(payload, default=str), now()))
    con.commit()
    return cur.lastrowid


def save_investigation(con, group_key, txn_ids, provider, prompt, answer=None, error=None) -> int:
    return _artifact(con, INVESTIGATION, dict(group_key=group_key, txn_ids=txn_ids, provider=provider,
                                              prompt=prompt, answer=answer, error=error))


def investigation_answers(con) -> dict[int, dict]:
    """Latest successful AI answer per transaction id."""
    out: dict[int, dict] = {}
    for r in con.execute("select id, payload, created_at from bank_flow_artifacts where kind=? order by id",
                         (INVESTIGATION,)):
        p = json.loads(r["payload"])
        answer = p.get("answer")
        if not answer:
            continue
        for item in answer.get("transactions", []):
            if isinstance(item, dict) and isinstance(item.get("id"), int):
                out[item["id"]] = dict(item, investigation_id=r["id"], group_key=p.get("group_key"),
                                       group_summary=answer.get("summary"), created_at=r["created_at"])
    return out


def add_message(con, txn_id: int, role: str, text: str, payload=None) -> None:
    _artifact(con, CONVERSATION, dict(txn_id=txn_id, role=role, text=text, payload=payload))


def messages(con, txn_id: int) -> list[dict]:
    out = []
    for r in con.execute("select payload, created_at from bank_flow_artifacts where kind=? "
                         "and json_extract(payload,'$.txn_id')=? order by id", (CONVERSATION, txn_id)):
        p = json.loads(r["payload"])
        out.append(dict(role=p.get("role"), text=p.get("text"),
                        payload_json=json.dumps(p["payload"]) if p.get("payload") else None, created_at=r["created_at"]))
    return out
