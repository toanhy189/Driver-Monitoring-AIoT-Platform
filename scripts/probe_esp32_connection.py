import time
import json
import sys
import paho.mqtt.client as mqtt

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

found_messages = []

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("[PROBE] Đã kết nối thành công tới MQTT Broker tại 127.0.0.1:1883!")
        client.subscribe([("driver/#", 0), ("driver/alert-01/status", 1), ("driver/alert-01/ack", 1)])
        print("[PROBE] Đang lắng nghe tín hiệu từ ESP32 trên topics: driver/# ...")
    else:
        print(f"[PROBE] Không thể kết nối tới Broker, mã lỗi rc={rc}")

def on_message(client, userdata, msg):
    payload = msg.payload.decode("utf-8", errors="ignore")
    print(f"\n>>> [PHÁT HIỆN TÍN HIỆU TỪ ESP32!]")
    print(f"    Topic:   {msg.topic}")
    print(f"    Payload: {payload}")
    found_messages.append({"topic": msg.topic, "payload": payload})

client = mqtt.Client(client_id="probe-detector-01")
client.on_connect = on_connect
client.on_message = on_message

try:
    client.connect("127.0.0.1", 1883, keepalive=60)
    client.loop_start()
    
    # Lắng nghe trong 8 giây (ESP32 phát heartbeat mỗi 5 giây)
    for i in range(8):
        time.sleep(1)
        if found_messages:
            break
            
    client.loop_stop()
    client.disconnect()
except Exception as e:
    print(f"[PROBE LỖI KẾT NỐI] {e}")

print("\n" + "="*50)
if found_messages:
    print(" KẾT QUẢ: ESP32 ĐÃ KẾT NỐI VÀ ĐANG HOẠT ĐỘNG ONLINE!")
    for m in found_messages:
        print(f"- {m['topic']}: {m['payload']}")
else:
    print(" KẾT QUẢ: Chưa nhận được gói tin nào từ ESP32 trong 8 giây qua.")
    print(" Gợi ý kiểm tra:")
    print("  1. ESP32 đã cắm nguồn và nạp xong firmware chưa?")
    print("  2. Xem màn hình Serial Monitor trên VS Code có in 'Connected' không?")
    print("  3. ESP32 và máy tính đã bắt chung một mạng Wi-Fi chưa?")
print("="*50)
