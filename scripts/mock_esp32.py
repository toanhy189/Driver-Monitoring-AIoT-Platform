import json
import time
import sys
sys.stdout.reconfigure(encoding='utf-8')
import paho.mqtt.client as mqtt

MQTT_HOST = "localhost"
MQTT_PORT = 1883
DEVICE_CODE = "alert-01"

STATUS_TOPIC = f"driver/{DEVICE_CODE}/status"
COMMAND_TOPIC = f"driver/{DEVICE_CODE}/command"
ACK_TOPIC = f"driver/{DEVICE_CODE}/ack"

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="mock_esp32_alert_01")

def on_connect(c, userdata, flags, rc, properties=None):
    print(f"--> [Mock ESP32] Connected to MQTT broker at {MQTT_HOST}:{MQTT_PORT} (rc={rc})")
    c.subscribe(COMMAND_TOPIC)
    print(f"--> [Mock ESP32] Subscribed to {COMMAND_TOPIC}")

def on_message(c, userdata, msg):
    try:
        data = json.loads(msg.payload.decode("utf-8"))
        req_id = data.get("request_id")
        cmd = data.get("command")
        print(f"\n[Mock ESP32] Nhận lệnh: {cmd} (request_id={req_id})")
        
        # Simulate hardware execution and send ACK COMPLETED
        time.sleep(0.5)
        ack_payload = {
            "request_id": req_id,
            "status": "COMPLETED",
            "device_code": DEVICE_CODE
        }
        c.publish(ACK_TOPIC, json.dumps(ack_payload))
        print(f"[Mock ESP32] -> Đã gửi ACK COMPLETED cho {req_id} tới {ACK_TOPIC}")
    except Exception as e:
        print("[Mock ESP32] Lỗi xử lý message:", e)

client.on_connect = on_connect
client.on_message = on_message

try:
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_start()
    print("--> [Mock ESP32] Đang chạy giả lập thiết bị alert-01...")
    
    while True:
        # Publish heartbeat every 5 seconds
        status_payload = {
            "status": "ONLINE",
            "firmware_version": "0.2.10"
        }
        client.publish(STATUS_TOPIC, json.dumps(status_payload))
        time.sleep(5)
except KeyboardInterrupt:
    print("\n--> [Mock ESP32] Dừng simulator.")
    client.loop_stop()
    client.disconnect()
