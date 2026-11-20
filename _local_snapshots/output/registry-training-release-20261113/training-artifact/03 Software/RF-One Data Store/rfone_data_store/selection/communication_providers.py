"""SMS/Email provider abstraction (Task 5D §30) — a small, injectable seam
so `communication_service.py` never depends on a real SMS/Email vendor
directly. No real provider credentials are required to complete or test
this task: `MockSmsProvider`/`MockEmailProvider` below are the default,
record every attempt in-process, and always report success. A real provider
(Twilio, SendGrid, ...) would implement the same two-method interface and be
swapped in via `set_sms_provider`/`set_email_provider` — nothing else in
this codebase would need to change.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class DeliveryResult:
    success: bool
    provider_ref: str | None
    error: str | None = None


class SmsProvider:
    def send(self, *, to_phone: str, text: str) -> DeliveryResult:
        raise NotImplementedError


class EmailProvider:
    def send(self, *, to_email: str, subject: str, body: str) -> DeliveryResult:
        raise NotImplementedError


@dataclass
class MockSmsProvider(SmsProvider):
    """Records every attempted send; never actually contacts a network. The
    honest, non-fabricating fallback this codebase already uses elsewhere
    (e.g. the deterministic résumé parser) — always reports success so
    Task 5D's behavior is fully testable without any external credentials."""

    sent: list[dict] = field(default_factory=list)

    def send(self, *, to_phone: str, text: str) -> DeliveryResult:
        ref = f"MOCK-SMS-{uuid.uuid4().hex[:12]}"
        self.sent.append({"to_phone": to_phone, "text": text, "provider_ref": ref})
        return DeliveryResult(success=True, provider_ref=ref)


@dataclass
class MockEmailProvider(EmailProvider):
    sent: list[dict] = field(default_factory=list)

    def send(self, *, to_email: str, subject: str, body: str) -> DeliveryResult:
        ref = f"MOCK-EMAIL-{uuid.uuid4().hex[:12]}"
        self.sent.append({"to_email": to_email, "subject": subject, "body": body, "provider_ref": ref})
        return DeliveryResult(success=True, provider_ref=ref)


_sms_provider: SmsProvider = MockSmsProvider()
_email_provider: EmailProvider = MockEmailProvider()


def get_sms_provider() -> SmsProvider:
    return _sms_provider


def get_email_provider() -> EmailProvider:
    return _email_provider


def set_sms_provider(provider: SmsProvider) -> None:
    global _sms_provider
    _sms_provider = provider


def set_email_provider(provider: EmailProvider) -> None:
    global _email_provider
    _email_provider = provider
