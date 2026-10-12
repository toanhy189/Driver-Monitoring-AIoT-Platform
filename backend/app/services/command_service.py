import json

import paho.mqtt.client as mqtt

from app.core.config import settings


def publish_command(device_code: str, payload: dict) -> bool:
    """Send one firmware command; false means publish was not confirmed by broker."""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if settings.MQTT_USERNAME:
        client.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)
    try:
        client.connect(settings.MQTT_HOST, settings.MQTT_PORT, 5)
        client.loop_start()
        result = client.publish(
            f"driver/{device_code}/command", json.dumps(payload), qos=1
        )
        result.wait_for_publish(timeout=5)
        return result.is_published()
    except (OSError, RuntimeError, ValueError):
        return False
    finally:
        client.disconnect()
        client.loop_stop()
