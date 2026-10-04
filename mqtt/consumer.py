import json
import paho.mqtt.client as mqtt

# from backend.app.core.config import settings
# from backend.app.services.telemetry_service import save_telemetry

# lệnh chạy
# set PYTHONPATH=backend      -> nhưng khi chạy mqtt.consumer, phải bảo đảm Python biết backend là module path.
# python -m mqtt.consumer
# vì đang chạy backend từ thư mục gốc bằng: python -m uvicorn app.main:app --reload --app-dir backend
from app.core.config import settings
from app.services.telemetry_service import save_telemetry
from app.services.websocket_manager import manager

MQTT_HOST = settings.MQTT_HOST
MQTT_PORT = settings.MQTT_PORT
MQTT_TOPICS = ["driver/+/telemetry"]

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
        message_type = parts[-1]

        if message_type == "telemetry":
            save_telemetry(payload)


    except json.JSONDecodeError:
        print("JSON không hợp lệ:", msg.payload.decode())


def start_mqtt_consumer():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(MQTT_HOST, MQTT_PORT, 60)

    client.loop_forever()


if __name__ == "__main__":
    start_mqtt_consumer()