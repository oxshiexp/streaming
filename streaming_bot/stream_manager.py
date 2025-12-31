"""Manage streaming sessions with ffmpeg and YouTube Live."""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import shlex
import subprocess
from typing import Dict, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dateutil.tz import tzutc

from .config import BotConfig, NotifierConfig
from .models import AnalyticsSnapshot, StreamContent, StreamRequest, StreamSession
from .notifier import Notifier
from .youtube_client import YouTubeStreamingClient

logger = logging.getLogger(__name__)


class StreamingManager:
    """Coordinates YouTube API calls, ffmpeg, and monitoring."""

    def __init__(self, config: BotConfig):
        self.config = config
        self.youtube = YouTubeStreamingClient(config.oauth)
        self.notifier = Notifier(config.notifier or NotifierConfig())
        self.sessions: Dict[str, StreamSession] = {}
        self.scheduler = AsyncIOScheduler(timezone=tzutc())
        self.scheduler.start()
        self.monitor_interval = 30

    async def start_stream(self, name: str, request: StreamRequest) -> StreamSession:
        broadcast_id = self.youtube.create_broadcast(
            title=request.title,
            description=request.description,
            privacy_status=request.privacy_status or self.config.default_privacy_status,
            scheduled_start_time=request.scheduled_start_time,
        )
        stream_info = self.youtube.create_stream(name, request.resolution, request.bitrate)
        ingestion_url = f"{stream_info['ingestion_address']}/{stream_info['stream_name']}"
        self.youtube.bind(broadcast_id, stream_info["stream_id"])

        live_chat_id = self.youtube.get_live_chat_id(broadcast_id)
        session = StreamSession(
            name=name,
            broadcast_id=broadcast_id,
            stream_id=stream_info["stream_id"],
            ingestion_url=ingestion_url,
            live_chat_id=live_chat_id,
            requested=request,
            status="configured",
        )
        session.append_log("Session configured and bound.")
        self.sessions[broadcast_id] = session

        if not request.scheduled_start_time:
            await self._launch_ffmpeg(session)

        if live_chat_id:
            self.youtube.add_live_chat_message(live_chat_id, "Streaming bot connected.")

        self.notifier.notify(
            subject=f"Stream {name} configured",
            message=f"Broadcast {broadcast_id} is ready with ingestion {ingestion_url}.",
        )
        asyncio.create_task(self._monitor_session(session.broadcast_id))
        return session

    async def _launch_ffmpeg(self, session: StreamSession) -> None:
        cmd = self._build_ffmpeg_command(session.requested.content, session.ingestion_url, session.requested)
        session.append_log(f"Launching ffmpeg: {cmd}")
        process = subprocess.Popen(
            shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True  # noqa: S603
        )
        session.ffmpeg_process_pid = process.pid
        session.started_at = dt.datetime.utcnow()
        session.status = "streaming"
        self.youtube.transition(session.broadcast_id, "live")
        self.notifier.notify(
            subject=f"Stream {session.name} started",
            message=f"Broadcast {session.broadcast_id} is now live.",
        )

    def _build_ffmpeg_command(self, content: StreamContent, ingestion_url: str, request: StreamRequest) -> str:
        input_args: List[str] = []
        if content.is_loop:
            input_args.extend(["-stream_loop", "-1"])
        input_args.extend(["-re", "-i", content.source])

        video_bitrate = request.bitrate
        audio_bitrate = "160k"

        filters: List[str] = []
        if request.resolution:
            filters.append(f"scale=-2:{request.resolution.replace('p', '')}")

        filter_args = []
        if filters:
            filter_args = ["-vf", ",".join(filters)]

        destinations = [ingestion_url, *request.extra_ingestion_urls]
        if len(destinations) == 1:
            output_target = destinations[0]
            output_args = ["-f", "flv", output_target]
        else:
            tee_targets = "|".join(f"[f=flv:onfail=ignore]{dest}" for dest in destinations)
            output_args = ["-f", "tee", f'"{tee_targets}"']

        args = [
            "ffmpeg",
            *input_args,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-b:v",
            video_bitrate,
            "-maxrate",
            video_bitrate,
            "-bufsize",
            str(int(int(video_bitrate.rstrip('k')) * 2)) + "k",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ar",
            "44100",
            "-b:a",
            audio_bitrate,
            *filter_args,
            *output_args,
        ]
        return " ".join(args)

    async def stop_stream(self, broadcast_id: str, reason: str = "manual stop") -> None:
        session = self.sessions.get(broadcast_id)
        if not session:
            return
        if session.ffmpeg_process_pid:
            session.append_log("Stopping ffmpeg process.")
            try:
                subprocess.Popen(["kill", "-15", str(session.ffmpeg_process_pid)])  # noqa: S603
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to terminate ffmpeg: %s", exc)
        self.youtube.transition(broadcast_id, "complete")
        session.status = "stopped"
        self.notifier.notify(subject=f"Stream {session.name} stopped", message=reason)

    async def _monitor_session(self, broadcast_id: str) -> None:
        session = self.sessions.get(broadcast_id)
        if not session:
            return
        while session.status in {"configured", "streaming"}:
            await asyncio.sleep(self.monitor_interval)
            session.last_healthcheck = dt.datetime.utcnow()
            health = self.youtube.get_stream_health(session.stream_id)
            session.append_log(f"Health: {health}")
            if health["status"] != "active" or health["health"] == "error":
                await self._handle_reconnect(session)

            metrics = self.youtube.get_broadcast_metrics(session.broadcast_id)
            if metrics.get("concurrent_viewers"):
                session.append_log(f"Viewers: {metrics['concurrent_viewers']}")

    async def _handle_reconnect(self, session: StreamSession) -> None:
        session.reconnect_attempts += 1
        session.append_log("Attempting reconnection.")
        self.notifier.notify(
            subject=f"Reconnecting stream {session.name}",
            message=f"Health degraded for broadcast {session.broadcast_id}, attempt {session.reconnect_attempts}.",
        )
        await self._launch_ffmpeg(session)

    def schedule_stream(self, name: str, request: StreamRequest) -> str:
        if not request.scheduled_start_time:
            raise ValueError("scheduled_start_time is required for scheduling.")

        job = self.scheduler.add_job(
            lambda: asyncio.create_task(self.start_stream(name, request)),
            trigger="date",
            run_date=request.scheduled_start_time,
            id=f"{name}-{request.scheduled_start_time.isoformat()}",
            replace_existing=True,
        )
        return job.id

    def update_content(self, broadcast_id: str, content: StreamContent) -> None:
        session = self.sessions.get(broadcast_id)
        if not session:
            raise ValueError("Unknown session")
        session.requested.content = content
        session.append_log("Content updated for next restart.")

    def get_status(self, broadcast_id: str) -> Dict[str, str]:
        session = self.sessions.get(broadcast_id)
        if not session:
            raise ValueError("Unknown session")
        health = self.youtube.get_stream_health(session.stream_id)
        metrics = self.youtube.get_broadcast_metrics(session.broadcast_id)
        snapshot = AnalyticsSnapshot(
            concurrent_viewers=metrics.get("concurrent_viewers"),
            health_status=health.get("health"),
            raw={"stream": str(health), "broadcast": str(metrics)},
        )
        return {
            "status": session.status,
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "reconnect_attempts": session.reconnect_attempts,
            "analytics": snapshot.__dict__,
            "log_tail": session.log[-10:],
        }

    def post_live_chat_message(self, broadcast_id: str, message: str) -> None:
        session = self.sessions.get(broadcast_id)
        if session and session.live_chat_id:
            self.youtube.add_live_chat_message(session.live_chat_id, message)

    def disable_chat(self, broadcast_id: str) -> None:
        session = self.sessions.get(broadcast_id)
        if session:
            self.youtube.disable_live_chat(session.broadcast_id)

    def list_sessions(self) -> List[str]:
        return list(self.sessions.keys())
