import json
import paho.mqtt.publish as mqtt_publish

from app.core.config import settings


def publish_command(
    command_id: int,
    device_code: str,
    command: str,
    mqtt_username: str,
    mqtt_password: str,
) -> bool:

    topic = f"driver/{device_code}/command"

    payload_dict = {
        "request_id": command_id,
        "command": command
    }
    payload = json.dumps(payload_dict)

    try:
        import paho.mqtt.client as mqtt
        client = mqtt.Client()
        client.connect(settings.MQTT_HOST, settings.MQTT_PORT, 5)
        client.publish(topic, payload)
        client.disconnect()

        print(
            f"Published command: "
            f"{topic} -> {command}"
        )

        return True

    except Exception as e:
        print(
            f"MQTT publish failed: {e}"
        )

        return False