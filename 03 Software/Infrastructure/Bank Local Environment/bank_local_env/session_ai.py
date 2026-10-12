"""AI Rules interpreted by the Claude Code session in VS Code (BANK_AI_RULES_008,
SESSION mode). See SESSION_INTERPRETATION.md for the procedure.

With RFONE_BANK_AI_MODE=SESSION the Preview button never calls an AI
provider: a rule with a saved interpretation runs at once (by code, no AI
call); a rule without one makes the preview wait for the session, saying so.
The session then:

  pending                 lists the rules waiting (previews in SESSION wait,
                          with no interpretation saved for their text yet)
  prompt  <preview id>    writes the EXACT prompt Bank would send, to a file
  answer  <preview id> <answer.json> [--model ID]
                          validates the session's JSON with Bank's own
                          validator and saves it in Bank's interpretation
                          cache, provider CLAUDE_CODE_SESSION — the next
                          Preview of the same text reuses it

Nothing else is written: no movement, no rule, no preview.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .config import DATA_STORE_DIR, Config

PROVIDER = "CLAUDE_CODE_SESSION"


def _prepare(db_path: Path) -> None:
    """Before any RF-One import: the Data Store on the path, the database chosen."""
    if not Path(db_path).exists():
        raise SystemExit(f"{db_path} does not exist.")
    os.environ["RFONE_DATABASE_URL"] = "sqlite:///" + Path(db_path).as_posix()
    if str(DATA_STORE_DIR) not in sys.path:
        sys.path.insert(0, str(DATA_STORE_DIR))


def _session(db_path: Path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    return Session(create_engine(os.environ["RFONE_DATABASE_URL"]))


def _context(db, preview_id: int):
    from rfone_data_store import models as m
    from rfone_data_store.bank_reconciliation import ai_rules
    preview = db.get(m.BankAiRulePreview, preview_id)
    if preview is None:
        raise SystemExit(f"Preview #{preview_id} does not exist in this database.")
    origin = ai_rules.row_for(db, preview.origin_transaction_id)
    instruction = ai_rules.current_instruction(db)
    instructions = instruction.instructions if instruction and instruction.instructions else None
    return preview, origin, instructions


def pending(cfg: Config, db_path: Path) -> int:
    _prepare(db_path)
    from sqlalchemy import select
    from rfone_data_store import models as m
    from rfone_data_store.bank_reconciliation import ai_rules
    with _session(db_path) as db:
        waiting = db.scalars(select(m.BankAiRulePreview).where(
            m.BankAiRulePreview.error_message.like(ai_rules.SESSION_WAIT_MARKER + "%"))
            .order_by(m.BankAiRulePreview.id.desc())).all()
        seen = set()
        rows = []
        for preview in waiting:
            _p, _origin, instructions = _context(db, preview.id)
            key = ai_rules.interpretation_key(preview.rule_text, instructions)
            if key in seen:
                continue
            seen.add(key)
            if ai_rules.saved_interpretation(db, preview.rule_text, instructions) is None:
                rows.append((preview.id, preview.started_at, " ".join(preview.rule_text.split())[:110]))
    if not rows:
        print("No AI rule is waiting for the session.")
        return 0
    print(f"{len(rows)} AI rule(s) waiting for the session (latest preview of each text):")
    for pid, when, text in rows:
        print(f"  Preview #{pid}  {when}  {text}")
    return 0


def prompt(cfg: Config, db_path: Path, preview_id: int) -> int:
    _prepare(db_path)
    from rfone_data_store.bank_reconciliation import ai_rules
    with _session(db_path) as db:
        preview, origin, instructions = _context(db, preview_id)
        text = ai_rules._interpretation_prompt(preview.rule_text, ai_rules.mask_numbers(origin.txn.description_original),
                                               instructions)
        saved = ai_rules.saved_interpretation(db, preview.rule_text, instructions)
    cfg.session_dir.mkdir(parents=True, exist_ok=True)
    out = cfg.session_dir / f"prompt_{preview_id}.txt"
    out.write_text(text, encoding="utf-8")
    print(f"Prompt of Preview #{preview_id}: {out}")
    print(f"Write the answer (JSON only) to: {cfg.session_dir / f'answer_{preview_id}.json'}")
    if saved is not None:
        print(f"Note: an interpretation for this text already exists (#{saved.id}, {saved.provider}).")
    return 0


def answer(cfg: Config, db_path: Path, preview_id: int, answer_path: Path, model: str) -> int:
    _prepare(db_path)
    from rfone_data_store import models as m
    from rfone_data_store.bank_reconciliation import ai_rules
    raw = json.loads(Path(answer_path).read_text(encoding="utf-8"))
    with _session(db_path) as db:
        preview, _origin, instructions = _context(db, preview_id)
        spec, reason = ai_rules.validate_interpretation(raw, preview.rule_text,
                                                        entities=ai_rules.EntityCatalog(db))
        key = ai_rules.interpretation_key(preview.rule_text, instructions)
        if ai_rules.saved_interpretation(db, preview.rule_text, instructions) is not None:
            raise SystemExit("An interpretation for this text and these instructions already exists; nothing written.")
        record = m.BankAiRuleInterpretation(
            cache_key=key, rule_text=preview.rule_text, instructions_snapshot=instructions,
            raw_answer=json.dumps(raw, ensure_ascii=False)[:20000],
            spec=json.dumps(spec, ensure_ascii=False) if spec else None, rejection_reason=reason,
            provider=PROVIDER, model=model)
        db.add(record)
        db.commit()
        print(f"Saved interpretation #{record.id} for Preview #{preview_id} ({PROVIDER} · {model}).")
    if spec:
        print("EXECUTABLE: press Preview again in Bank — the rule runs by code, with no AI call.")
    else:
        print(f"BLOCKED (not executable): {reason}. Press Preview again to see the reason in Bank.")
    return 0
