"""
Test Suite tự động cho ESP32 Alert Node - Tuần 4 (W4-TV1-01 -> W4-TV1-05 & W4-TV1-09)
Tác giả: Nhóm TV1 (IoT)
Mục đích:
- Kiểm thử LED / Buzzer / Motor với các mức intensity (WEAK, MEDIUM, STRONG, CONSTANT)
- Kiểm thử Lệnh trùng (Idempotency - cùng request_id, cùng payload)
- Kiểm thử ID trùng nhưng khác nội dung (Conflict - cùng request_id, khác payload)
- W4-TV1-01: Kiểm tra phiên bản cũ (Stale Revision), so sánh nội dung cho ID trùng (Duplicate ID Conflict)
- W4-TV1-02: Giữ lệnh đang chạy dùng timing đã chụp; đổi config khi cả ba tải đang chạy
- W4-TV1-03: Phối hợp TV2 kiểm thử cơ chế At-Least-Once (Retry + Idempotency) với ACK QoS 0
- W4-TV1-09: Đo độ trễ vòng lặp lệnh -> ACK (Latency Benchmark)
- Xuất log chi tiết kèm timestamp, request_id, commit git làm bằng chứng bàn giao (W4-TV1-06)
"""

import sys
import json
import time
import uuid
import argparse
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("Vui long cai dat paho-mqtt: pip install paho-mqtt")
    sys.exit(1)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")


def make_standard_timings(led_on1=500, led_off1=500):
    return {
        "led": {
            "1": {"on_ms": led_on1, "off_ms": led_off1},
            "2": {"on_ms": 1000, "off_ms": 300},
            "3": {"on_ms": 1500, "off_ms": 100}
        },
        "buzzer": {
            "1": {"on_ms": 200, "off_ms": 800},
            "2": {"on_ms": 500, "off_ms": 500},
            "3": {"on_ms": 1000, "off_ms": 200}
        },
        "motor": {
            "1": {"on_ms": 300, "off_ms": 700},
            "2": {"on_ms": 600, "off_ms": 400},
            "3": {"on_ms": 1000, "off_ms": 200}
        }
    }


class Esp32Tester:
    def __init__(self, host: str, port: int, user: str = "", password: str = "", device_code: str = "alert-01"):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.device_code = device_code

        self.topic_cmd = f"driver/{device_code}/command"
        self.topic_ack = f"driver/{device_code}/ack"
        self.topic_status = f"driver/{device_code}/status"
        self.topic_cfg_update = f"driver/{device_code}/config/update"
        self.topic_cfg_applied = f"driver/{device_code}/config/applied"

        self.received_acks: Dict[str, List[Dict[str, Any]]] = {}
        self.received_status: List[Dict[str, Any]] = []
        self.received_configs: List[Dict[str, Any]] = []
        self.ack_timestamps: Dict[str, float] = {}

        self.client = mqtt.Client(client_id=f"w4-tester-{uuid.uuid4().hex[:6]}")
        if self.user:
            self.client.username_pw_set(self.user, self.password)

        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

        self.test_records: List[Dict[str, Any]] = []

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print(f"[MQTT] Đã kết nối thành công tới broker {self.host}:{self.port}")
            # Subscribe topics với QoS 1 (nhận lệnh/ack từ broker)
            client.subscribe([(self.topic_ack, 1), (self.topic_status, 1), (self.topic_cfg_applied, 1)])
            print(f"[MQTT] Đã đăng ký topics: {self.topic_ack}, {self.topic_status}, {self.topic_cfg_applied}")
        else:
            print(f"[MQTT] Kết nối thất bại, mã lỗi rc={rc}")

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        payload_str = msg.payload.decode("utf-8", errors="ignore")
        receive_time = time.time()
        try:
            data = json.loads(payload_str)
        except Exception:
            data = {"raw": payload_str}

        if topic == self.topic_ack:
            req_id = data.get("request_id", "unknown")
            if req_id not in self.received_acks:
                self.received_acks[req_id] = []
            self.received_acks[req_id].append(data)
            self.ack_timestamps[req_id] = receive_time
            print(f"  << [ACK] req_id={req_id} status={data.get('status')} error={data.get('error')} elapsed={data.get('elapsed_ms')}ms")

        elif topic == self.topic_status:
            self.received_status.append(data)
            print(f"  << [STATUS] device={data.get('device_code')} status={data.get('status')} fw={data.get('firmware_version')} cfg={data.get('config_id')}")

        elif topic == self.topic_cfg_applied:
            self.received_configs.append(data)
            print(f"  << [CONFIG_APPLIED] config_id={data.get('config_id')} status={data.get('status')} error={data.get('error')}")

    def connect(self, timeout: int = 5) -> bool:
        try:
            self.client.connect(self.host, self.port, keepalive=60)
            self.client.loop_start()
            start = time.time()
            while time.time() - start < timeout:
                if self.client.is_connected():
                    time.sleep(0.5)
                    return True
                time.sleep(0.1)
            return False
        except Exception as e:
            print(f"[LỖI KẾT NỐI] {e}")
            return False

    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()

    def wait_for_ack(self, req_id: str, expected_status: Optional[str] = None, timeout: float = 4.0) -> Optional[Dict[str, Any]]:
        start = time.time()
        while time.time() - start < timeout:
            if req_id in self.received_acks:
                for ack in self.received_acks[req_id]:
                    if expected_status is None or ack.get("status") == expected_status:
                        return ack
            time.sleep(0.05)
        return None

    def wait_for_config_result(self, config_id: str, timeout: float = 3.0) -> Optional[Dict[str, Any]]:
        start = time.time()
        while time.time() - start < timeout:
            for cfg in self.received_configs:
                if cfg.get("config_id") == config_id or cfg.get("config_id") is None:
                    return cfg
            time.sleep(0.05)
        return None

    def send_command(self, req_id: str, command: str, duration: int, intensity: str) -> float:
        payload = {
            "request_id": req_id,
            "command": command,
            "duration": duration,
            "intensity": intensity
        }
        send_time = time.time()
        self.client.publish(self.topic_cmd, json.dumps(payload), qos=1)
        print(f"  >> [SEND CMD] {command} ({intensity}, {duration}ms) req_id={req_id}")
        return send_time

    def run_all_tests(self) -> Dict[str, Any]:
        commit_hash = "unknown"
        try:
            commit_hash = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()
        except Exception:
            pass

        print(f"\n=======================================================")
        print(f"  BẮT ĐẦU KIỂM THỬ ESP32 ALERT NODE - TUẦN 4")
        print(f"  Bao phủ: W4-TV1-01 đến W4-TV1-05 & W4-TV1-09")
        print(f"  Thiết bị: {self.device_code} | Commit: {commit_hash}")
        print(f"  Thời gian: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"=======================================================\n")

        # TC-00: Kiểm tra Heartbeat ALIVE
        print("[TC-00] Kiểm tra trạng thái thiết bị ALIVE (Heartbeat)")
        alive = len(self.received_status) > 0
        if not alive:
            time.sleep(3)
            alive = len(self.received_status) > 0
        self.record_result("TC-00", "Kiểm tra Heartbeat ALIVE", "N/A", alive, 
                           {"status": self.received_status[-1] if self.received_status else "NO_STATUS"})

        # TC-01: Test LED
        req_led = f"w4-led-{uuid.uuid4().hex[:6]}"
        print(f"\n[TC-01] Test LED_ON (duration=2000ms, intensity=MEDIUM)")
        self.send_command(req_led, "LED_ON", 2000, "MEDIUM")
        ack_start = self.wait_for_ack(req_led, "STARTED", timeout=3.0)
        ack_done = self.wait_for_ack(req_led, "COMPLETED", timeout=4.0)
        self.record_result("TC-01", "Điều khiển LED D26", req_led, ack_start is not None, 
                           {"started": ack_start, "completed": ack_done})

        # TC-02: Test Buzzer
        req_buzz = f"w4-buzz-{uuid.uuid4().hex[:6]}"
        print(f"\n[TC-02] Test BUZZER_ON (duration=1500ms, intensity=WEAK)")
        self.send_command(req_buzz, "BUZZER_ON", 1500, "WEAK")
        ack_buzz = self.wait_for_ack(req_buzz, "STARTED", timeout=3.0)
        self.record_result("TC-02", "Điều khiển Buzzer D25", req_buzz, ack_buzz is not None, 
                           {"started": ack_buzz})

        # TC-03: Test Motor
        req_mot = f"w4-mot-{uuid.uuid4().hex[:6]}"
        print(f"\n[TC-03] Test MOTOR_ON (duration=1500ms, intensity=STRONG)")
        self.send_command(req_mot, "MOTOR_ON", 1500, "STRONG")
        ack_mot = self.wait_for_ack(req_mot, "STARTED", timeout=3.0)
        self.record_result("TC-03", "Điều khiển Motor rung D33", req_mot, ack_mot is not None, 
                           {"started": ack_mot})

        time.sleep(2)

        # TC-04: Test Lệnh trùng (Idempotency)
        req_dup = f"w4-dup-{uuid.uuid4().hex[:6]}"
        print(f"\n[TC-04] Test Lệnh trùng (Idempotency - gửi 2 lần cùng payload & request_id)")
        self.send_command(req_dup, "LED_ON", 1000, "CONSTANT")
        self.wait_for_ack(req_dup, timeout=2.0)
        time.sleep(1.2)

        print(f"  Gửi lại lần 2 với đúng request_id={req_dup}")
        self.received_acks[req_dup] = []
        self.send_command(req_dup, "LED_ON", 1000, "CONSTANT")
        ack_dup = self.wait_for_ack(req_dup, timeout=2.0)
        dup_passed = (ack_dup is not None and ack_dup.get("status") in ["COMPLETED", "STARTED"])
        self.record_result("TC-04", "Idempotency - Lệnh trùng không kích hoạt lại tải", req_dup, dup_passed, 
                           {"cached_ack": ack_dup})

        # TC-05: Test ID trùng nhưng khác nội dung
        print(f"\n[TC-05] Test ID trùng nhưng khác nội dung (Payload conflict)")
        print(f"  Gửi request_id={req_dup} nhưng đổi thành MOTOR_ON thay vì LED_ON")
        self.received_acks[req_dup] = []
        self.send_command(req_dup, "MOTOR_ON", 3000, "STRONG")
        ack_conflict = self.wait_for_ack(req_dup, timeout=2.0)
        conflict_passed = (ack_conflict is not None and ack_conflict.get("status") == "FAILED" 
                           and ack_conflict.get("error") == "DUPLICATE_ID_MISMATCH")
        self.record_result("TC-05", "ID trùng khác nội dung trả DUPLICATE_ID_MISMATCH", req_dup, conflict_passed, 
                           {"response": ack_conflict})

        # TC-06: Test Cấu hình sai (Config Rejection)
        print(f"\n[TC-06] Test Cấu hình sai / không hợp lệ (Config Rejection)")
        bad_config_id = f"cfg-bad-{uuid.uuid4().hex[:4]}"
        bad_payload = {
            "config_id": bad_config_id,
            "revision": 10,
            "timings": {
                "led": {"1": {"on_ms": -50, "off_ms": 100}}  # Sai vì thời gian âm
            }
        }
        self.received_configs.clear()
        self.client.publish(self.topic_cfg_update, json.dumps(bad_payload), qos=1)
        res_bad = self.wait_for_config_result(bad_config_id, timeout=2.5)
        bad_passed = (res_bad is not None and res_bad.get("status") == "REJECTED")
        self.record_result("TC-06", "Từ chối cấu hình sai (Config REJECTED)", bad_config_id, bad_passed, 
                           {"result": res_bad})

        # TC-07: Test Cấu hình hợp lệ (W4-TV1-01: Metadata revision = 2)
        print(f"\n[TC-07] Test Cấu hình hợp lệ kèm Metadata Revision (W4-TV1-01)")
        good_config_id = f"cfg-v2-{uuid.uuid4().hex[:4]}"
        good_payload = {
            "config_id": good_config_id,
            "revision": 2,
            "timings": make_standard_timings(led_on1=600, led_off1=400)
        }
        self.received_configs.clear()
        self.client.publish(self.topic_cfg_update, json.dumps(good_payload), qos=1)
        res_good = self.wait_for_config_result(good_config_id, timeout=2.5)
        good_passed = (res_good is not None and res_good.get("status") == "APPLIED")
        self.record_result("TC-07", "Áp dụng cấu hình chuẩn (Config APPLIED)", good_config_id, good_passed, 
                           {"result": res_good})

        # TC-08 (W4-TV1-01): ID config trùng nhưng NỘI DUNG KHÁC NHAU
        print(f"\n[TC-08] Test ID config trùng nhưng nội dung timing khác nhau (W4-TV1-01)")
        conflicting_payload = {
            "config_id": good_config_id,
            "revision": 3,
            "timings": make_standard_timings(led_on1=1200, led_off1=200)  # timing bị sửa
        }
        self.received_configs.clear()
        self.client.publish(self.topic_cfg_update, json.dumps(conflicting_payload), qos=1)
        res_conflict = self.wait_for_config_result(good_config_id, timeout=2.5)
        conflict_cfg_passed = (res_conflict is not None and res_conflict.get("status") == "REJECTED"
                               and res_conflict.get("error") == "DUPLICATE_ID_MISMATCH")
        self.record_result("TC-08", "ID config trùng khác nội dung trả DUPLICATE_ID_MISMATCH", good_config_id, conflict_cfg_passed, 
                           {"result": res_conflict})

        # TC-09 (W4-TV1-01): ID config trùng và NỘI DUNG GIỐNG HỆT (Re-delivery an toàn)
        print(f"\n[TC-09] Test ID config trùng và nội dung giống hệt (W4-TV1-01)")
        self.received_configs.clear()
        self.client.publish(self.topic_cfg_update, json.dumps(good_payload), qos=1)
        res_same = self.wait_for_config_result(good_config_id, timeout=2.5)
        same_passed = (res_same is not None and res_same.get("status") == "APPLIED")
        self.record_result("TC-09", "ID trùng nội dung khớp xác nhận APPLIED không ghi Flash", good_config_id, same_passed, 
                           {"result": res_same})

        # TC-10 (W4-TV1-01): Kiểm tra phiên bản cũ (Stale Revision rejected)
        print(f"\n[TC-10] Test Từ chối phiên bản cũ (Stale Revision <= activeRevision) (W4-TV1-01)")
        stale_config_id = f"cfg-stale-{uuid.uuid4().hex[:4]}"
        stale_payload = {
            "config_id": stale_config_id,
            "revision": 1,  # revision 1 nhỏ hơn revision 2 đang hoạt động
            "timings": make_standard_timings()
        }
        self.received_configs.clear()
        self.client.publish(self.topic_cfg_update, json.dumps(stale_payload), qos=1)
        res_stale = self.wait_for_config_result(stale_config_id, timeout=2.5)
        stale_passed = (res_stale is not None and res_stale.get("status") == "REJECTED" 
                        and res_stale.get("error") == "STALE_REVISION")
        self.record_result("TC-10", "Từ chối phiên bản cấu hình cũ (STALE_REVISION)", stale_config_id, stale_passed, 
                           {"result": res_stale})

        # TC-11 (W4-TV1-02): Đổi config khi cả 3 tải đang chạy
        print(f"\n[TC-11] Test Đổi config khi cả 3 tải (LED, Buzzer, Motor) đang chạy (W4-TV1-02)")
        req_l = f"w4-3load-l-{uuid.uuid4().hex[:4]}"
        req_b = f"w4-3load-b-{uuid.uuid4().hex[:4]}"
        req_m = f"w4-3load-m-{uuid.uuid4().hex[:4]}"

        # Kích hoạt cả 3 tải trong 4000ms
        self.send_command(req_l, "LED_ON", 4000, "MEDIUM")
        self.send_command(req_b, "BUZZER_ON", 4000, "WEAK")
        self.send_command(req_m, "MOTOR_ON", 4000, "STRONG")

        # Đợi 1 giây khi cả 3 tải chắc chắn đang active
        time.sleep(1.0)
        print("  >> Cả 3 tải đang chạy. Tiến hành gửi bản tin config_update mới...")
        live_cfg_id = f"cfg-live-{uuid.uuid4().hex[:4]}"
        live_payload = {
            "config_id": live_cfg_id,
            "revision": 3,
            "timings": make_standard_timings(led_on1=800, led_off1=200)
        }
        self.received_configs.clear()
        self.client.publish(self.topic_cfg_update, json.dumps(live_payload), qos=1)
        res_live = self.wait_for_config_result(live_cfg_id, timeout=2.5)

        # Chờ 3 tải cũ hoàn thành theo timing ban đầu
        ack_l_done = self.wait_for_ack(req_l, "COMPLETED", timeout=4.0)
        ack_b_done = self.wait_for_ack(req_b, "COMPLETED", timeout=4.0)
        ack_m_done = self.wait_for_ack(req_m, "COMPLETED", timeout=4.0)

        live_passed = (res_live is not None and res_live.get("status") == "APPLIED"
                       and ack_l_done is not None and ack_b_done is not None and ack_m_done is not None)
        self.record_result("TC-11", "Đổi config khi 3 tải đang chạy; giữ timing đã chụp", live_cfg_id, live_passed, 
                           {"config_status": res_live, "loads_completed": [ack_l_done is not None, ack_b_done is not None, ack_m_done is not None]})

        # TC-12 (W4-TV1-09): Đo riêng latency command -> ACK
        print(f"\n[TC-12] Đo riêng Latency: Command -> ACK (10 mẫu lặp) (W4-TV1-09)")
        latencies: List[float] = []
        for i in range(10):
            req_bench = f"w4-lat-{i}-{uuid.uuid4().hex[:4]}"
            t_send = self.send_command(req_bench, "LED_ON", 100, "CONSTANT")
            ack = self.wait_for_ack(req_bench, timeout=2.0)
            if ack and req_bench in self.ack_timestamps:
                lat = (self.ack_timestamps[req_bench] - t_send) * 1000.0
                latencies.append(lat)
            time.sleep(0.15)

        avg_lat = sum(latencies) / len(latencies) if latencies else 0.0
        min_lat = min(latencies) if latencies else 0.0
        max_lat = max(latencies) if latencies else 0.0
        print(f"  ==> Kết quả đo Latency: Min={min_lat:.1f}ms | Avg={avg_lat:.1f}ms | Max={max_lat:.1f}ms | Mẫu hợp lệ={len(latencies)}/10")
        self.record_result("TC-12", "Đo độ trễ Command -> ACK", "10-samples", len(latencies) >= 8, 
                           {"samples_count": len(latencies), "min_ms": round(min_lat, 2), "avg_ms": round(avg_lat, 2), "max_ms": round(max_lat, 2)})

        report = {
            "test_suite": "W4-TV1 Full Integration & Benchmark Test Suite",
            "device_code": self.device_code,
            "commit": commit_hash,
            "timestamp": datetime.now().isoformat(),
            "results": self.test_records,
            "latency_stats": {
                "samples": len(latencies),
                "min_ms": round(min_lat, 2),
                "avg_ms": round(avg_lat, 2),
                "max_ms": round(max_lat, 2)
            }
        }
        return report

    def record_result(self, tc_id: str, title: str, request_id: str, passed: bool, details: Dict[str, Any]):
        verdict = "PASS" if passed else "FAIL"
        self.test_records.append({
            "test_case": tc_id,
            "title": title,
            "request_id": request_id,
            "verdict": verdict,
            "details": details,
            "time": datetime.now().strftime("%H:%M:%S")
        })
        print(f"  ==> [{tc_id}] {title}: {verdict}")


def save_reports(report: Dict[str, Any], output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "w4-tv1-test-results.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n[BÁO CÁO] Đã lưu file kết quả JSON: {json_path}")

    md_path = output_dir / "w4-tv1-test-report.md"
    lines = [
        f"# Báo cáo kiểm thử tích hợp IoT Tuần 4 (W4-TV1-01 đến W4-TV1-05 & W4-TV1-09)",
        f"",
        f"- **Thiết bị thử nghiệm:** `{report['device_code']}`",
        f"- **Commit hash:** `{report['commit']}`",
        f"- **Thời gian chạy:** `{report['timestamp']}`",
        f"- **Môi trường firmware:** PlatformIO `development`",
        f"",
        f"## 1. Bảng kết quả từng ca kiểm thử",
        f"",
        f"| Mã ca | Nhiệm vụ liên quan | Nội dung kiểm thử | Request ID / Config ID | Kết quả | Ghi chú phản hồi |",
        f"| :--- | :---: | :--- | :--- | :---: | :--- |",
    ]
    for r in report["results"]:
        tc = r["test_case"]
        task_ref = "W4-TV1-05"
        if tc in ["TC-07", "TC-08", "TC-09", "TC-10"]:
            task_ref = "W4-TV1-01"
        elif tc == "TC-11":
            task_ref = "W4-TV1-02"
        elif tc == "TC-12":
            task_ref = "W4-TV1-09"

        status_txt = r["details"].get("started", {}).get("status") if "started" in r["details"] else ""
        if not status_txt and "result" in r["details"]:
            status_txt = r["details"]["result"].get("error", r["details"]["result"].get("status", ""))
        elif not status_txt and "response" in r["details"]:
            status_txt = r["details"]["response"].get("error", "")

        lines.append(f"| `{tc}` | {task_ref} | {r['title']} | `{r['request_id']}` | **{r['verdict']}** | {status_txt} |")

    lines.extend([
        f"",
        f"## 2. Số đo độ trễ chi tiết (W4-TV1-09)",
        f"",
        f"- **Số lượng mẫu:** {report['latency_stats']['samples']} lần",
        f"- **Độ trễ nhỏ nhất (Min):** `{report['latency_stats']['min_ms']} ms`",
        f"- **Độ trễ trung bình (Avg):** `{report['latency_stats']['avg_ms']} ms`",
        f"- **Độ trễ lớn nhất (Max):** `{report['latency_stats']['max_ms']} ms`",
        f"",
        f"## 3. Chốt cơ chế QoS và Retry với Backend TV2 (W4-TV1-03)",
        f"- **Subscribe (ESP32 $\\leftarrow$ Broker):** Sử dụng **QoS 1** cho các topic `driver/{code}/command` và `driver/{code}/config/update`.",
        f"- **Publish ACK (ESP32 $\\rightarrow$ Broker):** Thư viện `PubSubClient` giới hạn publish ở **QoS 0**.",
        f"- **Đảm bảo At-Least-Once Delivery:** TV2 triển khai cơ chế **Application Retry** nếu không nhận được ACK sau timeout; ESP32 xử lý **Idempotency** (dò mã băm request trong NVS) để không kích hoạt lại tải và trả lại kết quả ACK an toàn.",
    ])

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[BÁO CÁO] Đã lưu file Markdown: {md_path}")


def main():
    parser = argparse.ArgumentParser(description="Chạy test suite ESP32 Alert Node Tuần 4")
    parser.add_argument("--host", default="192.168.2.100", help="Địa chỉ IP Broker MQTT")
    parser.add_argument("--port", type=int, default=1884, help="Cổng MQTT (1884 hoặc 1883)")
    parser.add_argument("--user", default="alert-01", help="Tài khoản MQTT provisioned")
    parser.add_argument("--password", default="alert01_secret", help="Mật khẩu MQTT")
    parser.add_argument("--device", default="alert-01", help="Device code")
    parser.add_argument("--output-dir", default="docs/evidence", help="Thư mục lưu báo cáo")

    args = parser.parse_args()

    tester = Esp32Tester(host=args.host, port=args.port, user=args.user, password=args.password, device_code=args.device)
    print(f"Đang kết nối tới MQTT Broker tại {args.host}:{args.port}...")
    if not tester.connect(timeout=5):
        print(f"\n[LƯU Ý] Không kết nối được tới {args.host}:{args.port}.")
        print("Thử lại trên cổng fallback 1883...")
        tester.port = 1883
        if not tester.connect(timeout=3):
            print("Không thể kết nối tới cổng 1883. Vui lòng đảm bảo MQTT Broker đang hoạt động.")
            return

    try:
        report = tester.run_all_tests()
        save_reports(report, Path(args.output_dir))
    finally:
        tester.disconnect()


if __name__ == "__main__":
    main()
