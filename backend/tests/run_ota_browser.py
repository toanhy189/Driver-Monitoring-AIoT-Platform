"""Real React/FastAPI OTA flow on temporary SQLite with a signed virtual device, no broker/hardware."""
import json
import hashlib
import os
from pathlib import Path
import secrets
import socket
import subprocess
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Header,HTTPException
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session,select
import uvicorn
from test_alert_video import AlertVideo
from test_ota_postgres import OtaAcceptance
from app.api.routes import users,devices,ota
from app.core.config import settings
from app.models.device import Device
from app.models.ota import OtaJob,FirmwareArtifact,utcnow
from app.services import ota_service as service

ROOT=Path(__file__).resolve().parents[2]

def main():
    if not os.getenv("PLAYWRIGHT_MODULE"):raise RuntimeError("External Playwright required")
    fixture=AlertVideo();fixture.setUp();server=thread=None
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    public=fixture.root/"public.pem";public.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
    config=patch.multiple(settings,OTA_ENABLED=True,OTA_STORAGE_DIR=fixture.root/"firmware",OTA_PUBLIC_KEY_FILE=public,
        OTA_PUBLIC_BASE_URL="https://virtual-ota.test:9443",OTA_ALLOW_HTTP_FOR_LAN=False)
    config.start()
    try:
        image,manifest=OtaAcceptance.fixture(SimpleNamespace(key=key))
        image_path=fixture.root/"fixture.bin";image_path.write_bytes(image)
        manifest_path=fixture.root/"fixture.json";manifest_path.write_text(json.dumps(manifest),encoding="utf-8")
        with Session(fixture.engine) as db:
            node=Device(device_code="ota-browser",model="ESP32",device_type="ALERT_NODE",lifecycle_state="ACTIVE",
                status="ONLINE",last_seen=utcnow(),firmware_version="0.4.0",hardware_version="esp32doit-devkit-v1",
                ota_capabilities={"protocol":"driver-ota-v1","supported":True,"max_image_bytes":1310720,
                    "rollback_supported":True,"signature_required":True,"key_sha256":service.key_fingerprint(),
                    "image_sha256":"a"*64,"outputs_busy":False})
            old=Device(device_code="ota-old-firmware",model="ESP32",device_type="ALERT_NODE",lifecycle_state="ACTIVE",
                status="ONLINE",last_seen=utcnow(),firmware_version="0.3.0",hardware_version="esp32doit-devkit-v1")
            db.add_all([node,old]);db.commit()
        app=fixture.client.app
        for router in (users.router,devices.router,ota.router):app.include_router(router,prefix="/api")
        qa_key=secrets.token_urlsafe(24)
        @app.post("/__qa/advance")
        def advance(x_qa_key: str=Header(default="")):
            if x_qa_key!=qa_key:raise HTTPException(403)
            service.tick(fixture.engine,lambda *args:True)
            with Session(fixture.engine) as db:
                job=db.exec(select(OtaJob).order_by(OtaJob.id.desc())).first()
                if not job:raise HTTPException(404)
                artifact=db.get(FirmwareArtifact,1)
                service.accept_status(db,"ota-browser",{"protocol":"driver-ota-v1","device_code":"ota-browser",
                    "job_id":job.id,"request_id":job.request_id,"sequence":5,"state":"CONFIRMED",
                    "firmware_version":artifact.version,"image_sha256":artifact.app_sha256,
                    "download_sha256":artifact.sha256,"bytes_received":artifact.size_bytes})
            return {"ok":True}
        app.mount("/",StaticFiles(directory=ROOT/"frontend/dist",html=True),name="frontend")
        with socket.socket() as sock:sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
        server=uvicorn.Server(uvicorn.Config(app,host="127.0.0.1",port=port,log_level="error"));thread=threading.Thread(target=server.run,daemon=True);thread.start()
        for _ in range(100):
            if server.started:break
            time.sleep(.05)
        path=fixture.root/"qa.json"
        path.write_text(json.dumps({"base_url":f"http://127.0.0.1:{port}","qa_key":qa_key,
            "tokens":{role:fixture.auth(role)["Authorization"].split(" ",1)[1] for role in ("Admin","Employee","Customer")},
            "image":str(image_path),"manifest":str(manifest_path)}),encoding="utf-8")
        return subprocess.run(["node","frontend/tests/ota-browser.cjs"],cwd=ROOT,env={**os.environ,"QA_FIXTURE":str(path)},timeout=120).returncode
    finally:
        if server:server.should_exit=True
        if thread:thread.join(timeout=10)
        config.stop();fixture.tearDown()

if __name__=="__main__":raise SystemExit(main())
