"""Optional Edge/Playwright test with synthetic video and a temporary SQLite DB.

Build frontend first. Install Playwright outside this repo, then set
PLAYWRIGHT_MODULE to its absolute module path. No production services are used.
"""
import hashlib
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import threading
import time

from fastapi.staticfiles import StaticFiles
from sqlmodel import Session
import uvicorn

from test_alert_video import AlertVideo
from app.api.routes import users, devices, history
from app.models.alert import Alert

ROOT = Path(__file__).resolve().parents[2]


def main():
    if not os.getenv("PLAYWRIGHT_MODULE"):
        raise RuntimeError("Set PLAYWRIGHT_MODULE to an external Playwright installation")
    if not (ROOT/"frontend/dist/index.html").is_file():
        raise RuntimeError("Build frontend before running browser acceptance")
    logging.getLogger().setLevel(logging.WARNING)
    fixture = AlertVideo()
    fixture.setUp()
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
            session.commit()
        other = fixture.video("unassigned", camera=fixture.other)
        app = fixture.client.app
        for router in (users.router, devices.router, history.router):
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


if __name__ == "__main__":
    raise SystemExit(main())
