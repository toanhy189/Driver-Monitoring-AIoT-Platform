"""Checks that merging the week-2 backend preserves the existing FE entry points."""

import os
import sys
import unittest
from pathlib import Path

from fastapi import HTTPException

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://postgres:test@localhost:5432/test"
)
os.environ.setdefault("SECRET_KEY", "merge-contract-test-only")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.deps import require_admin, require_operator  # noqa: E402
from app.api.routes.devices import get_all_device, get_current_telemetry  # noqa: E402
from app.api.routes.users import login  # noqa: E402
from app.core.security import decode_access_token, get_password_hash  # noqa: E402
from app.main import app  # noqa: E402
from app.models.device import Device  # noqa: E402
from app.models.telemetry import Telemetry  # noqa: E402
from app.models.user import User  # noqa: E402
from app.schemas.device import DeviceResponse  # noqa: E402
from app.schemas.user import LoginRequest  # noqa: E402


class Result:
    def __init__(self, value):
        self.value = value

    def first(self):
        return self.value

    def all(self):
        return self.value


class FakeSession:
    def __init__(self, value, device=None):
        self.value = value
        self.device = device
        self.statement = None

    def exec(self, statement):
        self.statement = statement
        return Result(self.value)

    def get(self, model, device_id):
        return self.device


class MergeContractTests(unittest.TestCase):
    def test_existing_fe_routes_are_kept(self):
        http_routes = {
            (route.path, method)
            for route in app.routes
            for method in getattr(route, "methods", [])
        }
        for path_and_method in (
            ("/api/login", "POST"),
            ("/api/me", "GET"),
            ("/api/devices", "GET"),
            ("/api/1/telemetry", "GET"),
        ):
            path, method = path_and_method
            expected_path = "/api/{device_id}/telemetry" if path == "/api/1/telemetry" else path
            self.assertIn((expected_path, method), http_routes)
        self.assertIn("/ws/telemetry", [route.path for route in app.routes])

    def test_login_still_accepts_json_schema_and_returns_user_id_token(self):
        user = User(
            id=7, fullname="Admin", username="admin",
            hash_password=get_password_hash("test-password"),
            email="admin@example.test", phone="000", role="Admin",
        )
        result = login(LoginRequest(username="admin", password="test-password"), FakeSession(user))
        self.assertEqual(decode_access_token(result.access_token), "7")

    def test_existing_role_names_are_authorized(self):
        admin = User(id=1, fullname="A", username="a", hash_password="x",
                     email="a@example.test", phone="1", role="Admin")
        employee = User(id=2, fullname="E", username="e", hash_password="x",
                        email="e@example.test", phone="2", role="Employee")
        self.assertIs(require_admin(admin), admin)
        self.assertIs(require_operator(employee), employee)

    def test_device_list_filters_by_user_and_active_assignment(self):
        session = FakeSession([])
        self.assertEqual(get_all_device(session=session, user_id=7), [])
        sql = str(session.statement.compile(compile_kwargs={"literal_binds": True}))
        self.assertIn("user_devices.user_id = 7", sql)
        self.assertIn("user_devices.unassigned_at IS NULL", sql)

    def test_telemetry_is_serializable_or_explicitly_missing(self):
        device = Device(id=1, device_code="vision-01", model="Vision V1")
        telemetry = Telemetry(device_id=1, ear=0.25, perclos=0.18)
        result = get_current_telemetry(1, 7, FakeSession(telemetry, device))
        self.assertEqual(result.device_code, "vision-01")
        self.assertEqual(result.ear, 0.25)
        with self.assertRaises(HTTPException) as missing:
            get_current_telemetry(1, 7, FakeSession(None, device))
        self.assertEqual(missing.exception.status_code, 404)

    def test_device_response_does_not_expose_mqtt_password(self):
        device = Device(id=1, device_code="alert-01", model="Alert V1",
                        mqtt_password="not-for-api")
        response = DeviceResponse.model_validate(device, from_attributes=True).model_dump()
        self.assertNotIn("mqtt_password", response)


if __name__ == "__main__":
    unittest.main()
