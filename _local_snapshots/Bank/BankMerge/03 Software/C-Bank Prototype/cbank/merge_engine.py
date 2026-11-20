"""Bank Claude coordinator — the existing engines, combined; nothing rewritten.

The single reconciliation engine (`cbank.engine.Engine`, C-Bank worktree) is reused as it is: Source owner,
matched transfers / card payments, WHO rules (111-117 included), name / alias recognition, rule-extracted WHO
registration, WHO + Source WHY, WHO WHY rules (WHO / category / general scope), Amazon documents and splits,
WHAT from WHY, protection of human decisions. `cbank.service._execute` is reused for the run itself
(registration, pairs, storage, matches) by giving it this module's engine.

What Bank Claude adds is only coordination:

1. **Approved text rules, WHY part.** The 101 older STRUCTURED rules approved by the Product Owner are still
   executed by the engine for the WHO, but their WHY was disconnected. Here, when the engine leaves a recognised
   UNIQUE WHO without WHY only because its exact WHO + Source pair has none (`WHO_SOURCE_CLASSIFICATION_MISSING`),
   the WHY named by the approved text rule(s) that matched THIS movement is used — only when every matching rule
   names the same active, non-provisional WHY, the rule names the same WHO (or no WHO), and no field is "Da
   verificare". WHO-only defaults (`why_default`), historical associations and other Sources are never used
   (BANK_WHO_SOURCE_CLASSIFICATION_001). Different WHYs = conflict, never a choice.
2. **Method conflicts, measured on every movement.** Approved text rule WHY ≠ pair WHY / WHO WHY rule WHY;
   WHO rule ≠ unique name/alias found in the text. They are recorded per movement and, in `strict` mode, turn
   the movement into a conflict instead of letting one method win.
3. **One final state per movement** (`final_state`), counted once, with the human decisions kept apart.

The engine's own trace, exceptions and protection logic are untouched: the WHY found by step 1 goes through
the same `_finish` (direction conflict, personal Source with business WHAT, provisional WHY, WHAT from WHY).
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict



POLICY = "bank-claude-v1"
LEGACY_METHOD = "REGOLA TESTUALE APPROVATA"

# Final states — exactly one per movement; they add up to the total.
HUMAN, COMPLETE, PROPOSAL, WHO_ONLY, CONFLICT, UNRESOLVED, ERROR = (
    "HUMAN", "COMPLETE", "PROPOSAL", "WHO_ONLY", "CONFLICT", "UNRESOLVED", "ERROR")
STATES = (HUMAN, COMPLETE, PROPOSAL, WHO_ONLY, CONFLICT, UNRESOLVED, ERROR)
STATE_LABELS = {
    HUMAN: "Decisione umana protetta",
    COMPLETE: "Classificazione completa (regola o evidenza verificabile)",
    PROPOSAL: "Proposta da confermare",
    WHO_ONLY: "WHO riconosciuto, classificazione da completare",
    CONFLICT: "Conflitto",
    UNRESOLVED: "Caso irrisolto",
    ERROR: "Errore tecnico",
}
# Engine exception codes that mean two sources of evidence disagree.
CONFLICT_CODES = {"WHO_AMBIGUOUS", "WHY_RULES_CONFLICT", "DIRECTION_CONFLICT", "PERSONAL_SOURCE_BUSINESS_WHAT",
                  "CARD_PAYMENT_AMBIGUOUS", "PROFILE_CONFLICT", "METHOD_CONFLICT"}


class Options(dict):
    """legacy_why: False | True; strict: method disagreements become conflicts; text_first: sequence variant
    (a unique name/alias found in the text is preferred over a different WHO read by a rule)."""

    def __init__(self, legacy_why=True, strict=True, text_first=False, blind=False, consistent_only=True):
        # blind: simulation only - the engine ignores the human decisions, to measure its own accuracy
        # against them. Never used for a run the person sees.
        # consistent_only: an approved text rule fills a missing WHY as a decision only when the current
        # configuration never contradicts it; otherwise its WHY is a proposal to confirm.
        super().__init__(legacy_why=legacy_why, strict=strict, text_first=text_first, blind=blind,
                         consistent_only=consistent_only)

    __getattr__ = dict.get


def engine_class():
    """The engine subclass, built after `config.bootstrap()` (the reused modules read the DB path at import)."""
    from cbank import engine as E
    from cbank.legacy import clean
    from rfone_data_store.bank_reconciliation import who_search_text as wst, who_why_rules as wwr
    from rfone_data_store.bank_reconciliation.who_recognition import who_key

    class ClaudeEngine(E.Engine):
        def __init__(self, db, con, options: Options | None = None):
            self.opts = options or Options()
            super().__init__(db, con)
            self.conflicts: dict[int, list] = defaultdict(list)   # txn id → method disagreements
            self.legacy_used: dict[int, str] = {}
            self.proposals: dict[int, dict] = {}                  # txn id -> proposal to confirm (never applied)
            self._recog: dict[int, object] = {}
            original = self.recogniser.recognise

            def recognise(txn, row=None):
                if txn.id not in self._recog:
                    self._recog[txn.id] = self._sequence(txn, original(txn, row=row))
                return self._recog[txn.id]
            self.recogniser.recognise = recognise

        # -- WHO: rules vs text, measured (and the text-first sequence variant) --------------------
        def _sequence(self, txn, rec):
            found = wst.recognise(txn.description_original, self.recogniser.keys)
            if rec.outcome == wst.FOUND and rec.method == wst.RULE and len(found) == 1:
                text_who = self.recogniser.names[found[0]]
                if who_key(text_who) != who_key(rec.who):
                    self.conflicts[txn.id].append(dict(kind="WHO_RULE_VS_TEXT", rule=rec.who, text=text_who,
                                                       evidence=rec.evidence))
                    if self.opts.strict:
                        return wst.Recognition(wst.RULES_DISAGREE, candidates=[rec.who, text_who],
                                               evidence=f"{rec.evidence}; nome o alias nella descrizione: {text_who}",
                                               legacy_hits=rec.legacy_hits)
                    if self.opts.text_first:
                        return wst.Recognition(wst.FOUND, text_who, wst.TEXT, True,
                                               evidence="text-first variant: name/alias in the description",
                                               legacy_hits=rec.legacy_hits)
            return rec

        # -- WHY: the approved text rules' WHY, reconnected ---------------------------------------
        def legacy_whys(self, txn, who) -> tuple[set, list, set]:
            """(WHY ids, references, rule ids) of the approved text rules that matched THIS movement for this
            WHO. A rule whose WHY is no longer an active catalog WHY is not executable: it is left out and
            listed (`self.stale`), never turned into a conflict or a WHY."""
            rec = self.recogniser.recognise(txn, row=self.c.rule_row(txn))
            whys, refs, rule_ids = set(), [], set()
            for rule, version, ex in rec.legacy_hits or []:
                if ex.why_verify or not ex.why or ex.why_default:
                    continue
                if ex.who and who and who_key(ex.who) != who_key(who):
                    continue               # the rule is about another WHO
                why_id = self.why_by_name.get(clean(ex.why))
                if why_id is None:
                    self.stale[rule.id] = ex.why
                    continue
                whys.add(why_id)
                rule_ids.add(rule.id)
                refs.append(f"regola #{rule.id} v{version.version_no} {rule.user_title or rule.title}")
            return whys, refs, rule_ids

        def _legacy_consistency(self):
            """Rules contradicted by the current configuration: on some movement the WHY the engine determines
            from an approved source (WHO + Source pair, WHO WHY rule) differs from the rule's WHY. Measured on
            every movement, protected ones included (their engine WHY is computed all the same)."""
            self.contradicted = defaultdict(list)     # rule id -> [(txn id, engine WHY, rule WHY)]
            self.stale = {}
            for txn in self.txns:
                if txn.id in self.matches:
                    continue
                rec = self.recogniser.recognise(txn, row=self.c.rule_row(txn))
                if rec.outcome != wst.FOUND:
                    continue
                who_id = self.c.who_by_name.get(clean(rec.who))
                if not who_id:
                    continue
                det = E.Engine.determine_why(self, txn, who_id, who=rec.who, row=self.c.rule_row(txn))
                if not det.why_id:
                    continue
                for rule, version, ex in rec.legacy_hits or []:
                    if ex.why_verify or not ex.why or ex.why_default or (ex.who and who_key(ex.who) != who_key(rec.who)):
                        continue
                    why_id = self.why_by_name.get(clean(ex.why))
                    if why_id is None:
                        self.stale[rule.id] = ex.why
                    elif why_id != det.why_id:
                        self.contradicted[rule.id].append((txn.id, det.why_id, why_id))

        def determine_why(self, txn, who_id, who=None, row=None):
            det = super().determine_why(txn, who_id, who=who, row=row)
            if not self.opts.legacy_why:
                return det
            if not hasattr(self, "contradicted"):
                self._legacy_consistency()
            whys, refs, rule_ids = self.legacy_whys(txn, who or self.c.whos.get(who_id))
            if not whys:
                return det
            if det.why_id:
                if whys != {det.why_id}:
                    # The approved source (pair / WHO WHY rule) decides; the disagreement is recorded and shown.
                    self.conflicts[txn.id].append(dict(kind="LEGACY_WHY_VS_" + ("PAIR" if det.method == wwr.METHOD_PAIR else "RULE"),
                                                       engine_why=det.why_id, legacy=sorted(whys), refs=refs))
                    if self.opts.strict:
                        return wwr.Determination(det.mode, code=wwr.CONFLICT, message=(
                            "Metodi in disaccordo: " + det.method + f" -> WHY #{det.why_id}; regole testuali approvate -> "
                            + ", ".join(str(w) for w in whys) + " (" + "; ".join(refs) + ")"))
                return det
            if det.code != wwr.NEEDS_PAIR:
                return det          # MULTIPLE WHO, rule conflict, missing document: never bypassed
            if len(whys) != 1:
                self.conflicts[txn.id].append(dict(kind="LEGACY_WHY_DISAGREE", legacy=sorted(whys), refs=refs))
                return wwr.Determination(det.mode, code=wwr.CONFLICT, message=(
                    "Regole testuali approvate in disaccordo tra loro: " + "; ".join(refs)))
            why_id = next(iter(whys))
            if why_id in self.provisional:
                return det
            against = [rid for rid in rule_ids if self.contradicted.get(rid)]
            if against and self.opts.consistent_only:
                # The rule is contradicted elsewhere by the current configuration: a proposal, not a decision.
                self.proposals[txn.id] = dict(source="LEGACY_RULE", who=who, who_id=who_id, why_id=why_id,
                                              refs=refs, contradicted={rid: len(self.contradicted[rid]) for rid in against})
                return det
            self.legacy_used[txn.id] = "; ".join(refs)
            return wwr.Determination(det.mode, why_id=why_id, method=LEGACY_METHOD,
                                     reference="; ".join(refs) + " - WHY della regola approvata; WHAT dal WHY; WHOM dalla Source")

        def bank_decision(self, txn) -> dict:
            d = super().bank_decision(txn)
            if self.opts.blind:
                d = dict(d, who_id=None, who=None, why_id=None, source=None, beneficiary_human=False)
            return d

        def _apply_human_matches(self):
            if not self.opts.blind:
                super()._apply_human_matches()

        def bank_split(self, txn):
            return None if self.opts.blind else super().bank_split(txn)

        def evaluate(self, txn) -> dict:
            r = super().evaluate(txn)
            if self.conflicts.get(txn.id):
                r["method_conflicts"] = self.conflicts[txn.id]
            if txn.id in self.proposals and r["status"] != E.RECONCILED and not r.get("protected"):
                r["claude_proposal"] = self.proposals[txn.id]
            return r

    return ClaudeEngine

