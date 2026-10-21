"""Experimental store (decision 57): the only place C-Bank writes.

A separate SQLite file outside OneDrive and outside the Bank folder. Every
record is marked experimental by living here; nothing is copied back to Bank.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from . import config

SCHEMA = """
create table if not exists runs (
  id integer primary key, created_at text not null, label text not null,
  scope_json text not null, summary_json text);
create table if not exists results (
  run_id integer not null, txn_id integer not null, status text not null,
  payload_json text not null, primary key (run_id, txn_id));
create table if not exists human_decisions (
  id integer primary key, txn_id integer not null, who_name text, beneficiary_id integer,
  why_id integer, category_id integer, note text, created_at text not null,
  active integer not null default 1);
create table if not exists investigations (
  id integer primary key, group_key text not null, txn_ids_json text not null,
  provider text not null, prompt text not null, answer_json text, error text,
  created_at text not null);
create table if not exists conversations (
  id integer primary key, txn_id integer not null, role text not null, text text not null,
  payload_json text, created_at text not null);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path=None) -> sqlite3.Connection:
    path = path or config.STORE_DB
    if str(path) != ":memory:":
        config.STORE_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path), check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


# -- runs / results ---------------------------------------------------------

def save_run(con, label: str, scope: dict, results: list[dict], summary: dict) -> int:
    cur = con.execute("insert into runs(created_at,label,scope_json,summary_json) values(?,?,?,?)",
                      (now(), label, json.dumps(scope), json.dumps(summary)))
    run_id = cur.lastrowid
    con.executemany("insert into results(run_id,txn_id,status,payload_json) values(?,?,?,?)",
                    [(run_id, r["txn_id"], r["status"], json.dumps(r, default=str)) for r in results])
    con.commit()
    return run_id


def runs(con) -> list[dict]:
    return [dict(r) | {"summary": json.loads(r["summary_json"] or "{}")}
            for r in con.execute("select * from runs order by id desc limit 50")]


def run(con, run_id: int) -> dict | None:
    r = con.execute("select * from runs where id=?", (run_id,)).fetchone()
    return dict(r) | {"summary": json.loads(r["summary_json"] or "{}"),
                      "scope": json.loads(r["scope_json"])} if r else None


def results(con, run_id: int) -> list[dict]:
    return [json.loads(r["payload_json"]) for r in
            con.execute("select payload_json from results where run_id=? order by txn_id", (run_id,))]


# -- human decisions (experimental, protected inside C-Bank) ---------------

def human_decisions(con) -> dict[int, dict]:
    rows = con.execute("select * from human_decisions where active=1 order by id")
    return {r["txn_id"]: dict(r) for r in rows}


def save_human_decision(con, txn_id: int, *, who_name, beneficiary_id, why_id, category_id, note) -> int:
    con.execute("update human_decisions set active=0 where txn_id=? and active=1", (txn_id,))
    cur = con.execute(
        "insert into human_decisions(txn_id,who_name,beneficiary_id,why_id,category_id,note,created_at)"
        " values(?,?,?,?,?,?,?)", (txn_id, who_name, beneficiary_id, why_id, category_id, note, now()))
    con.commit()
    return cur.lastrowid


def decision_history(con, txn_id: int) -> list[dict]:
    return [dict(r) for r in con.execute("select * from human_decisions where txn_id=? order by id", (txn_id,))]


# -- AI investigations ------------------------------------------------------

def save_investigation(con, group_key, txn_ids, provider, prompt, answer=None, error=None) -> int:
    cur = con.execute(
        "insert into investigations(group_key,txn_ids_json,provider,prompt,answer_json,error,created_at)"
        " values(?,?,?,?,?,?,?)",
        (group_key, json.dumps(txn_ids), provider, prompt, json.dumps(answer) if answer else None, error, now()))
    con.commit()
    return cur.lastrowid


def investigation_answers(con) -> dict[int, dict]:
    """Latest successful AI answer per transaction id."""
    out: dict[int, dict] = {}
    for r in con.execute("select * from investigations where answer_json is not null order by id"):
        answer = json.loads(r["answer_json"])
        for item in answer.get("transactions", []):
            if isinstance(item, dict) and isinstance(item.get("id"), int):
                out[item["id"]] = dict(item, investigation_id=r["id"], group_key=r["group_key"],
                                       group_summary=answer.get("summary"), created_at=r["created_at"])
    return out


# -- conversations ----------------------------------------------------------

def add_message(con, txn_id: int, role: str, text: str, payload=None) -> None:
    con.execute("insert into conversations(txn_id,role,text,payload_json,created_at) values(?,?,?,?,?)",
                (txn_id, role, text, json.dumps(payload) if payload else None, now()))
    con.commit()


def messages(con, txn_id: int) -> list[dict]:
    return [dict(r) for r in con.execute("select role,text,payload_json,created_at from conversations"
                                         " where txn_id=? order by id", (txn_id,))]
