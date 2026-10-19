"""Publish a device's desired configuration to its retained MQTT topic."""

import json

import paho.mqtt.client as mqtt

from app.core.config import settings


def publish_config(device_code: str, config: dict) -> bool:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if settings.MQTT_USERNAME:
        client.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)
    try:
        client.connect(settings.MQTT_HOST, settings.MQTT_PORT, 5)
        client.loop_start()
        result = client.publish(
            f"driver/{device_code}/config/update",
            json.dumps({"device_code": device_code, **config}),
            qos=1,
            retain=True,
        )
        result.wait_for_publish(timeout=5)
        return result.is_published()
    except (OSError, RuntimeError, ValueError):
        return False
    finally:
        client.disconnect()
        client.loop_stop()
