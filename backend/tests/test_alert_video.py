"""HTTP permission/link tests on an isolated SQLite DB; real synthetic encoding.

No production DB, camera, private recordings, MQTT commands or physical outputs.
"""
from datetime import datetime, timezone, timedelta
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.dialects.postgresql import INET, MACADDR
from sqlalchemy.ext.compiler import compiles
from app.main import app as production_app  # Register all model tables, no lifespan run.
from app.api.deps import get_db
from app.api.routes import alerts, videos
from app.core.config import settings
from app.core.db import get_session
from app.core.security import create_access_token
from app.models.ai_event import AiEvent
from app.models.alert import Alert
from app.models.device import Device
from app.models.user import User
from app.models.user_device import UserDevice
from app.models.video import AiVideo
from app.services.video_playback import playback


@compiles(INET, "sqlite")
@compiles(MACADDR, "sqlite")
def _test_inet_column(_type, _compiler, **_kw):
    # These tests use NULL IPs; production INET behavior is covered on PostgreSQL.
    return "TEXT"


class AlertVideo(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="alert-video-test-")
        self.root = Path(self.directory.name)
        self.storage = patch.object(settings, "AI_VIDEO_DIR", self.root)
        self.storage.start()
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        SQLModel.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            self.users = {}
            for role in ("Admin", "Employee", "Customer"):
                user = User(fullname=role, username=role, hash_password="unused",
                            email=role+"@example.test", phone=role, role=role)
                session.add(user); session.flush(); self.users[role] = user.id
            self.camera = Device(device_code="vision-a", model="Camera", device_type="VISION_NODE", lifecycle_state="ACTIVE")
            self.other = Device(device_code="vision-b", model="Camera", device_type="VISION_NODE", lifecycle_state="ACTIVE")
            session.add(self.camera); session.add(self.other); session.flush()
            for role in ("Employee", "Customer"):
                session.add(UserDevice(user_id=self.users[role], device_id=self.camera.id))
            session.commit(); session.refresh(self.camera); session.refresh(self.other)
        app = FastAPI()
        app.include_router(alerts.router, prefix="/api")
        app.include_router(videos.router, prefix="/api")
        def sessions():
            with Session(self.engine) as session:
                yield session
        app.dependency_overrides[get_db] = sessions
        app.dependency_overrides[get_session] = sessions
        self.client = TestClient(app)

    def tearDown(self):
        # Complete/cancel preview work before removing its synthetic input root.
        deadline = time.monotonic() + 10
        while any(path.is_relative_to(self.root) for path in list(playback.jobs)) and time.monotonic() < deadline:
            time.sleep(.05)
        self.client.close()
        self.engine.dispose()
        self.storage.stop()
        self.directory.cleanup()

    def auth(self, role="Customer"):
        return {"Authorization": "Bearer " + create_access_token(self.users[role], timedelta(minutes=5))}

    def event(self, name, payload=None, camera=None, kind="DROWSY_THRESHOLD_REACHED"):
        device = camera or self.camera
        with Session(self.engine) as session:
            row = AiEvent(event_id=name, device_id=device.id, event_type=kind,
                          occurred_at=datetime.now(timezone.utc).replace(tzinfo=None),
                          payload_hash=hashlib.sha256(name.encode()).hexdigest(), payload=payload or {})
            session.add(row); session.commit()

    def alert(self, name, camera=None):
        with Session(self.engine) as session:
            row = Alert(device_id=(camera or self.camera).id, source_event_id=name,
                        alert_type="DROWSY_THRESHOLD_REACHED", severity="1")
            session.add(row); session.commit(); session.refresh(row); return row.id

    def video(self, name, camera=None, real=False):
        path = self.root/(name+".mp4")
        if real:
            import imageio_ffmpeg
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-f", "lavfi",
                            "-i", "testsrc=size=160x120:rate=10", "-t", "1", "-c:v", "mpeg4",
                            "-pix_fmt", "yuv420p", "-y", str(path)], check=True, capture_output=True, timeout=20)
        else:
            path.write_bytes(b"synthetic-invalid-mp4")
        with Session(self.engine) as session:
            row = AiVideo(device_id=(camera or self.camera).id, message_id=name, state="DROWSY",
                          storage_key=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(), size_bytes=path.stat().st_size)
            session.add(row); session.commit(); session.refresh(row); return row

    def link(self, alert_id, role="Customer"):
        r = self.client.get(f"/api/alerts/{alert_id}/video", headers=self.auth(role))
        self.assertEqual(r.status_code, 200, r.text); return r.json()

    def wait_preview(self, video):
        deadline = time.monotonic()+20
        while time.monotonic()<deadline:
            result = self.client.get(f"/api/videos/{video.id}/playback", headers=self.auth()).json()
            if result["status"] != "PROCESSING": return result
            time.sleep(.05)
        self.fail("Preview did not finish")

    def test_explicit_policy_and_legacy_links_work_without_schema_migration(self):
        for key in ("clip_message_id", "state_event_id", "episode_start_event_id"):
            with self.subTest(field=key):
                row=self.video(key); self.event("event-"+key,{key:key}); alert_id=self.alert("event-"+key)
                result=self.link(alert_id)
                self.assertEqual(result["status"],"AVAILABLE")
                self.assertEqual(result["video"]["video_id"],row.id)
        listing=self.client.get('/api/alerts',headers=self.auth()).json()
        self.assertEqual(len(listing),3)
        self.assertTrue(all(x['video_status']=='AVAILABLE' for x in listing))

    def test_no_link_is_guessed_from_nearby_time_or_matching_state(self):
        self.video("nearby"); self.event("unlinked"); aid=self.alert("unlinked")
        self.assertEqual(self.link(aid)["status"],"UNLINKED")
        self.assertIsNone(self.link(aid)["video"])

    def test_current_clip_pointer_never_falls_back_to_another_clip_in_episode(self):
        self.video("old-clip")
        self.event("threshold",{"clip_message_id":"new-clip","episode_start_event_id":"old-clip"})
        aid=self.alert("threshold")
        self.assertEqual(self.link(aid)["status"],"PENDING_OR_UNAVAILABLE")
        row=self.video("new-clip")
        self.assertEqual(self.link(aid)["video"]["video_id"],row.id)

    def test_video_before_event_and_event_before_video_both_resolve(self):
        self.video("early"); aid=self.alert("late-event")
        self.assertEqual(self.link(aid)["status"],"UNLINKED")
        self.event("late-event",{"clip_message_id":"early"})
        self.assertEqual(self.link(aid)["status"],"AVAILABLE")
        self.event("early-event",{"clip_message_id":"late-video"}); aid=self.alert("early-event")
        self.assertEqual(self.link(aid)["status"],"PENDING_OR_UNAVAILABLE")
        self.video("late-video")
        self.assertEqual(self.link(aid)["status"],"AVAILABLE")

    def test_cross_camera_pointer_and_unassigned_access_do_not_leak(self):
        row=self.video("other-clip",camera=self.other)
        self.event("wrong-camera",{"clip_message_id":"other-clip"}); aid=self.alert("wrong-camera")
        self.assertIsNone(self.link(aid)["video"])
        self.event("other-event",{"clip_message_id":"other-clip"},camera=self.other)
        aid=self.alert("other-event",camera=self.other)
        for endpoint in [f'/alerts/{aid}/video',f'/videos/{row.id}/content',f'/videos/{row.id}/playback',f'/videos/{row.id}/playback/content']:
            self.assertEqual(self.client.get('/api'+endpoint,headers=self.auth()).status_code,404)
        self.assertEqual(self.client.post(f'/api/videos/{row.id}/playback',headers=self.auth()).status_code,404)
        self.assertEqual(self.link(aid,role="Admin")["video"]["video_id"],row.id)

    def test_missing_file_and_manual_delete_have_distinct_states(self):
        row=self.video("missing"); self.event("e",{"clip_message_id":"missing"}); aid=self.alert("e")
        (self.root/row.storage_key).unlink()
        self.assertEqual(self.link(aid)["status"],"MISSING")
        self.assertEqual(self.client.delete(f'/api/videos/{row.id}',headers=self.auth('Employee')).status_code,204)
        self.assertEqual(self.link(aid)["status"],"DELETED")

    def test_h264_preview_preserves_original_and_delete_removes_preview(self):
        row=self.video("original",real=True)
        original=(self.root/row.storage_key).read_bytes()
        self.assertEqual(self.client.get(f'/api/videos/{row.id}/playback',headers=self.auth()).json()['status'],'NOT_PREPARED')
        for _ in range(2):
            result=self.client.post(f'/api/videos/{row.id}/playback',headers=self.auth())
            self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(self.wait_preview(row)['status'],'READY')
        preview=self.client.get(f'/api/videos/{row.id}/playback/content',headers=self.auth())
        self.assertEqual(preview.status_code,200,preview.text[:100])
        self.assertIn(b'avc1',preview.content)
        self.assertEqual((self.root/row.storage_key).read_bytes(),original)
        self.assertEqual(self.client.get(f'/api/videos/{row.id}/content',headers=self.auth()).content,original)
        self.assertEqual(self.client.delete(f'/api/videos/{row.id}',headers=self.auth('Admin')).status_code,204)
        self.assertFalse(playback.path(row).exists())
        self.assertEqual(self.client.get(f'/api/videos/{row.id}/playback/content',headers=self.auth()).status_code,404)

    def test_failed_conversion_keeps_original_download_available(self):
        row=self.video("bad-video")
        self.client.post(f'/api/videos/{row.id}/playback',headers=self.auth())
        self.assertEqual(self.wait_preview(row)['status'],'FAILED')
        self.assertEqual(self.client.get(f'/api/videos/{row.id}/content',headers=self.auth()).status_code,200)

    def test_delete_during_conversion_does_not_restore_a_preview(self):
        row=self.video('deleted-during-job',real=True)
        self.client.post(f'/api/videos/{row.id}/playback',headers=self.auth())
        self.client.delete(f'/api/videos/{row.id}',headers=self.auth('Admin'))
        deadline=time.monotonic()+10
        while playback.path(row) in playback.jobs and time.monotonic()<deadline:time.sleep(.05)
        self.assertFalse(playback.path(row).exists())
        self.assertFalse((self.root/row.storage_key).exists())


if __name__ == '__main__':
    unittest.main()
