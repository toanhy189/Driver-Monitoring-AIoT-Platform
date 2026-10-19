"""Synchronous client for Mosquitto's dynamic-security control topic."""

import json
import secrets
from threading import Event, Lock

import paho.mqtt.client as mqtt

from app.core.config import settings


CONTROL = "$CONTROL/dynamic-security/v1"
RESPONSE = CONTROL + "/response"


def acl(kind: str, topic: str) -> dict:
    return {"acltype": kind, "topic": topic, "allow": True, "priority": 1}


def device_acls(code: str) -> list[dict]:
    prefix = f"driver/{code}"
    writes = ("telemetry", "status", "ack", "heartbeat", "config/applied")
    reads = ("command", "config/update")
    return [acl("publishClientSend", f"{prefix}/{part}") for part in writes] + [
        acl("subscribeLiteral", f"{prefix}/{part}") for part in reads
    ] + [acl("publishClientReceive", f"{prefix}/{part}") for part in reads]


class BrokerSecurity:
    def __init__(self):
        if not settings.MQTT_ADMIN_PASSWORD:
            raise RuntimeError("MQTT broker admin credential is not configured")
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.username_pw_set(settings.MQTT_ADMIN_USERNAME, settings.MQTT_ADMIN_PASSWORD)
        self.client.on_connect = self._on_connect
        self.client.on_subscribe = self._on_subscribe
        self.client.on_message = self._on_message
        self.ready = Event()
        self.reply = Event()
        self.lock = Lock()
        self.error = None
        self.correlation = None
        self.response = None

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            self.error = "MQTT broker rejected admin login"
            self.ready.set()
        else:
            client.subscribe(RESPONSE, qos=1)

    def _on_subscribe(self, client, userdata, mid, reason_codes, properties):
        if any(code.is_failure for code in reason_codes):
            self.error = "MQTT broker rejected admin response subscription"
        self.ready.set()

    def _on_message(self, client, userdata, message):
        try:
            payload = json.loads(message.payload)
            for item in payload.get("responses", []):
                if item.get("correlationData") == self.correlation:
                    self.response = item
                    self.reply.set()
                    break
        except (ValueError, TypeError):
            pass

    def __enter__(self):
        self.client.connect(settings.MQTT_HOST, settings.MQTT_PORT, keepalive=10)
        self.client.loop_start()
        if not self.ready.wait(5):
            self.__exit__(None, None, None)
            raise RuntimeError("MQTT broker admin connection timed out")
        if self.error:
            self.__exit__(None, None, None)
            raise RuntimeError(self.error)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.client.disconnect()
        self.client.loop_stop()

    def command(self, name: str, **fields) -> dict:
        with self.lock:
            self.correlation = secrets.token_hex(12)
            self.response = None
            self.reply.clear()
            payload = {"commands": [{"command": name, "correlationData": self.correlation, **fields}]}
            result = self.client.publish(CONTROL, json.dumps(payload), qos=1)
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError("MQTT broker control publish failed")
            result.wait_for_publish(timeout=5)
            if not result.is_published():
                raise RuntimeError("MQTT broker control publish timed out")
            if not self.reply.wait(5):
                raise RuntimeError("MQTT broker control response timed out")
            if self.response.get("error"):
                raise RuntimeError(f"MQTT broker {name} failed: {self.response['error']}")
            return self.response.get("data", {})

    def has_client(self, username: str) -> bool:
        try:
            self.command("getClient", username=username)
            return True
        except RuntimeError as error:
            if "Client not found" in str(error):
                return False
            raise

    def has_role(self, role: str) -> bool:
        try:
            self.command("getRole", rolename=role)
            return True
        except RuntimeError as error:
            if "Role not found" in str(error):
                return False
            raise

    def create_role(self, role: str, acls: list[dict]):
        self.command("createRole", rolename=role, acls=acls)

    def delete_role(self, role: str):
        self.command("deleteRole", rolename=role)

    def create_client(self, username: str, password: str, role: str):
        self.command("createClient", username=username, password=password,
                     roles=[{"rolename": role, "priority": 1}])

    def delete_client(self, username: str):
        self.command("deleteClient", username=username)
