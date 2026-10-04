import json
import paho.mqtt.client as mqtt

from backend.app.core.config import settings

MQTT_HOST = settings.MQTT_HOST
MQTT_PORT = settings.MQTT_PORT

if __name__ == "__main__":
    print("Thử publish topic với payload")

    device = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    device.connect(MQTT_HOST, MQTT_PORT, 60)

    device.publish(
        topic='driver/device_01/telemetry',
        payload=json.dumps({
            "device_code": "DM-000001",
            "ear": 0.31,
            "perclos": 0.02,
            "angle_x": 2.1,
            "angle_y": 1.2,
            "angle_z": 0.5,
            "confidence": 0.67
        })
    )