"""Bounded background H.264/AAC previews; originals and upload hashes stay intact."""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
import logging
from pathlib import Path
import subprocess
import tempfile
from threading import Lock
import time

from app.core.config import settings
from app.services.video_storage import storage_usage, video_path

logger = logging.getLogger(__name__)


class PlaybackService:
    def __init__(self):
        self.lock = Lock()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="video-playback")
        self.jobs = set()
        self.failures = OrderedDict()

    def path(self, video):
        # Validate the original key before deriving a cache path. IDs/hashes are
        # server-owned, never request paths. Version the output encoding recipe.
        source = video_path(video)
        return source.with_name(f".playback-v1-{video.id}-{video.sha256}.mp4")

    def status(self, video):
        target = self.path(video)
        with self.lock:
            if target.is_file():
                return {"status": "READY"}
            if target in self.jobs:
                return {"status": "PROCESSING"}
            if target in self.failures:
                return {"status": "FAILED", "reason": self.failures[target]}
        return {"status": "NOT_PREPARED"}

    def prepare(self, video):
        target, source = self.path(video), video_path(video)
        with self.lock:
            if target.is_file():
                return {"status": "READY"}
            if target in self.jobs:
                return {"status": "PROCESSING"}
            if len(self.jobs) >= 4:
                return {"status": "BUSY"}
            if storage_usage()["used_bytes"] >= settings.AI_VIDEO_TOTAL_MAX_BYTES:
                return {"status": "FAILED", "reason": "STORAGE_FULL"}
            self.failures.pop(target, None)
            self.jobs.add(target)
            try:
                self.pool.submit(self._encode, source, target)
            except Exception:
                self.jobs.discard(target)
                raise
        return {"status": "PROCESSING"}

    def _encode(self, source: Path, target: Path):
        temporary = target.with_suffix(".part.mp4")
        reason = None
        process = None
        try:
            import imageio_ffmpeg
            command = [imageio_ffmpeg.get_ffmpeg_exe(), "-nostdin", "-y", "-v", "error",
                       "-protocol_whitelist", "file,pipe", "-i", str(source),
                       "-map", "0:v:0", "-map", "0:a:0?", "-c:v", "libx264",
                       "-preset", "veryfast", "-crf", "23", "-threads", "1", "-filter_threads", "1",
                       "-vf", "scale=w='min(1280,iw)':h='min(720,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2",
                       "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k",
                       "-movflags", "+faststart", str(temporary)]
            with tempfile.TemporaryFile() as errors:
                process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                           stderr=errors)
                deadline = time.monotonic() + 120
                while process.poll() is None:
                    time.sleep(.1)
                    if time.monotonic() >= deadline:
                        reason = "ENCODE_TIMEOUT"
                        break
                    if not source.is_file():
                        reason = "SOURCE_REMOVED"
                        break
                    if (temporary.exists() and temporary.stat().st_size > settings.AI_VIDEO_MAX_BYTES
                            or storage_usage()["used_bytes"] > settings.AI_VIDEO_TOTAL_MAX_BYTES):
                        reason = "STORAGE_FULL"
                        break
                if reason:
                    process.kill()
                code = process.wait()
            if not reason and (code != 0 or not temporary.is_file() or temporary.stat().st_size == 0):
                reason = "ENCODE_FAILED"
            if not reason and (temporary.stat().st_size > settings.AI_VIDEO_MAX_BYTES
                               or storage_usage()["used_bytes"] > settings.AI_VIDEO_TOTAL_MAX_BYTES):
                reason = "STORAGE_FULL"
            # Deletion takes the same lock: no preview is resurrected after the
            # original is manually removed. No DB/session is held by this worker.
            with self.lock:
                if not reason and source.is_file():
                    temporary.replace(target)
                elif not reason:
                    reason = "SOURCE_REMOVED"
        except (OSError, RuntimeError, ImportError):
            reason = "ENCODER_UNAVAILABLE"
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()
            temporary.unlink(missing_ok=True)
            with self.lock:
                self.jobs.discard(target)
                if reason:
                    self.failures[target] = reason
                    while len(self.failures) > 64:
                        self.failures.popitem(last=False)
            if reason:
                logger.warning("Video preview not prepared: %s", reason)

    def remove_files(self, video):
        with self.lock:
            video_path(video).unlink(missing_ok=True)
            self.path(video).unlink(missing_ok=True)
            self.failures.pop(self.path(video), None)


playback = PlaybackService()
