"""THE completeness gate, for every RF-One Web path that starts automatic Bank processing
(BANK_UPLOAD_AND_RECONCILE_001). One implementation: `intake.require_ready`, checked server side, so a direct
call to an endpoint is refused exactly like the disabled button. Reading, configuration, simulations that apply
nothing and the manual completion of single movements never come here."""
from rfone_data_store.bank_reconciliation import intake


def refusal(SessionFactory, what: str) -> str | None:
    """None when the data are complete; otherwise the message to show (what is missing, where to go)."""
    with SessionFactory() as db:
        try:
            intake.require_ready(db, what=what)
        except intake.NotReady as exc:
            return str(exc)
    return None
