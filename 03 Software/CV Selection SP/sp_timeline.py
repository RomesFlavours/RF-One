"""Work history dates, durations, gaps and stability, computed in code (CV Selection SP).

The AI only points at the date text of each job ("date_text", copied from the
CV). Here that text must be found in the CV, is parsed by Pino's existing
date normalizer (`parsing/flexible_dates.normalize_date_pair`), and every
duration and gap is computed from it. A job is "current" only when the CV
itself says so (Present, Current, ...).

Year-only dates ("2022 - 2024") are kept as a range of possible months, never
turned into an invented month: a duration is exact only when both ends are
known to the month, and a short-job or gap flag is raised only when it holds
for every possible reading of the dates. Stability thresholds and levels are
Shelbi's (`profile_screening.stability`), applied to these certain values.
"""

from __future__ import annotations

import re
from datetime import date

from rfone_data_store.selection.parsing import flexible_dates as fd

from workspace import ai_adapter

SHORT_MONTHS = 6       # a job under 6 months is short (Shelbi's draft threshold)
LONG_MONTHS = 36       # 3+ years at one relevant employer is positive evidence
GAP_MONTHS = 3         # a gap is listed to verify only when it is certainly at least 3 months


def _mi(d: date) -> int:
    """Month index, for arithmetic."""
    return d.year * 12 + d.month - 1


def _label(mi: int) -> str:
    return date(mi // 12, mi % 12 + 1, 1).strftime("%b %Y")


def _bounds(value, precision: str) -> tuple[int, int] | None:
    """Earliest and latest possible month of one end of a job."""
    if value is None:
        return None
    if precision == fd.PRECISION_YEAR:
        return value.year * 12, value.year * 12 + 11
    return _mi(value), _mi(value)


def _in_text(fragment: str | None, haystack: str) -> bool:
    n = ai_adapter._normalized(fragment or "")
    return bool(n) and n in haystack


def _split_range(date_text: str) -> tuple[str | None, str | None]:
    """'Mar 2021 - Present' -> ('Mar 2021', 'Present'); '2021' -> ('2021', None)."""
    parts = re.split(r"\s*(?:-|–|—|\bto\b|\buntil\b)\s*", date_text.strip(), maxsplit=1, flags=re.I)
    start = parts[0].strip() or None
    end = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
    return start, end


_D = r"(?:(?:[A-Za-z]{3,9}\.?\s+)?(?:19|20)\d{2}|\d{1,2}/(?:19|20)\d{2})"
_RANGE_RE = re.compile(rf"({_D}\s*(?:-|–|—|\bto\b)\s*(?:{_D}|present|current|now|ongoing))", re.I)
_YEAR_RE = re.compile(r"(?<![\d/])((?:19|20)\d{2})(?![\d/])")


def find_date_text(job: dict, cv_text: str) -> str | None:
    """The job's dates found by code on the CV line naming the employer (or the next line), when the AI gave none.
    The AI did not always copy year-only ranges (Bedrock comparison, 1 Nov 2026: "2022 - 2024" came back empty)."""
    employer = str(job.get("employer") or "").strip().lower()
    if len(employer) < 3:
        return None
    lines = cv_text.splitlines()
    for i, line in enumerate(lines):
        if employer in line.lower():
            for candidate in (line, lines[i + 1] if i + 1 < len(lines) else ""):
                match = _RANGE_RE.search(candidate) or _YEAR_RE.search(candidate)
                if match:
                    return match.group(1).strip()
    return None


def job_dates(job: dict, cv_norm: str, today: date, cv_text: str = "") -> dict:
    """Verified dates of one AI-read job. Returns the fields added to the job."""
    date_text = str(job.get("date_text") or "").strip()
    found_by_code = False
    if not date_text:
        date_text = find_date_text(job, cv_text) or ""
        found_by_code = bool(date_text)
    if not date_text:
        return {"date_status": "MISSING", "date_note": f"No dates for {job.get('employer') or 'a job'} in the CV."}
    if found_by_code:
        job["date_text"], job["date_source"] = date_text, "Found by code on the job's line (the AI gave none)"
    if not _in_text(date_text, cv_norm):
        return {"date_status": "NOT_IN_CV", "date_note": f"The dates read by the AI (“{date_text}”) are not in the CV: "
                                                         "not used."}
    start_text, end_text = _split_range(date_text)
    pair = fd.normalize_date_pair(start_text, end_text)
    now = _mi(today.replace(day=1))
    start = _bounds(pair.normalized_start, pair.start_precision)
    if pair.is_current:
        end = (now, now)
    elif end_text is None and start and pair.start_precision == fd.PRECISION_YEAR:
        end = start                                   # "2021" alone: some months within that year
    else:
        end = _bounds(pair.normalized_end, pair.end_precision)
    if not start or not end:
        return {"date_status": "PARTIAL", "date_text": date_text,
                "date_note": f"“{date_text}”: start or end is missing, the duration cannot be computed."}
    lo = max(1, end[0] - start[1] + 1)
    hi = max(lo, end[1] - start[0] + 1)
    return {"date_status": "OK", "date_text": date_text, "is_current": pair.is_current,
            "start_lo": start[0], "start_hi": start[1], "end_lo": end[0], "end_hi": end[1],
            "months_min": lo, "months_max": hi, "exact": lo == hi,
            "duration_label": duration_label(lo, hi)}


def duration_label(lo: int, hi: int) -> str:
    if lo == hi:
        return f"{lo} month{'s' if lo != 1 else ''}" if lo < 24 else f"{lo // 12} yr {lo % 12} mo"
    if lo >= 24:
        years = f"about {lo // 12}" if lo // 12 == hi // 12 else f"{lo // 12}–{hi // 12}"
        return f"{years} years (year-only dates)"
    return f"{lo}–{hi} months (year-only dates)"


def analyze(jobs: list[dict], cv_text: str, today: date | None = None) -> dict:
    """Adds verified dates to every job (in place) and computes gaps and stability."""
    today = today or date.today()
    cv_norm = ai_adapter._normalized(cv_text)
    for job in jobs:
        for key in [k for k in job if k.startswith(("start_", "end_", "months_"))]:
            job.pop(key)
        job.update(job_dates(job, cv_norm, today, cv_text))
    dated = sorted([j for j in jobs if j["date_status"] == "OK"], key=lambda j: (j["start_lo"], j["end_lo"]))
    notes = [j["date_note"] for j in jobs if j.get("date_note")]

    gaps = []
    for prev, nxt in zip(dated, dated[1:]):
        gap_min = nxt["start_lo"] - prev["end_hi"] - 1
        if gap_min >= GAP_MONTHS:
            gap_max = nxt["start_hi"] - prev["end_lo"] - 1
            size = f"{gap_min} months" if gap_min == gap_max else f"at least {gap_min} months"
            gaps.append({"text": f"{size} between {prev.get('employer') or 'a job'} (ended {prev['date_text']}) "
                                 f"and {nxt.get('employer') or 'the next job'} ({nxt['date_text']})",
                         "months_min": gap_min})

    stability = _stability(dated, len(jobs) - len(dated), today)
    return {"gaps": gaps, "stability": stability, "date_notes": notes}


def _stability(dated: list[dict], undated: int, today: date) -> dict:
    if not dated:
        return {"level": None, "known": False, "flags": [], "positives": [],
                "reasons": ["No job has dates that can be verified in the CV: stability cannot be assessed "
                            "(missing information, to verify)."]}
    now = _mi(today.replace(day=1))
    run = longest_run = 0
    for j in dated:
        run = run + 1 if j["months_max"] < SHORT_MONTHS else 0     # short for every reading of the dates
        longest_run = max(longest_run, run)
    changes_24 = sum(1 for j in dated if j["start_lo"] >= now - 24)
    changes_36 = sum(1 for j in dated if j["start_lo"] >= now - 36)
    relevant = [j for j in dated if j.get("relevant")]
    longest_relevant = max((j["months_min"] for j in relevant), default=0)
    longest = max(j["months_min"] for j in dated)

    flags, positives = [], []
    if longest_run >= 3:
        flags.append({"code": "THREE_SHORT", "severity": "high",
                      "text": f"{longest_run} consecutive jobs under 6 months (computed from the CV dates)"})
    elif longest_run == 2:
        flags.append({"code": "TWO_SHORT", "severity": "flag",
                      "text": "Two consecutive jobs under 6 months (computed from the CV dates)"})
    if changes_36 >= 5:
        flags.append({"code": "FIVE_CHANGES", "severity": "high",
                      "text": f"{changes_36} jobs started in the last 36 months (computed from the CV dates)"})
    if longest_relevant >= LONG_MONTHS:
        positives.append({"code": "LONG_TENURE",
                          "text": f"At least {longest_relevant} months at one relevant employer"})

    if any(f["severity"] == "high" for f in flags):
        level = 1
    elif flags:
        level = 2 if positives else 1
    elif longest_relevant >= LONG_MONTHS:
        level = 4
    elif longest >= 18:
        level = 3
    else:
        level = 2
    reasons = [f"Longest job at least {longest} months; jobs started in the last 24 / 36 months: "
               f"{changes_24} / {changes_36}."]
    if undated:
        reasons.append(f"{undated} job(s) without verifiable dates are not counted.")
    return {"level": level, "known": True, "flags": flags, "positives": positives, "reasons": reasons,
            "longest_months": longest, "longest_relevant_months": longest_relevant}
