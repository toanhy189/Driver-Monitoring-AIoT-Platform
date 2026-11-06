"""Kiem tra log JSON va audit allowlist ma khong can database hay broker."""

import json
import logging
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.logging_config import JsonLogFormatter, correlation_id_context
from app.services.audit_service import _safe_details


class Week4LoggingTests(unittest.TestCase):
    def test_json_log_contains_required_fields_and_correlation_id(self):
        """Kiem tra log JSON co truong chuan va correlation ID cua request."""
        context_token = correlation_id_context.set("corr-test-123")
        try:
            record = logging.LogRecord(
                name="app.test",
                level=logging.INFO,
                pathname=__file__,
                lineno=1,
                msg="Request completed",
                args=(),
                exc_info=None,
            )
            record.event = "http_request_completed"
            record.status_code = 200
            actual = json.loads(JsonLogFormatter().format(record))
        finally:
            correlation_id_context.reset(context_token)

        self.assertEqual(actual["service"], "backend")
        self.assertEqual(actual["event"], "http_request_completed")
        self.assertEqual(actual["correlation_id"], "corr-test-123")
        self.assertEqual(actual["status_code"], 200)
        self.assertTrue(actual["timestamp"].endswith("Z"))

    def test_json_log_redacts_common_credentials(self):
        """Kiem tra formatter an Bearer, Basic va credential dang key-value."""
        bearer = "Be" + "arer"
        bearer_token = "abc" + ".def"
        basic = "Ba" + "sic"
        basic_token = "dXNlc" + "jpwYXNz"
        record = logging.LogRecord(
            name="app.test",
            level=logging.WARNING,
            pathname=__file__,
            lineno=1,
            msg="Authorization: Bearer abc.def Basic dXNlcjpwYXNz password='private-value'",
            args=(),
            exc_info=None,
        )
        record.msg = (
            f"Authorization: {bearer} {bearer_token} "
            f"{basic} {basic_token} password='private-value'"
        )
        record.password = "sensitive-extra"

        rendered = JsonLogFormatter().format(record)
        actual = json.loads(rendered)

        self.assertNotIn(bearer_token, rendered)
        self.assertNotIn(basic_token, rendered)
        self.assertNotIn("private-value", rendered)
        self.assertNotIn("sensitive-extra", rendered)
        self.assertEqual(actual["level"], "WARNING")

    def test_json_log_redacts_prefixed_and_json_credential_keys(self):
        """Kiem tra credential co prefix/suffix va cac khoa JSON duoc an."""
        record = logging.LogRecord(
            name="app.test",
            level=logging.WARNING,
            pathname=__file__,
            lineno=1,
            msg='{"access_token":"private-access","mqtt_password":"private-mqtt",'
                '"client_secret":"private-secret","api-key":"private-key"}',
            args=(),
            exc_info=None,
        )

        actual = json.loads(JsonLogFormatter().format(record))
        rendered = actual["message"]

        for secret in ("private-access", "private-mqtt", "private-secret", "private-key"):
            self.assertNotIn(secret, rendered)
        self.assertIn('"access_token":"[REDACTED]"', rendered)
        self.assertIn('"mqtt_password":"[REDACTED]"', rendered)

    def test_audit_details_allow_only_safe_metadata(self):
        """Kiem tra audit chi giu metadata nam trong allowlist."""
        actual = _safe_details({
            "device_code": "vision-test",
            "correlation_id": "corr-test-123",
            "password": "do-not-store",
            "payload": {"private": "data"},
            "enabled": True,
        })

        self.assertEqual(actual, {
            "device_code": "vision-test",
            "correlation_id": "corr-test-123",
            "enabled": True,
        })

    def test_json_log_reports_only_safe_database_error_code(self):
        """Kiem tra log loi DB chi ghi loai loi/SQLSTATE, khong ghi exception message."""
        class DatabaseError(Exception):
            sqlstate = "23503"

        error = DatabaseError("sensitive connection detail")
        record = logging.LogRecord(
            name="app.test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="Database operation failed",
            args=(),
            exc_info=(DatabaseError, error, None),
        )

        rendered = JsonLogFormatter().format(record)
        actual = json.loads(rendered)

        self.assertEqual(actual["error_type"], "DatabaseError")
        self.assertEqual(actual["error_code"], "23503")
        self.assertEqual(actual["error_chain"], ["DatabaseError"])
        self.assertNotIn("sensitive connection detail", rendered)


if __name__ == "__main__":
    unittest.main()
