"""The shared Edge AI topics use the dedicated pre-created account."""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://postgres:test@localhost:5432/test")
os.environ.setdefault("SECRET_KEY", "test-only")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.services.mqtt_provision_service import provision_device  # noqa: E402
from app.services.mqtt_revoke_service import revoke_device  # noqa: E402


class AiAccountTest(unittest.TestCase):
    def test_ai_provision_returns_shared_topic_account(self):
        broker = MagicMock()
        broker.__enter__.return_value = broker
        broker.has_client.return_value = True
        with patch("app.services.mqtt_provision_service.BrokerSecurity", return_value=broker):
            result = provision_device(settings.AI_MQTT_USERNAME)
        self.assertEqual(result["username"], settings.AI_MQTT_USERNAME)
        self.assertEqual(result["password"], settings.AI_MQTT_PASSWORD)
        broker.create_role.assert_not_called()

    def test_ai_revoke_disables_account(self):
        broker = MagicMock()
        broker.__enter__.return_value = broker
        with patch("app.services.mqtt_revoke_service.BrokerSecurity", return_value=broker):
            revoke_device(settings.AI_MQTT_USERNAME)
        broker.command.assert_called_once_with(
            "disableClient", username=settings.AI_MQTT_USERNAME
        )
