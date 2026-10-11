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
import uuid
import paho.mqtt.client as mqtt

from config import (
    DEVICE_ID,
    MQTT_BROKER,
    MQTT_PORT,
    MQTT_TOPIC,
    MQTT_EVENT_TOPIC,
    MQTT_STATUS_TOPIC,
    MQTT_USERNAME,
    MQTT_PASSWORD
)


class MQTTClient:

    def __init__(self):

        # TV3-14: Client ID rieng cho moi lan khoi dong
        self.client_id = f"{DEVICE_ID}-{uuid.uuid4().hex[:8]}"

        self.client = mqtt.Client(
            client_id=self.client_id
        )

        self.connected = False

        # Neu broker co authentication
        if MQTT_USERNAME:
            self.client.username_pw_set(
                MQTT_USERNAME,
                MQTT_PASSWORD
            )

        # TV3-14: Last Will
        offline_payload = json.dumps({
            "device_id": DEVICE_ID,
            "status": "OFFLINE"
        })

        self.client.will_set(
            MQTT_STATUS_TOPIC,
            payload=offline_payload,
            qos=1,
            retain=True
        )

        # MQTT callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

        # TV3-15: tu dong thu ket noi lai
        self.client.reconnect_delay_set(
            min_delay=1,
            max_delay=10
        )

        try:

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


    # MQTT ket noi thanh cong
    def _on_connect(
        self,
        client,
        userdata,
        flags,
        rc
    ):

        if rc == 0:

            self.connected = True

            print("MQTT connected")

            online_payload = json.dumps({
                "device_id": DEVICE_ID,
                "status": "ONLINE"
            })

            client.publish(
                MQTT_STATUS_TOPIC,
                online_payload,
                qos=1,
                retain=True
            )

        else:

            self.connected = False

            print(
                f"MQTT connection failed, rc={rc}"
            )


    # MQTT mat ket noi
    def _on_disconnect(
        self,
        client,
        userdata,
        rc
    ):

        self.connected = False

        if rc != 0:

            print(
                "MQTT disconnected unexpectedly - reconnecting..."
            )

        else:

            print("MQTT disconnected")


    # Gui telemetry
    def publish_telemetry(self, data):

        if not self.connected:
            return

        payload = json.dumps(data)

        self.client.publish(
            MQTT_TOPIC,
            payload
        )

        print(
            json.dumps(
                data,
                indent=4
            )
        )


    # Gui event
    def publish_event(self, data):

        if not self.connected:
            return

        payload = json.dumps(data)

        self.client.publish(
            MQTT_EVENT_TOPIC,
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

            offline_payload = json.dumps({
                "device_id": DEVICE_ID,
                "status": "OFFLINE"
            })

            # Clean shutdown -> chu dong gui OFFLINE
            self.client.publish(
                MQTT_STATUS_TOPIC,
                offline_payload,
                qos=1,
                retain=True
            )

            self.client.disconnect()

        self.client.loop_stop()