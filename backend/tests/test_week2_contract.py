"""Focused checks for the FE/BE boundary and existing MQTT devices."""

import asyncio
import json
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://postgres:test@localhost:5432/test")
os.environ.setdefault("SECRET_KEY", "week2-test-only")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.deps import require_admin, require_operator, require_viewer  # noqa: E402
from app.main import app  # noqa: E402
from app.models.command import Command  # noqa: E402
from app.models.device import Device  # noqa: E402
from app.models.telemetry import Telemetry  # noqa: E402
from app.models.alert import Alert  # noqa: E402
from app.models.config import Config  # noqa: E402
from app.models.audit_log import AuditLog  # noqa: E402
from app.models.user_device import UserDevice  # noqa: E402
from app.schemas.command import TestAlertRequest as AlertTestRequest  # noqa: E402
from app.schemas.config import validate_timings  # noqa: E402
from app.schemas.device import DeviceResponse  # noqa: E402
from app.services.command_state import aggregate, update_dispatch  # noqa: E402
from app.services.config_publish_service import publish_config  # noqa: E402
from app.api.routes.commands import _publish_actions  # noqa: E402
from app.api.routes.configs import ConfigUpdateRequest, _snapshot, update_device_config  # noqa: E402
from app.services.mqtt_service import _save_ack, _save_applied_config, process_message  # noqa: E402
from app.services.websocket_manager import ConnectionManager  # noqa: E402
from app.services.ws_tickets import consume_ticket, issue_ticket  # noqa: E402


class Result:
    def __init__(self, value):
        self.value = value

    def first(self):
        return self.value

    def all(self):
        return self.value

    def one(self):
        return self.value


class FakeSession:
    def __init__(self, command=None, device=None):
        self.command = command
        self.device = device
        self.commits = 0

    def exec(self, statement):
        if statement.column_descriptions[0].get("entity") is Device:
            return Result(self.device)
        return Result(self.command)

    def get(self, model, identifier):
        if model is Command:
            return self.command
        return self.device

    def add(self, value):
        pass

    def commit(self):
        self.commits += 1

    def refresh(self, value):
        pass


class Week2ContractTests(unittest.TestCase):
    def test_each_http_method_and_path_has_one_handler(self):
        routes = [(method, route.path) for route in app.routes
                  for method in getattr(route, "methods", ())]
        self.assertEqual(len(routes), len(set(routes)))

    def test_config_ranges_match_current_firmware(self):
        for field, minimum, maximum in (("on_ms", 50, 5000), ("off_ms", 50, 10000)):
            for value in (minimum, maximum, minimum - 1, maximum + 1, True):
                timings = {output: {str(level): {"on_ms": 100, "off_ms": 200}
                           for level in (1, 2, 3)} for output in ("led", "buzzer", "motor")}
                timings["led"]["1"][field] = value
                with self.subTest(field=field, value=value):
                    if type(value) is int and minimum <= value <= maximum:
                        self.assertEqual(validate_timings(timings)["led"]["1"][field], value)
                    else:
                        with self.assertRaises(HTTPException) as rejected:
                            validate_timings(timings)
                        self.assertEqual(rejected.exception.status_code, 422)

    def test_openapi_operation_ids_are_unique_for_alias_routes(self):
        schema = app.openapi()
        identifiers = [operation["operationId"] for methods in schema["paths"].values()
                       for operation in methods.values() if isinstance(operation, dict) and "operationId" in operation]
        self.assertEqual(len(identifiers), len(set(identifiers)))

    def test_config_publish_is_retained_qos_one_and_addressed_to_device(self):
        payload = {"config_id": "cfg-123", "timings": {}}
        with patch("app.services.config_publish_service.mqtt.Client") as factory:
            client = factory.return_value
            client.publish.return_value.is_published.return_value = True
            self.assertTrue(publish_config("alert-01", payload))
        topic, body = client.publish.call_args.args
        self.assertEqual(topic, "driver/alert-01/config/update")
        self.assertEqual(json.loads(body), {"device_code": "alert-01", **payload})
        self.assertEqual(client.publish.call_args.kwargs, {"qos": 1, "retain": True})

    def test_database_timestamp_columns_accept_naive_utc_values(self):
        for model, fields in (
            (Command, ("created_at", "executed_at")),
            (Device, ("created_at", "last_seen")),
            (Telemetry, ("recorded_at",)),
            (Alert, ("created_at",)),
            (Config, ("updated_at",)),
            (AuditLog, ("created_at",)),
            (UserDevice, ("assigned_at", "unassigned_at")),
        ):
            for field in fields:
                self.assertFalse(model.__table__.c[field].type.timezone, f"{model.__name__}.{field}")

    def test_fe_routes_exist_with_expected_methods(self):
        routes = {
            (route.path, method)
            for route in app.routes
            for method in getattr(route, "methods", [])
        }
        for route in (
            ("/api/login", "POST"),
            ("/api/me", "GET"),
            ("/api/devices", "GET"),
            ("/api/devices", "POST"),
            ("/api/devices/{device_id}", "GET"),
            ("/api/devices/{device_id}/provision", "POST"),
            ("/api/devices/{device_id}/activate", "POST"),
            ("/api/devices/{device_id}/maintenance", "POST"),
            ("/api/devices/{device_id}/decommission", "POST"),
            ("/api/devices/{device_id}/commands", "POST"),
            ("/api/devices/{device_id}/config", "GET"),
            ("/api/devices/{device_id}/config", "PUT"),
            ("/api/commands", "GET"),
            ("/api/commands/{request_id}", "GET"),
            ("/api/alerts", "GET"),
            ("/api/alerts/{alert_id}/acknowledge", "POST"),
            ("/api/ws-ticket", "POST"),
        ):
            self.assertIn(route, routes)

    def test_customer_cannot_send_and_command_body_is_strict(self):
        with self.assertRaises(HTTPException) as blocked:
            require_operator(SimpleNamespace(role="Customer"))
        self.assertEqual(blocked.exception.status_code, 403)
        with self.assertRaises(ValueError):
            AlertTestRequest(action="TEST_ALERT", buzzer_ms=True,
                             vibration_ms=1000, led_mode="FLASH")
        with self.assertRaises(ValueError):
            AlertTestRequest(action="TEST_ALERT", buzzer_ms=0,
                             vibration_ms=1000, led_mode="FLASH")

    def test_backend_role_boundaries_match_three_week2_roles(self):
        for role in ("Admin", "Employee", "Customer"):
            self.assertEqual(require_viewer(SimpleNamespace(role=role)).role, role)
        self.assertEqual(require_operator(SimpleNamespace(role="Employee")).role, "Employee")
        self.assertEqual(require_admin(SimpleNamespace(role="Admin")).role, "Admin")
        for checker, role in ((require_viewer, "Unknown"),
                              (require_operator, "Customer"),
                              (require_admin, "Employee")):
            with self.assertRaises(HTTPException) as blocked:
                checker(SimpleNamespace(role=role))
            self.assertEqual(blocked.exception.status_code, 403)

    def test_config_requires_all_outputs_and_integer_timings(self):
        timings = {
            output: {str(level): {"on_ms": 100, "off_ms": 200}
                     for level in (1, 2, 3)}
            for output in ("led", "buzzer", "motor")
        }
        self.assertEqual(validate_timings(timings)["motor"]["3"]["off_ms"], 200)
        timings["led"]["1"]["on_ms"] = True
        with self.assertRaises(HTTPException) as invalid:
            validate_timings(timings)
        self.assertEqual(invalid.exception.status_code, 422)

    def test_ack_matches_child_id_and_device_before_completing_parent(self):
        device = Device(id=2, device_code="alert-01", model="Alert", device_type="ALERT_NODE")
        command = Command(
            id=12, request_id="cmd-12", device_id=2, command_type_id=1,
            action="TEST_ALERT", status="SENT",
            dispatches={name: {"request_id": f"cmd-12-{name}", "status": "SENT"}
                        for name in ("led", "buzzer", "motor")},
        )
        session = FakeSession(command, device)
        self.assertEqual(_save_ack(session, "another-device", {
            "request_id": "cmd-12-led", "status": "COMPLETED"}), [])
        self.assertEqual(command.status, "SENT")
        for name in ("led", "buzzer"):
            _save_ack(session, "alert-01", {
                "request_id": f"cmd-12-{name}", "status": "COMPLETED"})
            self.assertNotEqual(command.ack_status, "COMPLETED")
        events = _save_ack(session, "alert-01", {
            "request_id": "cmd-12-motor", "status": "COMPLETED"})
        self.assertEqual(command.ack_status, "COMPLETED")
        self.assertEqual(events[0]["data"]["request_id"], "cmd-12")
        self.assertEqual(_save_ack(session, "alert-01", {
            "request_id": "cmd-12-motor", "status": "COMPLETED"}), [])

    def test_sent_cannot_overwrite_early_ack(self):
        dispatches = {"led": {"request_id": "cmd-1-led", "status": "COMPLETED"}}
        self.assertEqual(update_dispatch(dispatches, "led", "SENT"), dispatches)
        command = SimpleNamespace(dispatches=dispatches, status="SENT",
                                  ack_status=None, error_message=None, executed_at=None)
        aggregate(command)
        self.assertEqual((command.status, command.ack_status),
                         ("ACKNOWLEDGED", "COMPLETED"))

    def test_http_command_result_can_be_failed_when_mqtt_publish_fails(self):
        device = Device(id=2, device_code="alert-01", model="Alert")
        command = Command(
            id=15, request_id="cmd-15", device_id=2, command_type_id=1,
            action="TEST_ALERT", status="PENDING",
            dispatches={"led": {"request_id": "cmd-15-led", "status": "PENDING"}},
        )
        with patch("app.api.routes.commands.publish_command", return_value=False), \
             patch("app.api.routes.commands._public", side_effect=lambda _s, item, _d: {
                 "request_id": item.request_id, "status": item.status,
             }):
            response = _publish_actions(FakeSession(command, device), command, device, {
                "led": {"command": "LED_ON", "duration": 1000, "intensity": "MEDIUM"},
            })
        self.assertEqual(response, {"request_id": "cmd-15", "status": "FAILED"})
        self.assertEqual(command.ack_status, "FAILED")

    def test_put_config_saves_desired_without_claiming_device_applied_it(self):
        config = Config(
            id=3, device_id=2,
            desired_config={"config_id": "cfg-old", "timings": {}},
            applied_config={"config_id": "cfg-old", "timings": {}},
        )
        device = Device(id=2, device_code="alert-01", model="Alert", device_type="ALERT_NODE")
        user = SimpleNamespace(id=1)
        timings = {
            output: {str(level): {"on_ms": 100, "off_ms": 200} for level in (1, 2, 3)}
            for output in ("led", "buzzer", "motor")
        }
        with patch("app.api.routes.configs.assigned_device", return_value=device), \
             patch("app.api.routes.configs._config_for", return_value=config), \
             patch("app.api.routes.configs.publish_config", return_value=True) as publish, \
             patch("app.api.routes.configs.log_action"):
            response = update_device_config(
                2, ConfigUpdateRequest(timings=timings), user, FakeSession(device=device)
            )
        self.assertEqual(response["status"], "PENDING_APPLICATION")
        self.assertEqual(config.desired_config["config_id"], response["config_id"])
        self.assertEqual(config.applied_config["config_id"], "cfg-old")
        publish.assert_called_once_with("alert-01", {"config_id": response["config_id"], "timings": timings, "revision": 1})

    def test_config_applied_event_must_match_saved_desired_id(self):
        device = Device(id=2, device_code="alert-01", model="Alert")
        config = Config(
            id=3, device_id=2,
            desired_config={"config_id": "cfg-new", "timings": {}},
            applied_config={"config_id": "cfg-old", "timings": {}},
        )
        session = FakeSession(config, device)
        with patch("app.services.mqtt_service._device", return_value=device):
            self.assertEqual(_save_applied_config(session, "alert-01", {
                "device_code": "alert-01", "config_id": "cfg-other", "status": "APPLIED",
            }), [])
            self.assertEqual(_save_applied_config(session, "alert-01", {
                "device_code": "alert-01", "config_id": "cfg-new",
            }), [])
            self.assertEqual(config.applied_config["config_id"], "cfg-old")
            self.assertEqual(_save_applied_config(session, "alert-01", {
                "device_code": "alert-01", "config_id": "cfg-new", "status": "REJECTED",
                "error": "INVALID_TIMING",
            })[0]["data"]["status"], "REJECTED")
            self.assertEqual(config.applied_config["config_id"], "cfg-old")
            self.assertEqual(config.desired_config["error"], "INVALID_TIMING")
            self.assertEqual(_snapshot(config)["status"], "REJECTED")
            self.assertEqual(_save_applied_config(session, "alert-01", {
                "device_code": "other", "config_id": "cfg-new", "status": "APPLIED",
            }), [])
            events = _save_applied_config(session, "alert-01", {
                "device_code": "alert-01", "config_id": "cfg-new", "status": "APPLIED",
            })
        self.assertEqual(config.applied_config["config_id"], "cfg-new")
        self.assertEqual(events[0]["data"]["applied_config_id"], "cfg-new")
        self.assertEqual(config.desired_config["status"], "APPLIED")
        with patch("app.services.mqtt_service._device", return_value=device):
            self.assertEqual(_save_applied_config(session, "alert-01", {
                "device_code": "alert-01", "config_id": "cfg-new",
                "status": "REJECTED", "error": "INVALID_TIMING",
            }), [])
        self.assertEqual(config.desired_config["status"], "APPLIED")

    def test_config_publish_failure_is_visible_without_claiming_applied(self):
        config = Config(id=3, device_id=2, applied_config=None)
        device = Device(id=2, device_code="alert-01", model="Alert", device_type="ALERT_NODE")
        timings = {output: {str(level): {"on_ms": 100, "off_ms": 200}
                            for level in (1, 2, 3)} for output in ("led", "buzzer", "motor")}
        with patch("app.api.routes.configs.assigned_device", return_value=device), \
             patch("app.api.routes.configs._config_for", return_value=config), \
             patch("app.api.routes.configs.publish_config", return_value=False), \
             patch("app.api.routes.configs.log_action"):
            with self.assertRaises(HTTPException) as failure:
                update_device_config(2, ConfigUpdateRequest(timings=timings),
                                     SimpleNamespace(id=1), FakeSession(device=device))
        self.assertEqual(failure.exception.status_code, 503)
        self.assertEqual(config.desired_config["status"], "PUBLISH_FAILED")
        self.assertIsNone(config.applied_config)

    def test_firmware_interrupted_ack_is_failure(self):
        device = Device(id=2, device_code="alert-01", model="Alert")
        command = Command(
            id=13, request_id="cmd-13", device_id=2, command_type_id=1,
            status="SENT", dispatches={"led": {
                "request_id": "cmd-13-led", "status": "SENT"}},
        )
        events = _save_ack(FakeSession(command, device), "alert-01", {
            "request_id": "cmd-13-led", "status": "INTERRUPTED"})
        self.assertEqual(command.status, "FAILED")
        self.assertEqual(events[0]["data"]["error_message"], "Command interrupted")

    def test_late_ack_only_replaces_timeout_after_all_outputs_complete(self):
        device = Device(id=2, device_code="alert-01", model="Alert")
        command = Command(
            id=16, request_id="cmd-16", device_id=2, command_type_id=1,
            status="TIMEOUT", error_message="No completed ACK before timeout",
            dispatches={name: {"request_id": f"cmd-16-{name}", "status": "SENT"}
                        for name in ("led", "buzzer")},
        )
        session = FakeSession(command, device)
        first = _save_ack(session, "alert-01", {
            "request_id": "cmd-16-led", "status": "COMPLETED",
        })
        self.assertEqual(first[0]["data"]["status"], "TIMEOUT")
        self.assertEqual(command.error_message, "No completed ACK before timeout")
        final = _save_ack(session, "alert-01", {
            "request_id": "cmd-16-buzzer", "status": "COMPLETED",
        })
        self.assertEqual(final[0]["data"]["status"], "ACKNOWLEDGED")
        self.assertEqual(final[0]["data"]["ack_status"], "COMPLETED")
        self.assertIsNone(command.error_message)

    def test_ai_and_esp32_topics_keep_their_current_payloads(self):
        class Context:
            def __enter__(self):
                return object()

            def __exit__(self, *args):
                return False

        with patch("app.services.mqtt_service.Session", return_value=Context()), \
             patch("app.services.mqtt_service._save_telemetry", return_value=[]) as telemetry, \
             patch("app.services.mqtt_service._save_status", return_value=[]) as status, \
             patch("app.services.mqtt_service._save_ack", return_value=[]) as ack:
            process_message("driver/telemetry", {"device_id": "vision-01"})
            process_message("driver/alert-01/status", {"status": "ALIVE"})
            process_message("driver/alert-01/ack", {"request_id": "cmd-12-led"})
            self.assertEqual(telemetry.call_args.args[1], "vision-01")
            self.assertEqual(status.call_args.args[1], "alert-01")
            self.assertEqual(ack.call_args.args[1], "alert-01")

    def test_websocket_ticket_is_one_use(self):
        ticket = issue_ticket(7)
        self.assertEqual(consume_ticket(ticket), 7)
        self.assertIsNone(consume_ticket(ticket))

    def test_database_utc_timestamps_are_marked_for_browser(self):
        response = DeviceResponse.from_device(Device(
            id=2, device_code="alert-01", model="Alert",
            created_at=datetime(2026, 10, 11, 9, 0),
            last_seen=datetime(2026, 10, 11, 9, 1),
        ))
        self.assertEqual(response.last_seen.tzinfo, timezone.utc)

    def test_websocket_sends_only_to_assigned_device_users(self):
        manager = ConnectionManager()
        sent = []

        class Socket:
            async def send_json(self, event):
                sent.append(event)

        owner, stranger = Socket(), Socket()
        manager.connections = {owner: 7, stranger: 8}

        class ScopedSession:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def exec(self, statement):
                return Result([7])

        with patch("app.services.websocket_manager.Session", return_value=ScopedSession()):
            asyncio.run(manager.send_to_device_users({
                "type": "telemetry.updated", "data": {"device_id": 2}}))
        self.assertEqual(len(sent), 1)


if __name__ == "__main__":
    unittest.main()
