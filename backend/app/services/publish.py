import paho.mqtt.publish as publish

from app.core.config import settings

host = settings.ESP32_HOST

def send_eye_close():
    publish.single(topic="eyes/close", payload="EYE_CLOSED", hostname=host)

def send_head_turn():
    publish.single(topic="head/turn", payload="HEAD_TURN", hostname=host)
