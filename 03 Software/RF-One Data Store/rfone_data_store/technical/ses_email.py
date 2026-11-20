"""Thin Amazon SES v2 sending wrapper — generic Technical infrastructure
helper (not tied to any one Domain), the email-sending counterpart to
`aws_secrets.py`'s database-credential resolution. Introduced for RF-One
Account email verification and password recovery
(`rfone_recovery_service.py`) but deliberately generic — no verification-
code or recovery concept appears here.

The From address is always a parameter the CALLER supplies explicitly
(read from `RFONE_EMAIL_FROM_ADDRESS` at the call site, never hardcoded or
guessed here) — this module never invents a sender and never lets a
message recipient's own address be used as the From (that decision belongs
to the caller, which is why this module takes no "reply as the user"
shortcut of any kind).

Never logs, prints, or includes the message body/recipient in a raised
exception — `EmailSendError`'s own text is a fixed, generic string;
callers must show an equally generic message to the end user and log
details (if at all) only server-side, never in a response body.
"""

from __future__ import annotations


class EmailSendError(Exception):
    """Raised for any failure to hand the message to SES (missing
    configuration, SES/network error, sandbox restriction on the
    recipient, etc). Callers must never surface this exception's message
    to an end user — it may carry AWS-internal detail — and must never let
    it reveal whether a given account/address exists."""


def send_email(
    *, to_address: str, subject: str, text_body: str, from_address: str, region_name: str,
) -> None:
    """Sends one plain-text transactional email via SES v2. Credentials are
    resolved by boto3's own standard chain (the App Runner instance role in
    production; the local AWS CLI profile only if a caller explicitly sets
    one up) — never read or accepted as a parameter here."""
    if not from_address:
        raise EmailSendError("No sender address is configured.")

    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    client = boto3.client("sesv2", region_name=region_name)
    try:
        client.send_email(
            FromEmailAddress=from_address,
            Destination={"ToAddresses": [to_address]},
            Content={
                "Simple": {
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {"Text": {"Data": text_body, "Charset": "UTF-8"}},
                }
            },
        )
    except (BotoCoreError, ClientError) as exc:
        raise EmailSendError("Failed to send email.") from exc
