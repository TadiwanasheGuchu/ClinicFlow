"""Channel adapters. Each returns a provider reference or raises DeliveryError."""

import logging
import smtplib
import uuid
from email.message import EmailMessage
from typing import Protocol

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class DeliveryError(Exception):
    pass


class Adapter(Protocol):
    def send(self, recipient: str, subject: str | None, body: str) -> str: ...


class LogAdapter:
    """Development adapter: records that a message was 'sent' without contacting anyone.
    Logs only a reference, never the recipient or the message (no personal data in logs)."""

    def __init__(self, channel: str) -> None:
        self.channel = channel

    def send(self, recipient: str, subject: str | None, body: str) -> str:
        reference = f"log-{uuid.uuid4().hex[:12]}"
        logger.info("Simulated %s delivery %s (%d chars)", self.channel, reference, len(body))
        return reference


class UnconfiguredAdapter:
    def __init__(self, channel: str) -> None:
        self.channel = channel

    def send(self, recipient: str, subject: str | None, body: str) -> str:
        raise DeliveryError(f"No {self.channel} provider is configured.")


class SmtpAdapter:
    def send(self, recipient: str, subject: str | None, body: str) -> str:
        s = get_settings()
        message = EmailMessage()
        message["From"] = s.email_from
        message["To"] = recipient
        message["Subject"] = subject or "Message from your practice"
        message_id = f"<{uuid.uuid4().hex}@clinicflow>"
        message["Message-ID"] = message_id
        message.set_content(body)
        try:
            with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
                if s.smtp_starttls:
                    smtp.starttls()
                if s.smtp_username:
                    smtp.login(s.smtp_username, s.smtp_password or "")
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            raise DeliveryError(f"SMTP delivery failed: {exc.__class__.__name__}") from exc
        return message_id


def adapter_for(channel: str) -> Adapter:
    s = get_settings()
    provider = {"sms": s.sms_provider, "whatsapp": s.whatsapp_provider, "email": s.email_provider}[
        channel
    ]
    if provider == "log":
        return LogAdapter(channel)
    if provider == "smtp":
        return SmtpAdapter()
    return UnconfiguredAdapter(channel)
