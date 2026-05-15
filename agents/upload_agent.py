"""
Upload Agent — uploads video to YouTube as UNLISTED first.
Never goes public until human approves via Telegram.
Uses resumable upload (handles large files reliably).
Sets containsSyntheticMedia=True (AI disclosure — mandatory).
"""

import json
import os
import pickle
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from agents.base import advance_job, record_policy
from core.config import YOUTUBE_CLIENT_SECRETS_PATH, YOUTUBE_TOKEN_PATH
from core.database import get_job, update_job
from core.logger import get_logger
from core.notification import send_video_review

log = get_logger("upload_agent", "system")

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


class UploadAgent:

    def __init__(self):
        self._youtube = None

    def _get_youtube(self):
        if self._youtube is not None:
            return self._youtube

        creds = None
        token_path = Path(YOUTUBE_TOKEN_PATH)

        if token_path.exists():
            with open(token_path, "rb") as f:
                creds = pickle.load(f)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    YOUTUBE_CLIENT_SECRETS_PATH, SCOPES
                )
                creds = flow.run_local_server(port=0)
            with open(token_path, "wb") as f:
                pickle.dump(creds, f)

        self._youtube = build("youtube", "v3", credentials=creds)
        return self._youtube

    async def run(self, state: dict, cb_approve, cb_reject) -> dict:
        job_id         = state["job_id"]
        video_path     = state["video_path"]
        thumbnail_path = state["thumbnail_path"]
        metadata       = state["metadata"]

        log.info(f"[Job {job_id}] Upload Agent starting — uploading as UNLISTED")
        advance_job(job_id, "uploading")

        yt = self._get_youtube()

        # Upload video
        video_id = self._upload_video(yt, job_id, video_path, metadata)
        if not video_id:
            state["error"] = "upload_failed"
            return state

        # Upload thumbnail
        self._upload_thumbnail(yt, video_id, thumbnail_path)

        preview_url = f"https://youtu.be/{video_id}"
        log.info(f"[Job {job_id}] Uploaded as unlisted: {preview_url}")

        update_job(job_id, {
            "youtube_video_id": video_id,
            "preview_url":      preview_url,
            "status":           "human_review",
        })

        policy_ok = not state.get("policy_violations")

        # Notify human via Telegram
        await send_video_review(
            job_id=job_id,
            preview_url=preview_url,
            metadata=metadata,
            policy_ok=policy_ok,
            cb_approve=cb_approve,
            cb_reject=cb_reject,
        )

        state["youtube_video_id"] = video_id
        state["preview_url"]      = preview_url
        log.info(f"[Job {job_id}] Waiting for human approval via Telegram")
        return state

    # ── Upload helpers ────────────────────────────────────────

    def _upload_video(self, yt, job_id: int, video_path: str, metadata: dict) -> str | None:
        title       = metadata.get("title", "Finance Video")
        description = metadata.get("description", "")
        tags        = metadata.get("tags", [])
        category_id = metadata.get("category_id", "27")

        body = {
            "snippet": {
                "title":               title,
                "description":         description,
                "tags":                tags,
                "categoryId":          category_id,
                "defaultLanguage":     "en",
                "defaultAudioLanguage":"en",
            },
            "status": {
                "privacyStatus":           "unlisted",  # NOT public yet
                "selfDeclaredMadeForKids": False,
                "containsSyntheticMedia":  True,        # AI voice + avatar disclosure
            },
        }

        media = MediaFileUpload(
            video_path,
            mimetype="video/mp4",
            resumable=True,
            chunksize=10 * 1024 * 1024,  # 10MB chunks
        )

        try:
            request = yt.videos().insert(part="snippet,status", body=body, media_body=media)
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    pct = int(status.progress() * 100)
                    log.info(f"[Job {job_id}] Upload progress: {pct}%")
            return response.get("id")
        except Exception as e:
            log.error(f"[Job {job_id}] Upload error: {e}")
            return None

    def _upload_thumbnail(self, yt, video_id: str, thumbnail_path: str) -> None:
        try:
            yt.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path, mimetype="image/jpeg"),
            ).execute()
            log.info(f"Thumbnail uploaded for video {video_id}")
        except Exception as e:
            log.warning(f"Thumbnail upload failed: {e}")
