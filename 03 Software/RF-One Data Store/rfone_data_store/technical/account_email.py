"""RF-One transactional mail through the existing configured SMTP transport."""
import os
from . import smtp_email

EmailSendError = smtp_email.SmtpSendError


def send_email(*, to_address, subject, text_body, from_address=None, region_name=None):
    settings = smtp_email.settings_from_environment()
    if settings is None:
        raise EmailSendError('not_configured')
    smtp_email.send_email(settings=settings, to_address=to_address, subject=subject,
        text_body=text_body, from_address=from_address or os.environ.get('RFONE_EMAIL_FROM_ADDRESS') or 'RFOne@romesflavours.com')
