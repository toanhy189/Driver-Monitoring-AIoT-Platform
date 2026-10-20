import logging
import os
import threading
import time

from edge_queue import (
    get_pending_videos,
    update_video_status,
    remove_video_from_queue,
)
from service.video.upload import upload_video

logger = logging.getLogger(__name__)


class VideoUploadWorker:
    def __init__(self, interval=5):
        self.interval = interval
        self.stop_event = threading.Event()
        self.thread = threading.Thread(
            target=self._run,
            daemon=True,
        )

    def start(self):
        self.thread.start()
        logger.info("Video upload worker started.")

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=5)

    def _run(self):
        while not self.stop_event.is_set():
            videos = get_pending_videos(limit=5)

            if videos is None:
                self.stop_event.wait(self.interval)
                continue

            for row in videos:
                if self.stop_event.is_set():
                    break

                (
                    video_id,
                    video_path,
                    device_code,
                    state,
                    status,
                    retry_count,
                ) = row

                # Upload đã thành công trước đó nhưng chưa dọn dẹp.
                if status == "UPLOADED":
                    try:
                        if os.path.isfile(video_path):
                            os.remove(video_path)

                        remove_video_from_queue(video_id)
                    except OSError:
                        logger.exception(
                            "Cannot clean uploaded video: %s",
                            video_path,
                        )
                    continue

                if not os.path.isfile(video_path):
                    logger.error(
                        "Queued video is missing: %s",
                        video_path,
                    )
                    # Giữ queue để xử lý thủ công, không tự xóa.
                    continue

                # Ghi nhận lần thử upload.
                update_video_status(
                    video_id,
                    "PENDING",
                    increment_retry=True,
                )

                uploaded = upload_video(
                    video_path,
                    device_code,
                    state,
                    video_id,
                )

                if not uploaded:
                    logger.warning(
                        "Video upload failed; will retry: %s",
                        video_id,
                    )
                    # Dừng lượt hiện tại để tránh dồn request.
                    break

                # Phải lưu trạng thái UPLOADED trước khi xóa file.
                if not update_video_status(video_id, "UPLOADED"):
                    logger.error(
                        "Upload succeeded but status update failed: %s",
                        video_id,
                    )
                    break

                try:
                    if os.path.isfile(video_path):
                        os.remove(video_path)

                    if not remove_video_from_queue(video_id):
                        logger.error(
                            "Video uploaded but queue cleanup failed: %s",
                            video_id,
                        )
                except OSError:
                    logger.exception(
                        "Cannot delete uploaded video: %s",
                        video_path,
                    )

            self.stop_event.wait(self.interval)