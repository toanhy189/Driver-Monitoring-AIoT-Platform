"""Real PostgreSQL/API acceptance in disposable schemas; no broker or hardware."""
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import secrets
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost/test")
os.environ.setdefault("SECRET_KEY", "isolated-test-key")
from fastapi import FastAPI, Header
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, Session, create_engine, select
from app.api.deps import get_current_user
from app.core.db import get_session
from app.api.routes import users, devices, alerts, history, commands, configs
from app.models.user import User
from app.models.user_device import UserDevice
from app.models.device import Device
from app.models.telemetry import Telemetry
from app.models.alert import Alert
from app.models.alert_read import AlertRead
from app.models.command import Command
from app.models.command_type import CommandType
from app.models.audit_log import AuditLog


@unittest.skipUnless(os.getenv("RULE_BINDING_TEST_POSTGRES"), "Use the disposable PostgreSQL runner")
class AccessMetrics(unittest.TestCase):
    def setUp(self):
        url = os.environ["RULE_BINDING_TEST_POSTGRES"]
        if "/codex_rule_binding_" not in url:
            raise RuntimeError("Only the disposable PostgreSQL database is allowed")
        schema = "codex_access_" + secrets.token_hex(6)
        control = create_engine(url)
        with control.begin() as db:
            db.execute(text(f'CREATE SCHEMA "{schema}"'))
        self.engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
        def cleanup():
            self.engine.dispose()
            with control.begin() as db:
                db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            control.dispose()
        self.addCleanup(cleanup)
        SQLModel.metadata.create_all(self.engine)
        self.now = datetime.now(timezone.utc).replace(tzinfo=None)
        with Session(self.engine) as db:
            self.people = {}
            for name, role in (("admin", "Admin"), ("operator", "Employee"), ("driver", "Customer"), ("other", "Customer")):
                person = User(username=name, fullname=name, email=name+"@example.test", phone=name,
                    role=role, hash_password="unused")
                db.add(person); db.flush(); self.people[name] = person.id
            source = Device(device_code="vision-test", device_type="VISION_NODE", model="camera", lifecycle_state="ACTIVE")
            target = Device(device_code="alert-test", device_type="ALERT_NODE", model="esp32", lifecycle_state="ACTIVE", status="ONLINE", last_seen=self.now)
            hidden = Device(device_code="alert-hidden", device_type="ALERT_NODE", model="esp32", lifecycle_state="ACTIVE")
            db.add_all([source, target, hidden]); db.flush()
            self.source, self.target, self.hidden = source.id, target.id, hidden.id
            for person in self.people.values():
                for device_id in (self.source, self.target):
                    db.add(UserDevice(user_id=person, device_id=device_id))
            kind = CommandType(code="AUTO_ALERT", name="Automatic")
            db.add(kind); db.flush(); self.kind = kind.id
            alert = Alert(device_id=self.source, alert_type="DROWSINESS", severity="1", created_at=self.now)
            db.add(alert); db.flush(); self.alert = alert.id
            db.commit()
        app = FastAPI()
        for router in (users.router, devices.router, alerts.router, history.router, commands.router, configs.router):
            app.include_router(router, prefix="/api")
        def session():
            with Session(self.engine) as db: yield db
        def actor(x_test_user: str = Header(default="admin")):
            with Session(self.engine) as db: return db.get(User, self.people[x_test_user])
        app.dependency_overrides[get_session] = session
        app.dependency_overrides[get_current_user] = actor
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.migration = Path(__file__).resolve().parents[2] / "database/migration_roles_metrics.sql"
        self.apply_migration()

    def apply_migration(self):
        with self.engine.connect() as db:
            db.exec_driver_sql(self.migration.read_text(encoding="utf-8")); db.commit()

    def auth(self, person): return {"X-Test-User": person}

    def test_single_admin_api_and_database_are_protected(self):
        body = dict(fullname="new", username="new", email="new@example.test", phone="12345678",
                    password="test-password", confirm_password="test-password", role="Admin")
        self.assertEqual(self.client.post("/api/users", json=body).status_code, 422)
        for role in ("Admin", "ADMIN"):
            result = self.client.patch(f"/api/users/{self.people['operator']}", json={"role": role})
            self.assertEqual(result.status_code, 422)
        for body in ({"status":"DISABLED"}, {"role":"Customer"}, {"status":"ACTIVE"}):
            self.assertEqual(self.client.patch(f"/api/users/{self.people['admin']}", json=body).status_code, 409)
        with Session(self.engine) as db:
            second = User(username="second", fullname="test", email="second@example.test", phone="second", hash_password="unused", role="Admin")
            db.add(second)
            with self.assertRaises(IntegrityError): db.commit()
            db.rollback()
        self.assertEqual(self.client.patch(f"/api/users/{self.people['driver']}", json={"role":"Employee"}).status_code, 200)

    def register(self, code="draft-device", kind="VISION_NODE", **extra):
        return self.client.post("/api/devices",json={"device_code":code,"device_type":kind,"name":"Draft","model":"USB",**extra})

    def test_device_type_is_explicit_and_required_independently_of_code_or_model(self):
        for body in ({"device_code":"alert-new","model":"Camera"},
                     {"device_code":"new","model":"USB","device_type":"CAMERA"},
                     {"device_code":"bad/#","model":"USB","device_type":"VISION_NODE"}):
            self.assertEqual(self.client.post("/api/devices",json=body).status_code,422)
        result = self.register(code="alert-shaped-code",kind="VISION_NODE",model="thiết bị cảnh báo")
        self.assertEqual(result.status_code,201,result.text)
        self.assertEqual(result.json()["device"]["type"],"VISION_NODE")
        result = self.register(code="vision-shaped-code",kind="ALERT_NODE",model="Camera")
        self.assertEqual(result.status_code,201,result.text)
        self.assertEqual(result.json()["device"]["type"],"ALERT_NODE")
        self.assertEqual(self.client.post("/api/devices",headers=self.auth("operator"),json={
            "device_code":"operator-created","model":"USB","device_type":"VISION_NODE"}).status_code,403)

    def test_unused_registration_can_be_deleted_and_audit_is_retained(self):
        result=self.register()
        self.assertEqual(result.status_code,201,result.text)
        identifier=result.json()["device"]["id"]
        path=f"/api/devices/{identifier}"
        self.assertTrue(self.client.get(path).json()["can_delete_registration"])
        for person in ("operator","driver"):
            self.assertEqual(self.client.delete(path,headers=self.auth(person)).status_code,403)
        deleted=self.client.delete(path)
        self.assertEqual(deleted.status_code,204,deleted.text)
        self.assertEqual(self.client.get(path).status_code,404)
        with Session(self.engine) as db:
            self.assertEqual(db.exec(select(UserDevice).where(UserDevice.device_id==identifier)).all(),[])
            audits=db.exec(select(AuditLog).where(AuditLog.entity_type=="Device",AuditLog.entity_id==str(identifier))).all()
            self.assertEqual({row.action for row in audits},{"REGISTER_DEVICE","DELETE_UNUSED_REGISTRATION"})

    def test_generated_codes_are_unique_typed_and_custom_codes_still_work(self):
        codes = []
        for kind, prefix in (("VISION_NODE","vision-"),("ALERT_NODE","alert-"),("VISION_NODE","vision-")):
            result = self.client.post("/api/devices",json={"device_type":kind,"name":"Auto","model":"USB"})
            self.assertEqual(result.status_code,201,result.text)
            device = result.json()["device"]
            self.assertTrue(device["device_code"].startswith(prefix))
            self.assertEqual(device["type"],kind)
            codes.append(device["device_code"])
        self.assertEqual(len(codes),len(set(codes)))
        self.assertEqual(self.register("existing-code").status_code,201)
        self.assertEqual(self.register("existing-code").status_code,409)

    def test_retired_device_has_no_restore_endpoint_and_cannot_be_reactivated(self):
        with Session(self.engine) as db:
            source = db.get(Device,self.source)
            source.lifecycle_state = "DECOMMISSIONED"
            source.status = "OFFLINE"
            source.mqtt_username = None
            db.add(source)
            db.commit()
        path = f"/api/devices/{self.source}/restore"
        self.assertEqual(self.client.post(path).status_code,404)
        with patch("app.api.routes.devices.provision_device") as broker:
            self.assertEqual(self.client.post(f"/api/devices/{self.source}/provision").status_code,409)
            self.assertEqual(self.client.post(f"/api/devices/{self.source}/activate").status_code,409)
            broker.assert_not_called()
        with Session(self.engine) as db:
            self.assertEqual(db.get(Device,self.source).lifecycle_state,"DECOMMISSIONED")
            self.assertIsNotNone(db.get(Alert,self.alert))
            self.assertIsNotNone(db.exec(select(UserDevice).where(UserDevice.device_id==self.source)).first())

    def test_delete_rejects_provisioned_assigned_connected_or_data_bearing_devices(self):
        from app.models.config import Config
        from app.models.video import AiVideo
        from app.models.ai_event import AiEvent, AiMessageReceipt, RuleBinding, RuleRuntime
        cases=("provisioned","active","decommissioned","mqtt","connected","assigned","telemetry","config","alert","command","video","event","receipt","binding","runtime")
        for index,case in enumerate(cases):
            with self.subTest(case=case):
                response=self.register(code=f"draft-{index}")
                self.assertEqual(response.status_code,201,response.text)
                identifier=response.json()["device"]["id"]
                with Session(self.engine) as db:
                    device=db.get(Device,identifier)
                    if case in ("provisioned","active","decommissioned"): device.lifecycle_state=case.upper()
                    if case=="mqtt": device.mqtt_username=device.device_code
                    if case=="connected": device.last_seen=self.now
                    if case=="assigned": db.add(UserDevice(device_id=identifier,user_id=self.people["driver"]))
                    if case=="telemetry": db.add(Telemetry(device_id=identifier))
                    if case=="config": db.add(Config(device_id=identifier))
                    if case=="alert": db.add(Alert(device_id=identifier,alert_type="TEST"))
                    if case=="command": db.add(Command(device_id=identifier,command_type_id=self.kind))
                    if case=="video": db.add(AiVideo(device_id=identifier,message_id=f"video-{index}",state="ATTENTIVE",storage_key="unused.mp4",sha256="a"*64,size_bytes=1))
                    if case=="event": db.add(AiEvent(device_id=identifier,event_id=f"event-{index}",event_type="STATE_CHANGED",occurred_at=self.now,payload_hash="a"*64,payload={}))
                    if case=="receipt": db.add(AiMessageReceipt(device_id=identifier,message_id=f"receipt-{index}",topic="test",payload_hash="a"*64))
                    if case=="binding": db.add(RuleBinding(source_device_id=identifier,target_device_id=self.target,policy={}))
                    if case=="runtime": db.add(RuleRuntime(source_device_id=identifier,state={}))
                    db.add(device);db.commit()
                path=f"/api/devices/{identifier}"
                self.assertFalse(self.client.get(path).json()["can_delete_registration"])
                self.assertEqual(self.client.delete(path).status_code,409)
                with Session(self.engine) as db: self.assertIsNotNone(db.get(Device,identifier))

    def test_unknown_type_never_reaches_mqtt_provisioner_or_activation(self):
        with Session(self.engine) as db:
            device=Device(device_code="vison-legacy",model="Edge Vision",device_type=None)
            db.add(device);db.commit();db.refresh(device);identifier=device.id
        with patch("app.api.routes.devices.provision_device") as broker:
            self.assertEqual(self.client.post(f"/api/devices/{identifier}/provision").status_code,409)
            broker.assert_not_called()
        with Session(self.engine) as db:
            device=db.get(Device,identifier);device.lifecycle_state="PROVISIONED";db.add(device);db.commit()
        self.assertEqual(self.client.post(f"/api/devices/{identifier}/activate").status_code,409)

    def test_provisioning_and_draft_deletion_serialize_on_the_device(self):
        from concurrent.futures import ThreadPoolExecutor
        import threading
        response=self.register()
        self.assertEqual(response.status_code,201,response.text)
        identifier=response.json()["device"]["id"]
        entered=threading.Event();release=threading.Event()
        def broker(*args,**kwargs):
            entered.set();release.wait(timeout=10)
            return {"username":"draft-device","password":"test-only"}
        with patch("app.api.routes.devices.provision_device",side_effect=broker),ThreadPoolExecutor(max_workers=2) as pool:
            provisioning=pool.submit(self.client.post,f"/api/devices/{identifier}/provision")
            self.assertTrue(entered.wait(timeout=5))
            deleting=pool.submit(self.client.delete,f"/api/devices/{identifier}")
            release.set()
            self.assertEqual(provisioning.result(timeout=10).status_code,200)
            self.assertEqual(deleting.result(timeout=10).status_code,409)

    def test_deleted_draft_cannot_leave_new_mqtt_credentials(self):
        from concurrent.futures import ThreadPoolExecutor
        import threading
        from app.services.device_registration import deletion_block_reason
        response=self.register()
        self.assertEqual(response.status_code,201,response.text)
        identifier=response.json()["device"]["id"]
        entered=threading.Event();release=threading.Event()
        def guard(*args):
            entered.set();release.wait(timeout=10)
            return deletion_block_reason(*args)
        with patch("app.api.routes.devices.deletion_block_reason",side_effect=guard), patch("app.api.routes.devices.provision_device") as broker, ThreadPoolExecutor(max_workers=2) as pool:
            deleting=pool.submit(self.client.delete,f"/api/devices/{identifier}")
            self.assertTrue(entered.wait(timeout=5))
            provisioning=pool.submit(self.client.post,f"/api/devices/{identifier}/provision")
            release.set()
            self.assertEqual(deleting.result(timeout=10).status_code,204)
            self.assertEqual(provisioning.result(timeout=10).status_code,404)
            broker.assert_not_called()

    def test_employee_cannot_change_lifecycle_mqtt_or_hardware(self):
        for person in ("operator", "driver"):
            for action in ("provision", "activate", "maintenance", "decommission"):
                response = self.client.post(f"/api/devices/{self.target}/{action}", headers=self.auth(person))
                self.assertEqual(response.status_code, 403, (person, action, response.text))
            for path, body in (("hardware", {"hardware_version":"rev2"}), ("status", {"status":"OFFLINE"})):
                self.assertEqual(self.client.patch(f"/api/devices/{self.target}/{path}", json=body, headers=self.auth(person)).status_code, 403)
        self.assertEqual(self.client.patch(f"/api/devices/{self.target}/hardware", json={"hardware_version":"rev2"}).status_code, 200)

    def test_customer_read_is_private_idempotent_and_does_not_touch_commands(self):
        path = f"/api/alerts/{self.alert}/acknowledge"
        for _ in range(2):
            result = self.client.post(path, headers=self.auth("driver"))
            self.assertEqual(result.status_code, 200, result.text)
            self.assertTrue(result.json()["acknowledged"])
        for person, seen in (("driver", True), ("operator", False), ("other", False), ("admin", False)):
            row = self.client.get("/api/alerts", headers=self.auth(person)).json()[0]
            self.assertEqual(row["acknowledged"], seen)
            self.assertEqual(row["status"], "ACKNOWLEDGED" if seen else "NEW")
        with Session(self.engine) as db:
            self.assertEqual(db.get(Alert, self.alert).status, "NEW")
            self.assertEqual(len(db.exec(select(AlertRead)).all()), 1)
            self.assertEqual(len(db.exec(select(AuditLog).where(AuditLog.action == "ACKNOWLEDGE_ALERT")).all()), 1)
            self.assertEqual(len(db.exec(select(Command)).all()), 0)
            assignment = db.exec(select(UserDevice).where(UserDevice.user_id == self.people["other"], UserDevice.device_id == self.source)).one()
            db.delete(assignment); db.commit()
        self.assertEqual(self.client.post(path, headers=self.auth("other")).status_code, 404)
        self.assertEqual(len(self.client.get("/api/alerts?status=ACKNOWLEDGED", headers=self.auth("driver")).json()), 1)
        self.assertEqual(self.client.get("/api/alerts?status=ACKNOWLEDGED", headers=self.auth("operator")).json(), [])

    def test_camera_statistics_link_actuator_commands_and_enforce_target_access(self):
        with Session(self.engine) as db:
            for index, (target, status, ack, duration) in enumerate(((self.target,"ACKNOWLEDGED","COMPLETED",1000),
                    (self.target,"FAILED","FAILED",None), (self.hidden,"ACKNOWLEDGED","COMPLETED",9000))):
                db.add(Command(device_id=target, alert_id=self.alert, command_type_id=self.kind,
                    status=status, ack_status=ack, created_at=self.now-timedelta(seconds=10),
                    completed_ack_at=self.now-timedelta(seconds=10)+timedelta(milliseconds=duration) if duration else None,
                    request_id="sample-"+str(index)))
            db.commit()
        path = f"/api/devices/{self.source}/metrics"
        result = self.client.get(path, headers=self.auth("operator"))
        self.assertEqual(result.status_code, 200, result.text)
        data = result.json()
        self.assertEqual(data["commands"]["count"], 2)
        self.assertEqual((data["commands"]["completed"],data["commands"]["failed"],data["commands"]["pending"]), (1,1,0))
        self.assertEqual(data["commands"]["manual"], 0)
        self.assertIsNone(data["latency"]["http_avg_ms"])
        self.assertEqual(data["latency"]["completed_avg_ms"], 1000)
        self.assertEqual(self.client.get(path).json()["commands"]["count"], 3)
        items = self.client.get(f"/api/devices/{self.source}/history", headers=self.auth("operator")).json()["items"]
        self.assertEqual(len(items), 2)
        self.assertTrue(all(item["source"] == "AI" and item["device_id"] == self.target for item in items))

    def test_resolved_and_closed_alerts_can_be_read_without_reopening_the_episode(self):
        for state in ("RESOLVED", "CLOSED"):
            with Session(self.engine) as db:
                row = Alert(device_id=self.source,alert_type="MONITORING_FAULT",status=state)
                db.add(row);db.commit();db.refresh(row);identifier=row.id
            for _ in range(2):
                response = self.client.post(f"/api/alerts/{identifier}/acknowledge",headers=self.auth("driver"))
                self.assertEqual(response.status_code,200,response.text)
                self.assertEqual(response.json()["system_status"],state)
                self.assertEqual(response.json()["status"],state)
                self.assertTrue(response.json()["acknowledged"])
            with Session(self.engine) as db:
                self.assertEqual(db.get(Alert,identifier).status,state)
                self.assertIsNone(db.get(AlertRead,(identifier,self.people["operator"])))
        self.assertEqual(self.client.get("/api/commands",headers=self.auth("driver")).json(),[])

    def test_commands_filtered_by_alert_preserve_source_and_target_access(self):
        with Session(self.engine) as db:
            other = Alert(device_id=self.source,alert_type="DROWSINESS")
            hidden = Alert(device_id=self.hidden,alert_type="DROWSINESS")
            db.add_all([other,hidden]);db.flush()
            other_id, hidden_id = other.id, hidden.id
            for index,(target,alert) in enumerate(((self.target,self.alert),(self.target,other_id),
                                                 (self.hidden,self.alert),(self.target,hidden_id))):
                db.add(Command(device_id=target,alert_id=alert,command_type_id=self.kind,request_id=f"linked-{index}"))
            db.commit()
        for query in (f"alert_id={self.alert}",f"device_id={self.target}&alert_id={self.alert}"):
            response = self.client.get("/api/commands?"+query,headers=self.auth("driver"))
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual([row["request_id"] for row in response.json()],["linked-0"])
        self.assertEqual(self.client.get(f"/api/commands?alert_id={hidden_id}",headers=self.auth("driver")).status_code,404)
        self.assertEqual(len(self.client.get(f"/api/commands?alert_id={self.alert}").json()),2)

    def test_full_window_chart_retains_extrema_nulls_and_timeline_gaps(self):
        start = self.now-timedelta(hours=20)
        with Session(self.engine) as db:
            for index in range(360):
                absent = 100 <= index <= 110
                db.add(Telemetry(device_id=self.source, recorded_at=start+timedelta(seconds=index*200),
                    ear=None if absent else .05 if index == 180 else .3,
                    perclos=None if absent else .9 if index == 180 else .1,
                    face_detected=not absent, driver_state="DROWSY" if index == 180 else "ATTENTIVE",
                    model_version="test-v2", ai_signals={"schema_version":"eye-mouth-v1", "mouth_available":True,
                        "mouth_state":"NORMAL", "mar": .7 if index == 180 else .02}))
            db.commit()
        path = f"/api/{self.source}/telemetry/history?chart=true"
        response = self.client.get(path, headers=self.auth("driver"))
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["total_samples"], 360)
        self.assertLessEqual(len(data["chart_points"]), 200)
        self.assertEqual(data["chart_mode"], "BUCKETED")
        self.assertEqual(min(row["ear_min"] for row in data["chart_points"] if row["ear_min"] is not None), .05)
        self.assertEqual(max(row["mar_max"] for row in data["chart_points"] if row["mar_max"] is not None), .7)
        self.assertTrue(any(row["ear"] is None for row in data["chart_points"]))
        self.assertEqual(data["chart_points"][0]["recorded_at"], start.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"))
        self.assertTrue(all(row["start"] == row["end"] for row in data["timeline_segments"]))
        # Legacy consumers still receive the most recent 100 raw samples.
        legacy = self.client.get(f"/api/{self.source}/telemetry/history").json()
        self.assertEqual(legacy["total_samples"], 100)
        self.assertIsNone(legacy["chart_points"])

    def test_migration_is_repeatable_and_preserves_existing_alerts(self):
        self.apply_migration(); self.apply_migration()
        with Session(self.engine) as db:
            self.assertEqual(db.get(Alert, self.alert).status, "NEW")
            self.assertEqual(len(db.exec(select(User)).all()), 4)

    def test_unsent_cancellations_are_separate_from_actual_device_failures(self):
        from app.services.command_result import cancellation_status
        cancelled = {"status":"FAILED", "dispatch_state":"CANCELLED", "error":"Risk episode no longer actionable"}
        completed = {"status":"COMPLETED", "dispatch_state":"PUBLISHED", "publish_started_at":self.now.isoformat()}
        device_failure = {"status":"FAILED", "dispatch_state":"PUBLISHED", "error":"COMMAND_EXPIRED"}
        cases = [({"led":cancelled,"buzzer":cancelled}, "CANCELLED"),
                 ({"led":completed,"buzzer":cancelled}, "PARTIALLY_CANCELLED"),
                 ({"led":device_failure,"buzzer":cancelled}, None),
                 ({"led":{**device_failure,"error":"Risk episode no longer actionable"}}, None)]
        with Session(self.engine) as db:
            for index, (children, expected) in enumerate(cases):
                row = Command(device_id=self.target, alert_id=self.alert, command_type_id=self.kind,
                    status="FAILED", ack_status="FAILED", created_at=self.now, request_id=f"cancel-{index}",
                    dispatches=children, error_message="Risk episode no longer actionable")
                self.assertEqual(cancellation_status(row), expected)
                db.add(row)
            db.commit()
        data = self.client.get(f"/api/devices/{self.source}/metrics", headers=self.auth("operator")).json()["commands"]
        self.assertEqual((data["count"],data["failed"],data["cancelled"],data["partially_cancelled"],data["pending"]), (4,2,1,1,0))
        rows = self.client.get(f"/api/devices/{self.source}/history", headers=self.auth("operator")).json()["items"]
        for row in rows:
            index = int(row["request_id"].split("-")[-1])
            self.assertEqual(row["cancellation_status"], cases[index][1])
            self.assertEqual(row["status"], "FAILED")

    def test_small_chart_keeps_raw_measurements_and_merges_only_continuous_states(self):
        with Session(self.engine) as db:
            for index, seconds in enumerate((0, 1, 2, 20, 21)):
                db.add(Telemetry(device_id=self.source, recorded_at=self.now-timedelta(minutes=1)+timedelta(seconds=seconds),
                    ear=.3, perclos=0, face_detected=index != 4, driver_state="ATTENTIVE" if index < 2 or index == 4 else "DROWSY"))
            db.commit()
        response = self.client.get(f"/api/{self.source}/telemetry/history?chart=true").json()
        self.assertEqual(response["chart_mode"], "RAW")
        self.assertEqual(len(response["chart_points"]), 5)
        self.assertEqual(len(response["timeline_segments"]), 4)
        self.assertEqual(response["timeline_segments"][0]["samples"], 2)
        self.assertEqual(response["timeline_segments"][-1]["driver_state"], "UNKNOWN")
        self.assertIsNone(response["chart_points"][-1]["ear"])

    def test_legacy_read_is_recovered_for_the_audited_actor_only(self):
        with Session(self.engine) as db:
            alert = db.get(Alert, self.alert); alert.status = "ACKNOWLEDGED"; db.add(alert)
            db.add(AuditLog(user_id=self.people["operator"], action="ACKNOWLEDGE_ALERT",
                entity_type="Alert", entity_id=str(self.alert), created_at=self.now))
            db.commit()
        self.apply_migration(); self.apply_migration()
        for person, seen in (("operator", True), ("driver", False), ("admin", False)):
            result = self.client.get("/api/alerts", headers=self.auth(person)).json()[0]
            self.assertEqual(result["acknowledged"], seen)
