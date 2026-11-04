#!/usr/bin/env python
"""Tests for the authenticated-SMTP helper (`rfone_data_store/technical/smtp_email.py`).

No network and no real credentials: `smtplib.SMTP_SSL` / `smtplib.SMTP` are
replaced by an in-process fake that records what would have been sent.
Covers configuration from the environment, implicit TLS vs required
STARTTLS, one recipient per message, every error mapped to a reason code
that never carries the password, the recipient or server text, the timeout
being passed through, and the process-wide send cap.

Usage:
    python test_smtp_email.py
"""

from __future__ import annotations

import os
import smtplib
import socket
import ssl
import sys

from rfone_data_store.technical import smtp_email

PASSWORD = "synthetic-Secret-123"
_ENV = ("RFONE_SMTP_HOST", "RFONE_SMTP_PORT", "RFONE_SMTP_USERNAME", "RFONE_SMTP_PASSWORD",
        "RFONE_SMTP_TIMEOUT_SECONDS", "RFONE_SMTP_MAX_PER_20_MIN")

passed: list[str] = []
failed: list[str] = []


def check(description: str, condition: bool) -> None:
    (passed if condition else failed).append(description)


class FakeSMTP:
    instances: list["FakeSMTP"] = []
    fail_with: BaseException | None = None
    offers_starttls = True

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port, self.timeout, self.context = host, port, timeout, context
        self.logged_in = None
        self.started_tls = False
        self.sent: list[tuple] = []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def ehlo(self):
        return 250, b"ok"

    def has_extn(self, name):
        return name == "starttls" and FakeSMTP.offers_starttls

    def starttls(self, context=None):
        self.started_tls = True

    def login(self, user, password):
        if FakeSMTP.fail_with is not None:
            raise FakeSMTP.fail_with
        self.logged_in = (user, password)

    def send_message(self, message, from_addr=None, to_addrs=None):
        self.sent.append((message, from_addr, list(to_addrs)))


def settings(**overrides) -> smtp_email.SmtpSettings:
    values = dict(host="smtps.example.test", port=465, username="sender@example.test", password=PASSWORD,
                  timeout_seconds=7.5, max_per_window=1000)
    values.update(overrides)
    return smtp_email.SmtpSettings(**values)


def send(**overrides) -> None:
    smtp_email.send_email(settings=overrides.pop("settings", settings()), to_address=overrides.get(
        "to", "candidate@example.test"), from_address="sender@example.test", subject="Code",
        text_body="Your code is 123456")


def error_of(fn) -> str | None:
    try:
        fn()
    except smtp_email.SmtpSendError as exc:
        return str(exc)
    return None


def main() -> int:
    saved = {k: os.environ.pop(k, None) for k in _ENV}
    original = smtplib.SMTP_SSL, smtplib.SMTP
    smtplib.SMTP_SSL = FakeSMTP
    smtplib.SMTP = FakeSMTP
    try:
        # --- configuration --------------------------------------------------
        check("no host -> not configured (None)", smtp_email.settings_from_environment() is None)
        os.environ["RFONE_SMTP_HOST"] = "smtps.example.test"
        check("host without credentials -> incomplete_configuration",
              error_of(smtp_email.settings_from_environment) == "incomplete_configuration")
        os.environ["RFONE_SMTP_USERNAME"] = "sender@example.test"
        os.environ["RFONE_SMTP_PASSWORD"] = PASSWORD
        cfg = smtp_email.settings_from_environment()
        check("defaults: port 465, timeout 20 s, cap 200 per 20 minutes",
              (cfg.port, cfg.timeout_seconds, cfg.max_per_window) == (465, 20.0, 200))
        check("the password never appears in the settings' repr", PASSWORD not in repr(cfg))
        os.environ["RFONE_SMTP_PORT"] = "not-a-number"
        check("invalid port -> invalid_configuration",
              error_of(smtp_email.settings_from_environment) == "invalid_configuration")

        # --- implicit TLS (465) ---------------------------------------------
        FakeSMTP.instances.clear()
        send()
        c = FakeSMTP.instances[-1]
        check("port 465 uses implicit TLS with a verifying context, TLS 1.2 minimum",
              isinstance(c.context, ssl.SSLContext) and c.context.verify_mode == ssl.CERT_REQUIRED
              and c.context.minimum_version >= ssl.TLSVersion.TLSv1_2)
        check("the configured timeout is passed to the connection", c.timeout == 7.5)
        check("authenticates with the mailbox user", c.logged_in == ("sender@example.test", PASSWORD))
        message, sender, recipients = c.sent[-1]
        check("exactly one recipient per message", recipients == ["candidate@example.test"]
              and message["To"] == "candidate@example.test" and message["Cc"] is None and message["Bcc"] is None)
        check("From is the given sender, with Date and Message-ID",
              sender == "sender@example.test" and message["Date"] and "@example.test" in message["Message-ID"])

        # --- STARTTLS on another port ---------------------------------------
        send(settings=settings(port=587))
        check("another port upgrades with STARTTLS before login", FakeSMTP.instances[-1].started_tls)
        FakeSMTP.offers_starttls = False
        check("no STARTTLS offered -> starttls_unavailable, nothing sent",
              error_of(lambda: send(settings=settings(port=587))) == "starttls_unavailable"
              and not FakeSMTP.instances[-1].sent)
        FakeSMTP.offers_starttls = True

        # --- recipient validation -------------------------------------------
        for bad in ("a@x.test, b@x.test", "a@x.test;b@x.test", "a@x.test\r\nBcc: c@x.test", "", "no-at-sign"):
            check(f"invalid recipient refused before connecting: {bad!r}",
                  error_of(lambda: send(to=bad)) == "invalid_address")

        # --- error mapping --------------------------------------------------
        cases = [
            (smtplib.SMTPAuthenticationError(535, b"5.7.8 bad credentials for sender@example.test"), "authentication_failed"),
            (smtplib.SMTPRecipientsRefused({"candidate@example.test": (550, b"no such user")}), "recipient_refused"),
            (smtplib.SMTPSenderRefused(553, b"not allowed", "sender@example.test"), "sender_refused_553"),
            (smtplib.SMTPResponseException(421, b"too many messages"), "smtp_421"),
            (socket.timeout("timed out"), "timeout"),
            (ssl.SSLError("handshake"), "tls_failed"),
            (ConnectionRefusedError("refused"), "connection_failed"),
        ]
        for raised, expected in cases:
            FakeSMTP.fail_with = raised
            try:
                send()
                got, hidden = None, False
            except smtp_email.SmtpSendError as exc:
                got = str(exc)
                hidden = exc.__cause__ is None and (exc.__context__ is None or exc.__suppress_context__)
            check(f"{type(raised).__name__} -> {expected}", got == expected)
            check(f"{type(raised).__name__}: no server text, address or password travels with the error", hidden)
        FakeSMTP.fail_with = None

        # --- process-wide cap -----------------------------------------------
        smtp_email._window = smtp_email._SendWindow()
        for _ in range(3):
            send(settings=settings(max_per_window=3))
        check("the 4th message in the window is refused locally (local_rate_limit), no connection opened",
              error_of(lambda: send(settings=settings(max_per_window=3))) == "local_rate_limit")
    finally:
        smtplib.SMTP_SSL, smtplib.SMTP = original
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    for p in passed:
        print(f"PASS  {p}")
    for f in failed:
        print(f"FAIL  {f}")
    print(f"\n{len(passed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
