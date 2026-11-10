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

    def v2_payload(self):
        body = self.payload()
        body["ear"] = .31
        body["ai_signals"].update(schema_version="eye-mouth-v2", quality_version="region-technical-quality-v1",
            ear_available=True, eyes_available=True, eye_sleepy_probability=.51, eye_confidence=.51,
            mouth_confidence=.8, eye_quality="VALID", mouth_quality="VALID", decision_reason="RF_NEGATIVE",
            sample_age_ms=25., eye_closure_state="DISABLED")
        return body

    def test_v2_uncertain_class_keeps_ear_probabilities_and_roundtrips_without_commands(self):
        body = self.v2_payload()
        events = _save_queued_ai(self.db, self.source.device_code,
            f"driver/{self.source.device_code}/telemetry", "telemetry", body)
        updated = next(event for event in events if event["type"] == "telemetry.updated")["data"]
        self.assertEqual(updated["ear"], .31)
        self.assertEqual(updated["ai_signals"]["eye_state"], "UNKNOWN")
        self.assertEqual(updated["ai_signals"]["eye_sleepy_probability"], .51)
        snapshot = get_current_telemetry(self.source.id, User(id=1, role="Admin"), self.db)
        self.assertEqual(snapshot.ai_signals.schema_version, "eye-mouth-v2")
        self.assertEqual(snapshot.ai_signals.decision_reason, "RF_NEGATIVE")
        self.assertTrue(snapshot.ai_signals.ear_available)
        self.assertEqual(self.db.exec(select(Command)).all(), [])
        _save_queued_ai(self.db, self.source.device_code, f"driver/{self.source.device_code}/telemetry", "telemetry", body)
        self.assertEqual(len(self.db.exec(select(Telemetry)).all()), 1)

    def test_v2_rejects_stale_or_contradictory_quality_metadata(self):
        for change in ({"sample_age_ms": 501.}, {"eye_quality": "NO_FACE"},
                       {"mouth_quality": "SATURATED"}, {"eye_confidence": float("nan")},
                       {"ear_available": "true"}, {"decision_reason": "guessed-state"}):
            body = self.v2_payload(); body["ai_signals"].update(change)
            with self.assertRaises(ValueError): QueuedTelemetry.model_validate(body)
        # EAR may be observed even if no classifier result exists for this frame.
        body = self.v2_payload()
        body["ai_signals"].update(eyes_available=False, eye_sleepy_probability=None, eye_confidence=None)
        self.assertTrue(QueuedTelemetry.model_validate(body).ai_signals.ear_available)

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

    def test_v2_outside_frame_reason_survives_storage_without_mouth_evidence(self):
        body = self.v2_payload()
        body["ai_signals"].update(mouth_available=False, mar=None, yawn_probability=None,
            mouth_state="UNKNOWN", mouth_confidence=None, mouth_quality="NO_CROP",
            mouth_crop_reason="OUTSIDE_FRAME", eye_crop_reason="VALID")
        result = _save_queued_ai(self.db, self.source.device_code,
            f"driver/{self.source.device_code}/telemetry", "telemetry", body)
        self.assertEqual(result[-1]["type"], "ingest.saved")
        snapshot = get_current_telemetry(self.source.id, User(id=1, role="Admin"), self.db)
        self.assertEqual(snapshot.ai_signals.mouth_crop_reason, "OUTSIDE_FRAME")
        self.assertIsNone(snapshot.ai_signals.yawn_probability)
        body["ai_signals"]["mouth_quality"] = "VALID"
        with self.assertRaises(ValueError): QueuedTelemetry.model_validate(body)

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

    def head_payload(self):
        body = self.v2_payload()
        body["ai_signals"]["head_motion"] = dict(version="head-motion-v1", mode="OBSERVE_ONLY",
            available=True, calibrated=True, state="REPEATED_NODS", pitch_deg=1., yaw_deg=2., roll_deg=0.,
            nod_count=2, repeated_nods=True, eye_closure_supported=False)
        return body

    def test_head_motion_roundtrips_sql_realtime_and_snapshot_without_creating_commands(self):
        body = self.head_payload()
        result = _save_queued_ai(self.db, self.source.device_code,
            f"driver/{self.source.device_code}/telemetry", "telemetry", body)
        self.assertEqual(result[-1]["type"], "ingest.saved")
        realtime = next(e for e in result if e["type"] == "telemetry.updated")
        self.assertEqual(realtime["data"]["ai_signals"]["head_motion"]["nod_count"], 2)
        saved = self.db.exec(select(Telemetry)).one()
        self.assertEqual(saved.ai_signals["head_motion"], body["ai_signals"]["head_motion"])
        from app.schemas.telemetry import TelemetryHistoryItem
        history = TelemetryHistoryItem.model_validate(saved, from_attributes=True)
        self.assertEqual(history.ai_signals.head_motion.mode, "OBSERVE_ONLY")
        snapshot = get_current_telemetry(self.source.id, User(id=1, role="Admin"), self.db)
        self.assertEqual(snapshot.ai_signals.head_motion.state, "REPEATED_NODS")
        self.assertEqual(snapshot.driver_state, "UNKNOWN")
        self.assertEqual(self.db.exec(select(Command)).all(), [])

    def test_head_motion_rejects_invalid_or_stale_evidence_and_active_mode(self):
        for change in ({"pitch_deg": float("nan")}, {"mode": "ACTIVE"}, {"nod_count": True},
                       {"nod_count": 1}, {"available": False}, {"calibrated": False},
                       {"state": "UNAVAILABLE"}, {"state": "REACQUIRING"}, {"eye_closure_supported": True}, {"unknown": "field"}):
            body = self.head_payload(); body["ai_signals"]["head_motion"].update(change)
            with self.assertRaises(ValueError): QueuedTelemetry.model_validate(body)
        body = self.head_payload()
        body["ai_signals"]["head_motion"].update(state="UNAVAILABLE", available=False, pitch_deg=None,
            yaw_deg=None, roll_deg=None, nod_count=0, repeated_nods=False)
        self.assertFalse(QueuedTelemetry.model_validate(body).ai_signals.head_motion.available)
        body = self.head_payload()
        body["ai_signals"]["head_motion"].update(state="REACQUIRING", nod_count=0, repeated_nods=False)
        self.assertTrue(QueuedTelemetry.model_validate(body).ai_signals.head_motion.available)

    def test_pose_bound_eye_risk_roundtrips_db_but_measurements_never_create_commands(self):
        body=self.head_payload()
        body["driver_state"]="DROWSY"
        body["ai_signals"].update(calibration_id="a"*64,decision_reason="HEAD_EYE_CLOSURE_RISK",
            head_eye_fusion=dict(version="pose-calibrated-head-eye-v1",mode="ENABLED",state="CLOSED_RISK",
                ear_threshold=.28,risk_candidate=True,profile_sha256="b"*64))
        result=_save_queued_ai(self.db,self.source.device_code,f"driver/{self.source.device_code}/telemetry","telemetry",body)
        self.assertEqual(result[-1]["type"],"ingest.saved")
        snapshot=get_current_telemetry(self.source.id,User(id=1,role="Admin"),self.db)
        self.assertEqual(snapshot.ai_signals.head_eye_fusion.profile_sha256,"b"*64)
        self.assertEqual(snapshot.ai_signals.decision_reason,"HEAD_EYE_CLOSURE_RISK")
        self.assertEqual(self.db.exec(select(Command)).all(),[])
        for change in ({"state":"OPEN"},{"ear_threshold":None},{"ear_threshold":float("nan")},
                       {"mode":"made-up"},{"profile_sha256":"wrong"}):
            original=dict(body["ai_signals"]["head_eye_fusion"])
            body["ai_signals"]["head_eye_fusion"].update(change)
            with self.assertRaises(ValueError):QueuedTelemetry.model_validate(body)
            body["ai_signals"]["head_eye_fusion"]=original
        body["ai_signals"]["head_motion"]["state"]="REACQUIRING"
        body["ai_signals"]["head_motion"].update(nod_count=0,repeated_nods=False)
        with self.assertRaises(ValueError):QueuedTelemetry.model_validate(body)

    def test_head_down_rule_survives_storage_without_claiming_eye_closure(self):
        body=self.head_payload();body["driver_state"]="DROWSY"
        body["ai_signals"].update(decision_reason="HEAD_DOWN_RISK",head_down_policy=dict(
            version="sustained-head-down-v1",state="DOWN_RISK",risk_candidate=True,
            observed_down_seconds=3.5,enter_pitch_deg=12.,min_seconds=3.))
        body["ai_signals"]["head_motion"].update(state="LOWERED",pitch_deg=15.,nod_count=0,repeated_nods=False)
        result=_save_queued_ai(self.db,self.source.device_code,f"driver/{self.source.device_code}/telemetry","telemetry",body)
        self.assertEqual(result[-1]["type"],"ingest.saved")
        snapshot=get_current_telemetry(self.source.id,User(id=1,role="Admin"),self.db)
        self.assertEqual(snapshot.ai_signals.head_down_policy.state,"DOWN_RISK")
        self.assertEqual(snapshot.ai_signals.eye_closure_state,"DISABLED")
        self.assertEqual(self.db.exec(select(Command)).all(),[])
        for change in ({"observed_down_seconds":1.},{"state":"NORMAL"},{"observed_down_seconds":float("nan")}):
            original=dict(body["ai_signals"]["head_down_policy"])
            body["ai_signals"]["head_down_policy"].update(change)
            with self.assertRaises(ValueError):QueuedTelemetry.model_validate(body)
            body["ai_signals"]["head_down_policy"]=original


if __name__=="__main__":
    unittest.main()
