"""Rewrite with AI (BANK_AI_RULES_026): a rule's text rewritten in clear,
unambiguous natural language that the AI Rules interpreter can execute.

It only rewrites and verifies — it never saves, changes or applies a rule:

  0. the ORIGINAL text goes through the interpreter first (its saved
     interpretation when there is one — no AI call): when the interpreter
     itself names an instruction it cannot represent, nothing is rewritten
     and that part is reported — a rewrite could only change its meaning;
  1. ONE AI call rewrites the text using exactly the elements the interpreter
     accepts (`ai_rules.interpreter_capabilities()`, the same description the
     interpreter itself is given — no separate list), or answers that a part
     is not representable (UNSUPPORTED) or must be clarified (AMBIGUOUS).
     A rule that can be read in more than one way with different results is
     never rewritten — no reading is picked; an informal wording with one
     reading may be. With a rewrite the AI must report its own check, empty:
     the points with more than one reading ("ambiguities") and what it added
     ("invented") — BANK_AI_RULES_027;
  2. the rewritten text goes through the SAME interpreter and the SAME checks
     as Preview (`ai_rules._interpret`: the same prompt, `validate_interpretation`
     with its mandatory coverage, nothing unsupported, every text copied from
     the rule, active entities) — its interpretation is saved like a Preview's,
     so a later Preview of that text reuses it;
  3. RF-One code then checks that nothing was invented or altered: every WHO
     and WHY name the rewritten rule assigns is written, character for
     character, in the original; every other text it uses is in the original;
     and when the original has a valid interpretation, the rewritten one must
     execute exactly the same way.

Only when all of this holds is the rewritten text returned; otherwise the
original stays as it is, with the reason.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from .. import models as m
from ..selection.parsing import ai_client
from . import ai_rules

REWRITTEN, UNSUPPORTED, AMBIGUOUS = "REWRITTEN", "UNSUPPORTED", "AMBIGUOUS"
_LOCK = threading.Lock()          # one rewrite at a time in this process: a second press never asks twice


@dataclass
class RewriteResult:
    ok: bool
    status: str                   # REWRITTEN (validated) / UNSUPPORTED / AMBIGUOUS / INVALID
    message: str
    text: str | None = None
    details: list[str] = field(default_factory=list)
    # Conflicts with the other ACTIVE rules (`ai_rules.rule_conflicts`): about other rules, never about this
    # text — reported next to the rewrite's own outcome, whatever it is.
    conflicts: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"ok": self.ok, "status": self.status, "message": self.message, "text": self.text,
                "details": self.details, "conflicts": self.conflicts}


def rewrite_prompt(rule_text: str, example: str, instructions: str | None) -> str:
    general = f"\nGENERAL AI INSTRUCTIONS OF THE OPERATOR (context):\n{instructions}\n" if instructions else ""
    return f"""An operator of a bank reconciliation tool wrote this classification rule for bank and card movements:

RULE:
{rule_text}

EXAMPLE movement description the rule was written from:
{example}
{general}
Rewrite the rule in clear, unambiguous natural language, in the same language as the rule, so that a program can
carry it out with ONLY the elements below — the complete list of what the program executes:

{ai_rules.interpreter_capabilities()}

How to rewrite:
- Keep EVERY condition, exception and assignment of the rule with exactly the same meaning. Add no constraint, drop
  nothing, never simplify by changing the meaning.
- Copy every WHO and WHY value EXACTLY as the rule writes it (same characters, same case), in quotes. Copy every other
  text the rule names (description texts, delimiters, Source names, entities) exactly.
- Never replace an operation with a different one, even a similar one the elements support: e.g. "is equal to" /
  "uguale a" is NOT "contains" / "contiene"; "ends with TEXT" is NOT "contains TEXT".
- Write sentences an operator understands ("la descrizione contiene “X”"), never JSON, field or mode names.
- If any instruction of the rule cannot be carried out with these elements: do NOT rewrite. Answer UNSUPPORTED and
  name, briefly, the part that is not supported.
- If the rule can be read in more than one way that the program would execute differently (e.g. which conditions an
  "or" / "and" / "except" joins, which movements an exception covers, which value goes to WHO and which to WHY, a
  vague word such as "le spese di casa" with no text to look for): do NOT rewrite and do NOT pick one reading. Answer
  AMBIGUOUS and say, briefly, which information is missing.
- An informal wording MAY be rewritten (abbreviations, arrows, missing verbs, word order, typos) as long as only ONE
  reading is possible and nothing has to be invented: no condition, exception or assignment the rule does not state.
- Before answering REWRITTEN, check yourself and report it: "ambiguities" lists every point where the rule can be
  read in more than one way that executes differently; "invented" lists every condition, exception or assignment
  of your text that the rule does not state. Both must be empty for a rewrite; otherwise answer AMBIGUOUS.

Answer ONLY with JSON, no markdown:
{{"status": "REWRITTEN", "text": "the rewritten rule", "who_why_values": ["every WHO and WHY value the rule names,
  exactly as written in the rule"], "ambiguities": [], "invented": []}}
or
{{"status": "UNSUPPORTED", "unsupported": ["the part that is not supported"], "reason": "why, briefly"}}
or
{{"status": "AMBIGUOUS", "clarify": ["what must be clarified"], "reason": "why, briefly"}}"""


def _ambiguous(missing: list[str]) -> RewriteResult:
    """BANK_AI_RULES_027 — the original stays; the window says which information is missing."""
    return RewriteResult(False, AMBIGUOUS, "Not rewritten: the rule can be read in more than one way, with different "
                         "results. The text was not changed. Missing information:", details=missing)


def _exact(text: str | None) -> str:
    """For comparing values character for character: only dashes, double
    quotes and spaces made alike — case kept."""
    return " ".join(str(text or "").translate(ai_rules._DASHES).translate(ai_rules._QUOTES).split())


def _in_exactly(container: str, value: str) -> bool:
    return bool(_exact(value)) and _exact(value) in _exact(container)


def _parts(spec: dict):
    """(assignments, texts) of a validated spec: its assignments, rule level and
    branches, and every text it uses."""
    blocks = [spec] + list(spec.get("branches") or [])
    assignments = [(kind, block.get(kind)) for block in blocks for kind in ("who", "why")]
    texts = []
    for block in blocks:
        texts += [c["value"] for c in block.get("conditions") or [] if c.get("value") and
                  c["field"] in ai_rules.TEXT_FIELDS]
        who = block.get("who") or {}
        texts += [who.get(k) for k in ("start", "end", "after") if who.get(k)] + list(who.get("starts") or [])
        for_whom = block.get("for_whom") or {}
        texts += [for_whom.get(k) for k in ("entity", "marker") if for_whom.get(k)]
        texts += [v for n in for_whom.get("names") or [] for v in (n.get("name"), n.get("entity"))]
    return assignments, texts


def _same_execution(a: dict, b: dict) -> bool:
    """Two specs execute alike: everything but the coverage, texts compared as
    the engine reads them (case, quotes, dashes and spaces aside)."""
    def norm(value):
        if isinstance(value, dict):
            return {k: norm(v) for k, v in value.items() if k != "coverage"}
        if isinstance(value, list):
            return [norm(v) for v in value]
        return ai_rules._norm(value) if isinstance(value, str) else value
    return norm(a) == norm(b)


def _faithfulness_problems(original: str, spec: dict, values: list[str]) -> list[str]:
    problems = []
    assignments, texts = _parts(spec)
    for kind, assignment in assignments:
        if assignment and assignment.get("mode") == "fixed" and not _in_exactly(original, assignment["name"]):
            problems.append(f"the {kind.upper()} “{assignment['name']}” is not written exactly so in the original rule")
    for text in texts:
        if not ai_rules._in_rule(original, text):
            problems.append(f"the text “{text}” is not in the original rule")
    for value in values:
        if not _in_exactly(original, value):
            problems.append(f"the WHO/WHY value “{value}” is not written exactly so in the original rule")
    return problems


def rewrite_rule(session: Session, *, rule_text: str | None, origin_transaction_id: int | None,
                 origin_description: str | None = None, generate=None, rule_id: int | None = None,
                 title: str | None = None) -> RewriteResult:
    """Rewrite and verify (see the module). Raises `ai_rules.AiRuleError` when
    it cannot even be attempted (no text, the AI not available, a rewrite
    already running); otherwise the result says whether the text was rewritten
    and validated, and why not — and, separately, which other ACTIVE rules it
    conflicts with (`rule_id`: the rule being edited, never compared with
    itself)."""
    seen: dict = {}
    result = _rewrite(session, rule_text=rule_text, origin_transaction_id=origin_transaction_id,
                      origin_description=origin_description, generate=generate, seen=seen)
    result.conflicts = ai_rules.rule_conflicts(session, seen.get("spec"), rule_id=rule_id, title=title)
    return result


def _rewrite(session: Session, *, rule_text: str | None, origin_transaction_id: int | None,
             origin_description: str | None, generate, seen: dict) -> RewriteResult:
    """The rewrite itself; `seen["spec"]`: the executable form found (the
    original's, else the rewritten text's), for the conflict check."""
    original = (rule_text or "").strip()
    if not original:
        raise ai_rules.AiRuleError("Write the rule before asking to rewrite it.")
    origin = session.get(m.FinancialTransaction, origin_transaction_id) if origin_transaction_id else None
    example = origin.description_original if origin is not None else (origin_description or "")
    generate = generate or ai_rules.default_generate()
    if generate is ai_rules._session_generate:
        raise ai_rules.AiRuleError("Rewrite with AI needs the AI, which is not available here (the Claude Code CLI "
                                   "is not enabled on this PC). The text was not changed.")
    instruction = ai_rules.current_instruction(session)
    instructions = instruction.instructions if instruction and instruction.instructions else None
    if not _LOCK.acquire(blocking=False):
        raise ai_rules.AiRuleError("A rewrite is already running: wait for it to finish. The text was not changed.")
    try:
        limiter, calls = ai_rules._Limiter(1), ai_rules._Calls()
        try:
            first, _reused = ai_rules._interpret(session, original, example, instructions, generate, limiter, calls)
        except ai_client.AIProviderUnavailable as exc:
            raise ai_rules.AiRuleError(f"The AI could not read the rule ({exc}). The text was not changed.") from exc
        original_spec = json.loads(first.spec) if first.spec else None
        if not (original_spec and ai_rules.spec_usable(original_spec)):
            original_spec = None
            raw = json.loads(first.raw_answer) if first.raw_answer else {}
            named = [" ".join(str(u).split()) for u in ((raw.get("unsupported") if isinstance(raw, dict) else None)
                                                        or []) if str(u).strip()]
            if named:
                return RewriteResult(False, UNSUPPORTED, "Not rewritten: the AI Rules interpreter cannot carry out "
                                     "part of the rule. The text was not changed.", details=named)
        else:
            seen["spec"] = original_spec
        try:
            answer = ai_rules._call(generate, rewrite_prompt(original, ai_rules.mask_numbers(example), instructions),
                                    limiter, calls)
        except ai_client.AIProviderUnavailable as exc:
            raise ai_rules.AiRuleError(f"The AI could not rewrite the rule ({exc}). The text was not changed.") from exc
        status = str((answer or {}).get("status") or "").upper() if isinstance(answer, dict) else ""
        if status == UNSUPPORTED:
            parts = [" ".join(str(p).split()) for p in answer.get("unsupported") or [] if str(p).strip()]
            return RewriteResult(False, UNSUPPORTED, "Not rewritten: part of the rule cannot be carried out by the "
                                 "AI Rules interpreter. The text was not changed.",
                                 details=parts or [" ".join(str(answer.get("reason") or "").split())])
        if status == AMBIGUOUS:
            parts = [" ".join(str(p).split()) for p in answer.get("clarify") or [] if str(p).strip()]
            return _ambiguous(parts or [" ".join(str(answer.get("reason") or "").split())])
        rewritten = str(answer.get("text") or "").strip() if status == REWRITTEN else ""
        if not rewritten:
            return RewriteResult(False, "INVALID", "Not rewritten: the AI did not return a rewritten rule. The text "
                                 "was not changed.")
        # BANK_AI_RULES_027 — a rewrite never picks one reading of an ambiguous
        # rule nor invents a condition, exception or assignment: the AI's own
        # check must be present and empty, otherwise nothing is replaced.
        ambiguities, invented = answer.get("ambiguities"), answer.get("invented")
        if not isinstance(ambiguities, list) or not isinstance(invented, list):
            return RewriteResult(False, "INVALID", "Not rewritten: the AI did not confirm that the rule has one "
                                 "reading only and that nothing was added. The text was not changed.")
        ambiguities = [" ".join(str(p).split()) for p in ambiguities if str(p).strip()]
        invented = [" ".join(str(p).split()) for p in invented if str(p).strip()]
        if ambiguities:
            return _ambiguous(ambiguities)
        if invented:
            return RewriteResult(False, "INVALID", "Not rewritten: the rewrite would add what the rule does not "
                                 "state. The text was not changed.", details=[f"added: {p}" for p in invented])
        values = [str(v) for v in answer.get("who_why_values") or [] if str(v).strip()]
        # The SAME interpreter and checks as Preview.
        try:
            interpretation, _reused = ai_rules._interpret(session, rewritten, example, instructions, generate,
                                                          limiter, calls)
        except ai_client.AIProviderUnavailable as exc:
            raise ai_rules.AiRuleError(f"The rewritten text could not be verified ({exc}). The text was not "
                                       "changed.") from exc
        spec = json.loads(interpretation.spec) if interpretation.spec else None
        if not spec or not ai_rules.spec_usable(spec):
            return RewriteResult(False, "INVALID", "Not rewritten: the rewritten text did not pass the interpreter's "
                                 "checks. The text was not changed.",
                                 details=[interpretation.rejection_reason or "no executable form"])
        seen.setdefault("spec", spec)
        problems = _faithfulness_problems(original, spec, values)
        if not problems:
            for value in values:
                if not _in_exactly(rewritten, value):
                    problems.append(f"the WHO/WHY value “{value}” is not kept exactly in the rewritten rule")
        if not problems and original_spec is not None and not _same_execution(original_spec, spec):
            problems.append("the rewritten rule would be executed differently from the original rule")
        if problems:
            return RewriteResult(False, "INVALID", "Not rewritten: the rewritten text would not keep the rule as it "
                                 "is. The text was not changed.", details=problems)
        return RewriteResult(True, REWRITTEN, "Rewritten and validated", text=rewritten,
                             details=[f"{c['instruction']} → {c['represented_by']}" for c in spec.get("coverage") or []])
    finally:
        _LOCK.release()
