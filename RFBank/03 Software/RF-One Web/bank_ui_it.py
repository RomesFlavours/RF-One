"""Italian presentation of existing Bank explanations; no stored data is changed."""
import re

MESSAGES = {
    'QBO account of the Source not set for this company': 'Conto QBO del conto o carta non impostato per questa azienda',
    'QBO account of a WHAT not set for this company': 'Conto QBO della categoria WHAT non impostato per questa azienda',
    'Not reconciled yet': 'Non ancora riconciliato',
    'Transfer between two companies: not one QBO transaction': 'Trasferimento tra aziende diverse: richiede registrazioni separate',
    'Relationship between the owners still to decide': 'Rapporto economico tra titolari ancora da definire',
    'Source has no owner': 'Conto o carta senza titolare',
    'Source': 'Conto o carta',
    'the OAuth 2.0 authorization of each company by its QuickBooks administrator (gives the company\'s realm id)': 'autorizzazione OAuth 2.0 dell’amministratore QuickBooks di ciascuna azienda, con il relativo identificativo realm',
    'secure storage and renewal of the access and refresh tokens': 'conservazione sicura e rinnovo dei token di accesso',
    'the QBO account Ids of each company, read through the API (the Account List export has none)': 'ID QBO dei conti di ciascuna azienda, letti tramite API (assenti nel file Account List)',
    'a test against an Intuit sandbox company before the first real send': 'verifica su un’azienda di prova Intuit prima del primo invio reale',
}
PHRASES = {
    'set the WHY of this WHO on this Source in Configuration.': 'imposta in Configurazione il WHY per questo WHO e conto o carta.',
    'the card payment itself is matched and complete.': 'il pagamento carta è già abbinato e completo.',
    'Card payment without its card-side credit: import the missing card statement; it is matched automatically on the next run.': 'Pagamento carta senza il corrispondente accredito: carica l’estratto carta mancante. L’abbinamento sarà ritentato alla prossima elaborazione.',
    'in personal accounting this needs a personal WHY, or a recorded decision (decision 86 — never moved to an LLC automatically).': 'su un conto personale serve un WHY personale oppure una decisione esplicita; il movimento non viene trasferito automaticamente a un’azienda.',
    'Personal Source, business WHAT ': 'Conto o carta personale con WHAT aziendale ',
    'is a provisional WHY: the nature of this movement is still to be established (investigate with AI or decide). It is never Reconciled with a provisional WHY.': 'è un WHY provvisorio: la natura del movimento è ancora da determinare con un’indagine o una decisione. Il movimento resta aperto.',
    'file(s) do not state their statement period: their period is read from their first and last movement, and only those days count as covered.': 'file non dichiarano il periodo dell’estratto: sono noti solo primo e ultimo movimento; soltanto quell’intervallo è considerato coperto.',
    'Amazon movement(s) in the work period and no Amazon order report loaded. If they were paid on an Amazon Business account, upload its orders report: Bank links each charge to its products and splits it by classification.': 'movimenti Amazon nel periodo controllato, ma nessun report ordini caricato. Se sono acquisti dell’account Amazon Business, carica il report: Bank collega gli addebiti ai prodotti e propone le ripartizioni.',
    'Internet research not authorized': 'Ricerca internet non autorizzata',
    'Changed after it went into an export file': 'Modificato dopo l’inclusione in un file di esportazione',
}

def bank_ui_it(value):
    if value is None:
        return ''
    text = str(value)
    if text in MESSAGES:
        return MESSAGES[text]
    for original, translated in PHRASES.items():
        text = text.replace(original, translated)
    # Known system reason prefixes may be followed by counts or context.
    for original, translated in MESSAGES.items():
        if original != 'Source' and text.startswith(original):
            text = translated + text[len(original):]
            break
    return text
