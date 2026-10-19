import os
from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://postgres:test@localhost:5432/test")
os.environ.setdefault("SECRET_KEY", "test-only")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.rules import AiEventRequest
from app.services.mqtt_bootstrap import ensure_identity
from app.services.mqtt_security import vision_acls
from app.services.mqtt_service import process_message


class EdgeAiContractTests(unittest.TestCase):
    def test_new_event_aliases_and_distracted_observation(self):
        event = AiEventRequest.model_validate({"message_id": "message-test", "device_code": "vision-01",
            "event_type": "DISTRACTED_THRESHOLD_REACHED", "state": "DISTRACTED",
            "state_duration_ms": 3200, "timestamp": "2026-10-19T12:00:00Z"})
        self.assertEqual(event.event_id, "message-test")
        self.assertEqual(event.device_id, "vision-01")

    def test_mismatched_topic_source_is_rejected_before_db_access(self):
        with patch("app.services.mqtt_service.Session") as session:
            result = process_message("driver/vision-01/events", {"device_code": "vision-other"})
        self.assertEqual(result, [])
        session.assert_not_called()

    def test_existing_broker_role_is_updated_without_resetting_account(self):
        broker = MagicMock()
        broker.has_role.return_value = True
        broker.has_client.return_value = True
        permissions = vision_acls("vision-01", legacy=True)
        ensure_identity(broker, "vision-01", "unused-test-only", "edge-ai", permissions)
        broker.command.assert_called_once_with("modifyRole", rolename="edge-ai", acls=permissions)
        broker.create_client.assert_not_called()

    def test_vision_role_only_receives_own_storage_ack(self):
        permissions = vision_acls("vision-test")
        received = [item["topic"] for item in permissions if item["acltype"] == "publishClientReceive"]
        published = [item["topic"] for item in permissions if item["acltype"] == "publishClientSend"]
        self.assertEqual(received, ["driver/vision-test/storage_ack"])
        self.assertEqual(set(published), {f"driver/vision-test/{kind}" for kind in ("telemetry", "events", "status")})

    def test_new_config_preserves_environment_authentication(self):
        config_path = Path(__file__).resolve().parents[2] / "edge-ai/config.py"
        with patch.dict(os.environ, {"AI_DEVICE_CODE": "vision-test", "AI_MQTT_HOST": "example.test",
            "AI_MQTT_PORT": "1884", "AI_MQTT_USERNAME": "test-only", "AI_MQTT_PASSWORD": "test-only-password"}):
            config = runpy.run_path(str(config_path))
        self.assertEqual(config["MQTT_USERNAME"], "test-only")
        self.assertEqual(config["MQTT_PORT"], 1884)
        self.assertEqual(config["ACK_TOPIC"], "driver/vision-test/storage_ack")


if __name__ == "__main__":
    unittest.main()
