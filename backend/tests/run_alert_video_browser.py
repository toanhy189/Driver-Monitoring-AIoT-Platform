"""Optional Edge/Playwright test with synthetic video and a temporary SQLite DB.

Build frontend first. Install Playwright outside this repo, then set
PLAYWRIGHT_MODULE to its absolute module path. No production services are used.
"""
import hashlib
from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
from unittest.mock import patch

from fastapi.staticfiles import StaticFiles
from sqlmodel import Session
import uvicorn

from test_alert_video import AlertVideo
from app.api.routes import users, devices, history, commands, rules
from app.models.alert import Alert
from app.models.device import Device
from app.models.user_device import UserDevice
from app.models.command import Command
from app.models.command_type import CommandType

ROOT = Path(__file__).resolve().parents[2]


def main():
    if not os.getenv("PLAYWRIGHT_MODULE"):
        raise RuntimeError("Set PLAYWRIGHT_MODULE to an external Playwright installation")
    if not (ROOT/"frontend/dist/index.html").is_file():
        raise RuntimeError("Build frontend before running browser acceptance")
    logging.getLogger().setLevel(logging.WARNING)
    fixture = AlertVideo()
    fixture.setUp()
    provisioner = patch("app.api.routes.devices.provision_device",
        side_effect=lambda code, **kwargs: {"username":code,"password":"private-browser-fixture-password"})
    provisioner.start()
    server = thread = None
    try:
        video = fixture.video("browser-original", real=True)
        fixture.event("browser-threshold", {"clip_message_id": video.message_id})
        aid = fixture.alert("browser-threshold")
        bad = fixture.video("browser-invalid")
        fixture.event("browser-bad", {"clip_message_id": bad.message_id})
        bad_aid = fixture.alert("browser-bad")
        fixture.event("browser-pending", {"clip_message_id": "not-uploaded"})
        pending_aid = fixture.alert("browser-pending")
        with Session(fixture.engine) as session:
            for identifier, severity in ((bad_aid, "2"), (pending_aid, "3")):
                row = session.get(Alert, identifier)
                row.severity = severity
                session.add(row)
            resolved = session.get(Alert, aid)
            resolved.status = "RESOLVED"
            session.add(resolved)
            target = Device(device_code="alert-browser",model="ESP32",device_type="ALERT_NODE",lifecycle_state="ACTIVE")
            archived = Device(device_code="vision-archived",model="USB",device_type="VISION_NODE",lifecycle_state="DECOMMISSIONED")
            setup_camera = Device(device_code="vision-setup",model="USB",device_type="VISION_NODE",lifecycle_state="REGISTERED")
            kind = CommandType(code="AUTO_ALERT",name="Automatic")
            session.add_all([target,kind,archived,setup_camera]);session.flush()
            target_id = target.id
            for role in ("Customer","Employee"):
                session.add(UserDevice(user_id=fixture.users[role],device_id=target.id))
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            session.add(Command(device_id=target.id,alert_id=aid,command_type_id=kind.id,action="AUTO_ALERT",
                request_id="browser-related",status="ACKNOWLEDGED",ack_status="COMPLETED",created_at=now,
                completed_ack_at=now+timedelta(seconds=1)))
            session.add(Command(device_id=target.id,alert_id=bad_aid,command_type_id=kind.id,action="AUTO_ALERT",
                request_id="browser-unrelated",status="FAILED",ack_status="FAILED",created_at=now,
                error_message="COMMAND_EXPIRED"))
            session.commit()
        other = fixture.video("unassigned", camera=fixture.other)
        app = fixture.client.app
        for router in (users.router, devices.router, history.router, commands.router, rules.router):
            app.include_router(router, prefix="/api")
        app.mount("/", StaticFiles(directory=ROOT/"frontend/dist", html=True), name="frontend")
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        for _ in range(100):
            if server.started:
                break
            time.sleep(.05)
        else:
            raise RuntimeError("Temporary HTTP server did not start")
        path = fixture.root/"browser-fixture.json"
        path.write_text(json.dumps({
            "base_url": f"http://127.0.0.1:{port}",
            "tokens": {role: fixture.auth(role)["Authorization"].split(" ", 1)[1]
                       for role in ("Admin", "Employee", "Customer")},
            "video_id": video.id, "unassigned_video_id": other.id,
            "camera_id": fixture.camera.id,
            "target_id": target_id, "linked_alert_id": aid,
            "original_sha256": hashlib.sha256((fixture.root/video.storage_key).read_bytes()).hexdigest(),
            "original": str(fixture.root/video.storage_key),
        }), encoding="utf-8")
        result = subprocess.run(["node", "frontend/tests/alert-video-browser.cjs"], cwd=ROOT,
            env={**os.environ, "QA_FIXTURE": str(path)}, timeout=120)
        return result.returncode
    finally:
        if server is not None:
            server.should_exit = True
        if thread is not None:
            thread.join(timeout=10)
        fixture.tearDown()
        provisioner.stop()


if __name__ == "__main__":
    raise SystemExit(main())
