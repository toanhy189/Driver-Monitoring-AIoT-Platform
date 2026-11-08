"""Verify retained MQTT messages survive a restart of the local Compose broker."""

import json
import os
from pathlib import Path
import queue
import secrets
import subprocess
import sys
import threading
import unittest

import paho.mqtt.client as mqtt

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import settings  # noqa: E402


class BrokerPeer:
    def __init__(self):
        self.connected = threading.Event()
        self.subscribed = threading.Event()
        self.messages = queue.Queue()
        self.reason_code = None
        self.subscribe_reason_codes = None
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
        self.client.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)
        self.client.on_connect = self._on_connect
        self.client.on_subscribe = self._on_subscribe
        self.client.on_message = lambda client, userdata, message: self.messages.put(message)
        self.client.connect(settings.MQTT_HOST, settings.MQTT_PORT, 10)
        self.client.loop_start()
        if not self.connected.wait(10):
            self.close()
            raise TimeoutError("Timed out connecting to the local MQTT broker")
        if self.reason_code.is_failure:
            self.close()
            raise ConnectionError("The configured backend MQTT credentials were rejected")

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        self.reason_code = reason_code
        self.connected.set()

    def _on_subscribe(self, client, userdata, mid, reason_codes, properties):
        self.subscribe_reason_codes = reason_codes
        self.subscribed.set()

    def publish(self, topic, payload, *, retain):
        result = self.client.publish(topic, payload, qos=1, retain=retain)
        result.wait_for_publish(timeout=10)
        if not result.is_published():
            raise TimeoutError("MQTT publish was not acknowledged")

    def subscribe(self, topic):
        self.client.subscribe(topic, qos=1)
        if not self.subscribed.wait(10):
            raise TimeoutError("Timed out subscribing to the retained test topic")
        if any(reason_code.is_failure for reason_code in self.subscribe_reason_codes):
            raise PermissionError("Backend MQTT credentials cannot subscribe to the retained test topic")

    def close(self):
        self.client.disconnect()
        self.client.loop_stop()


class MqttPersistenceTest(unittest.TestCase):
    def receive_topic(self, peer, topic):
        while True:
            message = peer.messages.get(timeout=10)
            if message.topic == topic:
                return message

    def test_retained_message_survives_compose_broker_restart(self):
        if os.getenv("W4_ALLOW_BROKER_RESTART") != "1":
            self.fail("Set W4_ALLOW_BROKER_RESTART=1 to confirm this test may restart the dev broker")
        if settings.MQTT_HOST not in {"localhost", "127.0.0.1"} or settings.MQTT_PORT != 1884:
            self.fail("Refusing to restart anything except the local Compose broker at localhost:1884")

        device_code = "w4-persist-" + secrets.token_hex(6)
        topic = f"driver/{device_code}/config/update"
        payload = json.dumps({"test_id": secrets.token_hex(8)}).encode()
        published = False

        try:
            publisher = BrokerPeer()
            try:
                published = True
                publisher.publish(topic, payload, retain=True)
            finally:
                publisher.close()

            initial_subscriber = BrokerPeer()
            try:
                initial_subscriber.subscribe("driver/#")
                initial_message = self.receive_topic(initial_subscriber, topic)
                self.assertEqual(initial_message.topic, topic)
                self.assertTrue(initial_message.retain, "The broker did not retain the test publish")
                self.assertEqual(initial_message.payload, payload)
            finally:
                initial_subscriber.close()

            restart = subprocess.run(
                ["docker", "compose", "--env-file", ".env", "-f",
                 "deployment/docker-compose.yml", "restart", "mosquitto"],
                cwd=ROOT, capture_output=True, text=True, timeout=60,
            )
            if restart.returncode:
                raise RuntimeError("Could not restart the local Mosquitto service: " + restart.stderr)

            subscriber = BrokerPeer()
            try:
                subscriber.subscribe("driver/#")
                message = self.receive_topic(subscriber, topic)
                self.assertEqual(message.topic, topic)
                self.assertTrue(message.retain, "Broker did not deliver this as a retained message")
                self.assertEqual(message.payload, payload)
            finally:
                subscriber.close()
        finally:
            if published:
                cleaner = BrokerPeer()
                try:
                    cleaner.publish(topic, b"", retain=True)
                finally:
                    cleaner.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
