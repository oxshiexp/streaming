"""Notification helpers for the streaming bot."""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from typing import Optional

import requests

from .config import NotifierConfig

logger = logging.getLogger(__name__)


class Notifier:
    """Send webhook or email notifications for streaming events."""

    def __init__(self, config: NotifierConfig):
        self.config = config

    def notify(self, subject: str, message: str) -> None:
        if self.config.webhook_url:
            self._send_webhook(subject, message)
        if self.config.smtp_host and self.config.email_from and self.config.email_to:
            self._send_email(subject, message)

    def _send_webhook(self, subject: str, message: str) -> None:
        payload = {"subject": subject, "message": message}
        try:
            response = requests.post(self.config.webhook_url, json=payload, timeout=10)
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to send webhook: %s", exc)

    def _send_email(self, subject: str, message: str) -> None:
        email = EmailMessage()
        email["From"] = self.config.email_from or ""
        email["To"] = self.config.email_to or ""
        email["Subject"] = subject
        email.set_content(message)

        context = ssl.create_default_context()
        try:
            with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as smtp:
                smtp.starttls(context=context)
                if self.config.smtp_username and self.config.smtp_password:
                    smtp.login(self.config.smtp_username, self.config.smtp_password)
                smtp.send_message(email)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to send email: %s", exc)
