
import os
import logging
from datetime import datetime

import cv2
import requests

from config import API_STR, BACKEND_HOST, DEVICE_CODE

# URL của backend
BACKEND_URL = (
    f"{BACKEND_HOST.rstrip('/')}"
    f"/{API_STR.strip('/')}"
    "/videos/upload"
)

# Thư mục lưu video cục bộ
RECORDING_DIR = "recordings"
VIDEO_FPS_FALLBACK = 20.0

logger = logging.getLogger(__name__)


def create_video_writer(frame, state, camera):
    """Tạo video mới và trả về writer cùng đường dẫn file."""
    os.makedirs(RECORDING_DIR, exist_ok=True)

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

    try:
        with open(video_path, "rb") as video_file:
            response = requests.post(
                BACKEND_URL,
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
            )

        response.raise_for_status()
        result = response.json()

        logger.info(
            "Video uploaded successfully: %s",
            result.get("video_id"),
        )
        return True

    except (requests.RequestException, ValueError) as exc:
        logger.error("Video upload failed: %s", exc)
        return False
