"""FastAPI application exposing streaming controls for Vercel and VPS."""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from typing import Any, Dict, Optional

from fastapi import Body, FastAPI, HTTPException
from pydantic import BaseModel, Field

from .config import load_config
from .models import StreamContent, StreamRequest
from .stream_manager import StreamingManager

logger = logging.getLogger(__name__)


class ContentPayload(BaseModel):
    source: str = Field(..., description="File path or URL for the media source.")
    is_loop: bool = True
    tags: list[str] = Field(default_factory=list)
    category: Optional[str] = None


class StartStreamPayload(BaseModel):
    name: str = Field(..., description="Internal name for the stream session.")
    title: str
    description: str
    privacy_status: str = Field("unlisted", description="public|unlisted|private")
    resolution: str = Field("1080p", description="1080p or 720p")
    bitrate: str = Field("4500k", description="Video bitrate, e.g. 4500k")
    content: ContentPayload
    scheduled_start_time: Optional[dt.datetime] = None
    extra_ingestion_urls: list[str] = Field(default_factory=list, description="Tambahan RTMP/RTMPS endpoint untuk multi-stream.")


class SchedulePayload(StartStreamPayload):
    scheduled_start_time: dt.datetime


class MessagePayload(BaseModel):
    broadcast_id: str
    message: str


def create_app() -> FastAPI:
    config = load_config()
    manager = StreamingManager(config)
    app = FastAPI(title=config.project_name)

    @app.get("/health")
    async def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.post("/streams/start")
    async def start_stream(payload: StartStreamPayload):
        content = StreamContent(**payload.content.model_dump())
        request = StreamRequest(
            title=payload.title,
            description=payload.description,
            privacy_status=payload.privacy_status,
            resolution=payload.resolution,
            bitrate=payload.bitrate,
            content=content,
            scheduled_start_time=payload.scheduled_start_time,
            extra_ingestion_urls=payload.extra_ingestion_urls,
        )
        session = await manager.start_stream(payload.name, request)
        return {"broadcast_id": session.broadcast_id, "ingestion_url": session.ingestion_url}

    @app.post("/streams/stop")
    async def stop_stream(broadcast_id: str = Body(..., embed=True)):
        await manager.stop_stream(broadcast_id)
        return {"status": "stopped"}

    @app.get("/streams/{broadcast_id}")
    async def stream_status(broadcast_id: str):
        try:
            return manager.get_status(broadcast_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/streams/schedule")
    async def schedule_stream(payload: SchedulePayload):
        content = StreamContent(**payload.content.model_dump())
        request = StreamRequest(
            title=payload.title,
            description=payload.description,
            privacy_status=payload.privacy_status,
            resolution=payload.resolution,
            bitrate=payload.bitrate,
            content=content,
            scheduled_start_time=payload.scheduled_start_time,
            extra_ingestion_urls=payload.extra_ingestion_urls,
        )
        try:
            job_id = manager.schedule_stream(payload.name, request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"job_id": job_id}

    @app.post("/streams/chat")
    async def chat_message(payload: MessagePayload):
        manager.post_live_chat_message(payload.broadcast_id, payload.message)
        return {"sent": True}

    @app.post("/streams/disable-chat")
    async def disable_chat(broadcast_id: str = Body(..., embed=True)):
        manager.disable_chat(broadcast_id)
        return {"chat": "disabled"}

    @app.get("/streams")
    async def list_streams() -> Dict[str, Any]:
        return {"broadcast_ids": manager.list_sessions()}

    @app.on_event("startup")
    async def startup_event() -> None:
        logger.info("Streaming bot started.")
        asyncio.get_running_loop()

    return app


app = create_app()
