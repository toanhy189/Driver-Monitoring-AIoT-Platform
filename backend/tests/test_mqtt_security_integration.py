"""Live broker checks; run directly after starting the Docker Mosquitto service."""

import os
import json
import secrets
import sys
import threading
import unittest
from pathlib import Path

import paho.mqtt.client as mqtt

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.services.mqtt_provision_service import provision_device  # noqa: E402
from app.services.mqtt_revoke_service import revoke_device  # noqa: E402
from app.services.config_publish_service import publish_config  # noqa: E402


class Peer:
    def __init__(self, username=None, password=None):
        self.connected = threading.Event()
        self.subscribed = threading.Event()
        self.published = threading.Event()
        self.disconnected = threading.Event()
        self.received = threading.Event()
        self.last_topic = None
        self.last_payload = None
        self.connect_reason = None
        self.subscribe_reason = None
        self.publish_reason = None
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
        if username:
            self.client.username_pw_set(username, password)
        self.client.on_connect = self.on_connect
        self.client.on_subscribe = self.on_subscribe
        self.client.on_publish = self.on_publish
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message
        self.client.connect(settings.MQTT_HOST, settings.MQTT_PORT, 10)
        self.client.loop_start()
        assert self.connected.wait(5), "MQTT connection timed out"

    def on_connect(self, client, userdata, flags, reason_code, properties):
        self.connect_reason = reason_code
        self.connected.set()

    def on_subscribe(self, client, userdata, mid, reason_codes, properties):
        self.subscribe_reason = reason_codes[0]
        self.subscribed.set()

    def on_publish(self, client, userdata, mid, reason_code, properties):
        self.publish_reason = reason_code
        self.published.set()

    def on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.disconnected.set()

    def on_message(self, client, userdata, message):
        self.last_topic = message.topic
        self.last_payload = message.payload
        self.received.set()

    def subscribe(self, topic):
        self.subscribed.clear()
        self.client.subscribe(topic, 1)
        assert self.subscribed.wait(5), "MQTT subscribe timed out"
        return self.subscribe_reason

    def publish(self, topic):
        self.published.clear()
        self.client.publish(topic, "{}", qos=1)
        assert self.published.wait(5), "MQTT publish timed out"
        return self.publish_reason

    def close(self):
        self.client.disconnect()
        self.client.loop_stop()


class MqttSecurityIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if __name__ != "__main__" and not os.getenv("MQTT_INTEGRATION"):
            raise unittest.SkipTest("Run this file directly for live MQTT checks")

    def test_accounts_acl_and_revoke(self):
        anonymous = Peer()
        self.assertTrue(anonymous.connect_reason.is_failure)
        anonymous.close()

        backend = Peer(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)
        ai = Peer(settings.AI_MQTT_USERNAME, settings.AI_MQTT_PASSWORD)
        self.assertFalse(backend.connect_reason.is_failure)
        self.assertFalse(ai.connect_reason.is_failure)
        self.assertFalse(backend.subscribe("driver/#").is_failure)
        self.assertTrue(ai.subscribe("driver/#").is_failure)
        self.assertFalse(ai.publish("driver/telemetry").is_failure)

        code = "tv2-security-" + secrets.token_hex(4)
        credentials = provision_device(code)
        device = Peer(credentials["username"], credentials["password"])
        revoked = False
        try:
            self.assertFalse(device.connect_reason.is_failure)
            self.assertFalse(device.subscribe(f"driver/{code}/command").is_failure)
            self.assertTrue(device.subscribe("driver/other/command").is_failure)
            self.assertFalse(backend.publish(f"driver/{code}/command").is_failure)
            self.assertTrue(device.received.wait(5), "Device did not receive its command")
            self.assertEqual(device.last_topic, f"driver/{code}/command")
            backend.received.clear()
            self.assertFalse(device.publish(f"driver/{code}/ack").is_failure)
            self.assertTrue(backend.received.wait(5), "Backend did not receive device ACK")
            self.assertEqual(backend.last_topic, f"driver/{code}/ack")
            self.assertTrue(device.publish("driver/other/ack").is_failure)
            self.assertTrue(ai.publish(f"driver/{code}/ack").is_failure)
            self.assertFalse(device.subscribe(f"driver/{code}/config/update").is_failure)
            self.assertTrue(device.subscribe("driver/other/config/update").is_failure)
            device.received.clear()
            config = {"config_id": "cfg-test", "timings": {}}
            self.assertTrue(publish_config(code, config))
            self.assertTrue(device.received.wait(5), "Device did not receive config")
            self.assertEqual(device.last_topic, f"driver/{code}/config/update")
            self.assertEqual(json.loads(device.last_payload), {"device_code": code, **config})
            device.close()
            device = Peer(credentials["username"], credentials["password"])
            self.assertFalse(device.subscribe(f"driver/{code}/config/update").is_failure)
            self.assertTrue(device.received.wait(5), "Offline device did not receive retained config")
            self.assertEqual(json.loads(device.last_payload), {"device_code": code, **config})
            backend.received.clear()
            self.assertFalse(device.publish(f"driver/{code}/config/applied").is_failure)
            self.assertTrue(backend.received.wait(5), "Backend did not receive config ACK")
            self.assertEqual(backend.last_topic, f"driver/{code}/config/applied")
            self.assertTrue(device.publish("driver/other/config/applied").is_failure)
            self.assertTrue(ai.publish(f"driver/{code}/config/applied").is_failure)
            revoke_device(code)
            revoked = True
            self.assertTrue(device.disconnected.wait(5), "Revoked device remained connected")
            rejected = Peer(credentials["username"], credentials["password"])
            self.assertTrue(rejected.connect_reason.is_failure)
            rejected.close()
        finally:
            cleared = backend.client.publish(f"driver/{code}/config/update", b"", qos=1, retain=True)
            cleared.wait_for_publish(timeout=5)
            if not revoked:
                revoke_device(code)
            device.close()
            backend.close()
            ai.close()


if __name__ == "__main__":
    os.environ["MQTT_INTEGRATION"] = "1"
    unittest.main()
