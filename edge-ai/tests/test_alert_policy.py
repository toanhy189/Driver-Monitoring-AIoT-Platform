from datetime import datetime, timedelta, timezone
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import edge_queue as queue
from mqtt_client import MQTTClient
from service.alert_policy import AlertPolicy
from service.local_alert import LocalAlertWorker
from service.message.publisher import send_message


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.policy = AlertPolicy("vision-test", "rf-frozen", clock=lambda: self.now,
            utcnow=lambda: datetime(2026, 11, 7, tzinfo=timezone.utc)+timedelta(seconds=self.now))

    def advance(self, state, seconds):
        events = []
        for _ in range(round(seconds*10)):
            self.now = round(self.now+0.1, 5)
            events += self.policy.update(state)
        return events

    def test_escalation_repeat_ids_and_clip_link(self):
        for state in ("DROWSY", "DISTRACTED"):
            self.setUp()
            events = self.advance(state, 21)
            alerts = [e for e in events if e["event_type"].endswith("THRESHOLD_REACHED")]
            self.assertEqual([e["level"] for e in alerts], [1, 2, 3, 3, 3])
            self.assertEqual(alerts[0]["outputs"], ["led", "buzzer"])
            self.assertEqual(len({e["episode_id"] for e in alerts}), 1)
            self.assertEqual(len({e["message_id"] for e in events}), len(events))
            self.assertEqual({e["clip_message_id"] for e in alerts}, {events[0]["message_id"]})
            self.assertTrue(all(e["model_version"] == "rf-frozen" for e in events))

    def test_thirty_minutes_keeps_repeating_without_real_sleep(self):
        events = self.advance("DROWSY", 1800)
        alerts = [e for e in events if e["event_type"].endswith("THRESHOLD_REACHED")]
        self.assertGreater(len(alerts), 350)
        self.assertLess(len(alerts), 365)
        dates = [datetime.fromisoformat(e["timestamp"]) for e in alerts if e["level"] == 3]
        self.assertTrue(all(5 <= (b-a).total_seconds() <= 5.1 for a, b in zip(dates, dates[1:])))

    def test_recovery_suspends_immediately_and_closes_after_two_seconds(self):
        self.advance("DROWSY", 12)
        early = self.advance("ATTENTIVE", 1.9)
        self.assertTrue(any(e["event_type"] == "RISK_SUSPENDED" for e in early))
        self.assertEqual(self.policy.state, "DROWSY")
        events = self.advance("ATTENTIVE", 0.3)
        self.assertEqual(self.policy.state, "ATTENTIVE")
        self.assertTrue(any(e.get("end_reason") == "RECOVERED" for e in events))
        self.assertFalse(any(e["event_type"].endswith("THRESHOLD_REACHED") for e in early+events))

    def test_unknown_breaks_duration_has_distinct_fault_and_reconfirms(self):
        self.advance("DISTRACTED", 4)
        old_episode = self.policy.episode_id
        events = self.advance("UNKNOWN", 35)
        faults = [e for e in events if e["event_type"] == "MONITORING_FAULT"]
        self.assertEqual(len(faults), 2)
        self.assertFalse(any(e.get("end_reason") == "RECOVERED" for e in events))
        self.assertFalse(any(e["event_type"].endswith("THRESHOLD_REACHED") for e in events))
        returned = self.advance("DISTRACTED", 4)
        alert = next(e for e in returned if e["event_type"].endswith("THRESHOLD_REACHED"))
        self.assertEqual(alert["level"], 1)
        self.assertNotEqual(alert["episode_id"], old_episode)
        self.assertLess(alert["state_duration_ms"], 4000)

    def test_loop_stall_cannot_catch_up_with_stale_alerts(self):
        self.advance("DROWSY", 4)
        self.now += 60
        events = self.policy.update("DROWSY")
        self.assertEqual(self.policy.state, "UNKNOWN")
        self.assertFalse(any(e["event_type"].endswith("THRESHOLD_REACHED") for e in events))

    def test_end_is_once_and_next_session_is_distinct(self):
        self.advance("DROWSY", 4)
        end = self.policy.end()
        self.assertEqual(end["session_id"], self.policy.session_id)
        self.assertIsNone(self.policy.end())
        self.assertEqual(self.advance("DROWSY", 10), [])
        self.assertNotEqual(AlertPolicy("vision-test", "rf-frozen").session_id, self.policy.session_id)

    def test_rotation_keeps_episode_but_updates_clip(self):
        self.advance("DROWSY", 4)
        episode = self.policy.episode_id
        segment = self.policy.rotate_clip()
        events = self.advance("DROWSY", 4)
        alert = next(e for e in events if e["event_type"].endswith("THRESHOLD_REACHED"))
        self.assertEqual(alert["episode_id"], episode)
        self.assertEqual(alert["clip_message_id"], segment["message_id"])


class OutboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name)/"queue.db"
        self.patch = patch.object(queue, "DB_PATH", self.db)
        self.patch.start()
        self.audit_patch = patch("service.message.publisher.EVENT_AUDIT_PATH", Path(self.temp.name)/"events.jsonl")
        self.audit_patch.start()
        self.assertTrue(queue.init_db())

    def tearDown(self):
        self.audit_patch.stop()
        self.patch.stop()
        self.temp.cleanup()

    def client(self):
        client = MQTTClient.__new__(MQTTClient)
        client.connected = True
        client.model_version = "rf-real-version"
        client.pending_acks = {}
        client.ack_lock = threading.Lock()
        client.stop_event = threading.Event()
        client.queue_wakeup = threading.Event()
        client.max_inflight, client.max_history_inflight = 24, 6
        client.client = Mock()
        client.client.publish.return_value = SimpleNamespace(rc=0)
        return client

    def test_persist_version_once_and_only_worker_publishes(self):
        client = self.client()
        event = {"message_id": "same", "event_type": "SESSION_ENDED"}
        self.assertTrue(send_message(client, "driver/vision-test/events", event))
        client.client.publish.assert_not_called()
        row = queue.get_queue()[0]
        self.assertEqual(json.loads(row[2])["model_version"], "rf-real-version")
        original = row[2]
        client.process_queue_once()
        self.assertEqual(client.client.publish.call_count, 1)
        client.process_queue_once()
        self.assertEqual(client.client.publish.call_count, 1)
        queue.mark_backfill()
        with queue.get_connection() as conn:
            self.assertEqual(conn.execute("SELECT payload FROM offline_queue").fetchone()[0], original)
        self.assertFalse(queue.add_to_queue("same", "other", original))

    def test_legacy_queue_migrates_without_losing_payload(self):
        legacy = Path(self.temp.name)/"legacy.db"
        with closing(sqlite3.connect(legacy)) as conn, conn:
            conn.execute("CREATE TABLE offline_queue (id INTEGER PRIMARY KEY, message_id TEXT UNIQUE, "
                         "topic TEXT, payload TEXT, created_at TEXT, status TEXT, retry_count INTEGER)")
            conn.execute("INSERT INTO offline_queue VALUES (1,'old','topic','{}','','PENDING',2)")
        with patch.object(queue, "DB_PATH", legacy):
            self.assertTrue(queue.init_db())
            self.assertEqual(queue.get_queue()[0][2], "{}")
            self.assertEqual(queue.get_queue()[0][-1], 1)

    def test_poison_is_retained_and_cannot_starve_next_message(self):
        queue.add_to_queue("bad", "topic", "invalid JSON", backfill=False)
        queue.add_to_queue("good", "topic", '{"message_id":"good"}', backfill=False)
        client = self.client()
        client.process_queue_once()
        self.assertEqual(client.client.publish.call_count, 1)
        with queue.get_connection() as conn:
            self.assertEqual(conn.execute("SELECT status FROM offline_queue WHERE message_id='bad'").fetchone()[0], "DEAD")

    def test_missing_ack_does_not_block_live_data_or_delete_anything(self):
        for index in range(15):
            queue.add_to_queue(f"old-{index}", "topic", json.dumps({"message_id": f"old-{index}"}), backfill=True)
        client = self.client()
        client.process_queue_once()
        self.assertEqual(len(client.pending_acks), 6)
        queue.add_to_queue("live", "driver/vision-test/events", '{"message_id":"live"}', backfill=False)
        client.process_queue_once()
        self.assertIn("live", client.pending_acks)
        with queue.get_connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM offline_queue").fetchone()[0], 16)

    def test_budget_rejects_without_deleting_pending_messages(self):
        queue.add_to_queue("first", "topic", '{"message_id":"first"}')
        with patch.dict("os.environ", {"AI_QUEUE_MAX_ROWS": "1"}):
            self.assertFalse(queue.add_to_queue("second", "topic", '{"message_id":"second"}'))
        self.assertEqual(queue.get_queue()[0][0], "first")

    def test_local_escalation_is_not_blocked_by_old_cooldown_and_can_cancel(self):
        worker = LocalAlertWorker(player=Mock())
        for index in range(3):
            self.assertTrue(worker.notify(dict(message_id=str(index), policy_version="v1",
                state="DROWSY", event_type="DROWSY_THRESHOLD_REACHED", level=index+1,
                observed_at=datetime.now(timezone.utc).isoformat())))
        worker.cancel()
        self.assertIsNone(worker.pending)

    def test_no_queue_publish_until_storage_ack_subscription_is_confirmed(self):
        client = self.client()
        client.client.subscribe.return_value = (0, 42)
        client._on_connect(client.client, None, None, 0, None)
        self.assertFalse(client.connected)
        client.client.publish.assert_not_called()
        client._on_subscribe(client.client, None, 41, [])
        self.assertFalse(client.connected)
        client._on_subscribe(client.client, None, 42, [SimpleNamespace(is_failure=True)])
        self.assertFalse(client.connected)
        client._on_subscribe(client.client, None, 42, [SimpleNamespace(is_failure=False)])
        self.assertTrue(client.connected)


if __name__ == "__main__":
    unittest.main()
