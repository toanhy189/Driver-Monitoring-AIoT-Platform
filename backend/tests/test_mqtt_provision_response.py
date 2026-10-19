"""The provisioning API gives credentials to Admin once without saving plaintext."""

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from fastapi import Response

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://postgres:test@localhost:5432/test")
os.environ.setdefault("SECRET_KEY", "test-only")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.routes.devices import provision_mqtt_credentials  # noqa: E402
from app.models.device import Device  # noqa: E402


class Session:
    def add(self, obj):
        pass

    def commit(self):
        pass

    def refresh(self, obj):
        pass


class ProvisionResponseTest(unittest.TestCase):
    def test_credentials_only_in_provision_response(self):
        device = Device(id=2, device_code="alert-01", model="Alert")
        with patch("app.api.routes.devices.assigned_device", return_value=device), patch(
            "app.api.routes.devices.provision_device",
            return_value={"username": "alert-01", "password": "test-secret"},
        ):
            http_response = Response()
            result = provision_mqtt_credentials(
                2, response=http_response, current_user=SimpleNamespace(id=1), session=Session()
            )
        self.assertEqual(result.mqtt_username, "alert-01")
        self.assertEqual(result.mqtt_password, "test-secret")
        self.assertEqual(result.lifecycle_state, "PROVISIONED")
        self.assertEqual(http_response.headers["Cache-Control"], "no-store")
        self.assertIsNone(device.mqtt_password)
