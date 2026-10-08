import json
import paho.mqtt.client as mqtt
from datetime import datetime, timezone
from sqlmodel import Session, select

from app.core.db import engine
from app.models.command import Command
from app.models.device import Device
from app.models.config import Config
from app.core.config import settings


MQTT_HOST = settings.MQTT_HOST
MQTT_PORT = settings.MQTT_PORT
# Sử dụng Shared Subscription để tránh trùng consumer (TV2-21)
MQTT_TOPICS = [
    ("$share/backend_group/driver/+/telemetry", 0),
    ("$share/backend_group/driver/+/ack", 0),
    ("$share/backend_group/driver/+/heartbeat", 0),
    ("$share/backend_group/driver/+/config/applied", 0),
]

def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        print("Đã kết nối với MQTT (Backend Consumer)", flush=True)
        client.subscribe(MQTT_TOPICS)
        print(f"Subscribed: {MQTT_TOPICS}", flush=True)
    else:
        print(f"Lỗi kết nối MQTT: {reason_code}", flush=True)


def handle_ack_message(topic: str, payload: dict):
    # Topic thực tế nhận được sẽ là driver/{device_code}/ack
    parts = topic.split("/")
    if len(parts) < 3 or parts[-1] != "ack":
        return
        
    device_code = parts[-2]
    request_id = payload.get("request_id")
    
    if not request_id:
        print(f"ACK missing request_id: {payload}")
        return

    with Session(engine) as session:
        command = session.get(Command, request_id)
        if not command:
            print(f"Command {request_id} not found")
            return

        # TV2-12: Xử lý sai thiết bị
        device = session.get(Device, command.device_id)
        if not device or device.device_code != device_code:
            print(f"ACK device mismatch: expected {device.device_code if device else 'None'}, got {device_code}")
            return
            
        # TV2-12: Xử lý ACK trùng
        if command.status in ["ACKED", "EXECUTED"]:
            print(f"Duplicate ACK for command {request_id}")
            return
            
        # TV2-14: Cập nhật DB
        command.status = "ACKED"
        command.executed_at = datetime.now(timezone.utc)
        session.add(command)
        session.commit()
        print(f"Command {request_id} updated to ACKED")


def handle_heartbeat_message(topic: str, payload: dict):
    parts = topic.split("/")
    if len(parts) < 3 or parts[-1] != "heartbeat":
        return
        
    device_code = parts[-2]
    timestamp = payload.get("timestamp")
    
    now = datetime.now(timezone.utc)
    # TV2-16: Kiểm tra timestamp (tránh lấy retained message cũ làm heartbeat mới)
    if timestamp:
        try:
            # Giả định timestamp là unix timestamp (giây)
            msg_time = datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
            if (now - msg_time).total_seconds() > 60:
                print(f"Bỏ qua heartbeat quá cũ từ {device_code}")
                return
        except (ValueError, TypeError) as e:
            print(f"Lỗi parse timestamp heartbeat: {e}")
            return
            
    with Session(engine) as session:
        device = session.exec(select(Device).where(Device.device_code == device_code)).first()
        if device:
            # TV2-15: Cập nhật last_seen và ONLINE
            device.last_seen = now
            if device.status != "ONLINE":
                device.status = "ONLINE"
            session.add(device)
            session.commit()
            print(f"Cập nhật heartbeat cho thiết bị {device_code}")

def handle_config_applied_message(topic: str, payload: dict):
    parts = topic.split("/")
    if len(parts) < 4 or parts[-2:] != ["config", "applied"]:
        return
        
    device_code = parts[-3]
    
    with Session(engine) as session:
        device = session.exec(select(Device).where(Device.device_code == device_code)).first()
        if not device:
            return
            
        config = session.exec(select(Config).where(Config.device_id == device.id)).first()
        if not config:
            config = Config(device_id=device.id, applied_config=payload)
            session.add(config)
        else:
            config.applied_config = payload
            config.updated_at = datetime.now(timezone.utc)
            session.add(config)
            
        session.commit()
        print(f"Đã cập nhật applied_config cho {device_code}")


from app.services.rule_engine import evaluate_telemetry

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        topic = msg.topic

        print(f"Nhận được message từ {topic}: {payload}", flush=True)
        
        if topic.endswith("/telemetry"):
            # Lấy device_code từ topic
            parts = topic.split("/")
            if len(parts) >= 3:
                device_code = parts[-2]
                evaluate_telemetry(device_code, payload)
        elif topic.endswith("/ack"):
            handle_ack_message(topic, payload)
        elif topic.endswith("/heartbeat"):
            handle_heartbeat_message(topic, payload)
        elif topic.endswith("/config/applied"):
            handle_config_applied_message(topic, payload)

    except json.JSONDecodeError:
        print("JSON không hợp lệ:", msg.payload.decode())
    except Exception as e:
        print(f"Lỗi xử lý message MQTT: {e}")


def start_mqtt_consumer():
    print(f"Bắt đầu MQTT Consumer thread tới {MQTT_HOST}:{MQTT_PORT}...", flush=True)
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.on_connect = on_connect
        client.on_message = on_message
        print("Đang kết nối...", flush=True)
        client.connect(MQTT_HOST, MQTT_PORT, 60)
        print("Đã gọi connect() xong, bắt đầu loop_forever()...", flush=True)
        client.loop_forever()
    except Exception as e:
        print(f"Lỗi khởi động MQTT Consumer: {e}", flush=True)