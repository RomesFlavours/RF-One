#!/usr/bin/env python
"""SELECTION_CV_STRUCTURE_READING_001 — the rule-based résumé reader keeps
each experience's job title, employer, dates and duties together, whatever
the layout.

ALL CANDIDATES BELOW ARE SYNTHETIC. Names, employers, places, contacts and
dates are invented for this test; no real résumé is used.

Covered:
  1. the same CV written three ways (title, employer and dates on one line;
     title + employer on one line and dates on the next; title, employer and
     dates on separate lines) yields the same experiences;
  2. the two layouts of the CV used in the Selection status review
     (2026-10-03): separate lines (A) and "Title, Employer" (B);
  3. duties stay attached to the experience they were written under, also
     when entries are not separated by blank lines;
  4. an incomplete CV: missing facts stay missing (None), nothing is
     invented, and missing information alone does not mark the reading as
     uncertain;
  5. an ambiguous layout (two header lines, no clue which is the employer)
     is shown as uncertain, raises a VERIFY flag about the reading and the
     import is PARTIAL, never COMPLETED;
  6. the original text behind every experience is kept (evidence snippet,
     raw résumé text).

Throwaway SQLite; the AI client is isolated, so no external service is
called. `python test_selection_cv_structure.py --dump` prints what the
reader extracts from each fixture.
"""

from __future__ import annotations

import os
import sys
import tempfile

_FD, _DB_PATH = tempfile.mkstemp(suffix=".db", prefix="selection_cv_structure_test_")
os.close(_FD)
os.remove(_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_DB_PATH.replace(os.sep, '/')}"

from rfone_data_store.database import (  # noqa: E402
    create_configured_engine, create_session_factory, run_migrations_to_head,
)
from rfone_data_store.selection.analysis import analyze_candidate  # noqa: E402
from rfone_data_store.selection.core import flags as flags_mod  # noqa: E402
from rfone_data_store.selection.core.resume_source import RawResumeRef as _Ref  # noqa: E402
from rfone_data_store.selection.import_pipeline import COMPLETED, PARTIAL, import_one_resume  # noqa: E402
from rfone_data_store.selection.normalization import normalize_profile  # noqa: E402
from rfone_data_store.selection.parsing.ai_test_isolation import isolated_ai_client  # noqa: E402
from rfone_data_store.selection.parsing.deterministic_parser import DeterministicResumeParser  # noqa: E402

HEADER = """Alex Synthetic
alex.synthetic@example.test | +1 555 0100 | Hamilton, ON
"""
EDUCATION = """
EDUCATION
Niagara College
Hospitality Diploma
2015 - 2017
"""

# --- 1. one CV, three layouts ---------------------------------------------
SAME_ONE_LINE = HEADER + """
EXPERIENCE
Team Leader, Trattoria Esempio, Hamilton, ON | Mar 2022 - Present
- Coordinated a team of 6 servers per shift
- Trained new hires on service standards

Floor Supervisor, Bistro Prova, Toronto, ON | Jan 2020 - Feb 2022
- Supervised dining room staff during dinner service

Server, Cafe Campione, Toronto, ON | Jun 2017 - Dec 2019
- Served guests in a 120-seat dining room
""" + EDUCATION

SAME_TITLE_EMPLOYER_LINE = HEADER + """
EXPERIENCE
Team Leader, Trattoria Esempio, Hamilton, ON
Mar 2022 - Present
- Coordinated a team of 6 servers per shift
- Trained new hires on service standards

Floor Supervisor, Bistro Prova, Toronto, ON
Jan 2020 - Feb 2022
- Supervised dining room staff during dinner service

Server, Cafe Campione, Toronto, ON
Jun 2017 - Dec 2019
- Served guests in a 120-seat dining room
""" + EDUCATION

SAME_SEPARATE_LINES = HEADER + """
EXPERIENCE
Team Leader
Trattoria Esempio, Hamilton, ON
Mar 2022 - Present
- Coordinated a team of 6 servers per shift
- Trained new hires on service standards

Floor Supervisor
Bistro Prova, Toronto, ON
Jan 2020 - Feb 2022
- Supervised dining room staff during dinner service

Server
Cafe Campione, Toronto, ON
Jun 2017 - Dec 2019
- Served guests in a 120-seat dining room
""" + EDUCATION

# Same as SAME_SEPARATE_LINES, with no blank line between the entries.
SAME_NO_BLANK_LINES = HEADER + """
EXPERIENCE
Team Leader
Trattoria Esempio, Hamilton, ON
Mar 2022 - Present
- Coordinated a team of 6 servers per shift
- Trained new hires on service standards
Floor Supervisor
Bistro Prova, Toronto, ON
Jan 2020 - Feb 2022
- Supervised dining room staff during dinner service
Server
Cafe Campione, Toronto, ON
Jun 2017 - Dec 2019
- Served guests in a 120-seat dining room
""" + EDUCATION

EXPECTED_SAME = [
    ("Team Leader", "Trattoria Esempio", "Hamilton, ON", "Mar 2022", "Present",
     ["Coordinated a team of 6 servers per shift", "Trained new hires on service standards"]),
    ("Floor Supervisor", "Bistro Prova", "Toronto, ON", "Jan 2020", "Feb 2022",
     ["Supervised dining room staff during dinner service"]),
    ("Server", "Cafe Campione", "Toronto, ON", "Jun 2017", "Dec 2019",
     ["Served guests in a 120-seat dining room"]),
]

# --- 2. the two layouts used in the status review (verbatim) --------------
REVIEW_LAYOUT_A = """Alex Synthetic
alex.synthetic@example.test | +1 555 0100 | Hamilton, ON

EXPERIENCE

Team Leader, Front of House
Trattoria Esempio, Hamilton, ON
March 2022 - Present
- Coordinated a team of 6 servers per shift and assigned sections
- Trained new hires on service standards

Floor Supervisor
Bistro Prova, Toronto, ON
January 2020 - February 2022
- Supervised dining room staff during dinner service

Server
Cafe Campione, Toronto, ON
June 2017 - December 2019
- Served guests in a 120-seat dining room

EDUCATION
Hospitality Diploma, Niagara College, 2017
"""

REVIEW_LAYOUT_B = """Alex Synthetic
alex.synthetic@example.test | +1 555 0100 | Hamilton, ON

EXPERIENCE
Team Leader, Trattoria Esempio
Mar 2022 - Present
Coordinated a team of 6 servers per shift and assigned sections. Trained new hires on service standards.

Floor Supervisor, Bistro Prova
Jan 2020 - Feb 2022
Supervised dining room staff during dinner service.

Server, Cafe Campione
Jun 2017 - Dec 2019
Served guests in a 120-seat dining room.

EDUCATION
Niagara College
Hospitality Diploma
2015 - 2017
"""

# --- 4. incomplete CV -------------------------------------------------------
INCOMPLETE = """Jordan Synthetic

EXPERIENCE
Server
Jun 2021 - Present
- Served lunch and dinner

Host, Osteria Finta
- Greeted guests
"""

# --- 5. ambiguous: two header lines, no clue which is the employer ---------
AMBIGUOUS = """Riley Synthetic
riley.synthetic@example.test

EXPERIENCE
Osteria Finta
Team Leader
Mar 2022 - Present
- Coordinated the floor team
"""


def parse(text: str, filename: str = "synthetic.txt"):
    profile = DeterministicResumeParser().parse(_Ref(source_type="LOCAL_UPLOAD", raw_text=text,
                                                       original_filename=filename))
    return normalize_profile(profile)


def lines_of(text: str | None) -> list[str]:
    return [l.strip() for l in (text or "").splitlines() if l.strip()]


def summary(profile) -> list[tuple]:
    return [
        (w.original_job_title, w.employer, w.location, w.start_date_text, w.end_date_text,
         lines_of(w.responsibilities))
        for w in profile.work_history
    ]


def dump() -> None:
    for name in ("SAME_ONE_LINE", "SAME_TITLE_EMPLOYER_LINE", "SAME_SEPARATE_LINES", "SAME_NO_BLANK_LINES",
                 "REVIEW_LAYOUT_A", "REVIEW_LAYOUT_B", "INCOMPLETE", "AMBIGUOUS"):
        profile = parse(globals()[name])
        print(f"== {name}")
        for w in profile.work_history:
            print(f"   title={w.original_job_title!r} employer={w.employer!r} location={w.location!r} "
                  f"dates={w.start_date_text!r}->{w.end_date_text!r} "
                  f"structure={getattr(w, 'structure_confidence', '-')!r}")
            for line in lines_of(w.responsibilities):
                print(f"      duty: {line}")
            note = getattr(w, "structure_note", None)
            if note:
                print(f"      note: {note}")


def main() -> int:
    results: list[tuple[str, bool]] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        results.append((name, bool(condition)))
        print(f"  {'PASS' if condition else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not condition else ""))

    with isolated_ai_client():
        # --- 1. same CV, different layouts ---------------------------------
        layouts = {name: parse(globals()[name]) for name in (
            "SAME_ONE_LINE", "SAME_TITLE_EMPLOYER_LINE", "SAME_SEPARATE_LINES", "SAME_NO_BLANK_LINES")}
        for name, profile in layouts.items():
            check(f"1. {name}: three experiences with title, employer, location, dates and duties",
                  summary(profile) == EXPECTED_SAME, f"{summary(profile)}")
        check("1. changing the layout does not change the experiences extracted",
              len({repr(summary(p)) for p in layouts.values()}) == 1)
        check("1. normalized dates and roles are the same in every layout",
              len({repr([(w.start_date, w.end_date, w.is_current, w.normalized_role) for w in p.work_history])
                   for p in layouts.values()}) == 1)
        check("1. no experience in these layouts is marked uncertain",
              all(w.structure_confidence != "LOW" for p in layouts.values() for w in p.work_history))

        # --- 2. the two review layouts ---------------------------------------
        a, b = parse(REVIEW_LAYOUT_A), parse(REVIEW_LAYOUT_B)
        check("2. layout A: the title line is no longer read as a duty, nor the employer as the title",
              [(w.original_job_title, w.employer) for w in a.work_history] == [
                  ("Team Leader, Front of House", "Trattoria Esempio"),
                  ("Floor Supervisor", "Bistro Prova"), ("Server", "Cafe Campione")],
              f"{[(w.original_job_title, w.employer) for w in a.work_history]}")
        check("2. layouts A and B: same employers, same dates and same duties per experience",
              [(w.employer, w.start_date, w.end_date) for w in a.work_history]
              == [(w.employer, w.start_date, w.end_date) for w in b.work_history]
              and [" ".join(lines_of(w.responsibilities)).replace(".", "").replace("  ", " ")
                   for w in a.work_history]
              == [" ".join(lines_of(w.responsibilities)).replace(".", "").replace("  ", " ")
                  for w in b.work_history])
        check("2. layouts A and B: same normalized role for the Floor Supervisor and Server experiences",
              [w.normalized_role for w in a.work_history][1:] == [w.normalized_role for w in b.work_history][1:])

        # --- 3. duties stay with their experience ----------------------------
        no_blank = layouts["SAME_NO_BLANK_LINES"]
        check("3. without blank lines, each entry's title is not swallowed by the previous entry",
              [w.original_job_title for w in no_blank.work_history] == ["Team Leader", "Floor Supervisor", "Server"])
        check("3. the training duty stays with the Team Leader experience only",
              ["Trained new hires" in (w.responsibilities or "") for w in no_blank.work_history] == [True, False, False])

        # --- 4. incomplete CV -------------------------------------------------
        inc = parse(INCOMPLETE)
        check("4. incomplete CV: two experiences", len(inc.work_history) == 2, f"{summary(inc)}")
        if len(inc.work_history) == 2:
            first, second = inc.work_history
            check("4. a title with dates and no employer keeps the employer empty (not invented)",
                  first.original_job_title == "Server" and first.employer is None
                  and first.start_date_text == "Jun 2021")
            check("4. an experience with no dates keeps the dates empty (not invented)",
                  second.original_job_title == "Host" and second.employer == "Osteria Finta"
                  and second.start_date_text is None and second.end_date_text is None)
            check("4. missing facts alone do not mark the reading as uncertain",
                  all(w.structure_confidence != "LOW" for w in inc.work_history))
        inc_view = analyze_candidate(inc, target_role="SERVER")
        check("4. no 'reading uncertain' flag on the incomplete CV",
              not any(f.type == flags_mod.EXTRACTION_UNCERTAIN for f in inc_view.flags))
        check("4. missing contact details are a VERIFY question, not a conclusion about the candidate",
              any(f.type == flags_mod.MISSING_INFORMATION and "not automatically negative" in f.explanation
                  for f in inc_view.flags))

        # --- 5. ambiguous layout ---------------------------------------------
        amb = parse(AMBIGUOUS)
        check("5. ambiguous header: the experience is marked uncertain with a note",
              len(amb.work_history) == 1 and amb.work_history[0].structure_confidence == "LOW"
              and bool(amb.work_history[0].structure_note))
        amb_view = analyze_candidate(amb, target_role="SERVER")
        uncertain_flags = [f for f in amb_view.flags if f.type == flags_mod.EXTRACTION_UNCERTAIN]
        check("5. a VERIFY flag about the reading asks a person to check it",
              len(uncertain_flags) == 1 and uncertain_flags[0].attention_level == flags_mod.VERIFY
              and "not about the candidate" in uncertain_flags[0].explanation)

        # --- import status + preservation (real pipeline, throwaway DB) ----
        run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])
        engine = create_configured_engine(os.environ["RFONE_DATABASE_URL"])
        try:
            factory = create_session_factory(engine)
            with factory() as session:
                ambiguous = import_one_resume(
                    session, restaurant_id=None, source_type="LOCAL_UPLOAD", original_filename="ambiguous.txt",
                    storage_path=None, raw_text=AMBIGUOUS, content_hash="synthetic-ambiguous")
                clean = import_one_resume(
                    session, restaurant_id=None, source_type="LOCAL_UPLOAD", original_filename="separate.txt",
                    storage_path=None, raw_text=SAME_SEPARATE_LINES, content_hash="synthetic-separate")
                incomplete = import_one_resume(
                    session, restaurant_id=None, source_type="LOCAL_UPLOAD", original_filename="incomplete.txt",
                    storage_path=None, raw_text=INCOMPLETE, content_hash="synthetic-incomplete")
            check("5. an uncertain reading is imported as PARTIAL with a request to verify, never COMPLETED",
                  ambiguous.status == PARTIAL and "verify" in (ambiguous.error or "").lower(),
                  f"{ambiguous.status} {ambiguous.error}")
            check("4. the incomplete CV is still COMPLETED (missing facts are not a reading error)",
                  incomplete.status == COMPLETED, f"{incomplete.status} {incomplete.error}")
            check("1. the CV with separate lines is COMPLETED", clean.status == COMPLETED,
                  f"{clean.status} {clean.error}")

            from rfone_data_store import models as m
            from rfone_data_store.selection import persistence
            with factory() as session:
                stored = persistence.to_profile(persistence.get_candidate(session, ambiguous.candidate_id))
                reloaded_flags = analyze_candidate(stored, target_role="SERVER").flags
                rows = session.query(m.CandidateWorkHistory).filter_by(candidate_id=ambiguous.candidate_id).all()
                raw = session.query(m.RawResume).all()
                check("5. the uncertainty is stored with the experience (confidence and note)",
                      len(rows) == 1 and rows[0].structure_confidence == "LOW" and bool(rows[0].structure_note))
                check("6. every stored experience keeps the original text it was read from",
                      all(r.evidence_snippet for r in session.query(m.CandidateWorkHistory).all()))
                from rfone_data_store.selection.parsing.dedup import compute_content_hash
                limit = m.RawResume.__table__.c.content_hash.type.length
                check("6. both content-hash forms fit the column (SQLite does not enforce it; PostgreSQL does)",
                      len(compute_content_hash(AMBIGUOUS, "a.txt")) <= limit
                      and len(compute_content_hash("", "a-very-ordinary-name.txt")) <= limit, f"limit {limit}")
                check("6. the full résumé text is kept as received",
                      sorted(r.raw_text for r in raw) == sorted([AMBIGUOUS, SAME_SEPARATE_LINES, INCOMPLETE]))
                check("5. the uncertainty survives a reload and still raises the VERIFY flag",
                      stored.work_history[0].structure_confidence == "LOW"
                      and any(f.type == flags_mod.EXTRACTION_UNCERTAIN for f in reloaded_flags))
        finally:
            engine.dispose()
            for suffix in ("", "-wal", "-shm", "-journal"):
                if os.path.exists(_DB_PATH + suffix):
                    os.remove(_DB_PATH + suffix)

    passed = sum(1 for _, ok in results if ok)
    failed = len(results) - passed
    print(f"\n{passed} passed, {failed} failed.")
    print("ALL CHECKS PASSED" if failed == 0 else "SOME CHECKS FAILED")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    if "--dump" in sys.argv:
        with isolated_ai_client():
            dump()
        sys.exit(0)
    sys.exit(main())
