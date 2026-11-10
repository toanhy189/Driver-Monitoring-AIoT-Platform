"""Runtime regressions; use synthetic frames, fake audio and temporary storage."""

import base64
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import edge_queue as queue
import main as app
from eye import EyeClosureTracker, PerclosCalculator
from face_detection import FaceLandmarkDetector
from head_pose import HeadPoseTracker
from service.local_alert import LocalAlertWorker
from service.observation import ObservationContinuity
from service.video import upload
from service.video import worker as video_worker


def state_data():
    return {"candidate_state": "DROWSY", "candidate_since": 0,
            "confirmed_state": "DROWSY", "state_since": 0, "event_sequence": 0,
            "confirm_seconds": app.CONFIRM_SECONDS,
            "threshold_seconds": app.THRESHOLD_SECONDS,
            "threshold_since": {"DROWSY": 0, "DISTRACTED": None},
            "threshold_event_sent": {"DROWSY": False, "DISTRACTED": False}}


def warning(state="DROWSY"):
    return {"event_type": f"{state}_THRESHOLD_REACHED", "state": state}


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db_patch = patch.object(queue, "DB_PATH", self.root / "queue.db")
        self.db_patch.start()
        self.assertTrue(queue.init_db())

    def tearDown(self):
        self.db_patch.stop()
        self.temp.cleanup()

    def clip(self, name="clip.mp4"):
        path = self.root / name
        path.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"fixture")
        return path

    def row(self, message_id):
        with queue.get_connection() as connection:
            return connection.execute("SELECT status, retry_count, next_attempt_at FROM "
                                      "video_upload_queue WHERE video_id = ?", (message_id,)).fetchone()

    def due(self, message_id):
        with queue.get_connection() as connection:
            connection.execute("UPDATE video_upload_queue SET next_attempt_at = 0 WHERE video_id = ?",
                               (message_id,))

    def test_legacy_schema_migrates_without_losing_pending_data(self):
        legacy = self.root / "legacy.db"
        with closing(sqlite3.connect(legacy)) as connection, connection:
            connection.execute("CREATE TABLE video_upload_queue (id INTEGER PRIMARY KEY, "
                               "video_id TEXT UNIQUE, video_path TEXT, device_code TEXT, state TEXT, "
                               "created_at TEXT, status TEXT, retry_count INTEGER)")
            connection.execute("INSERT INTO video_upload_queue VALUES "
                               "(1, 'old', 'clip.mp4', 'vision-test', 'DROWSY', '', 'PENDING', 2)")
        with patch.object(queue, "DB_PATH", legacy):
            self.assertTrue(queue.init_db())
            self.assertEqual(queue.get_pending_videos()[0][0], "old")
            self.assertEqual(queue.get_pending_videos()[0][-1], 2)

    def test_retry_survives_restart_and_only_saved_clips_are_deleted(self):
        path = self.clip()
        first = video_worker.VideoUploadWorker(interval=5)
        self.assertTrue(first.enqueue("event-1", path, "vision-test", "DROWSY"))
        with patch.object(video_worker, "upload_video", return_value=False) as send, \
                self.assertLogs(video_worker.logger, level="INFO") as first_log:
            first.process_once()
            first.process_once()
        self.assertEqual(send.call_count, 1)
        self.assertTrue(any("Video upload FIRST: message_id=event-1 attempt=1" in line
                            for line in first_log.output))
        self.assertTrue(path.exists())
        self.assertEqual(self.row("event-1")[:2], ("PENDING", 1))
        self.due("event-1")
        self.assertTrue(queue.init_db())
        restarted = video_worker.VideoUploadWorker()
        with patch.object(video_worker, "upload_video", return_value=True) as send, \
                self.assertLogs(video_worker.logger, level="INFO") as retry_log:
            restarted.process_once()
        self.assertTrue(any("Video upload RETRY: message_id=event-1 attempt=2" in line
                            for line in retry_log.output))
        # Windows CI may give TEMP its 8.3 alias while the queue stores the
        # canonical path. Verify the same file and unchanged event metadata.
        sent_path = Path(send.call_args.args[0])
        self.assertTrue(sent_path.parent.samefile(path.parent))
        self.assertEqual(sent_path.name, path.name)
        self.assertEqual(send.call_args.args[1:], ("vision-test", "DROWSY", "event-1"))
        self.assertFalse(path.exists())
        self.assertIsNone(self.row("event-1"))

    def test_video_id_cannot_be_reused_for_different_metadata(self):
        path = self.clip()
        self.assertTrue(queue.add_video_to_queue("same-id", path, "vision-test", "DROWSY"))
        self.assertTrue(queue.add_video_to_queue("same-id", path, "vision-test", "DROWSY"))
        with self.assertLogs("edge_queue", level="ERROR"):
            self.assertFalse(queue.add_video_to_queue("same-id", path, "vision-test", "ATTENTIVE"))
        self.assertEqual(queue.get_pending_videos()[0][3], "DROWSY")

    def test_failed_uploaded_status_commit_keeps_local_bytes(self):
        path = self.clip()
        worker = video_worker.VideoUploadWorker()
        worker.enqueue("event-1", path, "vision-test", "DROWSY")
        update = queue.update_video_status
        with patch.object(video_worker, "upload_video", return_value=True), \
                patch.object(video_worker, "update_video_status",
                             side_effect=lambda identifier, status, **kw:
                             False if status == "UPLOADED" else update(identifier, status, **kw)):
            worker.process_once()
        self.assertTrue(path.exists())
        self.assertEqual(self.row("event-1")[0], "PENDING")

    def test_cleanup_failure_recovers_without_uploading_twice(self):
        path = self.clip()
        worker = video_worker.VideoUploadWorker(interval=0.1)
        worker.enqueue("event-1", path, "vision-test", "DROWSY")
        with patch.object(video_worker, "upload_video", return_value=True), \
                patch.object(Path, "unlink", side_effect=PermissionError("busy")), \
                self.assertLogs(video_worker.logger, level="WARNING"):
            worker.process_once()
        self.assertTrue(path.exists())
        self.assertEqual(self.row("event-1")[0], "UPLOADED")
        self.due("event-1")
        with patch.object(video_worker, "upload_video") as send:
            video_worker.VideoUploadWorker().process_once()
        send.assert_not_called()
        self.assertFalse(path.exists())
        self.assertIsNone(self.row("event-1"))

    def test_missing_or_failed_clip_does_not_starve_next_clip(self):
        worker = video_worker.VideoUploadWorker()
        worker.enqueue("missing", self.root / "missing.mp4", "vision-test", "DROWSY")
        bad = self.clip("bad.mp4")
        good = self.clip("good.mp4")
        worker.enqueue("bad", bad, "vision-test", "DROWSY")
        worker.enqueue("good", good, "vision-test", "DROWSY")
        with patch.object(video_worker, "upload_video", side_effect=[False, True]), \
                self.assertLogs(video_worker.logger, level="ERROR"):
            worker.process_once()
        self.assertEqual(self.row("missing")[0], "MISSING")
        self.assertTrue(bad.exists())
        self.assertFalse(good.exists())

    def test_http_confirmation_and_device_basic_auth(self):
        path = self.clip()
        for code, body, expected in [
            (201, {"status": "SAVED", "message_id": "event-1", "video_id": 7}, True),
            (200, {"status": "SAVED", "message_id": "event-1", "video_id": 7, "duplicate": True}, True),
            (401, {}, False), (503, {}, False), (302, {}, False),
            (200, {"status": "SAVED", "message_id": "another", "video_id": 7}, False),
            (200, {"message_id": "event-1", "video_id": 7}, False),
            (200, {"status": "SAVED", "message_id": "event-1", "video_id": True}, False),
            (200, [], False),
        ]:
            response = Mock(status_code=code)
            response.json.return_value = body
            with self.subTest(code=code, body=body), \
                    patch.object(upload, "MQTT_USERNAME", "vision-test"), \
                    patch.object(upload, "MQTT_PASSWORD", "test-only"), \
                    patch.object(upload.requests, "post", return_value=response) as send:
                self.assertEqual(upload.upload_video(path, "vision-test", "DROWSY", "event-1"), expected)
                self.assertEqual(send.call_args.kwargs["auth"], ("vision-test", "test-only"))
                self.assertFalse(send.call_args.kwargs["allow_redirects"])
            self.assertTrue(path.exists())

    def test_missing_credentials_never_sends_anonymous_upload(self):
        with patch.object(upload, "MQTT_PASSWORD", None), \
                patch.object(upload.requests, "post") as send, \
                self.assertLogs(upload.logger, level="ERROR"):
            self.assertFalse(upload.upload_video(self.clip(), "vision-test", "DROWSY", "event-1"))
        send.assert_not_called()

    def test_actual_http_upload_includes_auth_and_same_message_id(self):
        received = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                received["auth"] = self.headers.get("Authorization")
                received["body"] = self.rfile.read(int(self.headers["Content-Length"]))
                body = json.dumps({"status": "SAVED", "message_id": "event-1", "video_id": 9}).encode()
                self.send_response(201)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.object(upload, "BACKEND_URL", f"http://127.0.0.1:{server.server_port}/api/videos/upload"), \
                    patch.object(upload, "MQTT_USERNAME", "vision-test"), \
                    patch.object(upload, "MQTT_PASSWORD", "test-only"):
                self.assertTrue(upload.upload_video(self.clip(), "vision-test", "DROWSY", "event-1"))
            expected = "Basic " + base64.b64encode(b"vision-test:test-only").decode()
            self.assertEqual(received["auth"], expected)
            self.assertIn(b'name="message_id"\r\n\r\nevent-1', received["body"])
            self.assertIn(b'name="file";', received["body"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=1)

    def test_camera_loop_continues_while_video_upload_is_waiting(self):
        uploading = threading.Event()
        release_upload = threading.Event()
        sent_threads = []
        frames = []
        workers = []

        class Camera:
            def isOpened(self):
                return True

            def read(self):
                frames.append(len(frames) + 1)
                if len(frames) == 3:
                    if not uploading.wait(2):
                        raise AssertionError("Upload worker did not start")
                if len(frames) == 5:
                    release_upload.set()
                return True, np.zeros((8, 8, 3), dtype=np.uint8)

            def release(self):
                pass

        def writer(*args):
            path = self.root / f"clip-{len(frames)}.mp4"
            return SimpleNamespace(release=lambda: path.write_bytes(b"synthetic"), write=lambda f: None), str(path)

        def confirm(candidate, data, device):
            if len(frames) > 2:
                return None
            state = "ATTENTIVE" if len(frames) == 1 else "DISTRACTED"
            data["confirmed_state"] = state
            return {"message_id": f"event-{len(frames)}", "state": state}

        def send(*args):
            sent_threads.append(threading.current_thread().name)
            uploading.set()
            if not release_upload.wait(3):
                raise AssertionError("Camera loop blocked on HTTP")
            return False

        def make_worker():
            worker = video_worker.VideoUploadWorker(interval=0.05)
            workers.append(worker)
            return worker

        policy = SimpleNamespace(session_id="synthetic-session", state="UNKNOWN", candidate="UNKNOWN",
            suspended=False, observed_at=None, episode_id=None, end=lambda: None)

        def update_policy(candidate, valid=True, now=None, observed_at=None):
            event = confirm(candidate, {}, "vision-test")
            if event is None:
                return []
            event["event_type"] = "STATE_CHANGED"
            policy.state = policy.candidate = event["state"]
            return [event]

        policy.update = update_policy

        try:
            with patch.object(app.cv2, "VideoCapture", return_value=Camera()), \
                    patch.object(app.cv2, "imshow"), patch.object(app.cv2, "destroyAllWindows"), \
                    patch.object(app.cv2, "waitKey", side_effect=lambda _: ord("q") if len(frames) >= 5 else -1), \
                    patch.object(app, "FaceLandmarkDetector", return_value=SimpleNamespace(process=lambda f: [], close=lambda: None)), \
                    patch.object(app, "MQTTClient"), patch.object(app, "LocalAlertWorker"), \
                    patch.object(app, "VideoUploadWorker", side_effect=make_worker), \
                    patch.object(app, "create_video_writer", side_effect=writer), \
                    patch.object(app, "AlertPolicy", return_value=policy), patch.object(app, "RuntimeMetrics"), \
                    patch.object(app, "publish_event"), patch.object(app, "publish_telemetry"), \
                    patch.object(app, "check_threshold_events", return_value=[]), \
                    patch.object(video_worker, "upload_video", side_effect=send):
                app.main()
            self.assertEqual(len(frames), 5)
            self.assertTrue(sent_threads)
            self.assertTrue(all(name == "video-upload" for name in sent_threads))
            # Both finalized clips remain durable, even if one is waiting for backoff.
            with queue.get_connection() as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM video_upload_queue").fetchone()[0], 2)
            self.assertFalse(workers[0].thread.is_alive())
        finally:
            release_upload.set()
            for worker in workers:
                worker.stop()


class ObservationTests(unittest.TestCase):
    def test_mediapipe_timestamp_uses_elapsed_time_and_is_strictly_increasing(self):
        detector = FaceLandmarkDetector.__new__(FaceLandmarkDetector)
        detector.head_motion = False
        detector.started_at = 100
        detector.timestamp_ms = -1
        detector.landmarker = Mock()
        detector.landmarker.detect_for_video.return_value = SimpleNamespace(face_landmarks=[])
        frame = np.zeros((8, 8, 3), dtype=np.uint8)
        with patch("face_detection.time.monotonic", side_effect=[101, 101, 104]):
            for _ in range(3):
                detector.process(frame)
        self.assertEqual([c.args[1] for c in detector.landmarker.detect_for_video.call_args_list],
                         [1000, 1001, 4000])

    def test_short_missing_interval_is_not_counted_in_perclos(self):
        perclos = PerclosCalculator(warmup_seconds=0)
        with patch("eye.time.monotonic", return_value=0) as clock:
            perclos.update(0.3)
            clock.return_value = 0.1
            self.assertEqual(perclos.update(0.3), 0)
            perclos.interrupt()
            clock.return_value = 0.2
            self.assertIsNone(perclos.update(0.1))
            clock.return_value = 0.3
            self.assertAlmostEqual(perclos.update(0.1), 0.5)

    def test_face_loss_breaks_continuous_timers_and_long_loss_restarts_warmup(self):
        with patch("time.monotonic", return_value=100) as clock:
            eyes, perclos = EyeClosureTracker(), PerclosCalculator(warmup_seconds=0)
            head = HeadPoseTracker(calibration_seconds=0)
            head.update({"yaw": 0, "pitch": 0})
            state = state_data()
            continuity = ObservationContinuity(eyes, perclos, head, state)
            continuity.update(True)
            clock.return_value = 100.1
            eyes.update(0.1)
            perclos.update(0.1)
            head.update({"yaw": 0.3, "pitch": 0})
            clock.return_value = 100.2
            continuity.update(False)
            self.assertIsNone(head.deviation_since)
            self.assertIsNone(eyes.closed_since)
            self.assertEqual(state["candidate_state"], "UNKNOWN")
            self.assertEqual(app.check_threshold_events(state, "vision-test"), [])
            clock.return_value = 105
            continuity.update(False)
            event = app.update_confirmed_state("UNKNOWN", state, "vision-test")
            self.assertEqual(event["state"], "UNKNOWN")
            clock.return_value = 106
            continuity.update(True)
            self.assertEqual(eyes.update(0.1)["closed_duration_ms"], 0)
            self.assertEqual(head.update({"yaw": 0.3, "pitch": 0})["deviation_duration"], 0)
            self.assertFalse(head.calibrating)
            self.assertIsNone(perclos.update(0.1))
            self.assertEqual(perclos.valid_time, 0)
            self.assertEqual(app.check_threshold_events(state, "vision-test"), [])

    def test_unobserved_camera_pause_also_interrupts_state(self):
        with patch("time.monotonic", return_value=100) as clock:
            eyes, perclos, head = EyeClosureTracker(), PerclosCalculator(), HeadPoseTracker()
            state = state_data()
            continuity = ObservationContinuity(eyes, perclos, head, state)
            continuity.update(True)
            eyes.update(0.1)
            clock.return_value = 106
            self.assertTrue(continuity.update(True))
            self.assertEqual(eyes.update(0.1)["closed_duration_ms"], 0)
            self.assertEqual(state["candidate_state"], "UNKNOWN")
            self.assertIsNone(state["threshold_since"]["DROWSY"])

    def test_head_calibration_waits_for_continuous_valid_observations(self):
        with patch("head_pose.time.monotonic", return_value=0) as clock:
            head = HeadPoseTracker(calibration_seconds=5)
            clock.return_value = 20
            head.update({"yaw": 0, "pitch": 0})
            self.assertTrue(head.calibrating)
            clock.return_value = 24
            head.update(None)
            clock.return_value = 30
            head.update({"yaw": 0.1, "pitch": 0})
            self.assertTrue(head.calibrating)
            clock.return_value = 35
            head.update({"yaw": 0.1, "pitch": 0})
            self.assertFalse(head.calibrating)
            self.assertEqual(head.yaw_baseline, 0.1)


class LocalAlertTests(unittest.TestCase):
    def test_audio_runs_off_thread_without_network_and_respects_cooldown(self):
        playing, finish = threading.Event(), threading.Event()
        calls = []

        def player(state):
            calls.append((state, threading.current_thread().name))
            playing.set()
            finish.wait(2)

        worker = LocalAlertWorker(cooldown=10, player=player)
        worker.start()
        try:
            self.assertFalse(worker.notify({"event_type": "STATE_CHANGED", "state": "DROWSY"}))
            self.assertTrue(worker.notify(warning()))
            self.assertTrue(playing.wait(1))
            self.assertFalse(worker.notify(warning()))
            self.assertEqual(calls, [("DROWSY", "local-alert")])
        finally:
            finish.set()
            worker.stop()
        self.assertFalse(worker.thread.is_alive())
        self.assertFalse(worker.notify(warning()))

    def test_disabled_audio_does_not_start_a_thread(self):
        player = Mock()
        worker = LocalAlertWorker(enabled=False, player=player)
        worker.start()
        self.assertFalse(worker.notify(warning()))
        worker.stop()
        player.assert_not_called()

    def test_player_failure_does_not_crash_the_worker(self):
        called = threading.Event()

        def player(state):
            called.set()
            raise OSError("speaker unavailable")

        worker = LocalAlertWorker(player=player)
        with self.assertLogs("service.local_alert", level="ERROR"):
            worker.start()
            try:
                worker.notify(warning("DISTRACTED"))
                self.assertTrue(called.wait(1))
            finally:
                worker.stop()


if __name__ == "__main__":
    unittest.main()
