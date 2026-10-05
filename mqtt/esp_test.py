import json
import time
import paho.mqtt.client as mqtt

from backend.app.core.config import settings

MQTT_HOST = settings.MQTT_HOST
MQTT_PORT = settings.MQTT_PORT

if __name__ == "__main__":
    print("Publishing topic: 'driver/alert-01/command'")

    device = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    device.connect(MQTT_HOST, MQTT_PORT, 60)

    device.publish(
        topic='driver/alert-01/command',
        payload=json.dumps({
            "command": "LED_ON",
            "duration": 10000,
            "intensity": "MEDIUM"

        })
    )
    time.sleep(5)
    device.publish(
        topic='driver/alert-01/command',
        payload=json.dumps({
            "command": "BUZZER_ON",
            "duration": 3000,
            "intensity": "WEAK"
        })
    )
