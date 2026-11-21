"""Allowlisted persisted CV facts and conservative, deterministic comparisons."""
from dataclasses import asdict
from datetime import date, datetime
import calendar
import re
import unicodedata

# Every label is an exact choice from the CV picker. No arbitrary attribute access.
CHOICES = {
    'Identità e contatti → Nome completo': 'full_name',
    'Identità e contatti → E-mail': 'email',
    'Identità e contatti → Telefono': 'phone',
    'Identità e contatti → Località dichiarata': 'location',
    'Profilo professionale → Presentazione personale': 'summary',
    'Profilo professionale → Riepilogo': 'summary',
    'Profilo professionale → Obiettivo professionale': 'summary',
    'Esperienze lavorative → Azienda': 'work_history.employer',
    'Esperienze lavorative → Sede': 'work_history.location',
    'Esperienze lavorative → Titolo della mansione': 'work_history.original_job_title',
    'Esperienze lavorative → Data di inizio': 'work_history.start_date_text',
    'Esperienze lavorative → Data di fine': 'work_history.end_date_text',
    'Esperienze lavorative → Mansioni e responsabilità': 'work_history.responsibilities',
    'Esperienze lavorative → Risultati dichiarati': 'work_history.achievements',
    'Formazione → Istituto': 'education.institution',
    'Formazione → Titolo di studio': 'education.qualification',
    'Formazione → Ambito di studio': 'education.field',
    'Formazione → Date': 'education.dates',
    'Formazione → Stato di completamento': 'education.completion_status',
    'Competenze → Competenze': 'skills',
    'Certificazioni → Nome della certificazione': 'certifications.name',
    'Certificazioni → Ente emittente': 'certifications.issuer',
    'Certificazioni → Data': 'certifications.date_text',
    'Lingue → Lingua': 'languages_detail.language',
    'Lingue → Livello dichiarato': 'languages_detail.proficiency',
    'Collegamenti → LinkedIn': 'linkedin_url',
    'Collegamenti → Altro sito o profilo': 'other_profile_url',
    'Altre sezioni → Testo di sezioni aggiuntive': 'other_sections_text',
}
LABELS = {path: label for label, path in CHOICES.items()}
COLLECTIONS = ('work_history', 'education', 'certifications', 'languages_detail')
DATE_FIELDS = {'work_history.start_date_text', 'work_history.end_date_text', 'education.dates',
               'certifications.date_text'}
TEXT_OPS = {'eq', 'contains', 'starts_with', 'ends_with'}
DATE_OPS = {'before', 'after', 'on_or_before', 'on_or_after'}
EDUCATION = {'HIGH_SCHOOL': 1, 'ASSOCIATE': 2, 'BACHELOR': 3, 'MASTER': 4, 'DOCTORATE': 5}
LANGUAGE = {level: n for n, level in enumerate(('A1', 'A2', 'B1', 'B2', 'C1', 'C2'), 1)}
LANGUAGE_NAMES = [
    ('english', 'inglese', 'en'), ('italian', 'italiano', 'it'),
    ('spanish', 'spagnolo', 'espanol', 'español', 'es'),
    ('french', 'francese', 'francais', 'français', 'fr'),
    ('german', 'tedesco', 'deutsch', 'de'), ('portuguese', 'portoghese', 'portugues', 'pt'),
    ('romanian', 'romeno', 'rumeno', 'ro'), ('russian', 'russo', 'ru'),
    ('ukrainian', 'ucraino', 'uk'), ('arabic', 'arabo', 'ar'),
    ('chinese', 'cinese', 'zh'), ('japanese', 'giapponese', 'ja'),
]


def normalized(value):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD', str(value)).casefold()
                           if not unicodedata.combining(c)).split())


def date_interval(value):
    if isinstance(value, (datetime, date)):
        value = value.date() if isinstance(value, datetime) else value
        return value, value
    value = str(value or '').strip()
    try:
        if re.fullmatch(r'\d{4}', value):
            y = int(value)
            return date(y, 1, 1), date(y, 12, 31)
        if re.fullmatch(r'\d{4}-\d{2}', value):
            y, m = map(int, value.split('-'))
            return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])
        for fmt in ('%B %Y', '%b %Y'):
            try:
                month = datetime.strptime(value, fmt)
                return date(month.year, month.month, 1), date(month.year, month.month, calendar.monthrange(month.year, month.month)[1])
            except ValueError:
                pass
        d = date.fromisoformat(value)
        return d, d
    except (ValueError, TypeError):
        return None


def education_level(value):
    text = normalized(value)
    # Uncompleted studies cannot establish an attained qualification.
    if re.search(r'\b(in progress|in corso|incomplete|not completed|some college|dropout)\b', text):
        return None
    for level, pattern in [
        (5, r'\b(ph\.?d\.?|doctorate|doctoral|dottorato)\b'),
        (4, r"\b(master'?s?|msc|m\.sc|m\.?[as]\.?|laurea magistrale|laurea specialistica)\b"),
        (3, r"\b(bachelor'?s?|bsc|b\.sc|b\.?[as]\.?|laurea triennale)\b"),
        (2, r"\b(associate'?s?|associate degree|a\.?[as]\.?)\b"),
        (1, r'\b(high school|highschool|ged|maturita|diploma di scuola superiore|diploma superiore)\b'),
        (0, r'\b(middle school|elementary school|primary school|licenza media|scuola media)\b'),
    ]:
        if re.search(pattern, text):
            return level
    return None


def language_level(value):
    text = str(value).upper().strip()
    match = re.fullmatch(r'(?:CEFR\s*)?(A1|A2|B1|B2|C1|C2)', text)
    return LANGUAGE[match.group(1)] if match else None


def profile_facts(profile):
    facts = asdict(profile)
    if not facts['languages_detail'] and profile.languages:
        facts['languages_detail'] = [{'language': profile.languages, 'proficiency': None}]
    for record in facts['education']:
        record['dates'] = [record.get('start_date_text'), record.get('end_date_text')]
    return facts


def values(facts, path):
    """Keep missing entries: a missing repeated record cannot become a false fact."""
    if '.' not in path:
        value = facts.get(path)
        return [(v, {}) for v in value] if isinstance(value, list) else [(value, {})]
    collection, name = path.split('.')
    result = []
    for record in facts.get(collection) or []:
        value = record.get(name)
        if isinstance(value, list):
            result.extend((v, record) for v in value)
        else:
            result.append((value, record))
    return result or [(None, {})]


def compare(value, expected, op, record, field=None):
    if value is None or not str(value).strip():
        return None
    if op in TEXT_OPS:
        a, b = normalized(value), normalized(expected)
        if field == 'languages_detail.language':
            for names in LANGUAGE_NAMES:
                aliases = {normalized(name) for name in names}
                if a in aliases:
                    a = names[0]
                if b in aliases:
                    b = names[0]
        return {'eq': lambda: a == b, 'contains': lambda: b in a,
                'starts_with': lambda: a.startswith(b), 'ends_with': lambda: a.endswith(b)}[op]()
    if op == 'education_gte':
        if record.get('completion_status') == 'IN_PROGRESS':
            return None
        level = education_level(value)
        return level >= EDUCATION[expected] if level is not None else None
    if op == 'language_gte':
        level = language_level(value)
        return level >= LANGUAGE[expected] if level is not None else None
    a, b = date_interval(value), date_interval(expected)
    if not a or not b:
        return None
    if op == 'before':
        return True if a[1] < b[0] else False if a[0] >= b[1] else None
    if op == 'after':
        return True if a[0] > b[1] else False if a[1] <= b[0] else None
    if op == 'on_or_before':
        return True if a[1] <= b[1] else False if a[0] > b[1] else None
    if op == 'on_or_after':
        return True if a[0] >= b[0] else False if a[1] < b[0] else None
    return None
