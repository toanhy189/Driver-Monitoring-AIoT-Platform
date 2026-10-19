"""Evidence uses real PostgreSQL and MQTT, with virtual ESP32 clients."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import secrets
import socket
import subprocess
import sys
import threading
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from sqlmodel import Session, select
import httpx
import paho.mqtt.client as mqtt
from websockets.sync.client import connect as ws_connect

from app.core.config import settings
from app.core.db import engine
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.models.ai_event import AiEvent, RuleBinding
from app.models.alert import Alert
from app.models.command import Command
from app.models.config import Config
from app.models.device import Device
from app.models.telemetry import Telemetry
from app.models.user import User
from app.models.user_device import UserDevice
from app.schemas.rules import RulePolicy
from app.services.background_tasks import expire_commands, run_once
from app.services.command_dispatch import create_command, dispatch_command
from app.services.mqtt_service import process_message
from app.services.mqtt_revoke_service import revoke_device
from app.services.websocket_manager import ConnectionManager


OBSERVATIONS = []


def record(case, detail):
    OBSERVATIONS.append({"case": case, "detail": detail})


def wait_for(callback, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = callback()
        if result:
            return result
        time.sleep(0.05)
    raise AssertionError("Condition was not met before timeout")


def timings(value=100):
    return {output: {str(level): {"on_ms": value, "off_ms": value + 100} for level in (1, 2, 3)}
            for output in ("led", "buzzer", "motor")}


class Peer:
    def __init__(self, username, password):
        self.messages = queue.Queue()
        self.connected = threading.Event()
        self.disconnected = threading.Event()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
        self.client.username_pw_set(username, password)
        def connected(client, userdata, flags, reason, properties):
            self.reason = reason
            self.connected.set()
        self.client.on_connect = connected
        self.client.on_message = lambda c, u, message: self.messages.put((message.topic, bytes(message.payload), message.retain))
        self.client.on_disconnect = lambda *args: self.disconnected.set()
        self.client.connect(settings.MQTT_HOST, settings.MQTT_PORT, 10)
        self.client.loop_start()
        if not self.connected.wait(5):
            raise AssertionError("MQTT connect timed out")

    def subscribe(self, topic):
        ready = threading.Event()
        self.client.on_subscribe = lambda *args: ready.set()
        self.client.subscribe(topic, 1)
        assert ready.wait(5)

    def publish(self, topic, payload, retain=False):
        result = self.client.publish(topic, json.dumps(payload) if isinstance(payload, dict) else payload,
                                     qos=1, retain=retain)
        result.wait_for_publish(5)

    def close(self):
        self.client.disconnect()
        self.client.loop_stop()


@unittest.skipUnless(os.getenv("W3_INTEGRATION") == "1", "Use run_week3_integration.py for isolated live checks")
class Week3Integration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not engine.url.database.startswith("codex_w3_"):
            raise RuntimeError("Live tests require a disposable codex_w3_ database")
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def setUp(self):
        self.suffix = secrets.token_hex(5)
        self.peers = []
        self.provisioned = []
        self.source_code = "vision-w3-" + self.suffix
        self.target_code = "alert-w3-" + self.suffix
        with Session(engine) as session:
            self.user = User(fullname="Week 3 Test", username="w3-" + self.suffix,
                hash_password=get_password_hash("temporary-test-only"), email=self.suffix + "@example.test",
                phone=self.suffix, role="Admin")
            session.add(self.user)
            session.flush()
            source = Device(device_code=self.source_code, model="Camera", device_type="VISION_NODE", lifecycle_state="ACTIVE")
            target = Device(device_code=self.target_code, model="Alert", device_type="ALERT_NODE", lifecycle_state="REGISTERED",
                            status="ONLINE", last_seen=datetime.now(timezone.utc).replace(tzinfo=None))
            session.add(source); session.add(target); session.flush()
            self.source_id, self.target_id, self.user_id = source.id, target.id, self.user.id
            for device in (source, target):
                session.add(UserDevice(user_id=self.user_id, device_id=device.id))
            session.commit()
        self.auth = {"Authorization": "Bearer " + create_access_token(self.user_id, timedelta(minutes=10))}

    def tearDown(self):
        for peer in self.peers:
            peer.close()
        for code in self.provisioned:
            backend = Peer(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)
            backend.publish(f"driver/{code}/config/update", b"", retain=True)
            backend.close()
            try:
                revoke_device(code)
            except Exception:
                pass

    def provision(self):
        result = self.client.post(f"/api/devices/{self.target_id}/provision", headers=self.auth)
        self.assertEqual(result.status_code, 200, result.text)
        self.provisioned.append(self.target_code)
        self.client.post(f"/api/devices/{self.target_id}/activate", headers=self.auth).raise_for_status()
        credentials = result.json()
        peer = Peer(credentials["mqtt_username"], credentials["mqtt_password"])
        self.peers.append(peer)
        self.assertFalse(peer.reason.is_failure)
        return peer, credentials

    def command(self, key=None):
        return self.client.post(f"/api/devices/{self.target_id}/commands",
            headers={**self.auth, **({"Idempotency-Key": key} if key else {})},
            json={"action": "TEST_ALERT", "buzzer_ms": 1000, "vibration_ms": 1000, "led_mode": "FLASH"})

    def get_command(self, request_id):
        return self.client.get(f"/api/commands/{request_id}", headers=self.auth).json()

    def event(self, event_id=None, duration=6500, timestamp=None):
        return {"event_id": event_id or "event-" + secrets.token_hex(8), "device_id": self.source_code,
            "event_type": "DROWSY_THRESHOLD_REACHED", "state": "DROWSY", "state_duration_ms": duration,
            "model_version": "w3-model-a", "timestamp": timestamp or datetime.now(timezone.utc).isoformat()}

    def binding(self, cooldown=0):
        policy = RulePolicy().model_dump()
        policy["cooldown_seconds"] = cooldown
        result = self.client.put(f"/api/devices/{self.source_id}/rule", headers=self.auth,
            json={"target_device_id": self.target_id, "enabled": True, "policy": policy})
        self.assertEqual(result.status_code, 200, result.text)

    def test_01_provision_revoke_and_api_guards(self):
        peer, credentials = self.provision()
        peer.subscribe(f"driver/{self.target_code}/command")
        peer.subscribe(f"driver/{self.target_code}/config/update")
        result = self.client.post(f"/api/devices/{self.target_id}/decommission", headers=self.auth)
        self.assertEqual(result.status_code, 200)
        self.assertTrue(peer.disconnected.wait(5))
        rejected = Peer(credentials["mqtt_username"], credentials["mqtt_password"])
        self.peers.append(rejected)
        self.assertTrue(rejected.reason.is_failure)
        self.assertEqual(self.command().status_code, 409)
        self.assertEqual(self.client.put(f"/api/devices/{self.target_id}/config", headers=self.auth,
                                       json={"timings": timings()}).status_code, 409)
        record("TV2-06", "HTTP provision 200; revoke disconnects real MQTT connection; old login rejected; command/config 409")

    def test_02_config_offline_invalid_late_and_old_ack(self):
        peer, mqtt_credentials = self.provision()
        peer.close()  # No config subscription yet: verify broker retains desired config.
        result = self.client.put(f"/api/devices/{self.target_id}/config", headers=self.auth, json={"timings": timings()})
        self.assertEqual(result.status_code, 200, result.text)
        config_id = result.json()["config_id"]
        before = self.client.get(f"/api/devices/{self.target_id}/config", headers=self.auth).json()
        self.assertIsNone(before["applied"])
        credentials = self.client.get(f"/api/devices/{self.target_id}", headers=self.auth).json()
        self.assertNotIn("mqtt_password", credentials)
        backend = Peer(mqtt_credentials["mqtt_username"], mqtt_credentials["mqtt_password"]); self.peers.append(backend)
        backend.subscribe(f"driver/{self.target_code}/config/update")
        topic, raw, retained = backend.messages.get(timeout=5)
        self.assertEqual(json.loads(raw)["config_id"], config_id)
        self.assertTrue(retained)
        malformed = self.client.put(f"/api/devices/{self.target_id}/config", headers=self.auth, json={"timings": {}})
        self.assertEqual(malformed.status_code, 422)
        for ack in ({"config_id": "cfg-wrong", "device_code": self.target_code, "status": "APPLIED"},
                    {"config_id": config_id, "device_code": "other", "status": "APPLIED"}):
            process_message(f"driver/{self.target_code}/config/applied", ack)
        rejected = {"config_id": config_id, "device_code": self.target_code, "status": "REJECTED", "error": "STORAGE_ERROR"}
        process_message(f"driver/{self.target_code}/config/applied", rejected)
        snapshot = self.client.get(f"/api/devices/{self.target_id}/config", headers=self.auth).json()
        self.assertEqual(snapshot["status"], "REJECTED"); self.assertIsNone(snapshot["applied"])
        ack = {**rejected, "status": "APPLIED", "error": None}
        process_message(f"driver/{self.target_code}/config/applied", ack)
        self.assertEqual(process_message(f"driver/{self.target_code}/config/applied", ack), [])
        second = self.client.put(f"/api/devices/{self.target_id}/config", headers=self.auth, json={"timings": timings(200)})
        self.assertEqual(second.status_code, 200)
        self.assertEqual(process_message(f"driver/{self.target_code}/config/applied", ack), [])
        snapshot = self.client.get(f"/api/devices/{self.target_id}/config", headers=self.auth).json()
        self.assertEqual(snapshot["applied_config_id"], config_id)
        self.assertNotEqual(snapshot["config_id"], config_id)
        self.assertEqual(snapshot["desired"]["revision"], 2)
        record("TV2-07/09/10", {"retained": retained, "invalid_http": 422, "old_ack_ignored": True,
            "desired_revision": 2, "applied_unchanged_until_matching_ack": True})

    def test_03_publish_failure_never_marks_applied(self):
        with patch("app.api.routes.configs.publish_config", return_value=False):
            response = self.client.put(f"/api/devices/{self.target_id}/config", headers=self.auth, json={"timings": timings()})
        self.assertEqual(response.status_code, 503)
        snapshot = self.client.get(f"/api/devices/{self.target_id}/config", headers=self.auth).json()
        self.assertEqual(snapshot["status"], "PUBLISH_FAILED"); self.assertIsNone(snapshot["applied"])
        record("TV2-08", {"http": 503, "status": snapshot["status"], "applied": None})

    def test_04_three_ack_completion_and_latency(self):
        peer, _ = self.provision(); peer.subscribe(f"driver/{self.target_code}/command")
        response = self.command(); self.assertEqual(response.status_code, 201, response.text)
        request_id = response.json()["request_id"]
        children = [json.loads(peer.messages.get(timeout=5)[1]) for _ in range(3)]
        for child in children[:2]:
            peer.publish(f"driver/{self.target_code}/ack", {"request_id": child["request_id"], "device_code": self.target_code, "status": "COMPLETED"})
        wait_for(lambda: self.get_command(request_id)["ack_status"] == "ACCEPTED")
        self.assertNotEqual(self.get_command(request_id)["ack_status"], "COMPLETED")
        peer.publish(f"driver/{self.target_code}/ack", {"request_id": children[2]["request_id"], "device_code": self.target_code, "status": "COMPLETED"})
        wait_for(lambda: self.get_command(request_id)["ack_status"] == "COMPLETED")
        result = self.get_command(request_id)
        self.assertIsNotNone(result["latency"]["http_ms"])
        self.assertTrue(all(v["mqtt_publish_ms"] is not None and v["ack_from_publish_ms"] is not None
                            for v in result["latency"]["dispatches"].values()))
        for child in children:
            self.assertEqual(process_message("driver/other/ack", {"request_id": child["request_id"], "status": "COMPLETED"}), [])
            self.assertEqual(process_message(f"driver/{self.target_code}/ack", {"request_id": child["request_id"], "status": "COMPLETED"}), [])
        record("TV2-11/12/20", {"after_two_ack": "ACCEPTED", "after_three_ack": result["ack_status"], "latency": result["latency"]})
        stats = self.client.get(f"/api/devices/{self.target_id}/metrics", headers=self.auth).json()
        self.assertEqual(stats["commands"]["count"], 1)
        self.assertIsNotNone(stats["latency"]["http_avg_ms"])

    def test_05_timeout_and_late_ack(self):
        self.provision()
        response = self.command(); self.assertEqual(response.status_code, 201, response.text)
        request_id = response.json()["request_id"]
        with Session(engine) as session:
            command = session.exec(select(Command).where(Command.request_id == request_id)).one()
            expire_commands(session, command.created_at + timedelta(seconds=31))
        self.assertEqual(self.get_command(request_id)["status"], "TIMEOUT")
        for key in ("led", "buzzer"):
            process_message(f"driver/{self.target_code}/ack", {"request_id": f"{request_id}-{key}", "status": "COMPLETED"})
            self.assertEqual(self.get_command(request_id)["status"], "TIMEOUT")
        process_message(f"driver/{self.target_code}/ack", {"request_id": f"{request_id}-motor", "status": "COMPLETED"})
        self.assertEqual(self.get_command(request_id)["ack_status"], "COMPLETED")
        record("TV2-12", "TIMEOUT persisted; two late ACKs retain TIMEOUT; all three late COMPLETED resolve it")

    def test_06_rule_chain_severity_cooldown_and_stale(self):
        self.provision(); self.binding(cooldown=30)
        invalid = self.event(); invalid["state"] = "ATTENTIVE"
        self.assertEqual(process_message("driver/events", invalid), [])
        first = self.event(duration=10500)
        process_message("driver/events", first)
        process_message("driver/events", self.event())
        with Session(engine) as session:
            event = session.exec(select(AiEvent).where(AiEvent.event_id == first["event_id"])).one()
            alert = session.exec(select(Alert).where(Alert.source_event_id == event.event_id)).one()
            command = session.exec(select(Command).where(Command.alert_id == alert.id)).one()
            self.assertEqual(alert.severity, "3")
            self.assertEqual(command.dispatches["motor"]["payload"]["intensity"], "STRONG")
            rows = session.exec(select(AiEvent).where(AiEvent.device_id == self.source_id)).all()
            self.assertEqual({r.outcome for r in rows}, {"QUEUED", "COOLDOWN_SUPPRESSED"})
            record("TV2-14/15", {"event_id": event.event_id, "alert_id": alert.id, "request_id": command.request_id,
                                 "severity": 3, "policy": "proposed defaults, not group approved"})
        self.binding(cooldown=0)
        old = self.event(timestamp=(datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat())
        process_message("driver/events", old)
        with Session(engine) as session:
            self.assertEqual(session.exec(select(AiEvent).where(AiEvent.event_id == old["event_id"])).one().outcome, "STALE_RECORDED")
        for duration, expected in ((3500, "1"), (6500, "2")):
            event = self.event(duration=duration); process_message("driver/events", event)
            with Session(engine) as session:
                self.assertEqual(session.exec(select(Alert).where(Alert.source_event_id == event["event_id"])).one().severity, expected)
        policy = RulePolicy().model_dump(); policy["cooldown_seconds"] = 0; policy["levels"]["1"]["outputs"] = ["led"]
        self.client.put(f"/api/devices/{self.source_id}/rule", headers=self.auth,
            json={"target_device_id": self.target_id, "enabled": True, "policy": policy}).raise_for_status()
        led_only = self.event(duration=3500); process_message("driver/events", led_only)
        with Session(engine) as session:
            alert = session.exec(select(Alert).where(Alert.source_event_id == led_only["event_id"])).one()
            command = session.exec(select(Command).where(Command.alert_id == alert.id)).one()
            self.assertEqual(set(command.dispatches), {"led"})

    def test_07_event_redelivery_concurrent_and_restart(self):
        self.provision(); self.binding()
        event = self.event()
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _: process_message("driver/events", event), range(2)))
        replay = subprocess.run([sys.executable, "-c", "import sys,json;sys.path.insert(0,'backend');from app.services.mqtt_service import process_message;process_message('driver/events',json.loads(sys.argv[1]))", json.dumps(event)],
            text=True, capture_output=True, timeout=15)
        self.assertEqual(replay.returncode, 0, replay.stderr)
        with Session(engine) as session:
            alerts = session.exec(select(Alert).where(Alert.source_event_id == event["event_id"])).all()
            self.assertEqual(len(alerts), 1)
            self.assertEqual(len(session.exec(select(Command).where(Command.alert_id == alerts[0].id)).all()), 1)
        record("TV2-16", "Two concurrent deliveries + replay from a new Python process -> exactly one event, alert and parent command")

    def test_08_command_idempotency_concurrent_and_conflict(self):
        self.provision()
        key = "test-key-" + self.suffix
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: self.command(key), range(2)))
        self.assertEqual([r.status_code for r in responses], [201, 201])
        self.assertEqual(responses[0].json()["request_id"], responses[1].json()["request_id"])
        conflict = self.client.post(f"/api/devices/{self.target_id}/commands", headers={**self.auth, "Idempotency-Key": key},
            json={"action": "TEST_ALERT", "buzzer_ms": 2000, "vibration_ms": 1000, "led_mode": "FLASH"})
        self.assertEqual(conflict.status_code, 409)
        with Session(engine) as session:
            self.assertEqual(len(session.exec(select(Command).where(Command.idempotency_key == key)).all()), 1)
        record("TV2-17", {"same_key_same_body": "one request_id", "different_body": 409})

    def test_09_history_filters_permissions_and_metrics(self):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with Session(engine) as session:
            for index in range(4):
                session.add(Telemetry(device_id=self.source_id, recorded_at=now - timedelta(minutes=index + 1),
                    ear=0.2, perclos=0.3, driver_state="DROWSY", model_version="model-a" if index < 2 else "model-b"))
            stranger = User(username="other-" + self.suffix, fullname="Other", hash_password="unused",
                            email="other-" + self.suffix + "@example.test", phone="other-" + self.suffix, role="Customer")
            session.add(stranger); session.commit(); stranger_id = stranger.id
        path = f"/api/devices/{self.source_id}"
        result = self.client.get(path + "/telemetry/history?model_version=model-a&limit=1", headers=self.auth)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertTrue(result.json()["has_more"])
        self.assertEqual(result.json()["items"][0]["model_version"], "model-a")
        self.assertTrue(result.json()["items"][0]["recorded_at"].endswith("Z"))
        legacy_path = f"/api/{self.source_id}/telemetry/history"
        legacy = self.client.get(legacy_path, params={
            "from_time": (now - timedelta(minutes=3)).replace(tzinfo=timezone.utc)
                .astimezone(timezone(timedelta(hours=7))).isoformat(),
            "to_time": now.replace(tzinfo=timezone.utc).isoformat(), "limit": 100,
        }, headers=self.auth)
        self.assertEqual(legacy.status_code, 200, legacy.text)
        self.assertEqual(legacy.json()["total_samples"], 3)
        self.assertEqual(legacy.json()["device_code"], self.source_code)
        self.assertEqual(legacy.json()["items"], sorted(legacy.json()["items"], key=lambda row: row["recorded_at"]))
        self.assertEqual(self.client.get(legacy_path + "?from_time=2026-10-01T00:00:00", headers=self.auth).status_code, 422)
        self.assertEqual(self.client.get(legacy_path, headers={"Authorization": "Bearer " +
            create_access_token(stranger_id, timedelta(minutes=5))}).status_code, 404)
        stats = self.client.get(path + "/metrics?model_version=model-a", headers=self.auth)
        self.assertEqual(stats.status_code, 200, stats.text)
        self.assertEqual(stats.json()["telemetry"]["count"], 2)
        self.assertAlmostEqual(stats.json()["telemetry"]["avg_ear"], 0.2)
        event_a, event_b = self.event(), self.event()
        event_a["model_version"], event_b["model_version"] = "model-a", "model-b"
        process_message("driver/events", event_a); process_message("driver/events", event_b)
        filtered = self.client.get(path + "/timeline?model_version=model-a", headers=self.auth).json()
        self.assertEqual({item["event_id"] for item in filtered["items"]}, {event_a["event_id"]})
        for suffix in ("/telemetry/history", "/timeline", "/metrics", "/history"):
            denied = self.client.get(path + suffix, headers={"Authorization": "Bearer " + create_access_token(stranger_id, timedelta(minutes=5))})
            self.assertEqual(denied.status_code, 404)
        for query in ("limit=201", "offset=-1", "from=2026-10-01T00:00:00", "from=2026-01-01T00:00:00Z&to=2026-10-01T00:00:00Z"):
            self.assertEqual(self.client.get(path + "/telemetry/history?" + query, headers=self.auth).status_code, 422)
        record("TV2-18/19", {"model_filter_count": 2, "utc": True, "other_user": 404, "bad_filters": 422,
                              "legacy_chart_api": "UTC offset converted; latest samples ascending; other user denied",
                              "metrics": stats.json()})

    def test_10_ws_ticket_permissions_change(self):
        ticket = self.client.post("/api/ws-ticket", headers=self.auth).json()["ticket"]
        with self.client.websocket_connect("/ws/telemetry?ticket=" + ticket):
            pass
        with self.assertRaises(Exception):
            with self.client.websocket_connect("/ws/telemetry?ticket=" + ticket):
                pass
        sent = []
        class Socket:
            async def send_json(self, event): sent.append(event)
        manager = ConnectionManager(); manager.connections = {Socket(): self.user_id}
        event = {"type": "device.updated", "data": {"device_id": self.source_id}}
        asyncio.run(manager.send_to_device_users(event)); self.assertEqual(len(sent), 1)
        with Session(engine) as session:
            link = session.exec(select(UserDevice).where(UserDevice.user_id == self.user_id,
                                                        UserDevice.device_id == self.source_id)).one()
            link.unassigned_at = datetime.now(timezone.utc).replace(tzinfo=None); session.add(link); session.commit()
        asyncio.run(manager.send_to_device_users(event)); self.assertEqual(len(sent), 1)
        record("TV2-21", "One-use ticket accepted once; reassignment is rechecked from PostgreSQL for every event")

    def test_11_ack_before_http_response_and_disabled_rule(self):
        self.provision()
        def instant_ack(code, payload):
            process_message(f"driver/{code}/ack", {"request_id": payload["request_id"], "status": "COMPLETED"})
            return True
        with patch("app.api.routes.commands.publish_command", side_effect=instant_ack):
            result = self.command()
        self.assertEqual(result.status_code, 201, result.text)
        self.assertEqual(result.json()["ack_status"], "COMPLETED")
        self.binding()
        event = self.event()
        with patch.object(settings, "RULE_ENGINE_ENABLED", False):
            process_message("driver/events", event)
        with Session(engine) as session:
            saved = session.exec(select(AiEvent).where(AiEvent.event_id == event["event_id"])).one()
            self.assertEqual(saved.outcome, "RULE_DISABLED")
        record("TV2-12/14", "ACK handled inside publisher before HTTP returns stays COMPLETED; global rule switch prevents auto commands")

    @unittest.skipUnless(os.getenv("W3_DOCKER_TESTS") == "1", "Set W3_DOCKER_TESTS=1 to verify a disposable Docker backend")
    def test_12_docker_restart_http_websocket_and_persistence(self):
        peer, credentials = self.provision()
        persistence_key = "persist-key-" + self.suffix
        command = self.command(persistence_key).json()
        for key in ("led", "buzzer", "motor"):
            process_message(f"driver/{self.target_code}/ack", {"request_id": command["request_id"] + "-" + key, "status": "COMPLETED"})
        config = self.client.put(f"/api/devices/{self.target_id}/config", headers=self.auth, json={"timings": timings()}).json()
        process_message(f"driver/{self.target_code}/config/applied", {"device_code": self.target_code,
            "config_id": config["config_id"], "status": "APPLIED"})
        process_message("driver/events", self.event())
        name = "codex-w3-" + self.suffix
        root = Path(__file__).resolve().parents[2]
        container_env = {key: str(value).lower() if isinstance(value, bool) else str(value)
                         for key, value in settings.model_dump().items()}
        container_env.update({"DATABASE_URL": engine.url.set(host="host.docker.internal").render_as_string(hide_password=False),
            "MQTT_HOST": "host.docker.internal", "ENABLE_BACKGROUND_TASKS": "false", "WS_TICKET_TTL_SECONDS": "2"})
        handle = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".env", delete=False)
        env_path = Path(handle.name)
        handle.write("\n".join(key + "=" + value for key, value in container_env.items())); handle.close()
        def docker(*args):
            return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=40, check=True).stdout.strip()
        try:
            with socket.socket() as reservation:
                reservation.bind(("127.0.0.1", 0))
                fixed_port = reservation.getsockname()[1]
            docker("run", "-d", "--name", name, "-p", f"127.0.0.1:{fixed_port}:8000", "--env-file", str(env_path),
                "--mount", f"type=bind,source={root / 'backend'},target=/app,readonly", "deployment-mqtt-setup:latest",
                "python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log")
            port = docker("port", name, "8000/tcp").split(":")[-1]
            http = httpx.Client(base_url="http://127.0.0.1:" + port, headers=self.auth, timeout=10, trust_env=False)
            def healthy():
                try: return http.get("/api/health").status_code == 200
                except httpx.HTTPError: return False
            wait_for(healthy, 25)
            login = http.post("/api/login", json={"username": "w3-" + self.suffix, "password": "temporary-test-only"})
            self.assertEqual(login.status_code, 200, login.text)
            self.assertEqual(http.get("/api/me").json()["role"], "Admin")
            with Session(engine) as session:
                stranger = User(username="ws-other-" + self.suffix, fullname="Other", hash_password="unused",
                    email="ws-" + self.suffix + "@example.test", phone="ws-" + self.suffix, role="Customer")
                session.add(stranger); session.commit(); stranger_id = stranger.id
            other_auth = {"Authorization": "Bearer " + create_access_token(stranger_id, timedelta(minutes=5))}
            url = "ws://127.0.0.1:" + port + "/ws/telemetry?ticket="
            ticket = http.post("/api/ws-ticket").json()["ticket"]
            other_ticket = http.post("/api/ws-ticket", headers=other_auth).json()["ticket"]
            ai = Peer(settings.AI_MQTT_USERNAME, settings.AI_MQTT_PASSWORD); self.peers.append(ai)
            with ws_connect(url + ticket, origin=settings.FRONTEND_HOST, proxy=None) as owner, \
                 ws_connect(url + other_ticket, origin=settings.FRONTEND_HOST, proxy=None) as other:
                with self.assertRaises(Exception):
                    ws_connect(url + ticket, origin=settings.FRONTEND_HOST, proxy=None)
                ai.publish("driver/status", {"device_id": self.source_code, "status": "ALIVE"})
                received = json.loads(owner.recv(timeout=5))
                self.assertEqual(received["data"]["device_id"], self.source_id)
                with self.assertRaises(TimeoutError): other.recv(timeout=0.5)
                with Session(engine) as session:
                    link = session.exec(select(UserDevice).where(UserDevice.user_id == self.user_id,
                        UserDevice.device_id == self.source_id)).one()
                    link.unassigned_at = datetime.now(timezone.utc).replace(tzinfo=None); session.add(link); session.commit()
                ai.publish("driver/status", {"device_id": self.source_code, "status": "ALIVE"})
                with self.assertRaises(TimeoutError): owner.recv(timeout=0.5)
                with Session(engine) as session:
                    link = session.exec(select(UserDevice).where(UserDevice.user_id == self.user_id,
                        UserDevice.device_id == self.source_id)).one()
                    link.unassigned_at = None; session.add(link)
                    user = session.get(User, self.user_id); user.role = "Customer"; session.add(user); session.commit()
                denied = http.post(f"/api/devices/{self.target_id}/commands", json={"action": "TEST_ALERT",
                    "buzzer_ms": 1000, "vibration_ms": 1000, "led_mode": "FLASH"})
                self.assertEqual(denied.status_code, 403)
                with Session(engine) as session:
                    user = session.get(User, self.user_id); user.role = "Admin"; session.add(user); session.commit()
                expired = http.post("/api/ws-ticket").json()["ticket"]
                time.sleep(2.2)
                with self.assertRaises(Exception): ws_connect(url + expired, origin=settings.FRONTEND_HOST, proxy=None)
                docker("restart", "--time", "5", name)
                with self.assertRaises(Exception): owner.recv(timeout=5)
            wait_for(healthy, 25)
            new_ticket = http.post("/api/ws-ticket").json()["ticket"]
            with ws_connect(url + new_ticket, origin=settings.FRONTEND_HOST, proxy=None) as restarted:
                peer.publish(f"driver/{self.target_code}/status", {"device_code": self.target_code, "status": "ALIVE"})
                self.assertEqual(json.loads(restarted.recv(timeout=5))["data"]["device_id"], self.target_id)
            self.assertEqual(http.get("/api/commands/" + command["request_id"]).json()["ack_status"], "COMPLETED")
            self.assertEqual(http.get(f"/api/devices/{self.target_id}/config").json()["applied_config_id"], config["config_id"])
            self.assertGreaterEqual(len(http.get(f"/api/devices/{self.target_id}/history").json()["items"]), 1)
            self.assertGreaterEqual(len(http.get(f"/api/alerts?device_id={self.source_id}").json()), 1)
            self.assertIn("event", {item["kind"] for item in http.get(f"/api/devices/{self.source_id}/timeline").json()["items"]})
            replay = http.post(f"/api/devices/{self.target_id}/commands", headers={"Idempotency-Key": persistence_key},
                json={"action": "TEST_ALERT", "buzzer_ms": 1000, "vibration_ms": 1000, "led_mode": "FLASH"})
            self.assertEqual(replay.status_code, 201, replay.text)
            self.assertEqual(replay.json()["request_id"], command["request_id"])
            output = docker("logs", name)
            (Path(os.environ["W3_EVIDENCE"]) / "docker-be-output.txt").write_text(output, encoding="utf-8")
            record("TV2-13/21", {"runtime": "Docker backend with real PostgreSQL/MQTT",
                "restart": "PASS", "websocket_owner_only": "PASS", "assignment_revoke": "PASS",
                "ticket_reuse_expiry": "PASS", "new_ticket_after_restart": "PASS",
                "command_ack_config_history_persisted": "PASS"})
            http.close()
        finally:
            logs = subprocess.run(["docker", "logs", name], capture_output=True, text=True, timeout=20)
            sanitized = re.sub(r'ticket=[^"\s]+', 'ticket=<redacted>', logs.stdout + logs.stderr)
            (Path(os.environ["W3_EVIDENCE"]) / "docker-be-output.txt").write_text(sanitized, encoding="utf-8")
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=30)
            env_path.unlink(missing_ok=True)

    def test_13_ai_mqtt_to_rule_to_command_to_three_ack(self):
        peer, _ = self.provision(); peer.subscribe(f"driver/{self.target_code}/command")
        self.binding()
        ai = Peer(settings.AI_MQTT_USERNAME, settings.AI_MQTT_PASSWORD); self.peers.append(ai)
        payload = self.event(duration=6500)
        ai.publish("driver/events", payload)
        def queued_command():
            with Session(engine) as session:
                alert = session.exec(select(Alert).where(Alert.source_event_id == payload["event_id"])).first()
                return session.exec(select(Command).where(Command.alert_id == alert.id)).first() if alert else None
        command = wait_for(queued_command)
        run_once()
        messages = [json.loads(peer.messages.get(timeout=5)[1]) for _ in range(3)]
        self.assertEqual({item["intensity"] for item in messages}, {"MEDIUM"})
        for child in messages:
            peer.publish(f"driver/{self.target_code}/ack", {"request_id": child["request_id"], "status": "COMPLETED"})
        wait_for(lambda: self.get_command(command.request_id)["ack_status"] == "COMPLETED")
        ai.publish("driver/events", payload)
        with self.assertRaises(queue.Empty): peer.messages.get(timeout=0.4)
        record("TV2-15/22", {"path": "AI MQTT -> Rule Engine -> persisted queue -> MQTT commands -> virtual ESP32 ACKs",
            "event_id": payload["event_id"], "alert_id": command.alert_id, "request_id": command.request_id,
            "severity": 2, "final_ack": "COMPLETED"})

    def test_14_interrupted_publish_is_not_retried_blindly(self):
        self.provision()
        with Session(engine) as session:
            device = session.get(Device, self.target_id)
            command = create_command(session, device, "TEST_ALERT", {
                "led": {"command": "LED_ON", "duration": 1000, "intensity": "WEAK"}}, user_id=self.user_id)
            session.commit(); identifier = command.id
            with self.assertRaises(RuntimeError):
                dispatch_command(session, identifier, publisher=lambda *args: (_ for _ in ()).throw(RuntimeError("simulated crash")))
        with Session(engine) as session:
            with patch("app.services.command_dispatch.publish_command") as publisher:
                dispatch_command(session, identifier)
                publisher.assert_not_called()
            command = session.get(Command, identifier)
            self.assertEqual(command.dispatches["led"]["dispatch_state"], "PUBLISHING")
            expire_commands(session, command.created_at + timedelta(seconds=31))
            session.refresh(command)
            self.assertEqual(command.status, "TIMEOUT")
            self.assertIn("Delivery unknown", command.error_message)
        record("TV2-17/13", "A crash after durable PUBLISHING marker -> no resend from a new session; timeout reports delivery unknown")


    def test_15_concurrent_first_config_put_preserves_latest_revision(self):
        peer, _ = self.provision()
        path = f"/api/devices/{self.target_id}/config"
        barrier = threading.Barrier(2)

        def send(value):
            barrier.wait(timeout=5)
            return self.client.put(path, headers=self.auth, json={"timings": timings(value)})

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(send, (100, 300)))
        self.assertEqual([response.status_code for response in responses], [200, 200])
        current = self.client.get(path, headers=self.auth).json()
        self.assertEqual(current["desired"]["revision"], 2)
        with Session(engine) as session:
            self.assertEqual(len(session.exec(select(Config).where(Config.device_id == self.target_id)).all()), 1)
        peer.subscribe(f"driver/{self.target_code}/config/update")
        _, retained, _ = peer.messages.get(timeout=5)
        self.assertEqual(json.loads(retained)["config_id"], current["config_id"])
        record("TV2-07/09", {"concurrent_first_put": "both HTTP 200; one config row; revision 2",
                             "retained": "matches latest desired config_id"})

    def test_16_firmware_reboot_ack_reports_failure(self):
        peer, _ = self.provision()
        peer.subscribe(f"driver/{self.target_code}/command")
        response = self.command()
        self.assertEqual(response.status_code, 201, response.text)
        child = json.loads(peer.messages.get(timeout=5)[1])
        peer.publish(f"driver/{self.target_code}/ack", {
            "request_id": child["request_id"], "device_code": self.target_code,
            "status": "INTERRUPTED", "elapsed_ms": 0, "error": "REBOOTED",
        })
        parent_id = response.json()["request_id"]
        wait_for(lambda: self.get_command(parent_id)["status"] == "FAILED")
        parent = self.get_command(parent_id)
        self.assertEqual(parent["error_message"], "REBOOTED")
        self.assertNotEqual(parent["ack_status"], "COMPLETED")
        record("TV2-12/13", {"firmware_ack": "INTERRUPTED/REBOOTED",
                              "parent_status": parent["status"], "error_message": parent["error_message"]})


class EvidenceResult(unittest.TextTestResult):
    def startTest(self, test):
        self.started = time.perf_counter(); super().startTest(test)
    def addSuccess(self, test):
        record(test.id(), {"result": "PASS", "duration_ms": round((time.perf_counter() - self.started) * 1000, 3)})
        super().addSuccess(test)


if __name__ == "__main__":
    selected = os.getenv("W3_TEST_NAME")
    suite = unittest.defaultTestLoader.loadTestsFromName("Week3Integration." + selected, module=sys.modules[__name__]) if selected else \
            unittest.defaultTestLoader.loadTestsFromTestCase(Week3Integration)
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
    directory = Path(os.environ["W3_EVIDENCE"])
    (directory / "integration-results.json").write_text(json.dumps({"executed_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Real PostgreSQL, HTTP/ASGI, MQTT broker; virtual ESP32, no hardware", "tests_run": result.testsRun,
        "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
        "observations": OBSERVATIONS}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() else 1)
