"""
Endurance Test Runner cho ESP32 Alert Node - Tuần 4 (W4-TV1-08)
Mục đích:
- Chạy kiểm thử tải liên tục trong 2 - 4 giờ
- Ghi nhận: Số lần Heartbeat ALIVE, Disconnect/Reconnect Wi-Fi & Broker, 
  Số lần phản hồi ACK thành công, Tự tắt sau timeout, Reset bất thường và Lỗi thực tế.
- Xuất dữ liệu thống kê ra file JSON và Markdown định kỳ.
"""

import sys
import json
import time
import uuid
import argparse
from datetime import datetime, timedelta
from pathlib import Path

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("Vui long cai dat paho-mqtt: pip install paho-mqtt")
    sys.exit(1)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")


class EnduranceRunner:
    def __init__(self, host: str, port: int, user: str, password: str, device_code: str, duration_hours: float, interval_sec: int):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.device_code = device_code
        self.duration_seconds = int(duration_hours * 3600)
        self.interval_sec = interval_sec

        self.topic_cmd = f"driver/{device_code}/command"
        self.topic_ack = f"driver/{device_code}/ack"
        self.topic_status = f"driver/{device_code}/status"

        self.stats = {
            "start_time": datetime.now().isoformat(),
            "target_duration_hours": duration_hours,
            "heartbeat_count": 0,
            "commands_sent": 0,
            "acks_received": 0,
            "reconnect_events": 0,
            "error_events": 0,
            "last_heartbeat": None,
            "last_ack": None,
            "log_records": []
        }

        self.client = mqtt.Client(client_id=f"w4-endurance-{uuid.uuid4().hex[:6]}")
        if self.user:
            self.client.username_pw_set(self.user, self.password)

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Đã kết nối MQTT Broker {self.host}:{self.port}")
            client.subscribe([(self.topic_ack, 1), (self.topic_status, 1)])
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Lỗi kết nối MQTT, rc={rc}")

    def _on_disconnect(self, client, userdata, rc):
        self.stats["reconnect_events"] += 1
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Mất kết nối broker! Đang reconnect (lần thứ {self.stats['reconnect_events']})")

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        payload_str = msg.payload.decode("utf-8", errors="ignore")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            data = json.loads(payload_str)
        except Exception:
            data = {"raw": payload_str}

        if topic == self.topic_status:
            self.stats["heartbeat_count"] += 1
            self.stats["last_heartbeat"] = now_str
            status = data.get("status")
            if status == "OFFLINE":
                self.stats["error_events"] += 1
                self.log_event("DEVICE_OFFLINE", data)
            elif status == "ALIVE":
                # Heartbeat bình thường, in mỗi 10 lần để không spam
                if self.stats["heartbeat_count"] % 12 == 0:
                    print(f"[{now_str}] Heartbeat # {self.stats['heartbeat_count']} - Thiết bị {self.device_code} ALIVE")

        elif topic == self.topic_ack:
            self.stats["acks_received"] += 1
            self.stats["last_ack"] = now_str
            req_id = data.get("request_id")
            status = data.get("status")
            error = data.get("error")
            if error or status == "FAILED":
                self.stats["error_events"] += 1
                self.log_event("ACK_ERROR", data)
                print(f"[{now_str}] [ACK CẢNH BÁO] req={req_id} status={status} error={error}")
            else:
                print(f"[{now_str}] [ACK THÀNH CÔNG] req={req_id} status={status} elapsed={data.get('elapsed_ms')}ms")

    def log_event(self, event_type: str, details: dict):
        self.stats["log_records"].append({
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "type": event_type,
            "details": details
        })

    def run(self, output_dir: Path):
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"Bắt đầu Endurance Test cho {self.device_code} trong {self.duration_seconds/3600:.1f} giờ...")
        self.client.connect(self.host, self.port, keepalive=60)
        self.client.loop_start()

        start_time = time.time()
        last_cmd_time = 0
        cycle_idx = 0

        try:
            while time.time() - start_time < self.duration_seconds:
                now = time.time()
                # Gửi lệnh tải tuần tự cách nhau mỗi `interval_sec`
                if now - last_cmd_time >= self.interval_sec:
                    cycle_idx += 1
                    last_cmd_time = now
                    # Luân phiên LED -> Buzzer -> Motor
                    cmd_type = ["LED_ON", "BUZZER_ON", "MOTOR_ON"][cycle_idx % 3]
                    req_id = f"endur-{cycle_idx:04d}-{uuid.uuid4().hex[:4]}"
                    payload = {
                        "request_id": req_id,
                        "command": cmd_type,
                        "duration": 1000,
                        "intensity": "WEAK"
                    }
                    self.stats["commands_sent"] += 1
                    self.client.publish(self.topic_cmd, json.dumps(payload), qos=1)
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Phát lệnh định kỳ #{cycle_idx}: {cmd_type} (req={req_id})")

                    # Ghi checkpoint ra đĩa mỗi 15 phút
                    if cycle_idx % 15 == 0:
                        self.save_checkpoint(output_dir)

                time.sleep(1)

        except KeyboardInterrupt:
            print("\nNgười dùng đã chủ động dừng test sớm.")

        finally:
            self.stats["end_time"] = datetime.now().isoformat()
            self.stats["total_run_seconds"] = int(time.time() - start_time)
            self.save_checkpoint(output_dir)
            self.client.loop_stop()
            self.client.disconnect()
            print("\nĐã hoàn thành Endurance Test. Báo cáo thống kê:")
            print(json.dumps({k: v for k, v in self.stats.items() if k != "log_records"}, indent=2))

    def save_checkpoint(self, output_dir: Path):
        json_file = output_dir / "w4-tv1-endurance-report.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(self.stats, f, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description="Chạy test tải liên tục 2-4 giờ (W4-TV1-08)")
    parser.add_argument("--host", default="192.168.2.100")
    parser.add_argument("--port", type=int, default=1884)
    parser.add_argument("--user", default="alert-01")
    parser.add_argument("--password", default="alert01_secret")
    parser.add_argument("--device", default="alert-01")
    parser.add_argument("--hours", type=float, default=2.0, help="Thời gian chạy (giờ), ví dụ: 2.0 hoặc 4.0")
    parser.add_argument("--interval", type=int, default=30, help="Chu kỳ phát lệnh (giây), mặc định 30s")
    parser.add_argument("--output-dir", default="docs/evidence")

    args = parser.parse_args()
    runner = EnduranceRunner(args.host, args.port, args.user, args.password, args.device, args.hours, args.interval)
    runner.run(Path(args.output_dir))


if __name__ == "__main__":
    main()
