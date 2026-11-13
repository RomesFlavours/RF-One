"""The prototype's ONLY door to AI.

It reuses Selection's existing provider-neutral client
(`rfone_data_store.selection.parsing.ai_client.generate_json`) — no second AI
infrastructure. When RF-One's central AI service (Cognito) exists, only
`_transport` below changes.

Two separate permissions, both OFF unless the prototype is started with them:

* `ai_enabled` (`--ai`): AI may draft positions (requirements, headcount,
  English ad) and candidate messages. No candidate data is sent: messages
  are drafted with placeholders filled in locally.
* `cv_ai_authorized` (`--ai-cv`): AI may read real CVs and interview answers
  (structured reading at import, follow-up questions, evaluation).

Important: Selection's import chain tries AI parsing first whenever a
provider is configured (the repo-root `.env` configures one). `install_guard`
replaces, in THIS process only, the function the CV parser calls, so no CV
leaves the PC without `--ai-cv`; the parser then falls back to the existing
rule-based reader. Nothing in the shared code is modified.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from rfone_data_store.selection.core import fit_assessment_model as fam
from rfone_data_store.selection.core import requirement_model as rm
from rfone_data_store.selection.parsing import ai_client, llm_parser
from rfone_data_store.selection.parsing.ai_client import AIProviderUnavailable

_REAL_GENERATE_JSON = ai_client.generate_json


@dataclass
class AIPolicy:
    ai_enabled: bool = False
    cv_ai_authorized: bool = False
    last_call: dict = field(default_factory=dict)  # {"at", "ok", "purpose", "message"}

    @property
    def provider_label(self) -> str:
        provider = ai_client._active_provider()
        if provider == ai_client.PROVIDER_BEDROCK:
            model = ai_client._read_env_or_dotenv("RFONE_BEDROCK_MODEL_ID") or "modello non configurato"
            return f"AWS Bedrock · {model}"
        if provider == ai_client.PROVIDER_ANTHROPIC:
            return "Anthropic API" + ("" if ai_client._anthropic_api_key() else " (chiave non configurata)")
        return f"provider non valido {provider!r}"

    def status_lines(self) -> list[tuple[str, bool, str]]:
        """(feature, active, explanation) for the status panel."""
        off_pos = "non attiva: avviare il prototipo con l'autorizzazione --ai"
        off_cv = "non attiva: nessun CV o risposta viene inviato all'AI senza autorizzazione esplicita (--ai-cv)"
        return [
            ("Proposta posizione (requisiti, persone, annuncio)", self.ai_enabled, "attiva" if self.ai_enabled else off_pos),
            ("Bozze di comunicazione in inglese", self.ai_enabled,
             "attiva" if self.ai_enabled else "non attiva: si usano testi standard modificabili"),
            ("Domande d'intervista costruite sul CV", self.cv_ai_authorized,
             "attiva" if self.cv_ai_authorized else off_cv + "; si usano solo le domande standard approvate"),
            ("Valutazione AI di CV e risposte", self.cv_ai_authorized,
             "attiva" if self.cv_ai_authorized else off_cv + "; valutazione con i motori esistenti"),
        ]


POLICY = AIPolicy()


def _record(purpose: str, ok: bool, message: str) -> None:
    POLICY.last_call = {"at": datetime.now(UTC).replace(tzinfo=None), "ok": ok, "purpose": purpose,
                        "message": message}


def _cv_parser_gate(prompt: str) -> dict:
    if not POLICY.cv_ai_authorized:
        raise AIProviderUnavailable("Lettura AI dei CV non autorizzata nel prototipo.")
    return _transport(prompt, "lettura CV")


def install_guard(*, ai_enabled: bool, cv_ai_authorized: bool) -> None:
    POLICY.ai_enabled = ai_enabled or cv_ai_authorized
    POLICY.cv_ai_authorized = cv_ai_authorized
    # Every in-process path that could send a CV to a provider goes through one of these two names.
    llm_parser.generate_json = _cv_parser_gate
    ai_client.generate_json = _cv_parser_gate


def _transport(prompt: str, purpose: str) -> dict:
    """Single seam towards the (future central) AI service."""
    try:
        result = _REAL_GENERATE_JSON(prompt)
    except AIProviderUnavailable as exc:
        text = str(exc)
        if any(k in text for k in ("expired", "reauthenticate", "Token", "credentials")):
            exc = AIProviderUnavailable("la sessione AWS di questo PC è scaduta: eseguire «aws login» e riprovare. "
                                        "Intanto puoi compilare la posizione a mano.")
        _record(purpose, False, str(exc))
        raise exc
    _record(purpose, True, "ok")
    return result


def _require(flag: bool, what: str) -> None:
    if not flag:
        raise AIProviderUnavailable(f"{what}: funzione AI non attiva nel prototipo.")


_PROTECTED = ("age, sex/gender, nationality, origin, ethnicity, religion, family status, pregnancy, disability, "
              "health, appearance, address or where the person lives, or proxies for them")

# ---------------------------------------------------------------------------
# 1. Position draft (no candidate data)
# ---------------------------------------------------------------------------

CATEGORY_LABELS_IT = {
    "Experience": "Esperienza",
    "Role Skills": "Competenze del ruolo",
    "Technical Knowledge": "Conoscenze tecniche",
    "Customer Orientation": "Orientamento al cliente",
    "Sales": "Vendita",
    "Leadership / Management": "Coordinamento / gestione",
    "Communication": "Comunicazione / lingue",
    "Availability / Practical Constraints": "Disponibilità / vincoli pratici",
    "Certifications / Legal Requirements": "Certificazioni / requisiti di legge",
    "Teamwork": "Lavoro in squadra",
    "Attitude / Behavioral Traits": "Atteggiamento",
    "Trainability / Learning": "Apprendimento",
    "Accountability / Work Ethic": "Affidabilità",
    "Other": "Altro",
}

_POSITION_PROMPT = """You help a restaurant manager open a position. Output ONLY a JSON object, no markdown.

Position title: {title}
Role: {role}
Restaurant location: {location}
Manager's description (natural language, may be Italian): <<<{description}>>>

Company facts available (use ONLY these; never invent company facts):
{company_facts}
Company information NOT available: {missing_facts}

Produce:
1. "requirements": job-relevant, observable requirements, written in ITALIAN ("name", "description", "why").
   Mark MUST_HAVE only what the description clearly makes essential. Never use {protected}.
   Résumés are in ENGLISH: in "cv_keywords" list English words a résumé would show (titles, certifications, skills).
2. "headcount": number of people to hire ONLY if the description states or clearly implies it, else null.
3. "job_ad_en": a short, friendly job ad in ENGLISH (max 180 words). Use only the facts above and the description.
   For important missing facts (pay, schedule, benefits, start date) write a bracketed placeholder such as
   [Pay: to be completed] — never invent them. No discriminatory wording.
4. "open_questions": in ITALIAN, what the manager should still decide or provide.

JSON shape:
{{"requirements": [{{"name": "...", "description": "...", "category": one of {categories},
  "criticality": one of ["MUST_HAVE","PREFERRED","OPTIONAL"], "trainability": one of {trainability},
  "cv_keywords": ["..."], "why": "..."}}],
 "headcount": <int or null>, "job_ad_en": "...", "open_questions": ["..."]}}
"""


def draft_position(*, title: str, role: str, location: str, description: str, company_facts: list[str],
                   missing_facts: list[str]) -> dict:
    _require(POLICY.ai_enabled, "Proposta posizione")
    prompt = _POSITION_PROMPT.format(
        title=title, role=role, location=location, description=description.strip() or "(nessuna descrizione)",
        company_facts="\n".join(f"- {f}" for f in company_facts) or "- (none)",
        missing_facts=", ".join(missing_facts) or "-", protected=_PROTECTED,
        categories=json.dumps(list(CATEGORY_LABELS_IT)), trainability=json.dumps(list(rm.TRAINABILITY_LEVELS)),
    )
    data = _transport(prompt, "proposta posizione")
    if not isinstance(data, dict) or not isinstance(data.get("requirements"), list):
        raise AIProviderUnavailable("Risposta AI non valida (manca l'elenco dei requisiti).")
    items = []
    for raw in data["requirements"][:20]:
        if not isinstance(raw, dict) or not str(raw.get("name") or "").strip():
            continue
        items.append({
            "name": str(raw["name"]).strip()[:255],
            "description": str(raw.get("description") or "").strip(),
            "category": raw.get("category") if raw.get("category") in CATEGORY_LABELS_IT else "Other",
            "criticality": raw.get("criticality") if raw.get("criticality") in (rm.MUST_HAVE, rm.PREFERRED, rm.OPTIONAL)
            else rm.PREFERRED,
            "trainability": raw.get("trainability") if raw.get("trainability") in rm.TRAINABILITY_LEVELS
            else rm.TRAINABILITY_UNKNOWN,
            "cv_keywords": [str(k).strip() for k in (raw.get("cv_keywords") or []) if str(k).strip()][:12],
            "why": str(raw.get("why") or "").strip(),
        })
    if not items:
        raise AIProviderUnavailable("La risposta AI non contiene requisiti utilizzabili.")
    headcount = data.get("headcount")
    headcount = headcount if isinstance(headcount, int) and 0 < headcount < 100 else None
    return {"requirements": items, "headcount": headcount, "job_ad_en": str(data.get("job_ad_en") or "").strip(),
            "open_questions": [str(q).strip() for q in (data.get("open_questions") or []) if str(q).strip()][:10]}


# ---------------------------------------------------------------------------
# 2. Interview follow-up questions from the CV (CV data)
# ---------------------------------------------------------------------------

_FOLLOWUP_PROMPT = """You prepare a SHORT written screening interview (about 5 minutes) for a restaurant job applicant.
Output ONLY a JSON object, no markdown. Questions in simple ENGLISH.

Position: {title} ({role})
Approved requirements: {requirements}
Standard questions already asked (do not repeat them): {standard}
Résumé text (contact details removed): <<<{cv_text}>>>

Write at most {n} additional questions that clarify job-relevant points of THIS résumé against the requirements:
missing or unclear experience, dates, duties, certifications. Neutral and respectful. Never ask about {protected}.
Do not assume that missing information means a negative answer.

JSON shape: {{"questions": ["..."]}}
"""


def interview_followups(*, title: str, role: str, requirements: list[str], standard: list[str], cv_text: str,
                        n: int = 3) -> list[str]:
    _require(POLICY.cv_ai_authorized, "Domande sul CV")
    data = _transport(_FOLLOWUP_PROMPT.format(
        title=title, role=role, requirements="; ".join(requirements) or "-", standard=json.dumps(standard),
        cv_text=redact_contacts(cv_text), n=n, protected=_PROTECTED), "domande d'intervista")
    questions = [str(q).strip() for q in (data.get("questions") or []) if str(q).strip()] if isinstance(data, dict) else []
    return questions[:n]


# ---------------------------------------------------------------------------
# 3. Candidate evaluation against approved requirements (CV + answers)
# ---------------------------------------------------------------------------

AI_STATUSES = (fam.EVIDENCED, fam.PARTIALLY_EVIDENCED, fam.NOT_EVIDENCED, fam.CONFLICTING_EVIDENCE,
               fam.NOT_ASSESSED_AT_THIS_STAGE)

_EVALUATION_PROMPT = """You assist a restaurant manager screening one applicant against the restaurant's APPROVED
requirements. You do not decide; the manager does. Output ONLY a JSON object, no markdown.
Write explanations and questions in ITALIAN.

Approved requirements:
{requirements}

Résumé text (contact details removed): <<<{cv_text}>>>

Applicant's interview answers: <<<{answers}>>>

Rules:
- For each requirement choose a status:
  EVIDENCED (clearly shown), PARTIALLY_EVIDENCED (some but incomplete evidence),
  NOT_EVIDENCED (not shown — this means MISSING INFORMATION, not proof of absence),
  CONFLICTING_EVIDENCE (the sources contradict each other), NOT_ASSESSED_AT_THIS_STAGE (cannot be judged
  from these sources, e.g. attitude — to verify in interview).
- Every EVIDENCED / PARTIALLY_EVIDENCED / CONFLICTING_EVIDENCE status needs at least one "quotes" entry copied
  EXACTLY, word for word, from the résumé text or from the answers. No paraphrase.
- Never use or infer {protected}. Do not judge personality from wording, grammar or English level unless a
  requirement explicitly concerns English communication.
- Suggest at most 5 neutral interview questions about what is missing or unclear.

JSON shape:
{{"requirements": [{{"id": <id>, "status": "...", "quotes": ["..."], "explanation": "..."}}],
  "interview_questions": ["..."]}}
"""

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")


def redact_contacts(text: str) -> str:
    return _PHONE_RE.sub("[telefono rimosso]", _EMAIL_RE.sub("[email rimossa]", text or ""))


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def evaluate_candidate(*, requirements: list[dict], cv_text: str, answers_text: str = "") -> dict:
    """requirements: [{"id", "name", "description", "criticality"}]. Only quotes found verbatim in
    the CV or the answers are kept; a status that needs evidence but has none verifiable becomes
    NOT_EVIDENCED (missing information)."""
    _require(POLICY.cv_ai_authorized, "Valutazione AI dei CV")
    req_text = "\n".join(
        f"- id={r['id']} [{r['criticality']}] {r['name']}: {r.get('description') or ''}" for r in requirements)
    data = _transport(_EVALUATION_PROMPT.format(requirements=req_text, cv_text=redact_contacts(cv_text),
                                                answers=redact_contacts(answers_text) or "(none)",
                                                protected=_PROTECTED), "valutazione candidato")
    if not isinstance(data, dict) or not isinstance(data.get("requirements"), list):
        raise AIProviderUnavailable("Risposta AI non valida (manca la valutazione dei requisiti).")

    cv_hay, answers_hay = _normalized(cv_text), _normalized(answers_text)
    known_ids = {r["id"] for r in requirements}
    results: dict[int, dict] = {}
    for raw in data["requirements"]:
        if not isinstance(raw, dict):
            continue
        try:
            req_id = int(raw.get("id"))
        except (TypeError, ValueError):
            continue
        if req_id not in known_ids:
            continue
        status = raw.get("status") if raw.get("status") in AI_STATUSES else fam.NOT_ASSESSED_AT_THIS_STAGE
        quotes, dropped = [], []
        for q in (raw.get("quotes") or [])[:5]:
            q = str(q).strip()
            nq = _normalized(q)
            if q and nq in cv_hay:
                quotes.append({"text": q, "source": "CV"})
            elif q and nq in answers_hay:
                quotes.append({"text": q, "source": "ANSWERS"})
            elif q:
                dropped.append(q)
        explanation = str(raw.get("explanation") or "").strip()
        if status in (fam.EVIDENCED, fam.PARTIALLY_EVIDENCED, fam.CONFLICTING_EVIDENCE) and not quotes:
            status = fam.NOT_EVIDENCED
            explanation = ("Nessuna citazione verificabile: trattato come non dimostrato. " + explanation).strip()
        results[req_id] = {"status": status, "quotes": quotes, "explanation": explanation, "dropped_quotes": dropped}
    for req_id in known_ids - results.keys():
        results[req_id] = {"status": fam.NOT_ASSESSED_AT_THIS_STAGE, "quotes": [], "dropped_quotes": [],
                           "explanation": "L'AI non ha restituito una valutazione per questo requisito."}
    questions = [str(q).strip() for q in (data.get("interview_questions") or []) if str(q).strip()][:5]
    return {"requirements": results, "interview_questions": questions}


# ---------------------------------------------------------------------------
# 4. Candidate messages (no candidate data: placeholders filled locally)
# ---------------------------------------------------------------------------

_MESSAGE_PROMPT = """Write a short, warm, professional message in ENGLISH from a restaurant to a job applicant.
Output ONLY a JSON object: {{"body": "..."}}. Plain text, max 120 words, no subject line.
Purpose: {purpose}
Position: {title} at {location}
Facts to include: {facts}
Use exactly these placeholders where needed and nothing invented: [Candidate first name], [Manager name].
Do not give reasons tied to personal characteristics. Do not promise anything not stated.
"""

MESSAGE_PURPOSES = {
    "INVITE": "invite the applicant to an interview at the date/time given",
    "SLOTS": "ask the applicant to choose an interview time using the link given",
    "REJECTION": "inform the applicant kindly that they were not selected this time",
    "HIRE": "tell the applicant the restaurant would like to offer them the position and ask them to confirm",
    "ON_HOLD": "tell the applicant their application is still being considered and they will hear back",
}


def draft_message(*, kind: str, title: str, location: str, facts: str) -> str:
    _require(POLICY.ai_enabled, "Bozza di comunicazione")
    data = _transport(_MESSAGE_PROMPT.format(purpose=MESSAGE_PURPOSES[kind], title=title, location=location,
                                             facts=facts or "none"), "bozza comunicazione")
    body = str(data.get("body") or "").strip() if isinstance(data, dict) else ""
    if not body:
        raise AIProviderUnavailable("La risposta AI non contiene un testo.")
    return body
