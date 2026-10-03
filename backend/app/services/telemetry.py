import paho.mqtt.publish as publish

from app.core.config import settings

host = settings.ESP32_HOST

def send_eye_close():
    publish.single(topic="eyes/close", payload="EYE_CLOSED", hostname=host)

def send_head_turn():
    publish.single(topic="head/turn", payload="HEAD_TURN", hostname=host)

import json
import time
import random
import paho.mqtt.client as mqtt

client = mqtt.Client()
client.connect("localhost", 1883)

while True:
    data = {
        "device_id": "device-01",
        "ear": round(random.uniform(0.2, 0.35), 2),
        "perclos": round(random.uniform(0.05, 0.2), 2),
        "driver_state": "ATTENTIVE"
    }

    client.publish(
        "driver/device-01/telemetry",
        json.dumps(data)
    )

    print("Published:", data)
    time.sleep(1)