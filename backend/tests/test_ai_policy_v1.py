"""Isolated SQL integration. No camera, broker, external DB or physical outputs."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch, MagicMock

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost/test")
os.environ.setdefault("SECRET_KEY", "isolated-test-key")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy.dialects.postgresql import INET, MACADDR
from sqlalchemy.ext.compiler import compiles
from sqlmodel import SQLModel, Session, create_engine, select
from app.models.ai_event import AiEvent, AiMessageReceipt, RuleBinding, RuleRuntime
from app.models.alert import Alert
from app.models.command import Command
from app.models.command_type import CommandType
from app.models.device import Device
from app.models.user import User
from app.schemas.rules import AiEventRequest, RulePolicy
from app.services import rule_engine
from app.services.ai_policy import VERSION
from app.services.command_dispatch import dispatch_command
from app.services.command_state import aggregate


@compiles(INET, "sqlite")
@compiles(MACADDR, "sqlite")
def pg_text_for_isolated_sqlite(type_, compiler, **kwargs):
    return "TEXT"


class Clock(datetime):
    value = datetime(2026, 11, 7, 10, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        return cls.value if tz else cls.value.replace(tzinfo=None)


class PolicyIntegrationTests(unittest.TestCase):
    def setUp(self):
        Clock.value = datetime(2026, 11, 7, 10, tzinfo=timezone.utc)
        self.engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(self.engine, tables=[Device.__table__, User.__table__,
            AiEvent.__table__, AiMessageReceipt.__table__, RuleBinding.__table__, RuleRuntime.__table__,
            Alert.__table__, CommandType.__table__, Command.__table__])
        self.db = Session(self.engine)
        self.source = Device(device_code="vision-test", model="camera", device_type="VISION_NODE", lifecycle_state="ACTIVE")
        self.target = Device(device_code="alert-test", model="esp32", device_type="ALERT_NODE",
            lifecycle_state="ACTIVE", status="ONLINE", last_seen=Clock.now())
        self.db.add_all([self.source, self.target, CommandType(code="AUTO_ALERT", name="Automatic alert")])
        self.db.flush()
        self.binding = RuleBinding(source_device_id=self.source.id, target_device_id=self.target.id,
            enabled=True, policy={"policy_version": VERSION})
        self.db.add(self.binding)
        self.db.commit()
        self.sequence = 0
        self.patches = [patch.object(rule_engine, "datetime", Clock),
                        patch.object(rule_engine.settings, "RULE_ENGINE_ENABLED", True)]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.db.close()
        self.engine.dispose()

    def event(self, kind="DROWSY_THRESHOLD_REACHED", **fields):
        self.sequence += 1
        return {"message_id": f"event-{self.sequence}", "device_code": "vision-test", "model_version": "rf-frozen",
            "policy_version": VERSION, "session_id": "session-1", "episode_id": "episode-1",
            "episode_start_event_id": "start-1", "sequence_number": self.sequence,
            "session_started_at": "2026-11-07T09:00:00+00:00", "timestamp": Clock.value.isoformat(),
            "observed_at": Clock.value.isoformat(), "event_type": kind, "state": "DROWSY",
            "level": 1, "state_duration_ms": 3000, "_delivery": {"mode": "live"}, **fields}

    def send(self, event):
        result = rule_engine.process_event(self.db, event)
        saved = self.db.exec(select(AiEvent).where(AiEvent.event_id == event["message_id"])).one()
        return result, saved.outcome

    def commands(self):
        return self.db.exec(select(Command).order_by(Command.id)).all()

    def finish_commands(self):
        for command in self.commands():
            command.dispatches = {key: {**child, "status": "COMPLETED", "dispatch_state": "PUBLISHED"}
                                  for key, child in command.dispatches.items()}
            aggregate(command)
            self.db.add(command)
        self.db.commit()

    def test_both_states_escalate_without_thirty_second_cooldown(self):
        for seconds, level in ((0, 1), (3, 2), (7, 3), (12, 3)):
            Clock.value = datetime(2026, 11, 7, 10, tzinfo=timezone.utc)+timedelta(seconds=seconds)
            self.finish_commands()
            _, outcome = self.send(self.event(level=level, state_duration_ms={1:3000, 2:6000, 3:10000}[level]))
            self.assertEqual(outcome, "QUEUED")
        self.assertEqual(len(self.commands()), 4)
        self.assertEqual(set(self.commands()[0].dispatches), {"led", "buzzer"})
        self.assertEqual(set(self.commands()[1].dispatches), {"led", "buzzer", "motor"})
        self.assertEqual(len(self.db.exec(select(Alert)).all()), 1)

    def test_distracted_uses_agreed_policy(self):
        _, outcome = self.send(self.event(kind="DISTRACTED_THRESHOLD_REACHED", state="DISTRACTED"))
        self.assertEqual(outcome, "QUEUED")

    def test_duplicate_transport_metadata_never_creates_another_command(self):
        event = self.event()
        self.send(event)
        event["_delivery"] = {"mode": "backfill"}
        self.send(event)
        self.assertEqual(len(self.commands()), 1)

    def test_backfill_stale_observation_and_unknown_policy_never_actuate(self):
        for fields, expected in (({"_delivery": {"mode":"backfill"}}, "BACKFILL_RECORDED"),
            ({"observed_at": (Clock.value-timedelta(seconds=3)).isoformat()}, "STALE_OBSERVATION"),
            ({"timestamp": (Clock.value-timedelta(seconds=6)).isoformat()}, "STALE_RECORDED"),
            ({"policy_version": "unknown-version"}, "UNKNOWN_POLICY")):
            self.assertEqual(self.send(self.event(**fields))[1], expected)
        self.assertEqual(self.commands(), [])

    def test_old_sequence_and_session_cannot_reopen_or_stop_new_session(self):
        self.send(self.event())
        self.finish_commands()
        self.send(self.event(session_id="session-2", episode_id="episode-2",
                             session_started_at="2026-11-07T09:30:00+00:00"))
        _, outcome = self.send(self.event(kind="SESSION_ENDED", final_state="DROWSY"))
        self.assertEqual(outcome, "OLD_SESSION")
        runtime = self.db.get(RuleRuntime, self.source.id)
        self.assertEqual(runtime.state["session_id"], "session-2")
        self.assertFalse(runtime.state["ended"])
        self.assertEqual(self.send(self.event(session_id="session-2", sequence_number=0,
            session_started_at="2026-11-07T09:30:00+00:00"))[1], "OLD_SEQUENCE")

    def test_recovery_cancels_unsent_but_not_manual_or_published_work(self):
        self.send(self.event())
        manual = Command(device_id=self.target.id, command_type_id=1, action="MANUAL", status="PENDING")
        self.db.add(manual)
        self.db.commit()
        self.send(self.event(kind="STATE_CHANGED", state="ATTENTIVE"))
        self.assertEqual(self.commands()[0].status, "FAILED")
        self.assertEqual(self.db.get(Command, manual.id).status, "PENDING")
        publisher = Mock(return_value=True)
        dispatch_command(self.db, self.commands()[0].id, publisher=publisher)
        publisher.assert_not_called()

    def test_dispatch_checks_expiry_again_and_restart_preserves_state(self):
        self.send(self.event())
        command_id = self.commands()[0].id
        source_id = self.source.id
        self.db.close()
        self.db = Session(self.engine)
        self.assertEqual(self.db.get(RuleRuntime, source_id).state["level"], 1)
        publisher = Mock(return_value=True)
        with patch("app.services.command_dispatch.now", return_value=Clock.now()+timedelta(seconds=3)):
            dispatch_command(self.db, command_id, publisher=publisher)
        publisher.assert_not_called()
        self.assertEqual(self.db.get(Command, command_id).status, "FAILED")

    def test_unresolved_dispatch_does_not_accumulate_commands(self):
        self.send(self.event())
        Clock.value += timedelta(seconds=6)
        self.assertEqual(self.send(self.event(level=2, state_duration_ms=6000))[1], "DISPATCH_UNRESOLVED")
        self.assertEqual(len(self.commands()), 1)

    def test_versioned_contract_rejects_missing_metadata(self):
        event = self.event()
        event.pop("session_id")
        with self.assertRaises(ValueError):
            AiEventRequest.model_validate(event)

    def test_preset_is_canonical_and_cannot_keep_legacy_cooldown(self):
        policy = RulePolicy(policy_version=VERSION)
        self.assertEqual(policy.levels["1"].outputs, ["led", "buzzer"])
        self.assertEqual(policy.max_event_age_seconds, 5)
        with self.assertRaises(ValueError):
            RulePolicy(policy_version=VERSION, cooldown_seconds=30)

    def test_ingest_receipt_survives_transport_change_but_schema_errors_are_rejected(self):
        from app.services.mqtt_service import _save_queued_ai
        event = self.event()
        first = _save_queued_ai(self.db, "vision-test", "driver/vision-test/events", "events", event)
        self.assertEqual(first[-1]["type"], "ingest.saved")
        event["_delivery"] = {"mode": "backfill"}
        retried = _save_queued_ai(self.db, "vision-test", "driver/vision-test/events", "events", event)
        self.assertEqual([item["type"] for item in retried], ["ingest.saved"])
        self.assertEqual(len(self.commands()), 1)
        invalid = self.event()
        invalid.pop("session_id")
        rejected = _save_queued_ai(self.db, "vision-test", "driver/vision-test/events", "events", invalid)
        self.assertEqual(rejected[0]["type"], "ingest.rejected")

    def test_clip_rotation_cannot_resume_suspended_risk(self):
        self.send(self.event())
        self.send(self.event(kind="RISK_SUSPENDED"))
        self.send(self.event(kind="STATE_CHANGED", reason="CLIP_ROTATED"))
        self.assertFalse(self.db.get(RuleRuntime, self.source.id).state["supported"])
        self.assertEqual(len(self.commands()), 1)

    def test_rule_disabled_before_dispatch_blocks_pending_command(self):
        self.send(self.event())
        command_id = self.commands()[0].id
        self.binding.enabled = False
        self.db.add(self.binding)
        self.db.commit()
        publisher = Mock(return_value=True)
        with patch("app.services.command_dispatch.now", return_value=Clock.now()):
            dispatch_command(self.db, command_id, publisher=publisher)
        publisher.assert_not_called()

    def test_legacy_payload_cannot_bypass_versioned_session_and_freshness_checks(self):
        event = {"message_id": "legacy", "device_code": "vision-test", "timestamp": Clock.value.isoformat(),
                 "event_type": "DROWSY_THRESHOLD_REACHED", "state": "DROWSY", "state_duration_ms": 3000}
        self.assertEqual(self.send(event)[1], "POLICY_METADATA_REQUIRED")
        self.assertEqual(self.commands(), [])

    def test_readiness_reports_missing_policy_migration(self):
        from app.services import ai_readiness
        inspector = Mock()
        inspector.get_table_names.return_value = ["ai_events", "ai_message_receipts", "rule_bindings", "ai_videos"]
        connection = MagicMock()
        connection.__enter__.return_value.exec.return_value.first.return_value = self.source
        with patch.object(ai_readiness, "inspect", return_value=inspector), \
                patch.object(ai_readiness, "Session", return_value=connection):
            result = ai_readiness.database_readiness()
        self.assertEqual(result["missing_tables"], ["rule_runtime"])
        self.assertFalse(result["database_ready"])

    def test_rule_disabled_or_target_offline_still_records_one_driver_alert(self):
        self.binding.enabled = False
        self.db.add(self.binding)
        self.db.commit()
        result, outcome = self.send(self.event())
        self.assertEqual(outcome, "RULE_DISABLED")
        self.assertEqual(result[0]["type"], "alert.created")
        self.binding.enabled = True
        self.target.status = "OFFLINE"
        self.db.add_all([self.binding, self.target])
        self.db.commit()
        result, outcome = self.send(self.event(level=2, state_duration_ms=6000))
        self.assertEqual(outcome, "TARGET_UNAVAILABLE")
        self.assertEqual(result[0]["type"], "alert.updated")
        self.assertEqual(len(self.db.exec(select(Alert)).all()), 1)
        self.assertEqual(self.commands(), [])


if __name__ == "__main__":
    unittest.main()
