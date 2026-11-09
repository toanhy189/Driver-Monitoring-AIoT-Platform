"""Optional eye/mouth measurements preserve the existing ingest/rule contract."""
from datetime import datetime, timezone
import unittest
from unittest.mock import patch

import test_ai_policy_v1 as fixtures
from sqlmodel import select
from app.models.telemetry import Telemetry
from app.models.command import Command
from app.models.user import User
from app.schemas.ai_telemetry import QueuedTelemetry
from app.api.routes.devices import get_current_telemetry
from app.services.mqtt_service import _save_queued_ai
from app.services.rule_engine import process_event
from app.services.command_dispatch import dispatch_command


class AiSignalsTests(unittest.TestCase):
    def setUp(self):
        fixtures.PolicyIntegrationTests.setUp(self)
        Telemetry.__table__.create(self.engine)
        self.addCleanup(lambda:fixtures.PolicyIntegrationTests.tearDown(self))

    def payload(self):
        return {"message_id":"signals-test","device_code":self.source.device_code,
            "timestamp":datetime.now(timezone.utc).isoformat(),"driver_state":"UNKNOWN",
            "face_detected":True,"model_version":"eye-mouth-test",
            "ai_signals":{"schema_version":"eye-mouth-v1","mar":.42,"mouth_state":"YAWN",
                "yawn_probability":.8,"eye_state":"UNKNOWN","eyes_available":False,
                "mouth_available":True,"experimental":True}}

    def test_storage_realtime_snapshot_and_duplicate_keep_same_measurements(self):
        body=self.payload()
        result=_save_queued_ai(self.db,self.source.device_code,f"driver/{self.source.device_code}/telemetry","telemetry",body)
        self.assertEqual(result[-1]["type"],"ingest.saved")
        realtime=next(event for event in result if event["type"]=="telemetry.updated")
        self.assertEqual(realtime["data"]["ai_signals"]["mouth_state"],"YAWN")
        self.assertFalse(realtime["data"]["ai_signals"]["eyes_available"])
        self.assertEqual(self.db.exec(select(Telemetry)).one().ai_signals["mar"],.42)
        snapshot=get_current_telemetry(self.source.id,User(id=1,role="Admin"),self.db)
        self.assertEqual(snapshot.ai_signals.mouth_state,"YAWN")
        self.assertEqual(snapshot.driver_state,"UNKNOWN")
        _save_queued_ai(self.db,self.source.device_code,f"driver/{self.source.device_code}/telemetry","telemetry",body)
        self.assertEqual(len(self.db.exec(select(Telemetry)).all()),1)
        self.assertEqual(self.db.exec(select(Command)).all(),[])

    def test_bad_measurements_rejected_without_saved_ack(self):
        for change in ({"mar":float("inf")},{"yawn_probability":1.5},{"eye_state":"NORMAL"},
                       {"eyes_available":"false"},{"password":"never-accept-extra"}):
            body=self.payload()
            body["ai_signals"].update(change)
            with self.assertRaises(ValueError):
                QueuedTelemetry.model_validate(body)
        body=self.payload();body["ai_signals"]["eye_state"]="NORMAL"
        events=_save_queued_ai(self.db,self.source.device_code,"driver/test/telemetry","telemetry",body)
        self.assertEqual(events[0]["type"],"ingest.rejected")
        self.assertEqual(self.db.exec(select(Telemetry)).all(),[])

    def test_legacy_payload_still_valid_without_signals(self):
        body=self.payload();body.pop("ai_signals")
        self.assertIsNone(QueuedTelemetry.model_validate(body).ai_signals)

    def test_readiness_requires_additive_measurements_migration(self):
        from app.services import ai_readiness
        with patch.object(ai_readiness,"engine",self.engine):
            self.assertEqual(ai_readiness.database_readiness()["missing_columns"],[])
        self.db.rollback()
        Telemetry.__table__.drop(self.engine)
        with patch.object(ai_readiness,"engine",self.engine):
            result=ai_readiness.database_readiness()
        self.assertEqual(result["missing_columns"],["telemetry.ai_signals"])
        self.assertFalse(result["database_ready"])

    def test_new_model_events_keep_existing_esp32_command_protocol(self):
        payload=fixtures.PolicyIntegrationTests.event(self,level=2,state_duration_ms=6000,model_version="eye-mouth-test")
        process_event(self.db,payload)
        command=self.db.exec(select(Command)).one()
        sent=[]
        with patch("app.services.command_dispatch.now",return_value=fixtures.Clock.now()):
            dispatch_command(self.db,command.id,publisher=lambda code,body:sent.append((code,body)) or True)
        self.assertEqual({body["command"] for _,body in sent},{"LED_ON","BUZZER_ON","MOTOR_ON"})
        self.assertEqual({body["duration"] for _,body in sent},{2000})
        for code,body in sent:
            self.assertEqual(code,self.target.device_code)
            self.assertIn("request_id",body)
            self.assertIn("expires_at_ms",body)
            self.assertNotIn("ai_signals",body)


if __name__=="__main__":
    unittest.main()
