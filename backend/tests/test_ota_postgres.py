"""Real DB/API OTA acceptance with signed fixture images and a virtual device; never flashes hardware."""
import base64
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import secrets
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL","postgresql+psycopg://test:test@localhost/test")
os.environ.setdefault("SECRET_KEY","ota-isolated-test-secret-at-least-32-bytes")
from cryptography.hazmat.primitives import serialization,hashes
from cryptography.hazmat.primitives.asymmetric import rsa,padding
from fastapi import FastAPI,Header
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import SQLModel,Session,select,create_engine
from app.api.deps import get_current_user
from app.api.routes import ota,devices
from app.core.db import get_session
from app.core.config import settings
from app.models.user import User
from app.models.device import Device
from app.models.ai_event import RuleBinding
from app.models.command import Command
from app.models.command_type import CommandType
from app.models.ota import FirmwareArtifact,OtaJob,OtaJobEvent,utcnow
from app.schemas.ota import signing_bytes
from app.services import ota_service as service

@unittest.skipUnless(os.getenv("RULE_BINDING_TEST_POSTGRES"),"Use disposable PostgreSQL runner")
class OtaAcceptance(unittest.TestCase):
    def setUp(self):
        url=os.environ["RULE_BINDING_TEST_POSTGRES"]
        if "/codex_rule_binding_" not in url: raise RuntimeError("Disposable DB required")
        self.tmp=tempfile.TemporaryDirectory(prefix="ota-test-");self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        pub=self.root/"public.pem";pub.write_bytes(self.key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
        self.config=patch.multiple(settings,OTA_ENABLED=True,OTA_STORAGE_DIR=self.root/"images",OTA_PUBLIC_KEY_FILE=pub,
            OTA_PUBLIC_BASE_URL="https://device-server.test:8443",OTA_ALLOW_HTTP_FOR_LAN=False)
        self.config.start();self.addCleanup(self.config.stop)
        schema="codex_ota_"+secrets.token_hex(6);control=create_engine(url)
        with control.begin() as connection: connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        self.engine=create_engine(url,connect_args={"options":f"-csearch_path={schema}"})
        def cleanup():
            self.engine.dispose()
            with control.begin() as connection: connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            control.dispose()
        self.addCleanup(cleanup);SQLModel.metadata.create_all(self.engine)
        with Session(self.engine) as db:
            self.actors={}
            for role in ("Admin","Employee","Customer"):
                user=User(username=role,fullname=role,email=role+"@test.local",phone=role,role=role,hash_password="unused")
                db.add(user);db.flush();self.actors[role]=user.id
            source=Device(device_code="vision-ota-test",device_type="VISION_NODE",model="Camera",lifecycle_state="ACTIVE")
            device=Device(device_code="alert-ota-test",device_type="ALERT_NODE",model="ESP32",lifecycle_state="ACTIVE",
                status="ONLINE",last_seen=utcnow(),hardware_version="esp32doit-devkit-v1",firmware_version="0.4.0",ota_capabilities=self.caps())
            db.add_all([source,device]);db.flush();self.device=device.id;self.source=source.id
            db.add(RuleBinding(source_device_id=source.id,target_device_id=device.id,enabled=True,policy={}))
            kind=CommandType(code="AUTO_ALERT",name="Automatic");db.add(kind);db.flush();self.kind=kind.id;db.commit()
        app=FastAPI();app.include_router(ota.router,prefix="/api");app.include_router(devices.router,prefix="/api")
        def sessions():
            with Session(self.engine) as db: yield db
        def actor(x_test_role: str=Header(default="Admin")):
            with Session(self.engine) as db: return db.get(User,self.actors[x_test_role])
        app.dependency_overrides[get_session]=sessions;app.dependency_overrides[get_current_user]=actor
        self.client=TestClient(app);self.addCleanup(self.client.close)
    def caps(self):
        return {"protocol":"driver-ota-v1","supported":True,"max_image_bytes":1310720,"rollback_supported":True,
            "signature_required":True,"key_sha256":service.key_fingerprint(),"image_sha256":"a"*64,"outputs_busy":False}
    def fixture(self,version="0.4.1",bad_signature=False):
        header=bytearray(24);header[0]=0xe9;header[1]=1;header[23]=1
        payload=service.BUILD_MARKER+self.key.public_key().public_bytes(serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo).strip()+b"fixture-image-"*30
        data=bytes(header)+struct.pack("<II",0x3f400020,len(payload))+payload
        checksum=0xef
        for value in payload:checksum^=value
        data+=b"\0"*((-len(data)-1)%16)+bytes([checksum]);data+=hashlib.sha256(data).digest()
        manifest={"format":"driver-ota-v1","key_id":"ota-key-v1","version":version,"hardware_version":"esp32doit-devkit-v1",
            "size_bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()}
        signature=self.key.sign(signing_bytes(manifest),padding.PKCS1v15(),hashes.SHA256())
        manifest["signature"]=base64.b64encode(b"x"*256 if bad_signature else signature).decode()
        return data,manifest
    def upload(self,version="0.4.1",bad_signature=False):
        data,manifest=self.fixture(version,bad_signature)
        result=self.client.post("/api/ota/firmware",files={"file":("firmware.bin",data,"application/octet-stream")},
            data={"manifest":json.dumps(manifest),"notes":"test"})
        self.assertEqual(result.status_code,201,result.text)
        return result.json()["id"]
    def release(self,version="0.4.1"):
        identifier=self.upload(version)
        self.assertEqual(self.client.post(f"/api/ota/firmware/{identifier}/verify").status_code,200)
        self.assertEqual(self.client.post(f"/api/ota/firmware/{identifier}/release").status_code,200)
        return identifier
    def create(self,artifact=None):
        artifact=artifact or self.release()
        result=self.client.post("/api/ota/deployments",json={"artifact_id":artifact,"device_ids":[self.device],"confirmed":True})
        self.assertEqual(result.status_code,201,result.text)
        with Session(self.engine) as db:
            job=db.exec(select(OtaJob).where(OtaJob.deployment_id==result.json()["id"])).one()
            return job.id
    def status(self,job,**extra):
        with Session(self.engine) as db:
            item=db.get(OtaJob,job)
            body={"protocol":"driver-ota-v1","device_code":"alert-ota-test","job_id":job,
                "request_id":item.request_id,"sequence":1,"state":"ACCEPTED",**extra}
            return service.accept_status(db,"alert-ota-test",body)
    def test_role_guards_and_download_auth_are_enforced(self):
        for role in ("Employee","Customer"):
            headers={"X-Test-Role":role}
            for path in ("/api/ota/firmware","/api/ota/devices","/api/ota/deployments"):
                self.assertEqual(self.client.get(path,headers=headers).status_code,403)
            result=self.client.post("/api/ota/deployments",headers=headers,json={"artifact_id":1,"device_ids":[self.device],"confirmed":True})
            self.assertEqual(result.status_code,403)
        self.assertEqual(self.client.get("/api/ota/device/jobs/1/image").status_code,401)
    def test_signed_artifact_lifecycle_and_rejection(self):
        bad=self.upload(bad_signature=True)
        self.assertEqual(self.client.post(f"/api/ota/firmware/{bad}/release").status_code,409)
        self.assertEqual(self.client.post(f"/api/ota/firmware/{bad}/verify").status_code,422)
        self.assertEqual(self.client.post(f"/api/ota/firmware/{bad}/release").status_code,409)
        good=self.release("0.4.2")
        self.assertEqual(self.client.post(f"/api/ota/firmware/{good}/verify").status_code,409)
        with Session(self.engine) as db:
            artifact=db.get(FirmwareArtifact,good);path=service.artifact_path(artifact)
            path.write_bytes(path.read_bytes()+b"tampered")
        result=self.client.post("/api/ota/deployments",json={"artifact_id":good,"device_ids":[self.device],"confirmed":True})
        self.assertEqual(result.status_code,422)
        with Session(self.engine) as db:self.assertEqual(db.get(Device,self.device).lifecycle_state,"ACTIVE")
    def test_preview_reports_real_blockers(self):
        artifact=self.release()
        for case in ("old-firmware","offline","wrong-hardware","wrong-key","busy","small-slot"):
            with self.subTest(case=case):
                with Session(self.engine) as db:
                    device=db.get(Device,self.device);device.status="ONLINE";device.hardware_version="esp32doit-devkit-v1";caps=self.caps()
                    if case=="old-firmware":caps=None
                    if case=="offline":device.status="OFFLINE"
                    if case=="wrong-hardware":device.hardware_version="another-board"
                    if case=="wrong-key":caps["key_sha256"]="b"*64
                    if case=="busy":caps["outputs_busy"]=True
                    if case=="small-slot":caps["max_image_bytes"]=100
                    device.ota_capabilities=caps;db.add(device);db.commit()
                result=self.client.post("/api/ota/deployments/preview",json={"artifact_id":artifact,"device_ids":[self.device]})
                self.assertFalse(result.json()["ready"]);self.assertTrue(result.json()["devices"][0]["reason"])
    def test_confirmed_deployment_pauses_rules_and_lifecycle(self):
        artifact=self.release()
        self.assertEqual(self.client.post("/api/ota/deployments",json={"artifact_id":artifact,"device_ids":[self.device]}).status_code,422)
        job=self.create(artifact)
        with Session(self.engine) as db:
            self.assertEqual(db.get(Device,self.device).lifecycle_state,"MAINTENANCE")
            self.assertFalse(db.get(RuleBinding,self.source).enabled)
        self.assertEqual(self.client.post(f"/api/devices/{self.device}/activate").status_code,409)
        self.assertEqual(self.client.post(f"/api/devices/{self.device}/decommission").status_code,409)
        self.assertEqual(self.client.post(f"/api/ota/jobs/{job}/cancel").status_code,200)
        self.assertEqual(self.client.post(f"/api/devices/{self.device}/activate").status_code,200)
    def test_dispatch_download_progress_and_only_matching_final_confirmation(self):
        job=self.create();sent=[]
        service.tick(self.engine,lambda code,payload:sent.append((code,payload)) or True)
        self.assertEqual(len(sent),1);payload=sent[0][1]
        url=f"/api/ota/device/jobs/{job}/image";headers={"Authorization":"Bearer "+payload["download_token"]}
        result=self.client.get(url,headers=headers);self.assertEqual(result.status_code,200)
        self.assertEqual(hashlib.sha256(result.content).hexdigest(),payload["manifest"]["sha256"])
        self.assertEqual(self.client.get(f"/api/ota/device/jobs/{job+1}/image",headers=headers).status_code,403)
        self.assertTrue(self.status(job))
        self.assertFalse(self.status(job)) # duplicate sequence
        self.assertFalse(self.status(job,sequence=2,state="CONFIRMED",firmware_version="0.4.1",image_sha256="b"*64,download_sha256="c"*64))
        with Session(self.engine) as db:
            artifact=db.get(FirmwareArtifact,1)
            final={"sequence":3,"state":"CONFIRMED","firmware_version":artifact.version,
                "image_sha256":artifact.app_sha256,"download_sha256":artifact.sha256,"bytes_received":artifact.size_bytes}
        self.assertTrue(self.status(job,**final));self.assertFalse(self.status(job,**final))
        with Session(self.engine) as db:
            self.assertEqual(db.get(OtaJob,job).state,"CONFIRMED")
            self.assertEqual(db.get(Device,self.device).lifecycle_state,"MAINTENANCE")
        self.assertEqual(self.client.get(url,headers=headers).status_code,409)
    def test_power_loss_or_publish_ambiguity_never_replays_automatically(self):
        job=self.create()
        with self.assertRaises(RuntimeError):service.tick(self.engine,lambda *args:(_ for _ in ()).throw(RuntimeError("process interrupted")))
        with Session(self.engine) as db:
            item=db.get(OtaJob,job);self.assertEqual(item.state,"PUBLISHING");item.updated_at-=timedelta(seconds=31);db.add(item);db.commit()
        publisher=unittest.mock.Mock(return_value=True);service.tick(self.engine,publisher);publisher.assert_not_called()
        with Session(self.engine) as db:self.assertEqual(db.get(OtaJob,job).state,"RESULT_UNKNOWN")
        self.assertTrue(self.status(job,sequence=5,state="ROLLED_BACK",firmware_version="0.4.0",image_sha256="a"*64))
        self.assertEqual(self.client.get("/api/ota/deployments").json()[0]["jobs"][0]["state"],"ROLLED_BACK")
    def test_pending_command_blocks_update_and_withdrawal_blocks_dispatch(self):
        artifact=self.release()
        with Session(self.engine) as db:
            command=Command(device_id=self.device,command_type_id=self.kind,action="AUTO_ALERT",status="PENDING")
            db.add(command);db.commit()
        result=self.client.post("/api/ota/deployments/preview",json={"artifact_id":artifact,"device_ids":[self.device]})
        self.assertFalse(result.json()["ready"])
        with Session(self.engine) as db:
            command=db.exec(select(Command)).one();command.status="FAILED";db.add(command);db.commit()
        job=self.create(artifact)
        self.assertEqual(self.client.post(f"/api/ota/firmware/{artifact}/withdraw").status_code,200)
        publisher=unittest.mock.Mock();service.tick(self.engine,publisher);publisher.assert_not_called()
        with Session(self.engine) as db:self.assertEqual(db.get(OtaJob,job).state,"REJECTED")

if __name__=="__main__":unittest.main()
