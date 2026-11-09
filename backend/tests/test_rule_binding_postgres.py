"""Optional real row-lock checks; run with run_rule_binding_postgres.py only."""
from concurrent.futures import ThreadPoolExecutor
import os
import secrets
import threading
import unittest
from unittest.mock import patch

from sqlalchemy import text
from sqlmodel import create_engine, Session, select
import test_rule_binding as fixtures
from app.models.command import Command
from app.services import rule_binding


@unittest.skipUnless(os.getenv("RULE_BINDING_TEST_POSTGRES"), "Use run_rule_binding_postgres.py for a disposable PostgreSQL")
class PostgresRuleBinding(fixtures.RuleBindingTests):
    def setUp(self):
        url = os.environ["RULE_BINDING_TEST_POSTGRES"]
        if "/codex_rule_binding_" not in url:
            raise RuntimeError("Only a disposable rule-binding database is allowed")
        schema = "codex_rule_" + secrets.token_hex(6)
        control = create_engine(url)
        with control.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema} -clock_timeout=5000 -cstatement_timeout=10000"})
        def cleanup():
            engine.dispose()
            with control.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            control.dispose()
        self.addCleanup(cleanup)
        with patch.object(fixtures, "create_engine", return_value=engine):
            super().setUp()

    def concurrent_saves(self, requests):
        barrier = threading.Barrier(len(requests))
        def save(kwargs):
            barrier.wait(timeout=5)
            return self.save(**kwargs).status_code
        with ThreadPoolExecutor(max_workers=len(requests)) as pool:
            return sorted(pool.map(save, requests))

    def test_two_editors_cannot_both_overwrite_the_same_revision(self):
        self.save()
        snapshot = self.read()
        self.assertEqual(self.concurrent_saves([
            {"enabled": True, "snapshot": snapshot}, {"enabled": True, "snapshot": snapshot},
        ]), [200, 409])

    def test_two_cameras_cannot_concurrently_enable_the_same_actuator(self):
        self.save()
        self.save(source=self.second_source)
        self.assertEqual(self.concurrent_saves([
            {"enabled": True, "snapshot": self.read()},
            {"source": self.second_source, "enabled": True, "snapshot": self.read(self.second_source)},
        ]), [200, 409])

    def test_cancelling_siblings_preserves_a_concurrent_completed_ack(self):
        snapshot = self.armed()
        command_id, _ = self.queued(snapshot)
        entering_cancel = threading.Event()
        original = rule_binding.source_commands
        def observe(session, source_id, **options):
            if options.get("lock"):
                entering_cancel.set()
            return original(session, source_id, **options)
        with Session(self.engine) as ack_session:
            command = ack_session.exec(select(Command).where(Command.id == command_id).with_for_update()).one()
            command.dispatches = {**command.dispatches, "motor": {**command.dispatches["motor"], "status": "COMPLETED"}}
            ack_session.add(command)
            ack_session.flush()
            with patch.object(rule_binding, "source_commands", side_effect=observe), ThreadPoolExecutor(max_workers=1) as pool:
                pending = pool.submit(self.save, snapshot=snapshot, enabled=False)
                try:
                    self.assertTrue(entering_cancel.wait(timeout=5))
                finally:
                    ack_session.commit()
                self.assertEqual(pending.result(timeout=10).status_code, 200)
        with Session(self.engine) as db:
            saved = db.get(Command, command_id)
            self.assertEqual(saved.dispatches["motor"]["status"], "COMPLETED")
            self.assertEqual(saved.dispatches["led"]["dispatch_state"], "CANCELLED")


if __name__ == "__main__":
    unittest.main()
