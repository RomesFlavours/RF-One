"""Candidate acquisition channels.

Every channel ends in the same place: a CV file handed to the existing
Selection import (`import_pipeline.import_one_resume`). A future channel
(Indeed, a job board, email) only has to deliver files plus the applicant's
declared contacts; nothing downstream changes.
"""

from __future__ import annotations

from dataclasses import dataclass

from rfone_data_store.selection.workspace_models import MANUAL_UPLOAD, PUBLIC_LINK


@dataclass(frozen=True)
class Channel:
    code: str
    label: str
    active: bool
    note: str


CHANNELS = (
    Channel(MANUAL_UPLOAD, "Caricamento CV dal manager", True, "Più file insieme: PDF, DOCX, TXT."),
    Channel(PUBLIC_LINK, "Pagina pubblica della posizione", True,
            "Il candidato si registra e verifica la propria email, poi carica il CV e risponde a una breve "
            "intervista in inglese, interrompibile e riprendibile. Nessun accesso alle funzioni interne."),
    Channel("INDEED", "Indeed", False,
            "Predisposto: la pagina pubblica contiene i dati strutturati JobPosting e può essere usata come "
            "link «Apply on company site». Nessuna integrazione automatica con Indeed."),
)
CHANNEL_LABELS = {c.code: c.label for c in CHANNELS}
