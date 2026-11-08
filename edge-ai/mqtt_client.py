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

from edge_queue import get_queue, remove_from_queue, mark_backfill, schedule_message

logger = logging.getLogger(__name__)

class MQTTClient:

    def __init__(self, model_version=MODEL_VERSION):
        self.model_version = model_version

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
        self.max_inflight = 24
        self.max_history_inflight = 6
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
            "model_version": self.model_version,
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
        self.client.on_subscribe = self._on_subscribe
        self.ack_subscription_mid = None

        # TV3-15: tu dong thu ket noi lai
        self.client.reconnect_delay_set(
            min_delay=1,
            max_delay=10
        )

        try:
            mark_backfill()
            self.client.max_inflight_messages_set(24)
            self.client.max_queued_messages_set(48)
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
            "model_version": self.model_version,
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
            self.connected = False
            print("[MQTT] Transport connected; waiting for storage ACK subscription", flush=True)

            # Subscribe topic nhận ACK từ backend
            result, self.ack_subscription_mid = client.subscribe(ACK_TOPIC, qos=1)
            if result != mqtt.MQTT_ERR_SUCCESS:
                logger.error("Failed to subscribe to ACK topic.")

        else:
            self.connected = False
            print(f"[MQTT] Connection failed, rc={rc}", flush=True)

    def _on_subscribe(self, client, userdata, mid, reason_codes, properties=None):
        if mid != self.ack_subscription_mid or any(getattr(code, "is_failure", False) for code in reason_codes):
            return
        self.connected = True
        self.publish_status("ONLINE")
        self.last_heartbeat = time.monotonic()
        self.notify_queue()
        logger.info("MQTT ready; storage ACK subscription confirmed")

    # MQTT mat ket noi
    def _on_disconnect(self, client, userdata, flags, rc, properties):
        self.connected = False
        try:
            mark_backfill()
        except Exception:
            logger.exception("Cannot mark disconnected outbox as history")

        if rc != 0:
            print("MQTT disconnected unexpectedly - reconnecting...")
        else:
            print("MQTT disconnected")

    def _on_message(self, client, userdata, msg):
        """Nhận ACK từ backend và xóa message đã lưu thành công."""
        if msg.topic != ACK_TOPIC:
            return
        try:
            ack = json.loads(msg.payload.decode("utf-8"))
            message_id = ack.get("message_id")
            status = ack.get("status")

            print("=====================================================", flush=True)
            print(f"[MQTT DEBUG] Received ACK: \n{ack}", flush=True)
            print("=====================================================", flush=True)
            
            if not isinstance(message_id, str) or not message_id:
                logger.warning("Received ACK without message_id.")
                return

            with self.ack_lock:
                pending = self.pending_acks.get(message_id)
            if status == "SAVED":
                if remove_from_queue([message_id]):
                    with self.ack_lock:
                        self.pending_acks.pop(message_id, None)
                    logger.info("Message %s acknowledged and removed.", message_id)
            elif status == "FAILED" and pending:
                schedule_message(message_id, 60, "Backend rejected message",
                                 dead=pending["attempt"] >= 8)
                with self.ack_lock:
                    self.pending_acks.pop(message_id, None)
                logger.warning("Backend rejected message %s; retained for inspection/retry", message_id)
            self.notify_queue()

        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.exception("Invalid ACK payload.")
        except Exception:
            logger.exception("Error while processing ACK.")

    def notify_queue(self):
        """Đánh thức worker để xử lý hàng đợi SQLite."""
        self.queue_wakeup.set()

    def process_queue_once(self):
        """Bounded in-flight window; history cannot consume the live-message slots."""
        if not self.connected:
            return
        now = time.monotonic()
        if hasattr(self, "heartbeat_interval") and now-self.last_heartbeat >= self.heartbeat_interval:
            self.publish_status("ALIVE")
            self.last_heartbeat = now
        with self.ack_lock:
            expired = [(key, item) for key, item in self.pending_acks.items()
                       if item["deadline"] <= now]
            for key, _ in expired:
                self.pending_acks.pop(key, None)
        for key, item in expired:
            delay = min(60, 2 ** min(item["attempt"], 6))
            schedule_message(key, delay, "Storage ACK timeout")
            logger.warning("MQTT RETRY scheduled: message_id=%s retry_in=%ss", key, delay)
        with self.ack_lock:
            available = self.max_inflight - len(self.pending_acks)
            history_slots = self.max_history_inflight - sum(
                item["backfill"] for item in self.pending_acks.values())
        if available <= 0:
            return
        live = get_queue(limit=available, backfill=False) or []
        history = get_queue(limit=max(0, min(history_slots, available-len(live))), backfill=True) or []
        for message_id, topic, payload, created_at, retries, backfill in live + history:
            if self.stop_event.is_set() or not self.connected:
                break
            with self.ack_lock:
                if message_id in self.pending_acks:
                    continue
            try:
                body = json.loads(payload)
                if not isinstance(body, dict) or body.get("message_id") != message_id:
                    raise ValueError("Invalid outbox message identity")
                # Transport metadata is excluded from BE idempotency hashes.
                # The application event stored in SQLite is never modified.
                body["_delivery"] = {"mode": "backfill" if backfill else "live"}
                wire = json.dumps(body, allow_nan=False, separators=(",", ":"))
            except (ValueError, TypeError):
                schedule_message(message_id, 0, "Invalid JSON/identity", dead=True)
                continue
            schedule_message(message_id, 10, attempted=True)
            with self.ack_lock:
                self.pending_acks[message_id] = dict(deadline=time.monotonic()+10,
                                                   attempt=retries+1, backfill=bool(backfill))
            try:
                info = self.client.publish(topic, payload=wire, qos=1)
                if info.rc != mqtt.MQTT_ERR_SUCCESS:
                    raise RuntimeError(f"MQTT rc={info.rc}")
                logger.info("MQTT %s: message_id=%s attempt=%d delivery=%s",
                            "FIRST" if retries == 0 else "RETRY", message_id, retries+1,
                            "backfill" if backfill else "live")
            except Exception:
                with self.ack_lock:
                    self.pending_acks.pop(message_id, None)
                schedule_message(message_id, min(60, 2 ** min(retries+1, 6)), "MQTT publish failed")
                logger.exception("Cannot publish queued message %s", message_id)

    def _queue_worker(self):
        while not self.stop_event.is_set():
            self.queue_wakeup.wait(timeout=0.2)
            self.queue_wakeup.clear()
            try:
                self.process_queue_once()
            except Exception:
                logger.exception("MQTT outbox cycle failed; data remains in SQLite")

    def publish_telemetry(self, data):
        from service.message.publisher import send_message
        return send_message(self, TELEMETRY_TOPIC, data)

    def publish_event(self, data):
        from service.message.publisher import send_message
        return send_message(self, EVENT_TOPIC, data)

    # Dong MQTT khi chuong trinh ket thuc binh thuong
    def close(self):

        self.stop_event.set()
        self.queue_wakeup.set()
        with self.ack_lock:
            self.pending_acks.clear()
        if hasattr(self, "worker"):
            self.worker.join(timeout=3)

        if self.connected:

            # Clean shutdown -> chu dong gui OFFLINE
            self.publish_status("OFFLINE")

            self.client.disconnect()

        self.client.loop_stop()
