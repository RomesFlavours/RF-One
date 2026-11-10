"""Thin AWS End User Messaging SMS (`pinpoint-sms-voice-v2`) sending
wrapper — generic Technical infrastructure helper, the text-message
counterpart of `ses_email.py`. Introduced for Selection candidate
verification codes (SELECTION_CANDIDATE_SMS_001) but deliberately generic:
no verification-code or candidate concept appears here.

The origination identity (a phone number, pool or sender ID registered in
the AWS account) is always a parameter the CALLER supplies from its own
configuration — never invented here. US traffic requires a dedicated,
registered identity: AWS has no shared route for the United States.

Never logs or prints the message body or the recipient, and never puts them
in a raised exception: `SmsSendError` carries only AWS's error code.
"""

from __future__ import annotations


class SmsSendError(Exception):
    """Raised for any failure to hand the message to AWS (missing
    configuration, sandbox restriction, unregistered number, spend limit,
    network error...). The text is only an AWS error code or a fixed word —
    callers must still show their own generic message to end users."""


def send_text(*, to_number: str, body: str, origination_identity: str, region_name: str,
              message_type: str = "TRANSACTIONAL") -> str:
    """Sends one SMS; returns AWS's MessageId. Credentials come from boto3's
    standard chain (the service role when deployed; the local AWS profile
    when run locally) — never from a parameter."""
    if not origination_identity:
        raise SmsSendError("not configured")

    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    client = boto3.client("pinpoint-sms-voice-v2", region_name=region_name)
    try:
        response = client.send_text_message(
            DestinationPhoneNumber=to_number, OriginationIdentity=origination_identity,
            MessageBody=body, MessageType=message_type,
        )
    except ClientError as exc:
        raise SmsSendError(exc.response.get("Error", {}).get("Code") or "ClientError") from exc
    except BotoCoreError as exc:
        raise SmsSendError(type(exc).__name__) from exc
    return response.get("MessageId", "")
