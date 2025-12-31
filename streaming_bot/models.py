"""Domain models for streaming sessions."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class StreamContent:
    source: str
    is_loop: bool = True
    tags: List[str] = field(default_factory=list)
    category: Optional[str] = None


@dataclass
class StreamRequest:
    title: str
    description: str
    privacy_status: str
    resolution: str
    bitrate: str
    content: StreamContent
    scheduled_start_time: Optional[dt.datetime] = None
    extra_ingestion_urls: List[str] = field(default_factory=list)


@dataclass
class StreamSession:
    name: str
    broadcast_id: str
    stream_id: str
    ingestion_url: str
    live_chat_id: Optional[str]
    requested: StreamRequest
    ffmpeg_process_pid: Optional[int] = None
    started_at: Optional[dt.datetime] = None
    last_healthcheck: Optional[dt.datetime] = None
    reconnect_attempts: int = 0
    status: str = "pending"
    log: List[str] = field(default_factory=list)

    def append_log(self, message: str) -> None:
        timestamp = dt.datetime.utcnow().isoformat()
        self.log.append(f"[{timestamp}] {message}")


@dataclass
class AnalyticsSnapshot:
    concurrent_viewers: Optional[int] = None
    health_status: Optional[str] = None
    frame_rate: Optional[float] = None
    encoder_settings: Dict[str, str] = field(default_factory=dict)
    raw: Dict[str, str] = field(default_factory=dict)
