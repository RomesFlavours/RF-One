"""Disposable-database helper for validation scripts and tests only.

REGISTRY_CONFIRM_NEEDS_PERSON_001: `employee_directory.attach_link` confirms a Clover identity only for a
signed-in RF-One account. Fixtures that confirm their own fake people use this local account, which exists
only in the throwaway database the validation or test creates."""
from sqlalchemy import select

from . import models as m


def validation_account(db):
    account = db.scalar(select(m.RFOneAccount).where(m.RFOneAccount.username == "validation-fixture"))
    if account is None:
        account = m.RFOneAccount(username="validation-fixture", display_name="Validation fixture",
                                 password_hash="!disabled", status="ACTIVE")
        db.add(account)
        db.flush()
    return account
