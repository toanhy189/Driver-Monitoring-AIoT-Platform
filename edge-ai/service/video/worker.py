"""Upload finalized clips off the camera thread; SQLite survives restarts."""

import logging
from pathlib import Path
import threading
import time

from config import VIDEO_UPLOAD_INTERVAL_SECONDS, VIDEO_UPLOAD_MAX_RETRY_SECONDS
from edge_queue import add_video_to_queue, get_pending_videos, update_video_status, remove_video_from_queue
from service.video.upload import upload_video

logger = logging.getLogger(__name__)


class VideoUploadWorker:
    def __init__(self, interval=VIDEO_UPLOAD_INTERVAL_SECONDS,
                 max_retry_seconds=VIDEO_UPLOAD_MAX_RETRY_SECONDS):
        self.interval = interval
        self.max_retry_seconds = max_retry_seconds
        self.stop_event = threading.Event()
        self.wakeup = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True, name="video-upload")

    def start(self):
        self.thread.start()
        logger.info("Video upload worker started; pending clips will be resumed")

    def enqueue(self, message_id, path, device_code, state):
        # Only call after VideoWriter.release() finalizes the MP4 file.
        if not add_video_to_queue(message_id, path, device_code, state):
            logger.error("Cannot queue finalized clip; retained locally: %s", path)
            return False
        self.wakeup.set()
        return True

    def stop(self, timeout=2):
        self.stop_event.set()
        self.wakeup.set()
        if self.thread.is_alive():
            self.thread.join(timeout=timeout)
        if self.thread.is_alive():
            logger.info("Upload still in progress; durable queue will recover on next start")

    def _cleanup(self, video_id, path):
        # UPLOADED must be committed before deleting any local bytes.
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            update_video_status(video_id, "UPLOADED", next_attempt_at=time.time() + self.interval)
            logger.warning("Cannot clean uploaded clip: %s", video_id)
            return
        remove_video_from_queue(video_id)

    def process_once(self):
        for video_id, path, device_code, state, status, retries in get_pending_videos(limit=5) or []:
            if self.stop_event.is_set():
                break
            if status == "UPLOADED":
                self._cleanup(video_id, path)
                continue
            if not Path(path).is_file():
                # Keep the record for inspection, without starving other queued clips.
                update_video_status(video_id, "MISSING")
                logger.error("Queued clip is missing: %s", video_id)
                continue
            delay = min(self.max_retry_seconds, self.interval * (2 ** min(retries, 10)))
            if not update_video_status(video_id, "PENDING", increment_retry=True,
                                       next_attempt_at=time.time() + delay):
                continue
            logger.info("Video upload %s: message_id=%s attempt=%d",
                        "FIRST" if retries == 0 else "RETRY", video_id, retries + 1)
            try:
                saved = upload_video(path, device_code, state, video_id)
            except Exception as error:
                logger.error("Video worker upload failed (%s)", type(error).__name__)
                saved = False
            if not saved:
                # Start backoff after the HTTP attempt, including slow failures.
                update_video_status(video_id, "PENDING", next_attempt_at=time.time() + delay)
                logger.warning("Video retry scheduled: message_id=%s retry_in=%.1fs", video_id, delay)
                continue
            if update_video_status(video_id, "UPLOADED"):
                self._cleanup(video_id, path)

    def _run(self):
        while not self.stop_event.is_set():
            self.wakeup.clear()
            try:
                self.process_once()
            except Exception as error:
                logger.error("Video worker cycle failed (%s)", type(error).__name__)
            self.wakeup.wait(self.interval)
