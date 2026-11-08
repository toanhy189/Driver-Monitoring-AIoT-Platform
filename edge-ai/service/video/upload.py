
import os
import logging
from datetime import datetime

import cv2
import requests

from config import (API_STR, BACKEND_HOST, MQTT_USERNAME, MQTT_PASSWORD,
                    RECORDING_DIR, VIDEO_STORAGE_MAX_BYTES)

# URL của backend
BACKEND_URL = (
    f"{BACKEND_HOST.rstrip('/')}"
    f"/{API_STR.strip('/')}"
    "/videos/upload"
)

# Thư mục lưu video cục bộ
VIDEO_FPS_FALLBACK = 20.0

logger = logging.getLogger(__name__)


def recorded_bytes(path):
    try:
        return os.path.getsize(path) if path else 0
    except OSError:
        return 0


def create_video_writer(frame, state, camera):
    """Tạo video mới và trả về writer cùng đường dẫn file."""
    os.makedirs(RECORDING_DIR, exist_ok=True)
    from pathlib import Path
    used = 0
    for path in Path(RECORDING_DIR).glob("*.mp4"):
        try:
            used += path.stat().st_size
        except FileNotFoundError:
            pass  # The upload worker may have just cleaned this clip.
    from config import VIDEO_MAX_CLIP_BYTES
    if used + VIDEO_MAX_CLIP_BYTES > VIDEO_STORAGE_MAX_BYTES:
        logger.error("Video storage budget reached; camera/alerts continue, recordings paused; no pending clip deleted")
        return None, None

    height, width = frame.shape[:2]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{state}_{timestamp}.mp4"
    filepath = os.path.join(RECORDING_DIR, filename)

    fps = camera.get(cv2.CAP_PROP_FPS)
    if fps <= 0 or not fps < float("inf"):
        fps = VIDEO_FPS_FALLBACK

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(
        filepath, fourcc, fps, (width, height)
    )

    if not writer.isOpened():
        writer.release()
        logger.error("Cannot create video: %s", filepath)
        return None, None

    logger.info("Recording started: %s", filepath)
    return writer, filepath


def upload_video(video_path, device_code, state, message_id):
    """Upload video MP4 lên backend."""
    if not os.path.isfile(video_path):
        logger.error("Video file not found: %s", video_path)
        return False

    if not MQTT_USERNAME or not MQTT_PASSWORD:
        logger.error("Video upload requires AI_MQTT_USERNAME and AI_MQTT_PASSWORD")
        return False

    try:
        with open(video_path, "rb") as video_file:
            response = requests.post(
                BACKEND_URL,
                auth=(MQTT_USERNAME, MQTT_PASSWORD),
                files={
                    "file": (
                        os.path.basename(video_path),
                        video_file,
                        "video/mp4",
                    )
                },
                data={
                    "device_code": device_code,
                    "state": state,
                    "message_id": message_id,
                },
                timeout=(5, 120),
                allow_redirects=False,
            )

        if response.status_code not in (200, 201):
            logger.warning("Video upload rejected: HTTP %s; local clip retained", response.status_code)
            return False
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict) or result.get("status") != "SAVED" or \
                result.get("message_id") != message_id or \
                type(result.get("video_id")) is not int or result["video_id"] <= 0:
            logger.error("Invalid video save confirmation; local clip retained")
            return False

        logger.info(
            "Video uploaded successfully: %s",
            result.get("video_id"),
        )
        return True

    except (requests.RequestException, ValueError) as exc:
        logger.error("Video upload failed (%s); local clip retained", type(exc).__name__)
        return False
