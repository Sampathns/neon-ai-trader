"""Notification & Alert Service (in-app persistence + optional Telegram/SMTP, zero secret leaks)."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Any, Dict, List

import httpx

from app.core.config import Settings
from app.core.enums import AlertSeverity
from app.core.security import redact_secrets
from app.db.database import Database


class NotificationService:
    """Dispatches sanitized alerts to in-app store and optional Telegram/Email channels."""

    def __init__(self, db: Database, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    def emit(
        self,
        *,
        category: str,
        severity: AlertSeverity,
        title: str,
        message: str,
    ) -> Dict[str, Any]:
        safe_title = redact_secrets(title)
        safe_message = redact_secrets(message)
        record = self.db.save_notification(
            category=category,
            severity=severity.value,
            title=safe_title,
            message=safe_message,
        )
        # Optional external channels (non-blocking best effort)
        if self.settings.telegram_bot_token and self.settings.telegram_chat_id:
            self._send_telegram(f"[{severity.value}] {safe_title}\n{safe_message}")
        if self.settings.smtp_host and self.settings.alert_email_to:
            self._send_email(f"[NEON AI TRADER] {safe_title}", safe_message)
        return record

    def list_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self.db.list_notifications(limit=limit)

    def _send_telegram(self, text: str) -> None:
        try:
            url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage"
            httpx.post(url, json={"chat_id": self.settings.telegram_chat_id, "text": text}, timeout=5.0)
        except Exception:
            pass

    def _send_email(self, subject: str, body: str) -> None:
        try:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = self.settings.smtp_user or "alerts@neon-trader.local"
            msg["To"] = self.settings.alert_email_to
            msg.set_content(body)
            with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=5) as srv:
                srv.starttls()
                if self.settings.smtp_user and self.settings.smtp_password:
                    srv.login(self.settings.smtp_user, self.settings.smtp_password)
                srv.send_message(msg)
        except Exception:
            pass
