"""Explicit criterion scope and contextual evidence contract for local screening."""
PERSON = 'PERSON'
ROLE_RESEARCH = 'ROLE_RESEARCH'
GROUPS = (PERSON, ROLE_RESEARCH)


def group(value):
    return value if value in GROUPS else ROLE_RESEARCH


def instructions(scope):
    if scope == PERSON:
        return '''Evaluate documented professional history and consistency only. Do not assess fit
to a particular job. Duration, career gaps, temporary or seasonal work do not prove reliability,
honesty, attitude or motivation. Consider explicitly documented context and uncertainty; do not
infer personal traits or use protected characteristics. Prior outcomes are historical decisions,
not proof of current capability. Compare evolution only when dated evidence supports it.'''
    return '''Evaluate fit to this role AND this specific research, using their supplied context.
Compare actual tasks, responsibilities, skills, autonomy, education, certifications and languages
only against explicit requirements. Schedule compatibility requires BOTH the research schedule
and the candidate's availability. Motivation requires an explicit statement about this opportunity;
application frequency or CV wording is not proof. If context needed for this criterion is missing,
return INSUFFICIENT_EVIDENCE with level null and say exactly what is missing. Never invent
requirements from a role title or assume a previous research has the same conditions.'''
