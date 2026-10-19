'''
Mục tiêu:
MQTT lỗi → camera không dừng.
Broker tắt → client tự thử kết nối lại.
Broker bật lại → tự reconnect.
Reconnect thành công → gửi lại ONLINE.
Mất kết nối bất thường → Last Will OFFLINE.
Tắt chương trình bình thường → gửi OFFLINE chủ động.
Vẫn giữ client_id riêng.
'''

import json
import logging
import threading
import uuid
import paho.mqtt.client as mqtt
import time
from datetime import datetime, timezone

from config import (
    ACK_TOPIC, MQTT_USERNAME, MQTT_PASSWORD,
    MQTT_BROKER, MQTT_PORT,
    DEVICE_CODE, MODEL_VERSION, 
    STATUS_TOPIC, TELEMETRY_TOPIC, EVENT_TOPIC,
)

from edge_queue import get_queue, remove_from_queue

logger = logging.getLogger(__name__)

class MQTTClient:

    def __init__(self):

        # TV3-14: Client ID rieng cho moi lan khoi dong
        self.client_id = f"{DEVICE_CODE}-{uuid.uuid4().hex[:8]}"

        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=self.client_id
        )

        self.connected = False

        self.heartbeat_interval = 15.0
        self.last_heartbeat = 0.0

        # Theo dõi ACK của từng message
        self.pending_acks = {}
        self.ack_lock = threading.Lock()

        # Đánh thức worker khi có kết nối hoặc có message mới
        self.queue_wakeup = threading.Event()
        self.stop_event = threading.Event()


        # Neu broker co authentication
        if MQTT_USERNAME:
            self.client.username_pw_set(
                MQTT_USERNAME,
                MQTT_PASSWORD
            )

        # TV3-14: Last Will
        offline_payload = json.dumps({
            "device_code": DEVICE_CODE,
            "model_version": MODEL_VERSION,
            "status": "OFFLINE",
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        self.client.will_set(
            STATUS_TOPIC,
            payload=offline_payload,
            qos=1,
            retain=True
        )

        # MQTT callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

        # TV3-15: tu dong thu ket noi lai
        self.client.reconnect_delay_set(
            min_delay=1,
            max_delay=10
        )

        try:
            self.worker = threading.Thread(
                target=self._queue_worker,
                daemon=True,
            )
            self.worker.start()

            # Khong chan camera neu MQTT dang loi
            self.client.connect_async(
                MQTT_BROKER,
                MQTT_PORT,
                60
            )

            # MQTT chay o background
            self.client.loop_start()

            print("MQTT client started")
            print(f"MQTT client ID: {self.client_id}")

        except Exception as e:

            print("MQTT startup failed:", e)


    # Publish status
    def _build_status_payload(self, status):
        return json.dumps({
            "device_code": DEVICE_CODE,
            "model_version": MODEL_VERSION,
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    def publish_status(self, status):
        if not self.connected:
            return

        info = self.client.publish(
            STATUS_TOPIC,
            self._build_status_payload(status),
            qos=1,
            retain=True
        )

        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            print(f"Failed to publish status: {status}")

    # MQTT ket noi thanh cong
    def _on_connect(self, client, userdata, flags, rc, properties):

        print(f"[MQTT DEBUG] on_connect called, rc={rc}", flush=True)

        if rc == 0:
            self.connected = True
            print("[MQTT] Connected successfully", flush=True)

            self.publish_status("ONLINE")
            self.last_heartbeat = time.monotonic()

            # Subscribe topic nhận ACK từ backend
            result, _ = client.subscribe(ACK_TOPIC, qos=1)
            if result != mqtt.MQTT_ERR_SUCCESS:
                logger.error("Failed to subscribe to ACK topic.")

            # Xử lý các message còn tồn trong SQLite
            self.notify_queue()

        else:
            self.connected = False
            print(f"[MQTT] Connection failed, rc={rc}", flush=True)

    # MQTT mat ket noi
    def _on_disconnect(self, client, userdata, flags, rc, properties):
        self.connected = False

        if rc != 0:
            print("MQTT disconnected unexpectedly - reconnecting...")
        else:
            print("MQTT disconnected")

    def _on_message(self, client, userdata, msg):
        """Nhận ACK từ backend và xóa message đã lưu thành công."""
        try:
            ack = json.loads(msg.payload.decode("utf-8"))
            message_id = ack.get("message_id")
            status = ack.get("status")

            if not message_id:
                logger.warning("Received ACK without message_id.")
                return

            if status != "SAVED":
                logger.warning(
                    "Message %s was not saved. Status: %s",
                    message_id,
                    status,
                )
                return

            # Chỉ xóa sau khi backend xác nhận đã lưu
            if remove_from_queue([message_id]):
                logger.info("Message %s acknowledged and removed.", message_id)

                # Báo cho worker biết message đã được ACK
                with self.ack_lock:
                    ack_event = self.pending_acks.get(message_id)

                if ack_event:
                    ack_event.set()
            else:
                logger.error(
                    "Could not remove acknowledged message %s.",
                    message_id,
                )

        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.exception("Invalid ACK payload.")
        except Exception:
            logger.exception("Error while processing ACK.")

    def notify_queue(self):
        """Đánh thức worker để xử lý hàng đợi SQLite."""
        self.queue_wakeup.set()

    def _queue_worker(self):
        """Publish message trong SQLite và chờ application-level ACK."""
        while not self.stop_event.is_set():
            self.queue_wakeup.wait(timeout=2)
            self.queue_wakeup.clear()

            if self.stop_event.is_set():
                break

            if not self.connected:
                continue

            messages = get_queue(limit=100)

            if messages is None:
                # Lỗi đọc DB; thử lại ở vòng tiếp theo
                continue

            for row in messages:
                if self.stop_event.is_set() or not self.connected:
                    break

                message_id, topic, payload = row[:3]

                ack_event = threading.Event()

                # Đăng ký trước khi publish để tránh lỡ ACK đến sớm
                with self.ack_lock:
                    self.pending_acks[message_id] = ack_event

                try:
                    info = self.client.publish(
                        topic,
                        payload=payload,
                        qos=1,
                    )

                    if info.rc != mqtt.MQTT_ERR_SUCCESS:
                        logger.warning(
                            "Publish failed for %s: rc=%s",
                            message_id,
                            info.rc,
                        )
                        continue

                    logger.info(
                        "Published queued message %s to %s.",
                        message_id,
                        topic,
                    )

                    # Giữ bản ghi trong DB nếu chưa có ACK
                    if not ack_event.wait(timeout=10):
                        logger.warning(
                            "ACK timeout for %s; message remains queued.",
                            message_id,
                        )
                        # Tránh gửi dồn liên tục khi backend chưa phản hồi
                        break

                except Exception:
                    logger.exception(
                        "Error publishing message %s.",
                        message_id,
                    )
                    break

                finally:
                    with self.ack_lock:
                        self.pending_acks.pop(message_id, None)


    # =========================
    # Gửi telemetry
    # =========================
    def publish_telemetry(self, data):

        if not self.connected:
            return

        payload = json.dumps(data)

        self.client.publish(
            TELEMETRY_TOPIC,
            payload
        )

        print(
            json.dumps(
                data,
                indent=4
            )
        )


    # =========================
    # Gửi event
    # =========================
    def publish_event(self, data):

        if not self.connected:
            return

        payload = json.dumps(data)

        self.client.publish(
            EVENT_TOPIC,
            payload
        )

        print("EVENT:")

        print(
            json.dumps(
                data,
                indent=4
            )
        )


    # Dong MQTT khi chuong trinh ket thuc binh thuong
    def close(self):

        if self.connected:

            # Clean shutdown -> chu dong gui OFFLINE
            self.publish_status("OFFLINE")

            self.client.disconnect()

        self.client.loop_stop()