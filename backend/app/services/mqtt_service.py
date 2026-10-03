import json
import paho.mqtt.client as mqtt

from app.core.config import settings


MQTT_HOST = settings.MQTT_HOST
MQTT_PORT = settings.MQTT_PORT
MQTT_TOPIC = "driver/+/telemetry"


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Đã kết nối với MQTT")
        client.subscribe(MQTT_TOPIC)
        print(f"Subscribed: {MQTT_TOPIC}")
    else:
        print(f"Lỗi kết nối MQTT: {rc}")


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())

        print("Nhận được telemetry:")
        print("Topic:", msg.topic)
        print("Data:", payload)

    except json.JSONDecodeError:
        print("JSON không hợp lệ:", msg.payload.decode())


def start_mqtt_consumer():
    client = mqtt.Client()

    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(MQTT_HOST, MQTT_PORT, 60)

    client.loop_forever()