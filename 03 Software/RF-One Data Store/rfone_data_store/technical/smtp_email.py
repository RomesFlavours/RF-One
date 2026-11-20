"""Thin authenticated-SMTP sending wrapper — generic Technical infrastructure
helper (not tied to any one Domain), the provider-neutral sibling of
`ses_email.py`. Introduced so Selection candidate verification codes go
through the company mailbox on Aruba (`smtps.aruba.it`, port 465, implicit
TLS, full address as user name — Aruba's published parameters) instead of
Amazon SES, but deliberately generic: no verification-code, candidate or
Aruba-specific concept appears in the sending logic.

Configuration comes only from the environment, never from code:

    RFONE_SMTP_HOST              e.g. smtps.aruba.it (unset = not configured)
    RFONE_SMTP_PORT              465 = implicit TLS (default); any other port
                                 must offer STARTTLS, which is required
    RFONE_SMTP_USERNAME          the mailbox address
    RFONE_SMTP_PASSWORD          production: injected from AWS Secrets Manager;
                                 locally: from the DPAPI-protected file read by
                                 the local launcher — never written in code
    RFONE_SMTP_TIMEOUT_SECONDS   connect/command timeout (default 20)
    RFONE_SMTP_MAX_PER_20_MIN    process-wide send cap (default 200, below the
                                 250 per 20 minutes Aruba recommends)

Every message goes to exactly one recipient. TLS 1.2 is the minimum and the
server certificate is always verified.

Never logs, prints, or includes the password, the message body or the
recipient in a raised exception: `SmtpSendError` carries only a fixed,
machine-readable reason code (and the numeric SMTP reply code where there is
one), and is raised `from None` so no server text travels with it.
"""

from __future__ import annotations

import os
import smtplib
import socket
import ssl
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

IMPLICIT_TLS_PORT = 465
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_MAX_PER_WINDOW = 200
WINDOW_SECONDS = 20 * 60


class SmtpSendError(Exception):
    """Raised for any failure to hand the message to the SMTP server. Its
    text is only a reason code such as `authentication_failed`, `timeout`,
    `recipient_refused`, `smtp_550` — callers must still show their own
    generic message to end users and never reveal whether an address exists."""


@dataclass(frozen=True)
class SmtpSettings:
    host: str
    port: int
    username: str
    password: str = field(repr=False)
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_per_window: int = DEFAULT_MAX_PER_WINDOW


def settings_from_environment() -> SmtpSettings | None:
    """The SMTP settings, or None when `RFONE_SMTP_HOST` is not set. A host
    without user name or password is a configuration error, not "off"."""
    host = (os.environ.get("RFONE_SMTP_HOST") or "").strip()
    if not host:
        return None
    username = (os.environ.get("RFONE_SMTP_USERNAME") or "").strip()
    password = os.environ.get("RFONE_SMTP_PASSWORD") or ""
    if not username or not password:
        raise SmtpSendError("incomplete_configuration")
    try:
        port = int(os.environ.get("RFONE_SMTP_PORT") or IMPLICIT_TLS_PORT)
        timeout = float(os.environ.get("RFONE_SMTP_TIMEOUT_SECONDS") or DEFAULT_TIMEOUT_SECONDS)
        cap = int(os.environ.get("RFONE_SMTP_MAX_PER_20_MIN") or DEFAULT_MAX_PER_WINDOW)
    except ValueError:
        raise SmtpSendError("invalid_configuration") from None
    return SmtpSettings(host=host, port=port, username=username, password=password,
                        timeout_seconds=timeout, max_per_window=cap)


class _SendWindow:
    """Process-wide sliding window protecting the mailbox from being blocked
    by the provider. Each service runs one process, so this is the real cap."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sent: deque[float] = deque()

    def acquire(self, limit: int) -> None:
        now = time.monotonic()
        with self._lock:
            while self._sent and now - self._sent[0] >= WINDOW_SECONDS:
                self._sent.popleft()
            if len(self._sent) >= limit:
                raise SmtpSendError("local_rate_limit")
            self._sent.append(now)


_window = _SendWindow()


def _single_address(value: str) -> str:
    address = (value or "").strip()
    if not address or "@" not in address or any(c in address for c in ",;<>\r\n\t "):
        raise SmtpSendError("invalid_address")
    return address


def _tls_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


def send_email(
    *, settings: SmtpSettings, to_address: str, subject: str, text_body: str, from_address: str,
) -> None:
    """Sends one plain-text message to exactly one recipient."""
    recipient = _single_address(to_address)
    sender = _single_address(from_address)

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=False, usegmt=True)
    message["Message-ID"] = make_msgid(domain=sender.rsplit("@", 1)[1])
    message.set_content(text_body, charset="utf-8")

    _window.acquire(settings.max_per_window)
    try:
        if settings.port == IMPLICIT_TLS_PORT:
            client = smtplib.SMTP_SSL(settings.host, settings.port, timeout=settings.timeout_seconds,
                                      context=_tls_context())
        else:
            client = smtplib.SMTP(settings.host, settings.port, timeout=settings.timeout_seconds)
        with client:
            if settings.port != IMPLICIT_TLS_PORT:
                client.ehlo()
                if not client.has_extn("starttls"):
                    raise SmtpSendError("starttls_unavailable")
                client.starttls(context=_tls_context())
                client.ehlo()
            client.login(settings.username, settings.password)
            client.send_message(message, from_addr=sender, to_addrs=[recipient])
    except SmtpSendError:
        raise
    except smtplib.SMTPAuthenticationError:
        raise SmtpSendError("authentication_failed") from None
    except smtplib.SMTPRecipientsRefused:
        raise SmtpSendError("recipient_refused") from None
    except smtplib.SMTPSenderRefused as exc:
        raise SmtpSendError(f"sender_refused_{exc.smtp_code}") from None
    except smtplib.SMTPResponseException as exc:
        raise SmtpSendError(f"smtp_{exc.smtp_code}") from None
    except (socket.timeout, TimeoutError):
        raise SmtpSendError("timeout") from None
    except ssl.SSLError:
        raise SmtpSendError("tls_failed") from None
    except smtplib.SMTPException:
        raise SmtpSendError("smtp_error") from None
    except OSError:
        raise SmtpSendError("connection_failed") from None
