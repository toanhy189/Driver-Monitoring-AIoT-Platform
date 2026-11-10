"""New policy paths on disposable PostgreSQL/MQTT; virtual ESP32, synthetic MP4."""
from datetime import datetime, timedelta, timezone
import json
import os
import queue
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

from sqlmodel import Session, select

import test_week3_integration as previous
from app.core.db import engine
from app.models.ai_event import AiEvent, RuleRuntime
from app.models.alert import Alert
from app.models.command import Command
from app.models.device import Device
from app.services.background_tasks import run_once


NAMES = ("test_versioned_escalation_repeat_and_ack", "test_backfill_recovery_session_and_video_link",
         "test_actual_edge_outbox_reconnect_and_schema_quarantine", "test_eye_mouth_telemetry_roundtrip",
         "test_head_motion_storage_and_existing_actuator_protocol")


@unittest.skipUnless(os.getenv("W4_LIVE") == "1", "Use run_week4_isolated.py for disposable services")
class Week4Live(previous.Week3Integration):
    def test_head_motion_storage_and_existing_actuator_protocol(self):
        self.prepare_policy()
        motion = dict(version="head-motion-v1", mode="OBSERVE_ONLY", available=True, calibrated=True,
            state="LOWERED", pitch_deg=15., yaw_deg=0., roll_deg=0., nod_count=0,
            repeated_nods=False, eye_closure_supported=False)
        signals = dict(schema_version="eye-mouth-v2", quality_version="region-technical-quality-v1",
            eyes_available=False, mouth_available=False, ear_available=True, calibration_id="a"*64,
            eye_quality="VALID", mouth_quality="NO_CROP", decision_reason="HEAD_DOWN_RISK",
            eye_closure_state="UNAVAILABLE", head_motion=motion,
            head_down_policy=dict(version="sustained-head-down-v1",state="DOWN_RISK",risk_candidate=True,
                observed_down_seconds=3.5,enter_pitch_deg=12.,min_seconds=3.),
            head_eye_fusion=dict(version="pose-calibrated-head-eye-v1",mode="ENABLED",state="CLOSED_RISK",
                ear_threshold=.28,risk_candidate=True,profile_sha256="b"*64))
        message_id = str(uuid.uuid4())
        self.vision.publish(f"driver/{self.source_code}/telemetry", dict(message_id=message_id,
            device_code=self.source_code, timestamp=datetime.now(timezone.utc).isoformat(),
            driver_state="UNKNOWN", face_detected=True, model_version="eye-mouth-head-observation-test",
            ai_signals=signals, _delivery={"mode": "live"}))
        deadline = time.monotonic()+8
        while time.monotonic() < deadline:
            _, raw, _ = self.vision.messages.get(timeout=8)
            ack = json.loads(raw)
            if ack.get("message_id") == message_id:
                self.assertEqual(ack["status"], "SAVED")
                break
        else:
            self.fail("No head-motion storage acknowledgement")
        from app.models.telemetry import Telemetry
        with Session(engine) as session:
            saved = session.exec(select(Telemetry).where(Telemetry.device_id == self.source_id)).one()
            self.assertEqual(saved.ai_signals["head_motion"], motion)
        snapshot = self.client.get(f"/api/{self.source_id}/telemetry", headers=self.auth)
        self.assertEqual(snapshot.status_code, 200, snapshot.text)
        self.assertEqual(snapshot.json()["ai_signals"]["head_motion"], motion)
        self.assertEqual(snapshot.json()["ai_signals"]["head_eye_fusion"], signals["head_eye_fusion"])
        self.assertEqual(snapshot.json()["ai_signals"]["head_down_policy"], signals["head_down_policy"])
        history = self.client.get(f"/api/{self.source_id}/telemetry/history", headers=self.auth)
        self.assertEqual(history.status_code, 200, history.text)
        self.assertEqual(history.json()["items"][-1]["ai_signals"]["head_motion"], motion)
        self.assertEqual(self.all_commands(), [])
        with self.assertRaises(queue.Empty): self.esp.messages.get(timeout=.2)
        self.assertEqual(self.send(self.message(level=2, state_duration_ms=6000)), "QUEUED")
        self.dispatch_and_complete(["LED_ON", "BUZZER_ON", "MOTOR_ON"])

    def test_eye_mouth_telemetry_roundtrip(self):
        self.prepare_policy()
        message_id=str(uuid.uuid4())
        signals={"schema_version":"eye-mouth-v1","mar":.42,"mouth_state":"TALKING_LAUGHING",
            "yawn_probability":.08,"eye_state":"NORMAL","eye_sleepy_probability":.1,
            "eyes_available":True,"mouth_available":True,"experimental":True}
        model_version="eye-mouth-integration-test"
        driver_state="ATTENTIVE"
        face_detected=True
        if os.getenv("W4_AI_SIGNALS_SAMPLE"):
            recordings=json.loads(Path(os.environ["W4_AI_SIGNALS_SAMPLE"]).read_text(encoding="utf-8"))["recordings"]
            recording=next(row for row in recordings if row["last_signals"]["mouth_available"])
            signals=recording["last_signals"]
            model_version=recording["model_version"]
            driver_state=recording["last_candidate"]
            face_detected=recording["last_face_detected"]
        body={"message_id":message_id,"device_code":self.source_code,"timestamp":datetime.now(timezone.utc).isoformat(),
            "driver_state":driver_state,"face_detected":face_detected,"model_version":model_version,
            "ai_signals":signals,"_delivery":{"mode":"live"}}
        self.vision.publish(f"driver/{self.source_code}/telemetry",body)
        while True:
            _,raw,_=self.vision.messages.get(timeout=8)
            ack=json.loads(raw)
            if ack.get("message_id")==message_id:
                self.assertEqual(ack["status"],"SAVED");break
        snapshot=self.client.get(f"/api/{self.source_id}/telemetry",headers=self.auth)
        self.assertEqual(snapshot.status_code,200,snapshot.text)
        self.assertEqual(snapshot.json()["ai_signals"]["mouth_state"],signals["mouth_state"])
        self.assertEqual(snapshot.json()["driver_state"],driver_state)
        self.assertEqual(snapshot.json()["model_version"],model_version)
        history=self.client.get(f"/api/{self.source_id}/telemetry/history",headers=self.auth)
        self.assertEqual(history.status_code,200,history.text)
        self.assertEqual(history.json()["items"][-1]["ai_signals"]["mar"],signals["mar"])
        self.assertEqual(self.all_commands(),[])

    def prepare_policy(self):
        self.vision, self.vision_credentials = self.provision_source()
        self.esp, _ = self.provision()
        self.vision.subscribe(f"driver/{self.source_code}/storage_ack")
        self.esp.subscribe(f"driver/{self.target_code}/command")
        self.vision.publish(f"driver/{self.source_code}/status", {"status":"ONLINE", "device_code":self.source_code})
        self.esp.publish(f"driver/{self.target_code}/status", {"status":"ONLINE", "device_code":self.target_code})
        def online():
            with Session(engine) as session:
                return session.get(Device, self.source_id).status == "ONLINE"
        previous.wait_for(online)
        response = self.client.put(f"/api/devices/{self.source_id}/rule", headers=self.auth,
            json={"target_device_id":self.target_id, "enabled":True,
                  "policy":{"policy_version":"driver-bench-20261107-v1"}})
        self.assertEqual(response.status_code, 200, response.text)
        self.session_id = str(uuid.uuid4())
        self.started = (datetime.now(timezone.utc)-timedelta(seconds=20)).isoformat()
        self.episode = str(uuid.uuid4())
        self.clip = str(uuid.uuid4())
        self.sequence = 0

    def message(self, kind="DROWSY_THRESHOLD_REACHED", **fields):
        self.sequence += 1
        now = datetime.now(timezone.utc).isoformat()
        return {"message_id":str(uuid.uuid4()), "device_code":self.source_code,
            "timestamp":now, "observed_at":now, "model_version":"virtual-sensor-policy-test",
            "policy_version":"driver-bench-20261107-v1", "session_id":self.session_id,
            "session_started_at":self.started, "episode_id":self.episode,
            "episode_start_event_id":self.clip, "clip_message_id":self.clip,
            "sequence_number":self.sequence, "event_type":kind, "state":"DROWSY",
            "level":1, "state_duration_ms":3000, "_delivery":{"mode":"live"}, **fields}

    def send(self, payload):
        self.vision.publish(f"driver/{self.source_code}/events", payload)
        deadline = time.monotonic()+8
        while time.monotonic() < deadline:
            topic, body, _ = self.vision.messages.get(timeout=8)
            acknowledgement = json.loads(body)
            if acknowledgement.get("message_id") == payload["message_id"]:
                self.assertEqual(acknowledgement["status"], "SAVED", acknowledgement)
                break
        else:
            self.fail("No storage acknowledgement")
        with Session(engine) as session:
            return session.exec(select(AiEvent).where(AiEvent.event_id == payload["message_id"])).one().outcome

    def all_commands(self):
        with Session(engine) as session:
            return session.exec(select(Command).where(Command.device_id == self.target_id).order_by(Command.id)).all()

    def dispatch_and_complete(self, expected):
        run_once()
        received = []
        for _ in expected:
            _, raw, retained = self.esp.messages.get(timeout=8)
            command = json.loads(raw)
            self.assertFalse(retained)
            self.assertGreater(command["expires_at_ms"], 0)
            received.append(command["command"])
            self.esp.publish(f"driver/{self.target_code}/ack",
                {"request_id":command["request_id"], "status":"COMPLETED"})
        self.assertEqual(set(received), set(expected))
        latest = self.all_commands()[-1]
        previous.wait_for(lambda: self.get_command(latest.request_id).get("ack_status") == "COMPLETED")

    def test_versioned_escalation_repeat_and_ack(self):
        self.prepare_policy()
        first = self.message()
        self.assertEqual(self.send(first), "QUEUED")
        self.dispatch_and_complete(["LED_ON", "BUZZER_ON"])
        first["_delivery"] = {"mode":"backfill"}
        self.send(first)
        self.assertEqual(len(self.all_commands()), 1)
        for level, milliseconds in ((2,6000), (3,10000)):
            self.assertEqual(self.send(self.message(level=level, state_duration_ms=milliseconds)), "QUEUED")
            self.dispatch_and_complete(["LED_ON", "BUZZER_ON", "MOTOR_ON"])
        self.assertEqual(self.send(self.message(level=3, state_duration_ms=11000, repeat=True)), "REPEAT_TOO_EARLY")
        time.sleep(5.2)
        self.assertEqual(self.send(self.message(level=3, state_duration_ms=16000, repeat=True)), "QUEUED")
        self.dispatch_and_complete(["LED_ON", "BUZZER_ON", "MOTOR_ON"])
        with Session(engine) as session:
            alerts = session.exec(select(Alert).where(Alert.device_id == self.source_id)).all()
            self.assertEqual(len(alerts), 1)
        self.assertEqual(len(self.all_commands()), 4)

    def test_backfill_recovery_session_and_video_link(self):
        self.prepare_policy()
        video = b"\x00\x00\x00\x18ftypmp42"+b"\x00"*64
        uploaded = self.client.post("/api/videos/upload", auth=(self.vision_credentials["mqtt_username"],
            self.vision_credentials["mqtt_password"]), files={"file":("synthetic.mp4", video, "video/mp4")},
            data={"device_code":self.source_code, "state":"DROWSY", "message_id":self.clip})
        self.assertEqual(uploaded.status_code, 201, uploaded.text)
        self.assertFalse(uploaded.json()["event_received"])
        self.send(self.message("STATE_CHANGED", message_id=self.clip))
        threshold = self.message(_delivery={"mode":"backfill"})
        self.assertEqual(self.send(threshold), "BACKFILL_RECORDED")
        linked = self.client.get(f"/api/devices/{self.source_id}/events/{threshold['message_id']}/video", headers=self.auth)
        self.assertEqual(linked.status_code, 200, linked.text)
        self.assertEqual(linked.json()["status"], "AVAILABLE")
        self.assertEqual(linked.json()["video"]["video_id"], uploaded.json()["video_id"])
        self.assertEqual(self.all_commands(), [])
        self.assertEqual(self.send(self.message()), "QUEUED")
        self.send(self.message("STATE_CHANGED", state="ATTENTIVE"))
        self.assertEqual(self.all_commands()[0].status, "FAILED")
        run_once()
        with self.assertRaises(queue.Empty):
            self.esp.messages.get(timeout=.2)
        old_session, old_started = self.session_id, self.started
        self.session_id = str(uuid.uuid4())
        self.started = datetime.now(timezone.utc).isoformat()
        self.send(self.message("STATE_CHANGED", state="ATTENTIVE", episode_id=None))
        self.assertEqual(self.send(self.message("SESSION_ENDED", session_id=old_session,
            session_started_at=old_started, final_state="DROWSY")), "OLD_SESSION")
        old = (datetime.now(timezone.utc)-timedelta(seconds=6)).isoformat()
        self.assertEqual(self.send(self.message(timestamp=old, observed_at=old)), "STALE_RECORDED")
        with Session(engine) as session:
            runtime = session.get(RuleRuntime, self.source_id)
            self.assertEqual(runtime.state["session_id"], self.session_id)
            self.assertFalse(runtime.state["ended"])

    def test_actual_edge_outbox_reconnect_and_schema_quarantine(self):
        self.prepare_policy()
        payloads = [self.message(model_version="actual-outbox-test"),
                    self.message(model_version="actual-outbox-test"),
                    self.message(model_version="actual-outbox-test"),
                    self.message("STATE_CHANGED", model_version="actual-outbox-test")]
        for payload in payloads:
            payload.pop("_delivery")
        payloads[2].pop("session_id")  # Permanent schema error, not a global outage.
        child = r'''
import json, os, sys, time
from datetime import datetime, timezone
sys.path.insert(0, "edge-ai")
from edge_queue import init_db, get_connection, add_to_queue
from mqtt_client import MQTTClient
from config import EVENT_TOPIC
from service.message.publisher import send_message
assert init_db()
messages = json.loads(os.environ["W4_TEST_MESSAGES"])
def wait(check):
    until = time.monotonic()+12
    while time.monotonic() < until:
        if check(): return
        time.sleep(.02)
    raise AssertionError("Outbox condition timed out")
def count_pending():
    with get_connection() as db:
        return db.execute("SELECT COUNT(*) FROM offline_queue WHERE status='PENDING'").fetchone()[0]
def refresh(message):
    message["timestamp"] = message["observed_at"] = datetime.now(timezone.utc).isoformat()
    return message
client = MQTTClient(model_version="actual-outbox-test")
try:
    wait(lambda: client.connected)
    send_message(client, EVENT_TOPIC, refresh(messages[0]))
    wait(lambda: count_pending() == 0)
    client.client.disconnect()
    wait(lambda: not client.connected)
    client.client.loop_stop()
    send_message(client, EVENT_TOPIC, refresh(messages[1]))
    with get_connection() as db:
        before = db.execute("SELECT payload,backfill FROM offline_queue WHERE message_id=?",(messages[1]["message_id"],)).fetchone()
    assert before[1] == 1
    client.client.reconnect()
    client.client.loop_start()
    wait(lambda: client.connected)
    wait(lambda: count_pending() == 0)
    client.connected = False
    bad = refresh(messages[2])
    assert add_to_queue(bad["message_id"], EVENT_TOPIC, json.dumps(bad), backfill=False)
    with get_connection() as db:
        db.execute("UPDATE offline_queue SET retry_count=7 WHERE message_id=?",(bad["message_id"],))
    client.connected = True
    client.notify_queue()
    def quarantined():
        with get_connection() as db:
            row = db.execute("SELECT status FROM offline_queue WHERE message_id=?",(bad["message_id"],)).fetchone()
            return row and row[0] == "DEAD"
    wait(quarantined)
    send_message(client, EVENT_TOPIC, refresh(messages[3]))
    wait(lambda: count_pending() == 0)
    with get_connection() as db:
        assert db.execute("SELECT COUNT(*) FROM offline_queue WHERE status='DEAD'").fetchone()[0] == 1
    print("ACTUAL_EDGE_OUTBOX_OK")
finally:
    client.close()
'''
        root = Path(__file__).resolve().parents[2]
        executable = root/"edge-ai/.venv/Scripts/python.exe"
        with tempfile.TemporaryDirectory(prefix="w4-outbox-") as folder:
            assert Path(folder).resolve().is_relative_to(Path(tempfile.gettempdir()).resolve())
            env = {**os.environ, "AI_MQTT_HOST":previous.settings.MQTT_HOST,
                "AI_MQTT_PORT":str(previous.settings.MQTT_PORT), "AI_DEVICE_CODE":self.source_code,
                "AI_MQTT_USERNAME":self.vision_credentials["mqtt_username"],
                "AI_MQTT_PASSWORD":self.vision_credentials["mqtt_password"],
                "AI_QUEUE_DB":str(Path(folder)/"queue.db"), "W4_TEST_MESSAGES":json.dumps(payloads),
                "AI_EVENT_AUDIT_PATH":str(Path(folder)/"events.jsonl")}
            result = subprocess.run([str(executable) if executable.exists() else sys.executable, "-X", "utf8", "-c", child],
                cwd=root, env=env, capture_output=True, text=True, encoding="utf-8", timeout=65)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            self.assertIn("ACTUAL_EDGE_OUTBOX_OK", result.stdout)
        with Session(engine) as session:
            saved = {event.event_id:event for event in session.exec(select(AiEvent).where(AiEvent.device_id == self.source_id)).all()}
            self.assertEqual(saved[payloads[0]["message_id"]].outcome, "QUEUED")
            self.assertEqual(saved[payloads[1]["message_id"]].outcome, "BACKFILL_RECORDED")
            self.assertNotIn(payloads[2]["message_id"], saved)
        self.assertEqual(len(self.all_commands()), 1)


def load_tests(loader, tests, pattern):
    # Only new cases; inherited week-3 cases keep their existing evidence.
    return unittest.TestSuite(Week4Live(name) for name in NAMES)


if __name__ == "__main__":
    unittest.main()
