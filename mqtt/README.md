# MQTT – Trạng thái & hướng bàn giao

## 1. Trạng thái hiện tại

Có các file chính:

```text
mqtt/
├── consumer.py
└── publish_test.py
```

Mục tiêu:

```text
TV3 / AI
    ↓
MQTT topic
    ↓
Mosquitto
    ↓
consumer.py
    ↓
PostgreSQL
    ↓
WebSocket
```

## 2. Consumer hiện tại

Consumer subscribe:

```text
driver/+/telemetry
```

Ví dụ:

```text
driver/device_01/telemetry
```

Khi nhận message, consumer:

1. decode JSON;
2. kiểm tra message type;
3. gọi `save_telemetry(payload)`.

## 3. Test hiện tại

Đã thử chạy:

```cmd
set PYTHONPATH=backend
python -m mqtt.consumer
```

Kết quả hiện tại:

```text
ConnectionRefusedError: [WinError 10061]
No connection could be made because the target machine actively refused it
```

Lỗi xảy ra tại:

```python
client.connect(MQTT_HOST, MQTT_PORT, 60)
```

Cấu hình hiện tại:

```env
MQTT_HOST=localhost
MQTT_PORT=1883
```

Kết luận:

**Chưa thể kết luận consumer sai. Máy TV4 hiện chưa có MQTT Broker/Mosquitto chạy tại localhost:1883.**

## 4. Việc TV2 cần làm

Trên máy TV2:

### Kiểm tra broker

```cmd
netstat -ano | findstr :1883
```

Phải có service LISTENING tại port 1883.

Nếu nhóm dùng Mosquitto service thì khởi động service.

Nếu nhóm dùng Docker thì chạy Mosquitto bằng Docker/Compose theo cấu hình của nhóm.

### Chạy consumer

```cmd
set PYTHONPATH=backend
python -m mqtt.consumer
```

Kỳ vọng:

```text
Đã kết nối với MQTT
Subscribed: driver/+/telemetry
```

## 5. Publisher test

`publish_test.py` hiện gửi thử:

```json
{
  "device_code": "DM-000001",
  "ear": 0.31,
  "perclos": 0.02,
  "angle_x": 2.1,
  "angle_y": 1.2,
  "angle_z": 0.5,
  "confidence": 0.67
}
```

Nên thống nhất import theo cách chạy:

```python
from app.core.config import settings
```

khi dùng:

```cmd
set PYTHONPATH=backend
```

## 6. Device code

Nên dùng:

```text
device_code
```

trong MQTT payload.

Ví dụ:

```json
{
  "device_code": "DM-000001",
  "ear": 0.31,
  "perclos": 0.02
}
```

Không nên dùng database `Device.id` làm định danh giao tiếp MQTT.

Backend sẽ xử lý:

```text
device_code
    ↓
Device.device_code
    ↓
Device.id
    ↓
Telemetry.device_id
```

## 7. Cần kiểm tra device tồn tại

`save_telemetry()` hiện tìm:

```python
Device.device_code == device_code
```

Nếu database chưa có:

```text
DM-000001
```

sẽ báo:

```text
Không tìm thấy device: DM-000001
```

Đây là lỗi dữ liệu device, không phải lỗi MQTT.

Có thể kiểm tra:

```sql
SELECT id, device_code, model, name
FROM devices;
```

## 8. Hướng phát triển tiếp theo

Sau khi MQTT hoạt động:

```text
publish_test.py
      ↓
Mosquitto
      ↓
consumer.py
      ↓
validate payload
      ↓
save_telemetry()
      ↓
WebSocket Manager
      ↓
React Dashboard
```

Consumer cần được bổ sung:

- Pydantic validation cho MQTT payload;
- broadcast telemetry sau khi lưu thành công;
- xử lý lỗi JSON;
- xử lý lỗi database;
- thống nhất payload với TV3.

## 9. Payload khuyến nghị

Nếu nhóm thống nhất có `driver_state`:

```json
{
  "device_code": "DM-000001",
  "ear": 0.31,
  "perclos": 0.02,
  "driver_state": "ATTENTIVE",
  "angle_x": 2.1,
  "angle_y": 1.2,
  "angle_z": 0.5,
  "confidence": 0.67
}
```

Cần thống nhất payload này với TV3 trước khi chốt code.
