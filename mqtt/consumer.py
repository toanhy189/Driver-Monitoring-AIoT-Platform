import json
import paho.mqtt.client as mqtt

from backend.app.core.config import settings
from backend.app.services.telemetry_service import save_telemetry

MQTT_HOST = settings.MQTT_HOST
MQTT_PORT = settings.MQTT_PORT
MQTT_TOPICS = ["driver/+/telemetry", "driver/+/response"]

def on_connect(client, userdata, flags, rc, properties):
    if rc == 0:
        print("Đã kết nối với MQTT")
        for topic in MQTT_TOPICS:
            client.subscribe(topic)
            print(f"Subscribed: {topic}")
    else:
        print(f"Lỗi kết nối MQTT: {rc}")


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())

        print("Nhận được telemetry:")
        print("Topic:", msg.topic)
        print("Data:", payload)

        parts = msg.topic.split("/")
        device_code = parts[1]
        message_type = parts[-1]

        if message_type == "telemetry":
            save_telemetry(device_code, payload)
        elif message_type == "response":
            print(payload)


    except json.JSONDecodeError:
        print("JSON không hợp lệ:", msg.payload.decode())


def start_mqtt_consumer():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(MQTT_HOST, MQTT_PORT, 60)

    client.loop_forever()

# lệnh chạy
# set PYTHONPATH=backend
# python -m mqtt.consumer
if __name__ == "__main__":
    start_mqtt_consumer()