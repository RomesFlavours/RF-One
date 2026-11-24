"""Lexical retrieval for Conoscenza that tolerates different wording.

Pino rarely uses the words a rule was written with. Retrieval therefore
works on CONCEPTS, not on literal words:

1. text is lower-cased, accents removed, split into words, stop words
   dropped (Italian and English);
2. every word is mapped to a concept when it belongs to a synonym group
   (Italian/English, singular/plural, verb/noun: "mance" = "tips" =
   "gratuity"); otherwise it is reduced to a short stem, so that
   "ripartire", "ripartizione" and "ripartisce" meet;
3. each item is scored with a BM25-like formula over weighted fields
   (title, keywords and domain weigh more than the body).

The recording AI also stores `keywords` (alternative words it expects), and
the consulting AI may search more than once with its own reformulations.
No external service is called: retrieval works offline on the local store.
The synonym groups are deliberately editable plain data.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

# Each group becomes one concept token. Keep groups specific: a group that
# is too broad makes unrelated rules match.
SYNONYM_GROUPS: dict[str, tuple[str, ...]] = {
    "tips": ("tip", "tips", "mancia", "mance", "gratuity", "gratuities", "tipping", "tronc"),
    "location": ("sede", "sedi", "location", "locations", "ristorante", "ristoranti", "locale", "locali",
                 "punto", "store", "site", "sites", "negozio", "filiale"),
    "company": ("llc", "societa", "azienda", "aziende", "company", "companies", "entita", "entity",
                "legal", "giuridica", "datore"),
    "person": ("persona", "persone", "dipendente", "dipendenti", "employee", "employees", "staff",
               "lavoratore", "lavoratori", "cameriere", "camerieri", "server", "servers", "collaboratore",
               "collaboratori", "addetto", "addetti", "worker", "workers", "individuo", "nominativo"),
    "allocation": ("ripartizione", "ripartire", "ripartisci", "ripartisce", "ripartite", "ripartiti",
                   "distribuzione", "distribuire", "distribuisci", "distribuite", "allocation", "allocate",
                   "split", "dividere", "divisione", "suddividere", "suddivisione", "spartire", "quota",
                   "quote", "share", "shares", "pool", "percentuale", "percentuali"),
    "sum": ("somma", "sommare", "sommate", "sommando", "totale", "totali", "aggregare", "aggregazione",
            "sum", "total", "cumulare", "cumulo", "accorpare", "unire", "insieme", "complessivo"),
    "order": ("ordine", "ordini", "order", "orders", "conto", "conti", "scontrino", "scontrini", "check",
              "checks", "ticket", "comanda", "comande", "transazione", "transazioni", "vendita", "vendite"),
    "download": ("scarico", "scarichi", "scaricare", "scaricato", "download", "sync", "sincronizzazione",
                 "sincronizzare", "acquisizione", "acquisire", "importazione", "import", "poller"),
    "night": ("notturno", "notturna", "notte", "nightly", "overnight", "giornaliero", "quotidiano", "daily"),
    "ready": ("pronto", "pronta", "pronte", "pronti", "prontezza", "ready", "readiness", "disponibile",
              "disponibili", "lavorabile", "lavorabili", "sbloccare", "sbloccato", "bloccare", "blocca",
              "bloccato", "bloccano", "bloccante", "condizione", "condizioni", "prerequisito", "prerequisiti"),
    "calculate": ("calcolo", "calcoli", "calcolare", "calcola", "calculate", "calculation", "computo",
                  "conteggio", "elaborazione", "elaborare", "lavorazione"),
    "payment": ("pagamento", "pagamenti", "pagare", "payout", "payment", "payments", "liquidare",
                "liquidazione", "erogare", "erogazione", "versare"),
    "period": ("periodo", "periodi", "period", "quindicina", "settimana", "mese", "range", "intervallo"),
    "rule": ("regola", "regole", "rule", "rules", "criterio", "criteri", "policy", "logica", "metodo"),
    "active": ("attiva", "attive", "attivo", "attivi", "active", "operativa", "operative", "aperta", "aperte"),
    "inactive": ("inattiva", "inattive", "inattivo", "disattivata", "disattivate", "disattivato", "chiusa",
                 "chiuse", "dismessa", "dismesse", "inactive", "closed", "sospesa"),
    "clover": ("clover", "pos", "cassa"),
    "registry": ("registry", "anagrafica", "anagrafiche", "registro"),
    "release": ("rilascio", "rilasci", "rilasciare", "release", "deploy", "deployment", "pubblicazione",
                "pubblicare", "produzione", "production", "online"),
    "test": ("test", "prova", "prove", "verifica", "verifiche", "verificare", "collaudo"),
    "help": ("help", "aiuto", "guida", "spiegazione", "how", "works", "funziona"),
    "decision": ("decisione", "decisioni", "deciso", "decision", "scelta", "scelto", "approvato",
                 "approvazione", "approvata"),
    "correction": ("correzione", "correzioni", "correggere", "corretto", "sbagliato", "errore", "errato",
                   "correction", "fix", "rettifica"),
    "knowledge": ("conoscenza", "knowledge", "memoria", "memory", "sapere", "know"),
    "scope": ("scope", "perimetro", "ambito", "richiesto", "richiesta", "chiesto", "aggiungere", "extra",
              "aggiuntivo", "aggiuntive"),
    "database": ("database", "db", "postgres", "postgresql", "sqlite", "rds", "dati"),
    "wine": ("wine", "wines", "vino", "vini", "annata", "vintage", "cantina"),
    "bank": ("bank", "banca", "bancario", "bancaria", "riconciliazione", "reconciliation", "movimento",
             "movimenti"),
}

STOP_WORDS = frozenset("""
a ad al alla alle allo ai agli all anche ancora che chi ci come con cosa cui da dal dalla dalle dai
degli dei del della delle dello di e ed era essere fa fra gli ha hanno ho i il in io la le lei li lo
loro lui ma mi mia mio ne nei nel nella nelle nello noi o oppure per perche piu poi puo qua quale
quali quando quanto quel quella quelle quelli quello questa queste questi questo se si sia siamo
sono su sua sue sui sul sulla sulle suo tra tu tua tuo tutti tutto un una uno vi voi gia deve devo
devono essere stato stata ogni solo cosi dove anzi mentre allora
the of and or to in on at by for with from is are be was were this that these those it its as an
do does did not no if then than so such can could should would will shall must may
""".split())

FIELD_WEIGHTS = {"title": 3.0, "keywords": 2.0, "domain": 2.0, "statement": 1.5,
                 "rationale": 1.0, "validity_conditions": 1.0, "exceptions": 1.0}

_WORD = re.compile(r"[a-z0-9]+")
_CONCEPT_OF: dict[str, str] = {}
for _concept, _words in SYNONYM_GROUPS.items():
    for _w in _words:
        _CONCEPT_OF.setdefault(_w, "#" + _concept)


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def tokens(text: str | None) -> list[str]:
    """Concept tokens of `text` (see module docstring)."""
    if not text:
        return []
    out: list[str] = []
    for word in _WORD.findall(_fold(text)):
        concept = _CONCEPT_OF.get(word)
        if concept:
            out.append(concept)
            continue
        if word in STOP_WORDS or len(word) < 3:
            continue
        out.append(word[:6] if len(word) > 6 else word)
    return out


@dataclass
class Scored:
    item: object
    score: float
    matched: list[str]


# Words that make a question about the state of work rather than about a rule.
WORK_QUESTION = frozenset({"#release", "#test", "stato", "lavoro", "lavori", "implem", "progett", "verifi",
                           "commit", "punto", "avanza", "progress", "status", "work", "riprendo", "ripren"})
WORK_DAMPING = 0.6


def rank(items: list, query: str, *, limit: int = 8) -> list[Scored]:
    """Rank `items` (objects with the FIELD_WEIGHTS attributes) for `query`."""
    query_terms = list(dict.fromkeys(tokens(query)))
    work_question = bool(set(query_terms) & WORK_QUESTION)
    if not query_terms or not items:
        return []
    docs: list[Counter] = []
    lengths: list[float] = []
    for item in items:
        bag: Counter = Counter()
        for field, weight in FIELD_WEIGHTS.items():
            for t in tokens(getattr(item, field, None)):
                bag[t] += weight
        docs.append(bag)
        lengths.append(sum(bag.values()) or 1.0)
    n = len(docs)
    avg_len = sum(lengths) / n
    k1, b = 1.2, 0.75
    results: list[Scored] = []
    for item, bag, length in zip(items, docs, lengths):
        score = 0.0
        matched = []
        for term in query_terms:
            tf = bag.get(term, 0.0)
            if not tf:
                continue
            df = sum(1 for d in docs if term in d)
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * length / avg_len))
            matched.append(term)
        if score > 0:
            # Reward covering several distinct concepts of the question.
            score *= 1 + 0.25 * (len(matched) - 1)
            # A rule question should surface rules before long work reports.
            if getattr(item, "kind", None) == "WORK_UPDATE" and not work_question:
                score *= WORK_DAMPING
            results.append(Scored(item, round(score, 3), matched))
    results.sort(key=lambda s: s.score, reverse=True)
    return results[:limit]
