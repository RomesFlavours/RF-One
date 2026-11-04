"""Primary sources actually researched during development, not live search results.

These are optional comparison evidence, never RF-One ontology or company facts.
Do not change consultation dates automatically on application startup.
"""
SOURCES = [
    dict(title='Bain · RAPID Decision Making',
         url='https://www.bain.com/insights/rapid-decision-making/',
         consulted_on='2026-10-18', published_on='2023-10-13',
         finding='Distinguere chi prepara una raccomandazione, chi decide e chi esegue; usare la formalizzazione dove il valore o la frequenza della decisione la giustificano.',
         limit='Metodo di riferimento: non dimostra chi abbia autorità nella tua azienda e non richiede di creare cinque nuove posizioni.'),
    dict(title='McKinsey · Untangling your organization’s decision making',
         url='https://www.mckinsey.com/capabilities/people-and-organization/our-insights/untangling-your-organizations-decision-making',
         consulted_on='2026-10-18', published_on='2017-07',
         finding='Distinguere decisioni importanti, trasversali e delegate, chiarendo responsabilità e modalità di coinvolgimento.',
         limit='Riferimento generale: la distribuzione dei poteri dipende dalle deleghe aziendali effettivamente confermate.'),
]


def attach_research(doc):
    from copy import deepcopy
    doc['research_sources'] = deepcopy(SOURCES)
    doc['research'] = ('Fonti online consultate il 18/10/2026 durante la preparazione del prototipo. '
                       'Il confronto seguente è una proposta progettuale, non una conclusione delle fonti sul tuo caso. '
                       'La sessione locale non esegue nuove ricerche automatiche.')
