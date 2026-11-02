"""One AI reading per CV, verified in code (CV Selection SP).

Replaces the three parallel readings of the same CV (Pino's rule-based
reading, Pino's AI requirement evaluation, Shelbi's profile screening) with
ONE call that returns, together: the work history with each job's date text,
an evidence level with word-for-word quotes for every APPROVED requirement
(Shelbi's 0-4 levels, Pino's quote rule), competences as claimed / executed /
owned / coordinated, strengths, flags, missing information and the stated
availability.

The AI only reads. Code then decides what is kept:
- quotes must be found in the CV (Pino's `evaluate_candidate` rule); a level
  without a verifiable quote becomes "not documented";
- evidence found only in a skills list is a claim: level 1 at most, and a
  competence stays "claimed" (Shelbi's rule, here enforced by code);
- dates must be in the CV; durations, gaps and stability are computed
  (`sp_timeline`); a flag that states a duration, a gap or a count of months
  written by the AI is dropped, because only the code computes those;
- residence, commute and protected characteristics are never asked for, and
  a flag or a missing-information line about them is dropped.
Everything dropped is listed in the verification log shown to the manager.
"""

from __future__ import annotations

import re
import time
from datetime import date

from rfone_data_store.selection.parsing.ai_client import AIProviderUnavailable

from .. import ai_adapter, position_profiles as pp

from . import timeline as sp_timeline

# The checks applied in code to the AI reading. An analysis stored with an older value is shown as needing an
# update (Analyze), so one Job never ranks CVs checked under two different sets of rules.
CHECKS_VERSION = "2026-11-02"
PROMPT_VERSION = "SP-1.1"  # 1.1: absence of information is never a flag
COMPETENCE_LEVELS = ("claimed", "executed", "owned", "coordinated")

# Pino's "never use" list, unchanged: residence included (no commute assumptions in SP).
PROTECTED = ai_adapter._PROTECTED

_PROMPT = """You read ONE job applicant's résumé for a restaurant manager. You do not decide and you do not rank;
the manager does. Output ONLY a JSON object, no markdown. Write in plain ENGLISH.

Position: {title} at Rome's Flavours (traditional Italian restaurant).
What the position is: {summary}

The manager's APPROVED requirements (give each a level 0-4: {levels}):
{requirements}

How prior work environments count for THIS position (use the label on the left for "environment"):
{environments}
Use "Unrelated work" for jobs outside restaurants.

Role-specific flags to look for: {role_flags}
Never assume: {must_not_assume}

Résumé text (contact details removed): <<<{cv_text}>>>

Rules:
- "jobs": every job, most recent first. "date_text" is the job's dates copied EXACTLY, character for character,
  from the résumé (for example "Mar 2021 - Present" or "2019 - 2020"), or null when the résumé gives none.
  Do not convert, complete or interpret dates and do not compute durations: the code does that.
- Every requirement level above 0 needs at least one entry in "quotes" copied EXACTLY, word for word, from the
  résumé. A keyword in a skills list with no duties behind it is level 1 at most (a claim, not evidence).
  Level 0 means NOT DOCUMENTED (missing information), never proof of inability. If something cannot be judged
  from a résumé at all, set "assessable": false. Use "against_quote" only when the résumé text itself shows the
  opposite of the requirement; otherwise null.
- "competences": {competence_hint} Level = the strongest one the résumé DOCUMENTS: claimed (only listed),
  executed (did it), owned (ran it alone / was responsible), coordinated (led others in it). Never upgrade.
- "risk_flags": only facts the résumé SHOWS that are a risk for this position, each with an exact "quote".
  Something the résumé does not mention is never a flag ("no documented...", "limited detail..."): it goes in
  "unknowns". Do NOT state durations, gaps, tenure or numbers of months or years: the code computes them from the
  dates. Do not invent reasons for leaving a job.
- Never use, infer or mention {protected}. Do not ask where the person lives and do not estimate any commute.
  Never judge personality, motivation or finances. Never treat age or many years of experience as a negative.
- "stated_hours" / "stated_availability": ONLY if the résumé states them, with the exact quote, else null.
- "questions": at most 5 neutral questions to verify in an interview, about flags and missing information.

JSON shape:
{{"full_name": "..."|null,
  "jobs": [{{"employer": "...", "title": "...", "date_text": "..."|null, "environment": "<label>",
            "relevant": true|false, "promotion": true|false, "duties": "<short summary>"}}],
  "requirements": {{"<requirement id>": {{"level": 0-4, "quotes": ["..."], "explanation": "...",
                    "assessable": true|false, "against_quote": "..."|null}}}},
  "competences": [{{"name": "...", "level": "claimed|executed|owned|coordinated", "employer": "...", "quote": "..."}}],
  "strengths": [{{"text": "...", "quote": "..."}}],
  "risk_flags": [{{"flag": "...", "fact": "...", "quote": "...", "question": "..."}}],
  "unknowns": ["..."],
  "stated_hours": {{"hours": <int>, "quote": "..."}}|null,
  "stated_availability": {{"text": "...", "quote": "..."}}|null,
  "questions": ["..."]}}
"""

_COMPETENCE_HINT = {
    "LINE_COOK": "each kitchen station or technique named (sauté, pasta, grill/broiler, fry, pantry/cold line, prep, "
                 "pizza, expo, sauces).",
    "SERVER": "each service skill named (table service, wine service, menu guidance, upselling, POS, cash-out, "
              "training others, bartending, hosting).",
}

_DURATION_RE = re.compile(r"\b\d+\s*(?:\+\s*)?(?:-\s*\d+\s*)?(?:months?|mos?|years?|yrs?|weeks?)\b|\bgaps?\b", re.I)
# Residence/commute and protected characteristics. Job words such as "health inspection" or "drive-thru" are
# deliberately not listed: they describe the work, not the person.
# "family" alone is not listed either ("a family Italian restaurant", "familiarity with the menu").
_SENSITIVE_RE = re.compile(r"\b(commut\w*|drive time|distance|lives|living in|resid\w*|relocat\w*|age|aged|"
                           r"years old|young|older|younger|family (?:status|situation|reasons|obligations|commitments)|"
                           r"pregnan\w*|nationalit\w*|religio\w*|ethnic\w*|disabilit\w*|married|children|"
                           r"gender|sex|sexual orientation|race|racial|skin colou?r|citizenship|u\.?s\.? citizen|"
                           r"immigra\w*|visa status|work visa|national origin|veteran status|military status)\b", re.I)
# Not listed on purpose, because they are restaurant words: "Visa" (cards), "colour-coded", "senior citizens",
# "veteran server".
# A "flag" that only says something is not in the CV is missing information: it goes to To verify.
_ABSENCE_RE = re.compile(r"^\s*(no|not|limited|minimal|unknown|unclear|lack\w*|missing|without|unverified|incomplete|"
                         r"few|little|insufficient|undocumented)\b|not documented|no documented|without documented|"
                         r"not shown|not stated|not specified|not detailed", re.I)
_HEADER_RE = re.compile(r"^[A-Z][A-Z &/]{2,40}:?$")
# Real CVs often write headings in Title Case ("Skills", then "Experience"): the skills section also ends at any
# usual heading, in any case, or a duty under Experience would count as a mere claim (SELECTION_SP_REAL_CVS_001).
_SECTION_RE = re.compile(r"^(?:(?:(?:work|professional|relevant|restaurant|employment|job|career)\s+)?"
                         r"(?:experience|history)|employment|education|training|certifications?|licenses?|"
                         r"languages?|references?|summary|profile|objective|awards|achievements|volunteer\w*|"
                         r"interests|hobbies|availability|contact)\s*:?\s*$", re.I)
# A quote this short ("POS", "Wine service") names a thing, it does not document work: it supports level 2
# (partly shown, to verify) at most, unless it is the title or employer of a dated job (SELECTION_SP_REAL_CVS_001).
MIN_EVIDENCE_WORDS, MIN_EVIDENCE_CHARS = 3, 15


def substantial(quote) -> bool:
    text = str(quote or "").strip()
    return len(text.split()) >= MIN_EVIDENCE_WORDS or len(text) >= MIN_EVIDENCE_CHARS
_SKILLS_RE = re.compile(r"^(skills|core skills|key skills|technical skills|competenc\w*|abilities|strengths)\b:?",
                        re.I)


def _norm(text) -> str:
    return ai_adapter._normalized(str(text or ""))


def skills_text(cv_text: str) -> str:
    """The normalized text of the CV's skills section(s): what is there is a claim, not evidence."""
    out, inside = [], False
    for line in cv_text.splitlines():
        stripped = line.strip()
        if _SKILLS_RE.match(stripped):
            inside = True
            rest = _SKILLS_RE.sub("", stripped).strip(" :")
            if rest:
                out.append(rest)
            continue
        if inside and stripped and (_HEADER_RE.match(stripped) or _SECTION_RE.match(stripped)):
            inside = False
        if inside and stripped:
            out.append(stripped)
    return _norm(" \n ".join(out))


class Verifier:
    def __init__(self, cv_text: str):
        self.cv = _norm(cv_text)
        self.skills = skills_text(cv_text)
        self.log: list[str] = []

    def quote_ok(self, quote) -> bool:
        return bool(_norm(quote)) and _norm(quote) in self.cv

    def only_in_skills(self, quotes: list[str]) -> bool:
        """True when every quote appears in the skills section and nowhere else in the CV."""
        if not quotes or not self.skills:
            return False
        for q in quotes:
            n = _norm(q)
            if n not in self.skills or self.cv.count(n) > self.skills.count(n):
                return False
        return True

    def quotes(self, raw, where: str) -> list[str]:
        kept = []
        for q in (raw if isinstance(raw, list) else [])[:5]:
            q = str(q).strip()
            if not q:
                continue
            if self.quote_ok(q):
                kept.append(q)
            else:
                self.log.append(f"{where}: quote not found in the CV, discarded (“{q[:80]}”).")
        return kept


def build_prompt(role_code: str, requirements: list[dict], cv_text: str) -> str:
    profile = pp.PROFILES[role_code]
    evaluated = [r for r in requirements if not r.get("computed")]
    return _PROMPT.format(
        title=profile["title"], summary=profile["summary"],
        levels="; ".join(f"{k} = {v}" for k, v in pp.LEVELS.items()),
        requirements="\n".join(f"- {r['id']}: {r['name']}. {r['look_for']}" for r in evaluated),
        environments="\n".join(f"- {label}: {value}" for label, value in profile["environments"]),
        role_flags=" ".join(profile["role_flags"]), must_not_assume=profile["must_not_assume"],
        competence_hint=_COMPETENCE_HINT.get(role_code, "each job-relevant skill named."),
        cv_text=ai_adapter.redact_contacts(cv_text), protected=PROTECTED)


THROTTLE_WAITS = (5, 10, 20, 40)  # seconds; Bedrock throttled 4 of 20 CVs analyzed 4 at a time (1 Nov 2026)
# Asked once more when a reply is not valid JSON: at temperature 0 the same prompt repeats the same broken reply.
JSON_RETRY_NOTE = ("\n\nYour previous reply was not valid JSON. Reply again with valid JSON only: inside every string, "
                   "escape double quotes as \\\" or use single quotes.")
PURPOSE = "CV Selection SP analysis"


def _generate(prompt: str) -> dict:
    """Selection's single AI seam (`ai_adapter._transport`), only when the position allows AI résumé evaluation,
    waiting and retrying when Bedrock asks to slow down (ThrottlingException)."""
    ai_adapter._require(ai_adapter.current_policy().allows("cv_evaluation"), "AI résumé evaluation")
    for wait in THROTTLE_WAITS + (None,):
        try:
            return ai_adapter._transport(prompt, PURPOSE)
        except AIProviderUnavailable as exc:
            if wait is None or not re.search(r"Throttling|Too many requests", str(exc)):
                raise
            time.sleep(wait)


def call_ai(prompt: str) -> dict:
    """One reading; asked once more only when the reply is not valid JSON."""
    try:
        return _generate(prompt)
    except AIProviderUnavailable as exc:
        if "unparsable" not in str(exc):
            raise
        return _generate(prompt + JSON_RETRY_NOTE)


def analyze_cv(*, role_code: str, requirements: list[dict], cv_text: str, today: date | None = None,
               generate=None) -> dict:
    """Read one CV with the AI (one call) and return the verified analysis. Raises AIProviderUnavailable."""
    if not (cv_text or "").strip():
        raise AIProviderUnavailable("The CV has no readable text.")
    data = (generate or call_ai)(build_prompt(role_code, requirements, cv_text))
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        raise AIProviderUnavailable("The AI reply has no work history.")
    return verify(data, role_code=role_code, requirements=requirements, cv_text=cv_text, today=today)


_LOW_TRANSFER_RE = re.compile(r"diner|breakfast|fast food|quick-service", re.I)


def _environment_flag(role_code: str, jobs: list[dict], v: Verifier) -> dict | None:
    """Shelbi's Server role flag, raised by code from the environment of each job: restaurant work only in
    diner / breakfast-chain / fast-food models is a provisional role-fit flag, not a ban. Not for Line Cook,
    where the profile says quick-service is not a negative."""
    if role_code != "SERVER":
        return None
    restaurant = [j for j in jobs if j.get("environment") and not str(j["environment"]).startswith("Unrelated")]
    if not restaurant or not all(_LOW_TRANSFER_RE.search(str(j["environment"])) for j in restaurant):
        return None
    quote = next((j["employer"] for j in restaurant if j.get("employer") and v.quote_ok(j["employer"])), "")
    if not quote:
        return None
    return {"flag": "Restaurant work only in diner, breakfast-chain or fast-food models",
            "fact": "Provisional role-fit flag from the Server profile, not a ban: later full-service experience counts.",
            "quote": quote, "question": "Tell me about any full-service table experience you have had.",
            "source": "PROFILE"}


def verify(data: dict, *, role_code: str, requirements: list[dict], cv_text: str, today: date | None = None) -> dict:
    v = Verifier(cv_text)
    name = str(data.get("full_name") or "").strip() or None
    if name and not v.quote_ok(name):
        v.log.append(f"Name “{name}” not found in the CV, not used.")
        name = None

    jobs = []
    for raw in data.get("jobs") or []:
        if not isinstance(raw, dict):
            continue
        job = {k: raw.get(k) for k in ("employer", "title", "date_text", "environment", "duties")}
        job["relevant"], job["promotion"] = bool(raw.get("relevant")), bool(raw.get("promotion"))
        for key in ("employer", "title"):
            if job[key] and not v.quote_ok(job[key]):
                v.log.append(f"Job {key} “{job[key]}” not found in the CV: shown as read, to check.")
                job[f"{key}_unverified"] = True
        jobs.append(job)
    for job in jobs:
        if job.get("duties") and _SENSITIVE_RE.search(str(job["duties"])):
            v.log.append(f"Duties read for {job.get('employer') or 'a job'} referred to residence or a personal "
                         "characteristic: not shown.")
            job["duties"] = None
    timeline = sp_timeline.analyze(jobs, cv_text, today)
    v.log += [n for n in timeline["date_notes"] if "not in the CV" in n]

    # The verified title or employer of a job with verified dates is real evidence even in one or two words
    # ("Server" at "Olive Garden", 2019 - 2023): a sparse CV is not a weak one.
    dated_jobs = {_norm(j[k]) for j in jobs if j.get("date_status") == "OK" for k in ("employer", "title")
                  if j.get(k) and not j.get(f"{k}_unverified")}
    raw_reqs = data.get("requirements") if isinstance(data.get("requirements"), dict) else {}
    results = {}
    for req in requirements:
        if req.get("computed"):
            level = timeline["stability"]["level"]
            results[req["id"]] = {"level": level, "quotes": [], "assessable": level is not None, "computed": True,
                                  "explanation": " ".join(timeline["stability"]["reasons"]), "against": None}
            continue
        raw = raw_reqs.get(req["id"]) if isinstance(raw_reqs.get(req["id"]), dict) else {}
        try:
            level = max(0, min(4, int(raw.get("level") or 0)))
        except (TypeError, ValueError):
            level = 0
        quotes = v.quotes(raw.get("quotes"), req["name"])
        explanation = str(raw.get("explanation") or "").strip()
        if level > 0 and not quotes:
            v.log.append(f"{req['name']}: level {level} without a verifiable quote, treated as not documented.")
            level, explanation = 0, ("No verifiable quote; not documented. " + explanation).strip()
        elif level > 1 and v.only_in_skills(quotes):
            v.log.append(f"{req['name']}: evidence only in the skills list, level {level} → 1 (claimed).")
            level, explanation = 1, ("Only listed among skills: a claim, not documented evidence. " + explanation)
        elif level > 2 and not any(substantial(q) or _norm(q) in dated_jobs for q in quotes):
            v.log.append(f"{req['name']}: only a word or two quoted, level {level} → 2 (partly shown).")
            level, explanation = 2, ("Only a word or two quoted from the CV: partly shown, to verify. " + explanation)
        if _SENSITIVE_RE.search(explanation):
            v.log.append(f"{req['name']}: explanation referred to residence or a personal characteristic, removed.")
            explanation = "Explanation removed: it referred to residence or a personal characteristic."
        against = str(raw.get("against_quote") or "").strip() or None
        if against and not v.quote_ok(against):
            v.log.append(f"{req['name']}: contrary quote not found in the CV, discarded.")
            against = None
        # Profile dimensions are designed to be read from a CV: only a requirement the manager added (for example
        # an attitude) can be declared not assessable. The AI had excluded 7 of 8 for a bare CV (20-CV run).
        assessable = not (req["id"].startswith("custom") and raw.get("assessable") is False)
        results[req["id"]] = {"level": level, "quotes": quotes, "explanation": explanation, "computed": False,
                              "assessable": assessable, "against": against}

    competences = []
    for raw in data.get("competences") or []:
        if not isinstance(raw, dict) or not str(raw.get("name") or "").strip():
            continue
        level = raw.get("level") if raw.get("level") in COMPETENCE_LEVELS else "claimed"
        quote = str(raw.get("quote") or "").strip()
        if not v.quote_ok(quote):
            v.log.append(f"Competence “{raw['name']}”: quote not found in the CV, discarded.")
            continue
        if level != "claimed" and v.only_in_skills([quote]):
            v.log.append(f"Competence “{raw['name']}”: only in the skills list, {level} → claimed.")
            level = "claimed"
        elif level != "claimed" and not substantial(quote):
            v.log.append(f"Competence “{raw['name']}”: quote too short to document work, {level} → claimed.")
            level = "claimed"
        competences.append({"name": str(raw["name"]).strip(), "level": level, "quote": quote,
                            "employer": raw.get("employer")})

    strengths = [{"text": str(s.get("text")).strip(), "quote": str(s.get("quote")).strip()}
                 for s in data.get("strengths") or []
                 if isinstance(s, dict) and s.get("text") and v.quote_ok(s.get("quote"))
                 and not _SENSITIVE_RE.search(str(s.get("text")))]

    flags, moved_to_verify = [], []
    for raw in data.get("risk_flags") or []:
        if not isinstance(raw, dict) or not raw.get("flag"):
            continue
        text = f"{raw.get('flag')} {raw.get('fact') or ''}"
        if _SENSITIVE_RE.search(text):
            v.log.append(f"Flag “{raw['flag']}” refers to residence or a personal characteristic: dropped.")
        elif _DURATION_RE.search(text):
            v.log.append(f"Flag “{raw['flag']}” states a duration or gap written by the AI: dropped "
                         "(durations are computed from the dates).")
        elif _ABSENCE_RE.search(str(raw["flag"])):
            moved_to_verify.append(str(raw["flag"]).strip())
            v.log.append(f"Flag “{raw['flag']}” describes missing information: moved to To verify.")
        elif not v.quote_ok(raw.get("quote")):
            # Usually missing information phrased as a flag: kept as a point to verify, not as a red flag.
            moved_to_verify.append(str(raw["flag"]).strip())
            v.log.append(f"Flag “{raw['flag']}” has no quote found in the CV: moved to To verify.")
        else:
            flags.append({"flag": str(raw["flag"]).strip(), "fact": str(raw.get("fact") or "").strip(),
                          "quote": str(raw["quote"]).strip(), "question": str(raw.get("question") or "").strip(),
                          "source": "CV"})
    role_flag = _environment_flag(role_code, jobs, v)
    if role_flag:
        flags.append(role_flag)
    for f in timeline["stability"]["flags"]:
        flags.append({"flag": f["text"], "fact": "Computed from the dates in the CV.", "quote": "",
                      "question": "Could you tell me about the shorter jobs in your work history?",
                      "source": "DATES", "severity": f["severity"]})

    unknowns = []
    for u in list(data.get("unknowns") or []) + moved_to_verify:
        u = str(u).strip()
        if u and _SENSITIVE_RE.search(u):
            v.log.append(f"Missing-information line about residence or a personal characteristic dropped (“{u[:60]}”).")
        elif u and _DURATION_RE.search(u) and not re.search(r"\bgaps?\b", u, re.I):
            v.log.append(f"Missing-information line states a duration written by the AI: dropped (“{u[:60]}”).")
        elif u and re.search(r"\bdates?\b", u, re.I) and (
                all(j.get("date_status") == "OK" for j in jobs)
                or any(j.get("employer") and str(j["employer"]).lower() in u.lower() for j in jobs)):
            # Dates are owned by the code: verified ones are shown, really missing ones get the code's own note.
            v.log.append(f"Missing-information line about a job's dates replaced by the code's check (“{u[:60]}”).")
        elif u and u not in unknowns:
            unknowns.append(u)
    unknowns += [f"Gap of {g['text']}: not explained in the CV (to verify, not a judgement)." for g in timeline["gaps"]]
    unknowns += [n for n in timeline["date_notes"] if "not in the CV" not in n]
    if not timeline["stability"]["known"]:
        unknowns.append("Stability cannot be computed: no verifiable job dates.")

    def stated(key, field):
        item = data.get(key)
        if isinstance(item, dict) and item.get(field) is not None and v.quote_ok(item.get("quote")):
            return item
        return None

    questions = [str(q).strip() for q in data.get("questions") or []
                 if str(q).strip() and not _SENSITIVE_RE.search(str(q))][:5]
    return {"full_name": name, "jobs": jobs, "gaps": timeline["gaps"], "stability": timeline["stability"],
            "requirements": results, "competences": competences, "strengths": strengths, "flags": flags,
            "unknowns": unknowns, "stated_hours": stated("stated_hours", "hours"),
            "stated_availability": stated("stated_availability", "text"), "questions": questions,
            "verification_log": v.log, "prompt_version": PROMPT_VERSION, "checks_version": CHECKS_VERSION,
            "profile_version": pp.PROFILES[role_code]["version"]}
