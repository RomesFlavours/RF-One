"""Display language: English for shared builds, Italian for the PO local launcher."""
import os

LABELS_IT = {
 'RECONCILED':'Riconciliato','EXCEPTION':'Da completare','SAME':'Uguale a Bank','DIFFERENT':'Diverso da Bank',
 'BANK_EMPTY':'Nessuna decisione precedente','CBANK_OPEN':'Ancora aperto','BOTH_OPEN':'Aperto in entrambi',
 'WHO_UNKNOWN':'WHO non riconosciuto','WHO_AMBIGUOUS':'Più WHO possibili','NO_PROFILE':'Classificazione WHO mancante',
 'WHO_SOURCE_CLASSIFICATION_MISSING':'Classificazione WHO e conto/carta mancante',
 'WHY_RULE_MISSING':'Regola WHY mancante','WHY_DOCUMENT_MISSING':'Documento necessario per il WHY',
 'WHY_RULES_CONFLICT':'Regole WHY in conflitto','WHY_SPLIT_INCOMPLETE':'Ripartizione incompleta',
 'PERSONAL_SOURCE_BUSINESS_WHAT':'Conto personale con categoria aziendale',
 'RELATIONSHIP_TO_DECIDE':'Rapporto economico tra titolari da decidere',
 'CARD_PAYMENT_UNMATCHED':'Pagamento carta senza contropartita','CARD_PAYMENT_AMBIGUOUS':'Pagamento carta con più contropartite',
 'PROVISIONAL_WHY':'WHY provvisorio','CATEGORY_MISSING':'Categoria contabile mancante','INCOMPLETE':'Classificazione incompleta',
 'RULE':'Regola','NAME_ALIAS':'Nome o alias','CONTEXT':'Contesto e abbinamenti','ACCOUNT':'Titolare del conto',
 'HUMAN':'Decisione umana','AI':'AI','ENGINE':'Motore','WHO_SOURCE_CLASSIFICATION':'Classificazione WHO e conto/carta',
 'WHO':'WHO','WHY':'WHY','WHAT':'WHAT','WHOM':'WHOM','Matching':'Abbinamento','Profile':'Profilo','Beneficiary':'Destinatario',
 'Category':'Categoria','Operation':'Operazione','WHO + Source classification':'Classificazione WHO e conto/carta',
 'INTERNAL_TRANSFER':'Giroconto','TRANSFER':'Trasferimento','CARD_SETTLEMENT':'Pagamento carta',
 'OPERATING_EXPENSE':'Spesa operativa','OPERATING_INCOME':'Entrata operativa','CAPITAL_ASSET':'Acquisto di un bene',
 'FINANCING':'Finanziamento','OTHER_PATRIMONIAL':'Altra operazione patrimoniale',
}

def language():
    return 'it' if os.environ.get('RFONE_UI_LANGUAGE', 'en').lower().split('-')[0] == 'it' else 'en'


def configure(app):
    italian = language() == 'it'
    labels = LABELS_IT if italian else {}
    app.jinja_env.globals['ui_labels'] = labels
    app.jinja_env.filters['ui_label'] = lambda value: labels.get(value, value)
    app.config['RFONE_UI_LANGUAGE'] = 'it' if italian else 'en'
    return 'index.it.html' if italian else 'index.html'
