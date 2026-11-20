"""Per-mailbox attachment-handling rules: configuration only, always inactive.

Phase scope: a person describes what should happen to PDF attachments of one of
their mailboxes; the saved rule records that intent for a future phase. Nothing
here downloads attachments, reads PDFs or executes actions, and `active` is
constrained to false at the database level.

AI assistance reuses the shared RF-One client `selection.parsing.ai_client`
through its per-consumer selector `generate_json_for_email_rules` (same Bedrock
implementation and the same per-consumer convention as Tips; the global
`RFONE_AI_PROVIDER` is neither read nor changed). The prompt carries only text the person typed into the rule editor and
the fixed PDF-only scope: no mailbox address, server, credential, message,
header or attachment. An AI answer is returned as a draft and never written to
the database; only `save_rule`, called on an explicit human Save, persists.

Callers own commit/rollback.
"""
from __future__ import annotations

import re

from sqlalchemy import (Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text)

from .models import Base
from .email_service import now
from .incoming_email import MailboxAudit, owned

FILE_TYPE_PDF = 'PDF'
FIELDS = ('instructions', 'selection', 'conditions', 'actions', 'missing')
FIELD_LIMIT = 2000
HISTORY_TURNS = 12
AI_TIMEOUT_SECONDS = 45


class AttachmentRule(Base):
    __tablename__ = 'email_attachment_rules'
    __table_args__ = (CheckConstraint("file_type = 'PDF'", name='ck_email_attachment_rules_pdf_only'),
                      CheckConstraint('NOT active', name='ck_email_attachment_rules_inactive'))
    mailbox_id = Column(String(36), ForeignKey('email_mailboxes.id'), primary_key=True)
    file_type = Column(String(10), nullable=False, default=FILE_TYPE_PDF)
    instructions = Column(Text, nullable=False, default='')  # the person's own description
    selection = Column(Text, nullable=False, default='')     # which PDF attachments
    conditions = Column(Text, nullable=False, default='')
    actions = Column(Text, nullable=False, default='')
    missing = Column(Text, nullable=False, default='')       # information still to be clarified
    active = Column(Boolean, nullable=False, default=False)
    version = Column(Integer, nullable=False, default=1)
    updated_by_account_id = Column(Integer, ForeignKey('rfone_accounts.id'), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=now)


TABLES = [AttachmentRule.__table__]


class AssistantUnavailable(Exception):
    """The shared AI engine gave no usable draft. `code` is a fixed category
    safe to show; provider details are never carried to the page or logs."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


# Fixed categories -> person-facing Italian messages (local UI).
ASSISTANT_ERRORS = {
    'NOT_CONFIGURED': 'L’assistente AI non è configurato su questo PC. Puoi compilare e salvare la regola manualmente.',
    'DEPENDENCY_MISSING': 'Manca un componente software dell’assistente AI su questo PC. Puoi compilare e salvare la regola manualmente.',
    'TIMEOUT': 'L’assistente AI non ha risposto in tempo. La bozza non è stata modificata: riprova tra poco.',
    'BAD_RESPONSE': 'L’assistente AI ha dato una risposta non utilizzabile. La bozza non è stata modificata: riprova o riformula.',
    'PROVIDER_ERROR': 'Il servizio AI non è raggiungibile in questo momento. La bozza non è stata modificata: riprova tra poco.',
}

def clean_text(value, *, limit=FIELD_LIMIT):
    if value is None:
        return ''
    if not isinstance(value, str):
        raise ValueError('Testo non valido.')
    value = value.replace('\r\n', '\n').strip()
    if len(value) > limit:
        raise ValueError(f'Ogni campo può contenere al massimo {limit} caratteri.')
    if any(ord(c) < 32 and c not in '\n\t' for c in value):
        raise ValueError('Il testo contiene caratteri non validi.')
    return value


def rule_values(**values):
    cleaned = {key: clean_text(values.get(key)) for key in FIELDS}
    if not any(cleaned[key] for key in FIELDS):
        raise ValueError('Descrivi la regola o compila almeno un campo prima di salvare.')
    return cleaned


def rule_for(db, *, owner, mailbox_id):
    box = owned(db, owner, mailbox_id)
    if box is None:
        raise LookupError('Mailbox not found.')
    return db.get(AttachmentRule, box.id)


def save_rule(db, *, owner, mailbox_id, **values):
    """The only write path. Explicit human Save; the rule stays inactive."""
    box = owned(db, owner, mailbox_id)
    if box is None:
        raise LookupError('Mailbox not found.')
    cleaned = rule_values(**values)
    row = db.get(AttachmentRule, box.id)
    if row is None:
        row = AttachmentRule(mailbox_id=box.id, version=1, updated_by_account_id=owner, **cleaned)
        db.add(row)
    else:
        for key, value in cleaned.items():
            setattr(row, key, value)
        row.version += 1
        row.updated_by_account_id, row.updated_at = owner, now()
    row.file_type, row.active = FILE_TYPE_PDF, False
    db.flush()
    # Audit records the event only, never the rule text.
    db.add(MailboxAudit(mailbox_id=box.id, actor_account_id=owner, action='ATTACHMENT_RULE_SAVE'))
    return row


def _history(history):
    turns = []
    for turn in (history or [])[-HISTORY_TURNS:]:
        if not isinstance(turn, dict) or turn.get('role') not in ('user', 'assistant'):
            raise ValueError('Conversazione non valida.')
        turns.append({'role': turn['role'], 'content': clean_text(turn.get('content'))})
    return turns


PROPOSAL_KEYS = ('selection', 'conditions', 'actions', 'missing')
NON_PDF = re.compile(r'\.(?:docx?|xlsx?|pptx?|jpe?g|png|gif|zip|rar|txt|csv|eml|msg|html?)\b|\b(?:word|excel|immagin\w*|foto)\b', re.I)
ACTION_TODO = 'Azione da definire: cosa fare con i PDF selezionati.'
PDF_ONLY_NOTE = 'In questa versione si possono selezionare solo allegati PDF.'
# The mailbox is fixed by the window the person opened; it is never an open point.
MAILBOX_QUESTION = re.compile(r'\b(?:casell[ae]\w*|mailbox\w*|inbox|account (?:di posta|e-?mail))\b', re.I)


def build_prompt(*, message, history, draft):
    lines = [
        'You are the RF-One assistant that helps a person WRITE a rule for the attachments of a mailbox.',
        'The mailbox is ALREADY DETERMINED: the rule applies by default to the mailbox from whose window the person',
        'opened this assistant. Never ask which mailbox, inbox, email account or address the rule applies to, and never',
        'list the mailbox as missing information. You are not told which mailbox it is and do not need to know.',
        'You only help formulate the rule. You have no access to any email, attachment, file, folder or system,',
        'you did not and cannot download, open, read or process anything, and the rule stays inactive after saving.',
        'Never say or imply that you downloaded, read, opened, processed or found files or emails.',
        'Scope of this version: only PDF attachments can be selected. If the person asks for other file types,',
        'explain that only PDF is available now.',
        'Never invent actions, destinations, folders, recipients, systems, schedules or conditions the person did not state.',
        'Do not suggest that RF-One can already perform any action: just record the action the person wants.',
        'When the action (what to do with the selected PDFs) is not stated or is undecided, leave "actions" empty,',
        'say so in "missing", and in "reply" ask one or two short open questions to help the person decide it.',
        'Do not list example actions, destinations or tools: they could suggest RF-One can perform them.',
        'You may say that the rule only records the intent and that execution is not available yet.',
        'Also ask when the selection or conditions are ambiguous. Put open points in "missing"; empty when nothing is missing.',
        'Reply in Italian unless the person writes in another language. Be brief and concrete.',
        'Good question when the action is missing (no examples of actions): "Cosa vuoi che succeda ai PDF selezionati?',
        'Descrivilo con parole tue: la regola registra solo la tua intenzione e per ora non esegue nulla."',
        'Answer with ONE JSON object only, no markdown, exactly these keys:',
        '{"reply": "message to the person", "rule": {"selection": "which PDF attachments",',
        '"conditions": "conditions to apply, empty if none stated", "actions": "what to do, only as stated",',
        '"missing": "information still missing"}}',
        '',
        'Current editable draft (written or accepted by the person):',
    ]
    for key in FIELDS:
        lines.append(f'- {key}: {draft.get(key) or "(empty)"}')
    lines.append('')
    lines.append('Conversation so far:')
    for turn in history:
        lines.append(f'{turn["role"]}: {turn["content"]}')
    lines.append(f'user: {message}')
    return '\n'.join(lines)


def validate_proposal(raw):
    """Server-side validation of a model answer into the modal's fields.
    Raises AssistantUnavailable('BAD_RESPONSE') when it is not usable."""
    if not isinstance(raw, dict) or not isinstance(raw.get('reply'), str) or not isinstance(raw.get('rule'), dict):
        raise AssistantUnavailable('BAD_RESPONSE')
    rule = raw['rule']
    if any(not isinstance(rule.get(key, ''), (str, type(None))) for key in PROPOSAL_KEYS):
        raise AssistantUnavailable('BAD_RESPONSE')
    try:
        reply = clean_text(raw['reply'])
        fields = {key: clean_text(rule.get(key) or '') for key in PROPOSAL_KEYS}
    except ValueError:
        raise AssistantUnavailable('BAD_RESPONSE') from None
    if not reply:
        raise AssistantUnavailable('BAD_RESPONSE')
    missing = fields['missing']
    parts = [part.strip() for part in re.split(r'[\n;,]', missing) if part.strip()]
    if any(MAILBOX_QUESTION.search(part) for part in parts):
        missing = '; '.join(part for part in parts if not MAILBOX_QUESTION.search(part))
        fields['missing'] = missing
    notes = [missing] if missing else []
    if NON_PDF.search(fields['selection']) and PDF_ONLY_NOTE not in fields['missing']:
        notes.append(PDF_ONLY_NOTE)
    if not fields['actions'] and 'azion' not in fields['missing'].lower() and 'action' not in fields['missing'].lower():
        notes.append(ACTION_TODO)
    fields['missing'] = '\n'.join(notes)[:FIELD_LIMIT]
    return {'reply': reply, 'rule': fields}


def _classify(exc, ai_client):
    if isinstance(exc, ai_client.AIProviderTimeout):
        return 'TIMEOUT'
    if isinstance(exc, ai_client.AIProviderNotConfigured):
        return 'NOT_CONFIGURED'
    if isinstance(exc, ai_client.AIProviderDependencyMissing):
        return 'DEPENDENCY_MISSING'
    if isinstance(exc, ai_client.AIProviderBadResponse):
        return 'BAD_RESPONSE'
    return 'PROVIDER_ERROR'


def assist(*, message, history=None, draft=None, generate_json_fn=None):
    """Return {'reply', 'rule'} as an unsaved, server-validated draft. Never
    touches the database. Only the person's typed text is sent. Raises
    AssistantUnavailable(code) when no usable answer exists; nothing is simulated."""
    from .selection.parsing import ai_client
    message = clean_text(message)
    if not message:
        raise ValueError('Scrivi un messaggio per l’assistente.')
    turns = _history(history)
    current = {key: clean_text((draft or {}).get(key)) for key in FIELDS}
    generate = generate_json_fn or (lambda prompt: ai_client.generate_json_for_email_rules(
        prompt, timeout=AI_TIMEOUT_SECONDS))
    try:
        raw = generate(build_prompt(message=message, history=turns, draft=current))
    except ai_client.AIProviderUnavailable as exc:
        # Exception text may describe configuration or the provider; it is not
        # propagated or logged. It never contains the prompt.
        raise AssistantUnavailable(_classify(exc, ai_client)) from None
    except Exception:
        raise AssistantUnavailable('PROVIDER_ERROR') from None
    return validate_proposal(raw)


def provider_status():
    """(available, description) of the Email assistant configuration; nothing is called."""
    from .selection.parsing import ai_client
    provider, model = ai_client.email_rules_provider_description()
    if provider != ai_client.PROVIDER_BEDROCK:
        return False, 'RFONE_EMAIL_AI_PROVIDER non configurato'
    if not model:
        return False, 'RFONE_EMAIL_BEDROCK_MODEL_ID non configurato'
    try:
        import boto3  # noqa: F401
    except ImportError:
        return False, "pacchetto Python 'boto3' non installato"
    return True, f'{provider} · {model}'
