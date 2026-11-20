"""Compatibility hooks for the removed legacy WHO/label worker. The single engine owns recognition."""
def enqueue_new(app, factory, transaction_ids, account_id=None):
    return None

def register(app, **kwargs):
    app.extensions["bank_who_worker"] = None
    return None
