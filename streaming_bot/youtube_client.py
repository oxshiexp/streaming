"""YouTube API client wrapper."""

from __future__ import annotations

import datetime as dt
import logging
from typing import Dict, Optional

import google.oauth2.credentials
import googleapiclient.discovery
from googleapiclient.errors import HttpError

from .config import OAuthConfig

logger = logging.getLogger(__name__)


class YouTubeStreamingClient:
    """Wrapper around YouTube Data API for live streaming operations."""

    def __init__(self, oauth_config: OAuthConfig):
        self.oauth_config = oauth_config
        self.service = self._build_service()

    def _build_service(self):
        credentials = google.oauth2.credentials.Credentials(
            None,
            refresh_token=self.oauth_config.refresh_token,
            client_id=self.oauth_config.client_id,
            client_secret=self.oauth_config.client_secret,
            token_uri="https://oauth2.googleapis.com/token",
        )
        return googleapiclient.discovery.build("youtube", "v3", credentials=credentials, cache_discovery=False)

    def create_broadcast(
        self, title: str, description: str, privacy_status: str, scheduled_start_time: Optional[dt.datetime] = None
    ) -> str:
        body = {
            "snippet": {"title": title, "description": description},
            "status": {"privacyStatus": privacy_status},
        }
        if scheduled_start_time:
            body["snippet"]["scheduledStartTime"] = scheduled_start_time.isoformat() + "Z"
        request = self.service.liveBroadcasts().insert(part="snippet,status,contentDetails", body=body)
        response = request.execute()
        broadcast_id = response["id"]
        logger.info("Created broadcast %s", broadcast_id)
        return broadcast_id

    def create_stream(self, name: str, resolution: str, bitrate: str) -> Dict[str, str]:
        ingestion_type = "rtmp"
        body = {
            "snippet": {"title": name},
            "cdn": {
                "frameRate": "60fps" if resolution.endswith("p60") else "30fps",
                "ingestionType": ingestion_type,
                "resolution": resolution.replace("p60", "p"),
                "bitrate": bitrate,
            },
        }
        request = self.service.liveStreams().insert(part="snippet,cdn,contentDetails,status", body=body)
        response = request.execute()
        ingestion = response["cdn"]["ingestionInfo"]
        logger.info("Created stream %s", response["id"])
        return {
            "stream_id": response["id"],
            "ingestion_address": ingestion["ingestionAddress"],
            "stream_name": ingestion["streamName"],
        }

    def bind(self, broadcast_id: str, stream_id: str) -> None:
        request = self.service.liveBroadcasts().bind(
            part="id,contentDetails", id=broadcast_id, streamId=stream_id, onBehalfOfContentOwner=None
        )
        request.execute()
        logger.info("Bound broadcast %s to stream %s", broadcast_id, stream_id)

    def transition(self, broadcast_id: str, status: str) -> None:
        request = self.service.liveBroadcasts().transition(part="status", id=broadcast_id, broadcastStatus=status)
        request.execute()
        logger.info("Transitioned broadcast %s to %s", broadcast_id, status)

    def get_stream_health(self, stream_id: str) -> Dict[str, str]:
        request = self.service.liveStreams().list(part="status", id=stream_id)
        response = request.execute()
        status = response["items"][0]["status"]
        health_status = status.get("healthStatus", {})
        return {
            "status": status.get("streamStatus", "unknown"),
            "health": health_status.get("status", "unknown"),
            "configurationIssues": "; ".join(issue.get("description", "") for issue in health_status.get("configurationIssues", [])),
        }

    def get_broadcast_metrics(self, broadcast_id: str) -> Dict[str, str]:
        request = self.service.liveBroadcasts().list(part="statistics,status,contentDetails", id=broadcast_id)
        response = request.execute()
        item = response["items"][0]
        return {
            "concurrent_viewers": item.get("statistics", {}).get("concurrentViewers"),
            "life_cycle_status": item.get("status", {}).get("lifeCycleStatus"),
        }

    def get_live_chat_id(self, broadcast_id: str) -> Optional[str]:
        request = self.service.liveBroadcasts().list(part="snippet", id=broadcast_id)
        response = request.execute()
        items = response.get("items", [])
        if not items:
            return None
        return items[0].get("snippet", {}).get("liveChatId")

    def disable_live_chat(self, broadcast_id: str) -> None:
        body = {
            "id": broadcast_id,
            "snippet": {"liveChatId": None},
            "contentDetails": {"monitorStream": {"enableMonitorStream": False}},
        }
        self.service.liveBroadcasts().update(part="snippet,contentDetails", body=body).execute()

    def add_live_chat_message(self, live_chat_id: str, message: str) -> None:
        body = {
            "snippet": {
                "liveChatId": live_chat_id,
                "type": "textMessageEvent",
                "textMessageDetails": {"messageText": message},
            }
        }
        self.service.liveChatMessages().insert(part="snippet", body=body).execute()

    def safe_call(self, func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except HttpError as exc:
            logger.error("YouTube API error: %s", exc)
            raise
