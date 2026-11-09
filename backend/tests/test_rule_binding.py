"""Disposable HTTP + SQL tests. No application startup, broker or physical outputs."""
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost/test")
os.environ.setdefault("SECRET_KEY", "isolated-test-key")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI, Header
from fastapi.testclient import TestClient
from sqlalchemy.dialects.postgresql import INET, MACADDR
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine, select

from app.api.deps import get_current_user
from app.api.routes.rules import router
from app.core.config import settings
from app.core.db import get_session
from app.models.ai_event import AiEvent, RuleBinding, RuleRuntime
from app.models.alert import Alert
from app.models.audit_log import AuditLog
from app.models.command import Command
from app.models.command_type import CommandType
from app.models.device import Device
from app.models.telemetry import Telemetry
from app.models.user import User
from app.schemas.rules import RulePolicy
from app.services.ai_policy import VERSION
from app.services.command_dispatch import dispatch_command
from app.services.rule_binding import revision
from app.services.rule_engine import process_event


@compiles(INET, "sqlite")
@compiles(MACADDR, "sqlite")
def text_for_sqlite(type_, compiler, **kwargs):
    return "TEXT"


class RuleBindingTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        SQLModel.metadata.create_all(self.engine, tables=[model.__table__ for model in (
            Device, User, RuleBinding, RuleRuntime, AiEvent, Alert, Command, CommandType, AuditLog, Telemetry)])
        with Session(self.engine) as db:
            devices = [Device(device_code=code, model="test", device_type=kind, lifecycle_state="ACTIVE",
                       status="ONLINE", last_seen=datetime.now(timezone.utc).replace(tzinfo=None),
                       mqtt_password="never-return-this") for code, kind in (
                       ("vision-one", "VISION_NODE"), ("alert-one", "ALERT_NODE"),
                       ("alert-two", "ALERT_NODE"), ("vision-two", "VISION_NODE"))]
            db.add_all(devices + [CommandType(code="AUTO_ALERT", name="Automatic")])
            db.commit()
            self.source, self.target, self.other, self.second_source = [item.id for item in devices]
        app = FastAPI()
        app.include_router(router, prefix="/api")

        def database():
            with Session(self.engine) as db:
                yield db

        def actor(x_test_role: str = Header(default="Admin")):
            return User(id=1, username="test-admin", role=x_test_role, status="ACTIVE")

        app.dependency_overrides[get_session] = database
        app.dependency_overrides[get_current_user] = actor
        self.client = TestClient(app)
        self.flag = patch.object(settings, "RULE_ENGINE_ENABLED", True)
        self.flag.start()
        self.addCleanup(self.flag.stop)
        self.addCleanup(self.client.close)
        self.addCleanup(self.engine.dispose)

    def read(self, source=None):
        result = self.client.get(f"/api/devices/{source or self.source}/rule")
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def save(self, source=None, target=None, enabled=False, snapshot=None, **extra):
        source = source or self.source
        snapshot = snapshot if snapshot is not None else self.read(source)
        return self.client.put(f"/api/devices/{source}/rule", json={
            "target_device_id": target or self.target, "enabled": enabled,
            "expected_updated_at": snapshot["updated_at"], "policy": {"policy_version": VERSION}, **extra})

    def armed(self):
        first = self.save()
        self.assertEqual(first.status_code, 200, first.text)
        result = self.save(enabled=True)
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def queued(self, snapshot):
        with Session(self.engine) as db:
            alert = Alert(device_id=self.source, alert_type="DROWSY_THRESHOLD_REACHED", status="NEW")
            db.add(alert)
            db.flush()
            command = Command(device_id=self.target, command_type_id=1, action="AUTO_ALERT", alert_id=alert.id,
                status="PENDING", dispatches={name: {"status": status, "dispatch_state": dispatch,
                    "request_id": f"test-{name}", "payload": {"command": "LED_ON"},
                    "policy_guard": {"source_device_id": self.source, "target_device_id": self.target,
                        "binding_revision": snapshot["updated_at"], "session_id": "s", "episode_id": "e",
                        "expires_at": (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=2)).isoformat()}}
                    for name, status, dispatch in (("led", "PENDING", "QUEUED"), ("motor", "SENT", "PUBLISHED"))})
            manual = Command(device_id=self.target, command_type_id=1, action="TEST_ALERT", status="PENDING")
            db.add_all([command, manual, RuleRuntime(source_device_id=self.source,
                state={"session_id": "s", "episode_id": "e", "supported": True})])
            db.commit()
            return command.id, manual.id

    def test_editor_create_disarmed_readiness_and_no_secret_or_publish(self):
        with patch("app.services.command_dispatch.publish_command") as publish:
            initial = self.read()
            self.assertIsNone(initial["updated_at"])
            self.assertIn("UNBOUND", initial["readiness"]["blockers"])
            self.assertNotIn("never-return-this", str(initial))
            created = self.save(enabled=True).json()
            self.assertFalse(created["enabled"])
            enabled = self.save(enabled=True).json()
            self.assertTrue(enabled["effective_enabled"])
            self.assertFalse(enabled["readiness"]["ready"])
            self.assertIn("WAITING_FOR_AI", enabled["readiness"]["blockers"])
            publish.assert_not_called()
        with Session(self.engine) as db:
            self.assertEqual(db.exec(select(Command)).all(), [])
            self.assertEqual(len(db.exec(select(AuditLog)).all()), 2)

    def test_role_guards_still_admin_only(self):
        for role in ("Employee", "Customer", "VIEWER", "OPERATOR"):
            headers = {"x-test-role": role}
            self.assertEqual(self.client.get(f"/api/devices/{self.source}/rule", headers=headers).status_code, 403)
            self.assertEqual(self.client.put(f"/api/devices/{self.source}/rule", headers=headers,
                json={"target_device_id": self.target}).status_code, 403)

    def test_concurrent_create_and_stale_edit_rejected(self):
        initial = self.read()
        self.assertEqual(self.save(snapshot=initial).status_code, 200)
        self.assertEqual(self.save(snapshot=initial, target=self.other).status_code, 409)
        before = self.read()
        self.assertEqual(self.save(snapshot=before, enabled=True).status_code, 200)
        self.assertEqual(self.save(snapshot=before, enabled=False).status_code, 409)
        self.assertTrue(self.read()["enabled"])

    def test_retarget_disarms_cancels_only_unsent_and_old_revision_cannot_publish(self):
        snapshot = self.armed()
        command_id, manual_id = self.queued(snapshot)
        changed = self.save(target=self.other, enabled=True)
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertFalse(changed.json()["enabled"])
        with Session(self.engine) as db:
            command = db.get(Command, command_id)
            self.assertEqual(command.dispatches["led"]["dispatch_state"], "CANCELLED")
            self.assertEqual(command.dispatches["motor"]["dispatch_state"], "PUBLISHED")
            self.assertEqual(command.dispatches["motor"]["status"], "SENT")
            self.assertEqual(db.get(Command, manual_id).status, "PENDING")
            publish = Mock(return_value=True)
            dispatch_command(db, command_id, publisher=publish)
            publish.assert_not_called()
        self.assertEqual(self.save(target=self.other, enabled=True).status_code, 409)

    def test_disable_then_enable_invalidates_old_guard_and_noop_keeps_revision(self):
        snapshot = self.armed()
        command_id, _ = self.queued(snapshot)
        self.assertEqual(self.save(enabled=True).json()["updated_at"], snapshot["updated_at"])
        self.save(enabled=False)
        with Session(self.engine) as db:
            command = db.get(Command, command_id)
            command.dispatches = {key: {**child, "status": "COMPLETED"} for key, child in command.dispatches.items()}
            db.add(command)
            db.commit()
        enabled = self.save(enabled=True).json()
        self.assertNotEqual(enabled["updated_at"], snapshot["updated_at"])
        # Simulate an old queued snapshot recovered after restart. It must fail
        # even when a valid current session and an enabled link both exist.
        with Session(self.engine) as db:
            command = db.get(Command, command_id)
            command.status = "PENDING"
            command.dispatches = {"led": {**command.dispatches["led"], "status": "PENDING", "dispatch_state": "QUEUED"}}
            db.add(command)
            db.commit()
            publish = Mock(return_value=True)
            dispatch_command(db, command_id, publisher=publish)
            publish.assert_not_called()

    def test_shared_active_target_blocked_but_disabled_link_can_be_prepared(self):
        self.armed()
        self.assertEqual(self.save(source=self.second_source).status_code, 200)
        self.assertEqual(self.save(source=self.second_source, enabled=True).status_code, 409)
        candidate = next(item for item in self.read(self.second_source)["targets"] if item["id"] == self.target)
        self.assertEqual(candidate["active_source_id"], self.source)

    def test_invalid_types_and_lifecycle_enable_but_allow_disable_after_revocation(self):
        self.assertEqual(self.save(target=self.second_source).status_code, 409)
        self.armed()
        with Session(self.engine) as db:
            target = db.get(Device, self.target)
            target.lifecycle_state = "DECOMMISSIONED"
            db.add(target)
            db.commit()
        self.assertEqual(self.save(enabled=True).status_code, 409)
        self.assertEqual(self.save(enabled=False).status_code, 200)
        self.assertNotIn(self.target, [item["id"] for item in self.read()["targets"]])

    def test_offline_global_disabled_and_unknown_do_not_look_ready(self):
        self.armed()
        with Session(self.engine) as db:
            db.add(Telemetry(device_id=self.source, driver_state="ATTENTIVE"))
            db.commit()
        self.assertTrue(self.read()["readiness"]["ready"])
        with patch.object(settings, "RULE_ENGINE_ENABLED", False):
            result = self.read()
            self.assertFalse(result["effective_enabled"])
            self.assertIn("ENGINE_DISABLED", result["readiness"]["blockers"])
        with Session(self.engine) as db:
            target = db.get(Device, self.target)
            target.last_seen = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=100)
            db.add_all([target, Telemetry(device_id=self.source, driver_state="UNKNOWN")])
            db.commit()
        result = self.read()
        self.assertIn("TARGET_OFFLINE", result["readiness"]["blockers"])
        self.assertIn("MONITORING_UNAVAILABLE", result["readiness"]["blockers"])

    def test_live_event_observed_before_enable_is_recorded_without_command(self):
        before = datetime.now(timezone.utc) - timedelta(seconds=1)
        self.armed()
        payload = {"message_id": "pre-enable", "device_code": "vision-one", "policy_version": VERSION,
            "model_version": "test", "session_id": "new-session", "session_started_at": before.isoformat(),
            "sequence_number": 1, "episode_id": "new-episode", "episode_start_event_id": "start",
            "event_type": "DROWSY_THRESHOLD_REACHED", "state": "DROWSY", "state_duration_ms": 3000, "level": 1,
            "timestamp": before.isoformat(), "observed_at": before.isoformat(), "_delivery": {"mode": "live"}}
        with Session(self.engine) as db:
            process_event(db, payload)
            self.assertEqual(db.exec(select(AiEvent)).one().outcome, "PRE_BINDING_EVENT")
            self.assertEqual(db.exec(select(Command)).all(), [])
            self.assertEqual(len(db.exec(select(Alert)).all()), 1)


if __name__ == "__main__":
    unittest.main()
