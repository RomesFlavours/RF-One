"""CV screening against a Position Selection Profile (SELECTION_POSITION_PROFILES_001).

The AI only READS the CV: it rebuilds the work history, classifies each
prior environment with the profile's table, assigns an evidence level per
dimension with word-for-word quotes, and lists flags, unknowns and questions.
Everything that decides the order is computed here, in code, from what the AI
read: tenure and stability from the dates, the weighted evidence score, the
commute band. Quotes not found in the CV are discarded and the level they
supported drops to "not shown" (the same rule as `ai_adapter.evaluate_candidate`).

Kept separate and visible, never hidden in one number: positive evidence,
business cut-offs, risk flags, unknowns. Nobody is excluded automatically; a
recruiter's priority (High / Medium / Low) overrides the proposed order.
"""

from __future__ import annotations

import json
import re
from datetime import date

from rfone_data_store.selection.parsing.ai_client import AIProviderUnavailable

from . import ai_adapter, position_profiles as pp

SOURCE = "PROFILE"  # WorkspaceProposal.source for these results

FIT_BANDS = (("STRONG", 60, "Strong CV fit"), ("MODERATE", 40, "Moderate CV fit"), ("LIMITED", 0, "Limited CV fit"))
FIT_LABELS = {code: label for code, _, label in FIT_BANDS}
FIT_LABELS["CUTOFF"] = "Business cut-off to review"

_PROMPT = """You read ONE job applicant's résumé for a restaurant manager. You do not decide; the manager does.
Output ONLY a JSON object, no markdown. Write in plain ENGLISH.

Position: {title} at Rome's Flavours, {location}, Florida.
What the position is: {summary}

Evidence dimensions (give each a level 0-4: {levels}):
{dimensions}

How prior work environments count for THIS position (use the label on the left for "environment"):
{environments}
Use "Unrelated work" for jobs outside restaurants.

Role-specific flags to look for: {role_flags}
Never assume: {must_not_assume}
{stations}
Résumé text (contact details removed): <<<{cv_text}>>>

Rules:
- Rebuild the work history in "timeline", most recent first. Dates as "YYYY-MM" (use "YYYY-01" if only a year
  is given and say so in "date_note"); "present" for a current job; null when missing. Never invent dates.
- Every level above 0 needs at least one entry in "quotes" copied EXACTLY, word for word, from the résumé.
  A skills-list keyword with no duties behind it is level 1 at most (a claim, not evidence).
- "Not shown" (0) means MISSING INFORMATION, not proof of inability. List what is missing in "unknowns".
- Do not score "stability": it is computed from your timeline.
- "home_location": the city/town the résumé says the person lives in, with the exact quote, or null.
  "commute_minutes": your rough estimate of the usual one-way DRIVE in minutes from that place to {location},
  Florida, or null if the location is missing or unclear. Never guess a location.
- "stated_hours": weekly hours ONLY if the résumé states them, else null. Same for "stated_availability".
- Never use or infer {protected}. Never judge personality, motivation or finances. Never treat age or many
  years of experience as a negative. Do not invent reasons for leaving a job.
- "questions": at most 5 neutral questions to verify in the interview, about the flags and unknowns.

JSON shape:
{{"timeline": [{{"employer": "...", "title": "...", "start": "YYYY-MM"|null, "end": "YYYY-MM"|"present"|null,
   "date_note": "...", "environment": "<label>", "relevant": true|false, "promotion": true|false,
   "duties": "<short summary>"}}],
  "dimensions": {{"<dimension id>": {{"level": 0-4, "quotes": ["..."], "explanation": "..."}}}},
  {stations_shape}"positive_evidence": [{{"text": "...", "quote": "..."}}],
  "risk_flags": [{{"flag": "...", "fact": "...", "quote": "...", "question": "..."}}],
  "unknowns": ["..."],
  "home_location": {{"place": "...", "quote": "..."}}|null, "commute_minutes": <int>|null,
  "stated_hours": {{"hours": <int>, "quote": "..."}}|null,
  "stated_availability": {{"text": "...", "quote": "..."}}|null,
  "adaptability": {{"status": "DOCUMENTED"|"NOT_ESTABLISHED", "quote": "..."}},
  "questions": ["..."]}}
"""

_STATIONS = ("For each named kitchen station (sauté, pasta, grill/broiler, fry, pantry/cold line, prep, pizza, expo) "
             "give the strongest level the résumé DOCUMENTS: claimed (skills list only), assisted, executed, owned "
             "(ran it alone), coordinated (ran several). Never upgrade a level.\n")
_STATIONS_SHAPE = ('"stations": [{"station": "...", "level": "claimed|assisted|executed|owned|coordinated", '
                   '"employer": "...", "quote": "..."}],\n  ')
_JSON_RETRY = ("\n\nYour previous reply was not valid JSON. Reply again with valid JSON only: inside every string, "
               "escape double quotes as \\\" or use single quotes.")


def _month(value, today: date) -> date | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in ("present", "current", "now"):
        return today.replace(day=1)
    match = re.fullmatch(r"(\d{4})-(\d{1,2})", text)
    if not match or not 1 <= int(match.group(2)) <= 12:
        return None
    return date(int(match.group(1)), int(match.group(2)), 1)


def _months(start: date, end: date) -> int:
    return max(1, (end.year - start.year) * 12 + end.month - start.month + 1)


def stability(timeline: list[dict], today: date | None = None) -> dict:
    """Tenure indicators from the dates, and the stability level (0-4) with its reasons.
    The thresholds are the draft ones shared by the Server and Line Cook models."""
    today = today or date.today()
    jobs = []
    for job in timeline:
        start, end = _month(job.get("start"), today), _month(job.get("end"), today)
        if start and end and end >= start:
            job["months"] = _months(start, end)
            jobs.append({**job, "_start": start, "_end": end})
        else:
            job["months"] = None
    jobs.sort(key=lambda j: j["_start"])
    undated = sum(1 for j in timeline if j.get("months") is None)
    if not jobs:
        return {"level": None, "known": False, "jobs_dated": 0, "jobs_undated": undated,
                "reasons": ["No job has usable start and end dates: stability is unknown."], "flags": [], "positives": []}

    months = [j["months"] for j in jobs]
    run, longest_run = 0, 0
    for m in months:
        run = run + 1 if m < 6 else 0
        longest_run = max(longest_run, run)
    cutoff = date(today.year - 3, today.month, 1)
    changes_36 = sum(1 for j in jobs if j["_start"] >= cutoff)
    relevant = [j for j in jobs if j.get("relevant")]
    longest_relevant = max((j["months"] for j in relevant), default=0)
    ordered = sorted(months)
    median = ordered[len(ordered) // 2] if len(ordered) % 2 else (ordered[len(ordered) // 2 - 1] + ordered[len(ordered) // 2]) / 2

    flags, positives = [], []
    if longest_run >= 3:
        flags.append(("THREE_SHORT", "high", f"{longest_run} consecutive jobs under 6 months"))
    elif longest_run == 2:
        flags.append(("TWO_SHORT", "flag", "Two consecutive jobs under 6 months"))
    if changes_36 >= 5:
        flags.append(("FIVE_CHANGES", "high", f"{changes_36} jobs started in the last 36 months"))
    if longest_relevant >= 36:
        positives.append(("LONG_TENURE", f"{longest_relevant} months at one relevant employer"))
    if any(j.get("promotion") for j in jobs):
        positives.append(("PROMOTION", "Promotion or more responsibility at the same employer"))

    if any(sev == "high" for _, sev, _ in flags):
        level = 1
    elif flags:
        level = 2 if positives else 1
    elif longest_relevant >= 36:
        level = 4
    elif max(months) >= 18:
        level = 3
    else:
        level = 2
    reasons = [f"Longest job {max(months)} months; median {median:g} months; {changes_36} job(s) started in the last 36 months."]
    if undated:
        reasons.append(f"{undated} job(s) without usable dates are not counted.")
    return {"level": level, "known": True, "jobs_dated": len(jobs), "jobs_undated": undated, "reasons": reasons,
            "flags": [{"code": c, "severity": s, "text": t} for c, s, t in flags],
            "positives": [{"code": c, "text": t} for c, t in positives],
            "longest_months": max(months), "longest_relevant_months": longest_relevant,
            "median_months": median, "changes_36": changes_36}


def _quote_ok(quote, haystack: str) -> bool:
    q = ai_adapter._normalized(str(quote or ""))
    return bool(q) and q in haystack


def screen(profile: dict, *, location: str, cv_text: str, today: date | None = None) -> dict:
    """Read the CV with the AI, then compute the order-deciding parts in code. Raises AIProviderUnavailable."""
    if not cv_text.strip():
        raise AIProviderUnavailable("The résumé text is empty.")
    dims = [d for d in profile["dimensions"] if d["id"] != "stability"]
    prompt = _PROMPT.format(
        title=profile["title"], location=location, summary=profile["summary"],
        levels="; ".join(f"{k} = {v}" for k, v in pp.LEVELS.items()),
        dimensions="\n".join(f"- {d['id']}: {d['name']}. {d['look_for']}" for d in dims),
        environments="\n".join(f"- {label}: {value}" for label, value in profile["environments"]),
        role_flags=" ".join(profile["role_flags"]), must_not_assume=profile["must_not_assume"],
        stations=_STATIONS if "station_levels" in profile else "",
        stations_shape=_STATIONS_SHAPE if "station_levels" in profile else "",
        cv_text=ai_adapter.redact_contacts(cv_text), protected=ai_adapter._PROTECTED.replace(
            ", address or where the person lives", ""))
    try:
        data = ai_adapter._transport(prompt, "position profile screening")
    except AIProviderUnavailable as exc:
        if "unparsable" not in str(exc):
            raise
        # Temperature is 0, so the same prompt gives the same broken JSON: ask once more, differently.
        data = ai_adapter._transport(prompt + _JSON_RETRY, "position profile screening (retry)")
    if not isinstance(data, dict) or not isinstance(data.get("timeline"), list):
        raise AIProviderUnavailable("Invalid AI response (work history missing).")
    return assemble(profile, data, cv_text=cv_text, today=today, location=location)


def assemble(profile: dict, data: dict, *, cv_text: str, today: date | None = None,
             location: str | None = None) -> dict:
    hay = ai_adapter._normalized(cv_text)
    timeline = [j for j in data.get("timeline") or [] if isinstance(j, dict)][:20]
    for job in timeline:
        for key in ("employer", "title", "environment", "duties", "date_note"):
            job[key] = str(job.get(key) or "").strip()[:200]
        job["relevant"], job["promotion"] = bool(job.get("relevant")), bool(job.get("promotion"))
    stab = stability(timeline, today)

    dimensions, dropped = [], 0
    raw_dims = data.get("dimensions") if isinstance(data.get("dimensions"), dict) else {}
    for d in profile["dimensions"]:
        if d["id"] == "stability":
            level = stab["level"]
            dimensions.append({**d, "level": level or 0, "known": stab["known"], "quotes": [],
                               "explanation": " ".join(stab["reasons"])})
            continue
        raw = raw_dims.get(d["id"]) if isinstance(raw_dims.get(d["id"]), dict) else {}
        try:
            level = min(4, max(0, int(raw.get("level") or 0)))
        except (TypeError, ValueError):
            level = 0
        quotes = [str(q).strip() for q in (raw.get("quotes") or [])[:4] if _quote_ok(q, hay)]
        dropped += len(raw.get("quotes") or []) - len(quotes)
        explanation = str(raw.get("explanation") or "").strip()
        if level and not quotes:
            level, explanation = 0, ("No quote found in the résumé; treated as not shown. " + explanation).strip()
        dimensions.append({**d, "level": level, "known": True, "quotes": quotes, "explanation": explanation})

    score = round(sum(d["weight"] * d["level"] / 4 for d in dimensions))

    home = data.get("home_location") if isinstance(data.get("home_location"), dict) else None
    if home and not _quote_ok(home.get("quote"), hay):
        home = None
    known = pp.known_drive(location, home.get("place")) if home else None
    minutes = data.get("commute_minutes") if known is None else known
    minutes = minutes if isinstance(minutes, int) and 0 <= minutes <= 600 and home else None
    band = pp.commute_band(minutes)
    commute = {"place": home.get("place") if home else None, "quote": home.get("quote") if home else None,
               "minutes": minutes, "band": band[0] if band else "UNKNOWN",
               "label": band[1] if band else "Commute unknown: no clear home location in the résumé",
               "points": band[2] if band else 0,
               "basis": (None if not band else "Typical drive from the town list, approximate" if known is not None
                         else "Rough AI estimate from the city on the résumé, not a verified route")}

    def stated(key, field):
        value = data.get(key) if isinstance(data.get(key), dict) else None
        return value if value and _quote_ok(value.get("quote"), hay) and value.get(field) not in (None, "") else None
    hours = stated("stated_hours", "hours")
    if hours and not isinstance(hours.get("hours"), int):
        hours = None
    availability = stated("stated_availability", "text")

    stations = []
    for s in data.get("stations") or []:
        if isinstance(s, dict) and s.get("level") in profile.get("station_levels", []) and _quote_ok(s.get("quote"), hay):
            stations.append({k: str(s.get(k) or "") for k in ("station", "level", "employer", "quote")})

    positives = [{"text": str(p.get("text") or ""), "quote": p.get("quote")} for p in data.get("positive_evidence") or []
                 if isinstance(p, dict) and _quote_ok(p.get("quote"), hay)][:6]
    positives += [{"text": p["text"], "quote": None} for p in stab.get("positives", [])]
    flags = [{"flag": str(f.get("flag") or ""), "fact": str(f.get("fact") or ""),
              "quote": f.get("quote") if _quote_ok(f.get("quote"), hay) else None,
              "question": str(f.get("question") or "")} for f in data.get("risk_flags") or [] if isinstance(f, dict)][:6]
    flags += [{"flag": f["text"], "fact": "Computed from the dates in the résumé.", "quote": None,
               "question": "Could you tell me about the shorter jobs in your work history?",
               "severity": f["severity"]} for f in stab.get("flags", [])]
    cutoffs = []
    if commute["band"] == "CUTOFF":
        cutoffs.append({"rule": "Commute 45 minutes or more (one way)", "status": "Estimated, not verified",
                        "fact": f"{commute['place']}: about {minutes} minutes", "exception": "Review with the candidate"})

    unknowns = [str(u) for u in data.get("unknowns") or [] if str(u).strip()][:8]
    if not stab["known"]:
        unknowns.insert(0, "Employment dates (stability cannot be computed).")
    if commute["band"] == "UNKNOWN":
        unknowns.append("Where the candidate lives (commute).")
    if not hours:
        unknowns.append("Desired weekly hours.")
    adaptability = data.get("adaptability") if isinstance(data.get("adaptability"), dict) else {}
    adaptability = ({"status": "DOCUMENTED", "quote": adaptability.get("quote")}
                    if adaptability.get("status") == "DOCUMENTED" and _quote_ok(adaptability.get("quote"), hay)
                    else {"status": "NOT_ESTABLISHED", "quote": None})

    questions = [str(q).strip() for q in data.get("questions") or [] if str(q).strip()][:5]
    dated_share = stab["jobs_dated"] / max(1, len(timeline))
    confidence = "High" if dated_share >= .8 and not dropped else ("Medium" if dated_share >= .5 else "Low")
    ranking = score + commute["points"]
    fit = "CUTOFF" if cutoffs else next(code for code, floor, _ in FIT_BANDS if score >= floor)
    return {"profile": profile["code"], "version": profile["version"], "status": pp.STATUS, "score": score,
            "ranking_score": ranking, "fit": fit, "confidence": confidence, "dimensions": dimensions,
            "timeline": timeline, "stability": stab, "stations": stations, "positive_evidence": positives,
            "risk_flags": flags, "cutoffs": cutoffs, "unknowns": unknowns, "commute": commute,
            "stated_hours": hours, "hours_band": pp.hours_band(hours["hours"]) if hours else None,
            "stated_availability": availability, "adaptability": adaptability, "questions": questions,
            "dropped_quotes": dropped}


def interview_steps(result: dict, profile: dict) -> list[dict]:
    """What the AI interview must verify for this candidate: availability and hours first, then where they
    live when it is unknown, then the résumé's flags and questions, then the position's own questions."""
    steps = [{"id": "availability", "ask": "Evening and weekend availability, and desired and minimum weekly hours.",
              "context": (result.get("stated_availability") or {}).get("text") or "Not stated in the résumé."}]
    commute = result.get("commute") or {}
    if commute.get("band") in ("UNKNOWN", "CONFIRM", "CUTOFF"):
        steps.append({"id": "commute", "ask": "Roughly how long their drive to the restaurant would be.",
                      "context": commute.get("label", "")})
    seen = set()
    for item in [f["question"] for f in result.get("risk_flags") or [] if f.get("question")] + list(result.get("questions") or []):
        key = ai_adapter._normalized(item)
        if key and key not in seen and len(steps) < 6:
            seen.add(key)
            steps.append({"id": f"cv{len(steps)}", "ask": item, "context": "From the résumé screening."})
    for i, item in enumerate(profile["interview_focus"][1:], start=1):
        steps.append({"id": f"role{i}", "ask": item, "context": f"{profile['title']} standard."})
    return steps[:9]


def dumps(result: dict) -> str:
    return json.dumps(result, default=str)
