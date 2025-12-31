"""Configuration helpers for the streaming bot."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class OAuthConfig:
    client_id: str
    client_secret: str
    refresh_token: str


@dataclass
class NotifierConfig:
    webhook_url: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    email_from: Optional[str] = None
    email_to: Optional[str] = None


@dataclass
class BotConfig:
    project_name: str = "YouTube Streaming Bot"
    default_privacy_status: str = "unlisted"
    default_resolution: str = "1080p"
    default_bitrate: str = "4500k"
    oauth: OAuthConfig | None = None
    notifier: NotifierConfig | None = None
    social_webhook_url: Optional[str] = None


def load_config() -> BotConfig:
    """Load configuration from environment variables."""
    oauth = OAuthConfig(
        client_id=os.environ["YOUTUBE_OAUTH_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_OAUTH_CLIENT_SECRET"],
        refresh_token=os.environ["YOUTUBE_OAUTH_REFRESH_TOKEN"],
    )

    notifier = NotifierConfig(
        webhook_url=os.getenv("NOTIFY_WEBHOOK_URL"),
        smtp_host=os.getenv("SMTP_HOST"),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        smtp_username=os.getenv("SMTP_USERNAME"),
        smtp_password=os.getenv("SMTP_PASSWORD"),
        email_from=os.getenv("NOTIFY_EMAIL_FROM"),
        email_to=os.getenv("NOTIFY_EMAIL_TO"),
    )

    return BotConfig(
        project_name=os.getenv("PROJECT_NAME", "YouTube Streaming Bot"),
        default_privacy_status=os.getenv("DEFAULT_PRIVACY_STATUS", "unlisted"),
        default_resolution=os.getenv("DEFAULT_RESOLUTION", "1080p"),
        default_bitrate=os.getenv("DEFAULT_BITRATE", "4500k"),
        oauth=oauth,
        notifier=notifier,
        social_webhook_url=os.getenv("SOCIAL_WEBHOOK_URL"),
    )
