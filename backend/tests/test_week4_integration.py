"""Kiem tra bo sung W4 tren database va broker tam cua runner isolated."""

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.config import settings
from app.core.db import engine
from app.core.security import create_access_token
from app.main import app
from app.models.alert import Alert
from app.models.audit_log import AuditLog
from app.models.command import Command
from app.models.device import Device
from app.models.telemetry import Telemetry
from app.models.user import User
from app.models.user_device import UserDevice
from app.models.video import AiVideo
from app.services.mqtt_bootstrap import setup
from app.services.mqtt_revoke_service import revoke_device
from app.services.mqtt_security import BrokerSecurity
from app.services.mqtt_service import process_message


OBSERVATIONS = []


@unittest.skipUnless(os.getenv("W4_INTEGRATION") == "1", "Run through run_week3_integration.py")
class Week4Integration(unittest.TestCase):
    """Suite W4 tach rieng vi suite W3 chua bao phu JWT HTTP va ma tran role."""

    @classmethod
    def setUpClass(cls):
        if not engine.url.database.startswith("codex_w3_"):
            raise RuntimeError("Week 4 integration tests require a disposable codex_w3_ database")
        # W3 truoc day chi chan database; bo sung chan broker neu khong phai broker Docker tam.
        if (os.getenv("W3_BROKER_SCOPE") != "isolated disposable broker"
                or not os.getenv("W3_TEST_MQTT_DOCKER_HOST", "").startswith("codex-w3-broker-")):
            raise RuntimeError("Week 4 integration tests require the isolated disposable MQTT broker")
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def setUp(self):
        self.suffix = secrets.token_hex(6)
        self.users = {}
        self.device_code = "w4-auth-" + self.suffix
        self.alert_device_code = "w4-node-" + self.suffix
        with Session(engine) as session:
            for role in ("Admin", "Employee", "Customer"):
                user = User(
                    fullname="Week 4 test",
                    username=f"w4-{role.lower()}-{self.suffix}",
                    hash_password="unused-test-hash",
                    email=f"w4-{role.lower()}-{self.suffix}@example.test",
                    # Cot phone trong schema la VARCHAR(20); dung gia tri ngan va rieng cho tung role.
                    phone=f"{role.lower()[:2]}-{self.suffix}",
                    role=role,
                )
                session.add(user)
                session.flush()
                self.users[role] = user.id

            device = Device(
                device_code=self.device_code,
                model="Test camera",
                device_type="VISION_NODE",
                lifecycle_state="ACTIVE",
            )
            session.add(device)
            session.flush()
            self.device_id = device.id
            for role in ("Admin", "Employee"):
                session.add(UserDevice(user_id=self.users[role], device_id=self.device_id))

            # Suite W3 chua co ma tran viewer tren cac route theo device; them node rieng gan ca ba role.
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            alert_device = Device(
                device_code=self.alert_device_code,
                model="Test alert node",
                device_type="ALERT_NODE",
                lifecycle_state="ACTIVE",
                status="ONLINE",
                last_seen=now,
            )
            session.add(alert_device)
            session.flush()
            self.alert_device_id = alert_device.id
            for role in ("Admin", "Employee", "Customer"):
                session.add(UserDevice(user_id=self.users[role], device_id=self.alert_device_id))
            session.add(Telemetry(
                device_id=self.alert_device_id,
                recorded_at=now,
                ear=0.2,
                perclos=0.1,
                driver_state="ATTENTIVE",
                face_detected=True,
                model_version="w4-test",
            ))
            alert = Alert(
                device_id=self.alert_device_id,
                alert_type="W4_TEST",
                description="Disposable role-matrix fixture",
                severity="1",
            )
            session.add(alert)
            session.flush()
            self.alert_id = alert.id
            session.commit()

    def auth(self, role):
        token = create_access_token(self.users[role], timedelta(minutes=5))
        return {"Authorization": "Bearer " + token}

    def test_jwt_invalid_expired_and_missing_are_rejected(self):
        """Kiem tra token sai, het han va vang mat deu bi tu choi, khong lo username."""
        # Suite W3 truoc day dung token hop le; bo sung ba truong hop JWT HTTP khong hop le.
        expired = create_access_token(self.users["Admin"], timedelta(seconds=-1))
        headers = (
            {"Authorization": "Bearer not-a-valid-jwt"},
            {"Authorization": "Bearer " + expired},
            {},
        )
        actual_statuses = []
        usernames_exposed = []
        for request_headers in headers:
            with self.subTest(headers_present=bool(request_headers)):
                response = self.client.get("/api/me", headers=request_headers)
                actual_statuses.append(response.status_code)
                usernames_exposed.append("username" in response.json())
                self.assertEqual(response.status_code, 401, response.text)
                self.assertFalse(usernames_exposed[-1])
        # Truoc day evidence ghi cung mot ket qua co dinh; luu status thuc te de khong bao PASS sai.
        OBSERVATIONS.append({
            "case": "JWT HTTP invalid, expired, and missing token",
            "expected": 401,
            "actual": actual_statuses,
            "username_exposed": usernames_exposed,
            "result": "PASS" if actual_statuses == [401, 401, 401] and not any(usernames_exposed) else "FAIL",
        })

    def test_role_and_assignment_matrix_for_users_and_devices(self):
        """Kiem tra quyen users, danh sach device va chi tiet theo role va assignment."""
        # Suite W3 truoc day kiem tra tung phan; bo sung ma tran ba role trong cung fixture.
        actual = {"users": {}, "devices": {}, "device_detail": {}, "device_visible": {}}
        for role, expected_users in (("Admin", 200), ("Employee", 403), ("Customer", 403)):
            with self.subTest(role=role, endpoint="users"):
                users_response = self.client.get("/api/users", headers=self.auth(role))
                actual["users"][role] = users_response.status_code
                self.assertEqual(users_response.status_code, expected_users, users_response.text)

            with self.subTest(role=role, endpoint="devices"):
                devices_response = self.client.get("/api/devices", headers=self.auth(role))
                actual["devices"][role] = devices_response.status_code
                self.assertEqual(devices_response.status_code, 200, devices_response.text)
                device_ids = {item["id"] for item in devices_response.json()}
                actual["device_visible"][role] = self.device_id in device_ids
                if role == "Customer":
                    self.assertNotIn(self.device_id, device_ids)
                    detail = self.client.get(
                        f"/api/devices/{self.device_id}",
                        headers=self.auth(role),
                    )
                    actual["device_detail"][role] = detail.status_code
                    self.assertEqual(detail.status_code, 404, detail.text)
                else:
                    self.assertIn(self.device_id, device_ids)
                    detail = self.client.get(
                        f"/api/devices/{self.device_id}",
                        headers=self.auth(role),
                    )
                    actual["device_detail"][role] = detail.status_code
                    self.assertEqual(detail.status_code, 200, detail.text)

        # 403 truoc day chi assert status; doi chieu them actor va route trong audit.
        with Session(engine) as session:
            denied_audits = session.exec(
                select(AuditLog).where(
                    AuditLog.action == "PERMISSION_DENIED",
                    AuditLog.user_id.in_([self.users["Employee"], self.users["Customer"]]),
                )
            ).all()
        self.assertEqual(len(denied_audits), 2)
        self.assertEqual({row.details["path"] for row in denied_audits}, {"/api/users"})
        self.assertTrue(all(row.details["result"] == "denied" for row in denied_audits))

        expected = {
            "users": {"Admin": 200, "Employee": 403, "Customer": 403},
            "devices": {"Admin": 200, "Employee": 200, "Customer": 200},
            "device_detail": {"Admin": 200, "Employee": 200, "Customer": 404},
            "device_visible": {"Admin": True, "Employee": True, "Customer": False},
        }
        # Truoc day evidence ghi expected thay cho actual; doi sang doi chieu toan bo ma tran thuc te.
        OBSERVATIONS.append({
            "case": "Admin, Employee, Customer role and assignment matrix",
            "expected": expected,
            "actual": actual,
            "result": "PASS" if actual == expected else "FAIL",
        })

    def test_admin_can_access_unassigned_devices_and_lookup_user_assignments(self):
        """Admin xem/toan quyen device; endpoint user tra ve assignment dang hieu luc."""
        unassigned = Device(
            device_code="w4-unassigned-" + self.suffix,
            model="Unassigned camera",
            device_type="VISION_NODE",
            lifecycle_state="REGISTERED",
            status="OFFLINE",
        )
        with Session(engine) as session:
            session.add(unassigned)
            session.commit()
            session.refresh(unassigned)
            unassigned_id = unassigned.id

        admin_devices = self.client.get("/api/devices", headers=self.auth("Admin"))
        employee_devices = self.client.get("/api/devices", headers=self.auth("Employee"))
        admin_detail = self.client.get(f"/api/devices/{unassigned_id}", headers=self.auth("Admin"))
        employee_detail = self.client.get(f"/api/devices/{unassigned_id}", headers=self.auth("Employee"))
        admin_status = self.client.patch(
            f"/api/devices/{unassigned_id}/status",
            headers=self.auth("Admin"),
            json={"status": "ONLINE"},
        )
        customer_assignments = self.client.get(
            f"/api/users/{self.users['Customer']}/devices",
            headers=self.auth("Admin"),
        )
        customer_status = self.client.patch(
            f"/api/devices/{self.alert_device_id}/status",
            headers=self.auth("Customer"),
            json={"status": "OFFLINE"},
        )
        employee_status = self.client.patch(
            f"/api/devices/{self.alert_device_id}/status",
            headers=self.auth("Employee"),
            json={"status": "OFFLINE"},
        )
        self.assertEqual(admin_devices.status_code, 200, admin_devices.text)
        self.assertIn(unassigned_id, {item["id"] for item in admin_devices.json()})
        self.assertNotIn(unassigned_id, {item["id"] for item in employee_devices.json()})
        self.assertEqual(admin_detail.status_code, 200, admin_detail.text)
        self.assertEqual(employee_detail.status_code, 404, employee_detail.text)
        self.assertEqual(admin_status.status_code, 200, admin_status.text)
        self.assertEqual(admin_status.json()["status"], "ONLINE")
        self.assertEqual(customer_assignments.status_code, 200, customer_assignments.text)
        self.assertEqual(
            {item["id"] for item in customer_assignments.json()},
            {self.alert_device_id},
        )
        self.assertEqual(customer_status.status_code, 403, customer_status.text)
        self.assertEqual(employee_status.status_code, 200, employee_status.text)
        self.assertEqual(employee_status.json()["status"], "OFFLINE")

    def test_viewer_endpoint_and_assignment_matrix(self):
        """Kiem tra viewer doc cac endpoint duoc gan va bi tu choi voi device chua gan."""
        # Truc day chi test viewer tren users/devices; mo rong sang cac route doc theo device.
        routes = {
            "device_config": f"/devices/{self.alert_device_id}/config",
            "legacy_config": f"/configs/{self.alert_device_code}",
            "current_telemetry": f"/{self.alert_device_id}/telemetry",
            "legacy_telemetry_history": f"/{self.alert_device_id}/telemetry/history",
            "telemetry_history": f"/devices/{self.alert_device_id}/telemetry/history",
            "command_history": f"/devices/{self.alert_device_id}/history",
            "timeline": f"/devices/{self.alert_device_id}/timeline",
            "metrics": f"/devices/{self.alert_device_id}/metrics",
            "alerts": f"/alerts?device_id={self.alert_device_id}",
            "commands": f"/commands?device_id={self.alert_device_id}",
            "videos": f"/devices/{self.alert_device_id}/videos",
        }
        actual = {}
        for role in ("Admin", "Employee", "Customer"):
            actual[role] = {}
            for name, path in routes.items():
                with self.subTest(role=role, route=name):
                    response = self.client.get("/api" + path, headers=self.auth(role))
                    actual[role][name] = response.status_code
                    self.assertEqual(response.status_code, 200, response.text)

        unassigned_routes = {
            "device_config": f"/devices/{self.device_id}/config",
            "legacy_config": f"/configs/{self.device_code}",
            "current_telemetry": f"/{self.device_id}/telemetry",
            "legacy_telemetry_history": f"/{self.device_id}/telemetry/history",
            "telemetry_history": f"/devices/{self.device_id}/telemetry/history",
            "command_history": f"/devices/{self.device_id}/history",
            "timeline": f"/devices/{self.device_id}/timeline",
            "metrics": f"/devices/{self.device_id}/metrics",
            "alerts": f"/alerts?device_id={self.device_id}",
            "commands": f"/commands?device_id={self.device_id}",
            "videos": f"/devices/{self.device_id}/videos",
        }
        actual["Customer_unassigned"] = {}
        for name, path in unassigned_routes.items():
            with self.subTest(role="Customer", unassigned_route=name):
                response = self.client.get("/api" + path, headers=self.auth("Customer"))
                actual["Customer_unassigned"][name] = response.status_code
                self.assertEqual(response.status_code, 404, response.text)

        expected = {
            role: {name: 200 for name in routes}
            for role in ("Admin", "Employee", "Customer")
        }
        expected["Customer_unassigned"] = {name: 404 for name in unassigned_routes}
        self.assertEqual(actual, expected)
        OBSERVATIONS.append({
            "case": "Viewer routes and unassigned-device access matrix",
            "expected": expected,
            "actual": actual,
            "result": "PASS" if actual == expected else "FAIL",
        })

    def test_operator_and_admin_endpoint_permissions(self):
        """Kiem tra role duoc phep sua config, acknowledge alert, gui command va sua rule."""
        # Chua co ma tran quyen tren config, alert acknowledge, command va rule routes.
        timings = {
            output: {
                str(level): {"on_ms": 100, "off_ms": 100}
                for level in (1, 2, 3)
            }
            for output in ("led", "buzzer", "motor")
        }
        actual = {"config_update": {}, "alert_acknowledge": {}, "command_create": {},
                  "rule_read": {}, "rule_update": {}}

        # Mock publisher de test command/config khong gui lenh toi bat ky broker hay hardware nao.
        with patch("app.api.routes.configs.publish_config", return_value=True):
            for role, expected_status in (("Admin", 200), ("Employee", 200), ("Customer", 403)):
                response = self.client.put(
                    f"/api/devices/{self.alert_device_id}/config",
                    headers=self.auth(role),
                    json={"timings": timings},
                )
                actual["config_update"][role] = response.status_code
                self.assertEqual(response.status_code, expected_status, response.text)

        for role, expected_status in (("Admin", 200), ("Employee", 200), ("Customer", 403)):
            response = self.client.post(
                f"/api/alerts/{self.alert_id}/acknowledge",
                headers=self.auth(role),
            )
            actual["alert_acknowledge"][role] = response.status_code
            self.assertEqual(response.status_code, expected_status, response.text)

        with patch("app.api.routes.commands.publish_command", return_value=True):
            for role, expected_status in (("Admin", 201), ("Employee", 201), ("Customer", 403)):
                response = self.client.post(
                    f"/api/devices/{self.alert_device_id}/commands",
                    headers=self.auth(role),
                    json={
                        "action": "TEST_ALERT",
                        "buzzer_ms": 100,
                        "vibration_ms": 100,
                        "led_mode": "ON",
                    },
                )
                actual["command_create"][role] = response.status_code
                self.assertEqual(response.status_code, expected_status, response.text)

        for role, expected_status in (("Admin", 200), ("Employee", 403), ("Customer", 403)):
            response = self.client.get(
                f"/api/devices/{self.device_id}/rule",
                headers=self.auth(role),
            )
            actual["rule_read"][role] = response.status_code
            self.assertEqual(response.status_code, expected_status, response.text)

        for role, expected_status in (("Admin", 200), ("Employee", 403), ("Customer", 403)):
            response = self.client.put(
                f"/api/devices/{self.device_id}/rule",
                headers=self.auth(role),
                json={"target_device_id": self.alert_device_id, "enabled": False},
            )
            actual["rule_update"][role] = response.status_code
            self.assertEqual(response.status_code, expected_status, response.text)

        with Session(engine) as session:
            command_children = [
                (command.created_by_user_id, child["request_id"])
                for command in session.exec(
                    select(Command).where(Command.device_id == self.alert_device_id)
                ).all()
                for child in (command.dispatches or {}).values()
            ]
        # Test command truoc day mock publish; xu ly ACK tren broker path isolated de test audit.
        for _, child_request_id in command_children:
            process_message(
                f"driver/{self.alert_device_code}/ack",
                {"request_id": child_request_id, "status": "COMPLETED"},
            )
        with Session(engine) as session:
            action_rows = session.exec(
                select(AuditLog).where(
                    AuditLog.user_id.in_([self.users["Admin"], self.users["Employee"]])
                )
            ).all()
        required_audit_actions = {
            "UPDATE_CONFIG",
            "ACKNOWLEDGE_ALERT",
            "TEST_ALERT",
            "UPDATE_RULE_BINDING",
            "COMMAND_ACK_UPDATED",
        }
        found_audit_actions = {row.action for row in action_rows}
        self.assertTrue(required_audit_actions <= found_audit_actions)
        OBSERVATIONS.append({
            "case": "Config, alert, command, ACK and rule audit actions",
            "purpose": "Xac nhan cac thao tac API va MQTT ACK duoc luu actor/action",
            "expected": sorted(required_audit_actions),
            "actual": sorted(required_audit_actions & found_audit_actions),
            "result": "PASS" if required_audit_actions <= found_audit_actions else "FAIL",
        })

        expected = {
            "config_update": {"Admin": 200, "Employee": 200, "Customer": 403},
            "alert_acknowledge": {"Admin": 200, "Employee": 200, "Customer": 403},
            "command_create": {"Admin": 201, "Employee": 201, "Customer": 403},
            "rule_read": {"Admin": 200, "Employee": 403, "Customer": 403},
            "rule_update": {"Admin": 200, "Employee": 403, "Customer": 403},
        }
        OBSERVATIONS.append({
            "case": "Operator and admin mutation permission matrix",
            "expected": expected,
            "actual": actual,
            "result": "PASS" if actual == expected else "FAIL",
        })

    def test_device_lifecycle_requires_admin_or_owner_and_allows_valid_transitions(self):
        """Kiem tra Admin/owner duoc doi lifecycle va role khong so huu bi tu choi."""
        # Suite truoc day chi test mot so ket qua lifecycle; bo sung quyen dang ky va chuoi chuyen trang thai.
        lifecycle_code = "w4-life-" + self.suffix
        actual = {}
        role_headers = {
            role: self.auth(role)
            for role in ("Employee", "Customer")
        }
        registration = {"device_code": lifecycle_code, "model": "Lifecycle test device"}
        for role, headers in role_headers.items():
            response = self.client.post("/api/devices/register", headers=headers, json=registration)
            actual[f"register_{role}"] = response.status_code
            self.assertEqual(response.status_code, 403, response.text)
        registered = self.client.post(
            "/api/devices/register",
            headers=self.auth("Admin"),
            json=registration,
        )
        actual["register_Admin"] = registered.status_code
        self.assertEqual(registered.status_code, 201, registered.text)
        lifecycle_device_id = registered.json()["device"]["id"]

        endpoints = {
            "provision": ("post", f"/api/devices/{lifecycle_device_id}/provision", None),
            "activate_provisioned": ("post", f"/api/devices/{lifecycle_device_id}/activate", None),
            "maintenance": ("post", f"/api/devices/{lifecycle_device_id}/maintenance", None),
            "activate_maintenance": ("post", f"/api/devices/{lifecycle_device_id}/activate", None),
            "status": ("patch", f"/api/devices/{lifecycle_device_id}/status", {"status": "OFFLINE"}),
            "decommission": ("post", f"/api/devices/{lifecycle_device_id}/decommission", None),
        }
        with patch(
            "app.api.routes.devices.provision_device",
            return_value={"username": lifecycle_code, "password": "temporary-test-credential"},
        ), patch("app.api.routes.devices.revoke_device", return_value={"revoked": True}):
            for phase in endpoints:
                method, path, body = endpoints[phase]
                for role, headers in role_headers.items():
                    if body is None:
                        response = getattr(self.client, method)(path, headers=headers)
                    else:
                        response = getattr(self.client, method)(path, headers=headers, json=body)
                    actual[f"{phase}_{role}"] = response.status_code
                    self.assertEqual(response.status_code, 403, response.text)

                if body is None:
                    response = getattr(self.client, method)(path, headers=self.auth("Admin"))
                else:
                    response = getattr(self.client, method)(path, headers=self.auth("Admin"),
                                                             json=body)
                expected_status = 200
                actual[f"{phase}_Admin"] = response.status_code
                self.assertEqual(response.status_code, expected_status, response.text)

        # Lifecycle truoc day chi assert state cuoi; xac nhan lich su va redaction audit.
        with Session(engine) as session:
            device = session.get(Device, lifecycle_device_id)
            self.assertEqual(device.lifecycle_state, "DECOMMISSIONED")
            self.assertEqual(device.status, "OFFLINE")
            self.assertIsNone(device.mqtt_username)
            lifecycle_audits = session.exec(
                select(AuditLog).where(
                    AuditLog.entity_type == "Device",
                    AuditLog.entity_id == str(lifecycle_device_id),
                )
            ).all()
        expected_audit_actions = {
            "REGISTER_DEVICE",
            "PROVISION_DEVICE_CREDENTIALS",
            "ACTIVATE_DEVICE",
            "DEVICE_MAINTENANCE",
            "UPDATE_DEVICE_STATUS",
            "DECOMMISSION_DEVICE",
        }
        self.assertEqual({row.action for row in lifecycle_audits}, expected_audit_actions)
        self.assertNotIn(
            "temporary-test-credential",
            json.dumps([row.details for row in lifecycle_audits]),
        )
        OBSERVATIONS.append({
            "case": "Admin or assigned-owner device lifecycle and valid transitions",
            "purpose": "Kiem tra Admin/owner thao tac duoc va role khong so huu bi tu choi",
            "expected": {
                **{f"register_{role}": (201 if role == "Admin" else 403)
                   for role in ("Admin", "Employee", "Customer")},
                **{f"{phase}_{role}": (200 if role == "Admin" else 403)
                for phase in endpoints
                for role in ("Admin", "Employee", "Customer")},
            },
            "actual": actual,
            "result": "PASS",
        })

    def test_video_content_requires_device_assignment(self):
        """Kiem tra tai video chi thanh cong voi user duoc gan thiet bi."""
        # Suite truoc day test metadata/download mot phan; bo sung endpoint tra noi dung video theo assignment.
        content = b"\x00\x00\x00\x18ftypisomW4-test-video"
        with tempfile.TemporaryDirectory(prefix="w4-video-content-") as directory:
            with patch.object(settings, "AI_VIDEO_DIR", Path(directory)):
                video = AiVideo(
                    device_id=self.device_id,
                    message_id="w4-video-" + self.suffix,
                    state="ATTENTIVE",
                    storage_key="w4-video-" + self.suffix + ".mp4",
                    sha256=hashlib.sha256(content).hexdigest(),
                    size_bytes=len(content),
                )
                with Session(engine) as session:
                    session.add(video)
                    session.commit()
                    session.refresh(video)
                    video_id = video.id
                (Path(directory) / video.storage_key).write_bytes(content)

                actual = {}
                for role in ("Admin", "Employee"):
                    response = self.client.get(
                        f"/api/videos/{video_id}/content",
                        headers=self.auth(role),
                    )
                    actual[role] = response.status_code
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(response.content, content)

                unassigned = self.client.get(
                    f"/api/videos/{video_id}/content",
                    headers=self.auth("Customer"),
                )
                actual["Customer_unassigned"] = unassigned.status_code
                self.assertEqual(unassigned.status_code, 404, unassigned.text)

                unauthenticated = self.client.get(f"/api/videos/{video_id}/content")
                actual["missing_token"] = unauthenticated.status_code
                self.assertEqual(unauthenticated.status_code, 401, unauthenticated.text)
                # Download truoc day chi assert response; doi chieu actor trong audit.
                with Session(engine) as session:
                    download_audits = session.exec(
                        select(AuditLog).where(
                            AuditLog.action == "DOWNLOAD_VIDEO",
                            AuditLog.entity_id == str(video_id),
                        )
                    ).all()
                self.assertEqual(
                    {row.user_id for row in download_audits},
                    {self.users["Admin"], self.users["Employee"]},
                )

        expected = {
            "Admin": 200,
            "Employee": 200,
            "Customer_unassigned": 404,
            "missing_token": 401,
        }
        self.assertEqual(actual, expected)
        OBSERVATIONS.append({
            "case": "Video content authentication and assignment matrix",
            "purpose": "Verify assigned users can download, unassigned users cannot, and anonymous access is rejected",
            "expected": expected,
            "actual": actual,
            "result": "PASS" if actual == expected else "FAIL",
        })

    # Login/permission truoc day chua duoc kiem tra audit; bo sung va xac nhan khong luu secret.
    def test_login_and_permission_audit_are_secret_safe(self):
        """Kiem tra login va tu choi quyen tao audit ma khong luu token hay mat khau."""
        username = f"w4-customer-{self.suffix}"
        password = "w4-audit-test-secret"
        with patch(
            "app.api.routes.users.acs.verify_password",
            side_effect=(True, False),
        ):
            login_success = self.client.post(
                "/api/login",
                json={"username": username, "password": password},
            )
            login_failure = self.client.post(
                "/api/login",
                json={"username": username, "password": password},
            )

        self.assertEqual(login_success.status_code, 200, login_success.text)
        self.assertEqual(login_failure.status_code, 401, login_failure.text)
        token = login_success.json()["access_token"]
        denied = self.client.get("/api/users", headers=self.auth("Customer"))
        self.assertEqual(denied.status_code, 403, denied.text)

        with Session(engine) as session:
            audits = session.exec(
                select(AuditLog).where(AuditLog.user_id == self.users["Customer"])
            ).all()
        actions = {row.action for row in audits}
        serialized = json.dumps([row.details for row in audits])
        self.assertTrue({"LOGIN_SUCCESS", "LOGIN_FAILED", "PERMISSION_DENIED"} <= actions)
        self.assertNotIn(password, serialized)
        self.assertNotIn(token, serialized)
        self.assertTrue(all(row.details.get("correlation_id") for row in audits
                            if row.action in {"LOGIN_SUCCESS", "LOGIN_FAILED", "PERMISSION_DENIED"}))
        self.assertTrue(all("password" not in key.lower() for row in audits
                            for key in (row.details or {})))
        OBSERVATIONS.append({
            "case": "Login and permission audit redaction",
            "purpose": "Xac nhan login va tu choi quyen duoc audit ma khong luu password hay token",
            "expected": ["LOGIN_SUCCESS", "LOGIN_FAILED", "PERMISSION_DENIED"],
            "actual": sorted(actions),
            "result": "PASS",
        })

    def test_revoked_ai_account_stays_disabled_after_setup(self):
        """Kiem tra chay lai MQTT setup khong tu kich hoat lai tai khoan AI da thu hoi."""
        # Setup W3 truoc day chi chay lap lai; bo sung kiem tra identity AI bi thu hoi khong duoc mo lai.
        try:
            with BrokerSecurity() as broker:
                before = broker.command("getClient", username=settings.AI_MQTT_USERNAME)
                self.assertFalse(before.get("client", {}).get("disabled", False))

            revoke_device(settings.AI_DEVICE_CODE)
            setup()

            with BrokerSecurity() as broker:
                after = broker.command("getClient", username=settings.AI_MQTT_USERNAME)
                self.assertTrue(after.get("client", {}).get("disabled", False))
        finally:
            # Broker nay la broker tam; khoi phuc identity de ACL suite tiep theo chay duoc.
            with BrokerSecurity() as broker:
                if broker.has_client(settings.AI_MQTT_USERNAME):
                    broker.delete_client(settings.AI_MQTT_USERNAME)
            setup()

        OBSERVATIONS.append({
            "case": "Revoked AI broker identity remains disabled after setup",
            "expected": "disabled after setup",
            "actual": "disabled after setup",
            "result": "PASS",
        })


class Week4EvidenceResult(unittest.TextTestResult):
    # Suite W3 ghi JSON rieng; suite W4 cung can evidence doc lap de khong ghi de ket qua cu.
    def addSuccess(self, test):
        OBSERVATIONS.append({"case": test.id(), "result": "PASS"})
        super().addSuccess(test)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Week4Integration)
    result = unittest.TextTestRunner(verbosity=2, resultclass=Week4EvidenceResult).run(suite)
    evidence = Path(os.environ["W4_EVIDENCE"])
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "week4-integration-results.json").write_text(
        json.dumps(
            {
                "tests_run": result.testsRun,
                "executed_at": datetime.now(timezone.utc).isoformat(),
                "scope": "Disposable codex_w3_ database and isolated Docker MQTT broker; no hardware",
                "failures": len(result.failures),
                "errors": len(result.errors),
                "skipped": len(result.skipped),
                # Chi ghi ten test loi, tranh dua traceback/co the chua du lieu noi bo vao JSON.
                "failed_tests": [test.id() for test, _ in result.failures + result.errors],
                "observations": OBSERVATIONS,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    raise SystemExit(0 if result.wasSuccessful() else 1)
