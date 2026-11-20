"""Test helper: a Tips test client signed in to RF-One.

TIPS_ACCESS_AND_DRILLDOWN_001 put every Tips page behind the RF-One login.
A test that is not about access itself signs in the way RF-One Web's
`auth.log_in` does — by carrying the two shared session keys
(`rfone_web_session`) for a real account in the test database — so it
exercises the same gate production uses rather than bypassing it.

Only ever used by the throwaway-SQLite Tips tests; never imported by the app.
"""

from __future__ import annotations

from sqlalchemy import select

from rfone_data_store import models as m
from rfone_data_store import rfone_account_service as account_service
from rfone_data_store import rfone_web_session as shared_session

TEST_USERNAME = "tips-test-signed-in"


def test_account(tips_app) -> tuple[int, int]:
    """`(account_id, session_version)` of the test account, created once."""
    with tips_app.SessionFactory() as s:
        account = s.scalars(select(m.RFOneAccount).where(m.RFOneAccount.username == TEST_USERNAME)).first()
        if account is None:
            account = account_service.create_account(
                s, username=TEST_USERNAME, display_name="Tips Test", password="a-long-enough-test-password",
            )
            s.commit()
        return account.id, account.session_version


def sign_in(client, account: tuple[int, int], base_url: str | None = None) -> None:
    """The cookie RF-One Web's `auth.log_in` issues: the same two shared keys."""
    kwargs = {"base_url": base_url} if base_url else {}
    with client.session_transaction(**kwargs) as sess:
        sess[shared_session.SESSION_ACCOUNT_KEY] = account[0]
        sess[shared_session.SESSION_VERSION_KEY] = account[1]


def signed_in_client(tips_app, base_url: str | None = None):
    """A Flask test client already carrying an RF-One session."""
    client = tips_app.app.test_client()
    sign_in(client, test_account(tips_app), base_url)
    return client
