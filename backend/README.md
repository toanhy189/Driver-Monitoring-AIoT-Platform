# Backend – Trạng thái & hướng bàn giao

## 1. Trạng thái hiện tại

Backend FastAPI hiện đã chạy được bằng:

```cmd
python -m uvicorn app.main:app --reload --app-dir backend
```

Hoặc khi đang đứng trong thư mục `backend`:

```cmd
python -m uvicorn app.main:app --reload
```

Các phần đã kiểm tra:

- PostgreSQL kết nối được.
- `POST /api/login` hoạt động.
- JWT login hoạt động.
- `GET /api/health` đã có.
- Frontend kết nối được tới WebSocket nội bộ:
  - `ws://localhost:8000/ws/telemetry`
- WebSocket hiện **chưa xác thực JWT**, chủ yếu để kiểm tra pipeline tuần 1.

## 2. WebSocket đã thêm

### `backend/app/services/websocket_manager.py`

Có `ConnectionManager` để:

- lưu các WebSocket client đang kết nối;
- accept/disconnect client;
- broadcast JSON tới các client;
- hỗ trợ gọi broadcast từ thread của MQTT consumer.

Điểm quan trọng:

```text
FastAPI WebSocket
        ↑
 WebSocket Manager
        ↑
   MQTT Consumer
```

MQTT callback chạy theo thread/event loop khác nên không `await manager.broadcast()` trực tiếp trong callback; dùng `broadcast_from_thread()`.

### `backend/app/api/routes/websocket.py`

Endpoint:

```text
GET/WS: /ws/telemetry
```

Endpoint hiện không yêu cầu JWT.

### `backend/app/main.py`

Đã đăng ký WebSocket router riêng, không nằm dưới `/api`.

Vì vậy:

```text
REST:
http://localhost:8000/api/...

WebSocket:
ws://localhost:8000/ws/telemetry
```

## 3. Các phần backend đã có từ trước

### Authentication

- `POST /api/login`
- `GET /api/me`
- JWT access token
- password hashing

### Device

Đang có:

- `Device`
- `UserDevice`
- API lấy danh sách device của user
- API lấy telemetry hiện tại của device

### Telemetry

Model hiện có các trường:

```text
id
device_id
recorded_at
ear
perclos
angle_x
angle_y
angle_z
confidence
```

`telemetry_service.py` đã có logic:

```text
device_code
    ↓
tìm Device
    ↓
tạo Telemetry
    ↓
PostgreSQL
```

## 4. Quy ước Device ID / Device Code – cần thống nhất

Dự kiến chuyển cách giao tiếp bên ngoài từ `device_id` sang **`device_code`**.

Khuyến nghị:

- `Device.id`: khóa chính nội bộ PostgreSQL, dùng làm FK.
- `Device.device_code`: mã thiết bị nghiệp vụ, dùng trong MQTT/API payload/frontend khi cần định danh thiết bị.

Ví dụ:

```json
{
  "device_code": "DM-000001",
  "ear": 0.31,
  "perclos": 0.02
}
```

Không nên đổi toàn bộ FK database từ `device_id` thành `device_code`.

Nên hiểu là:

```text
Database relationship:
Telemetry.device_id → Device.id

External payload:
device_code → Device.device_code
```

## 5. Việc cần làm tiếp

### Ưu tiên 1 – MQTT

TV2 cần kiểm tra:

```text
Mosquitto :1883
      ↓
mqtt/consumer.py
```

Trên máy TV4 chưa test được vì chưa cài/chạy MQTT Broker. Khi chạy consumer hiện gặp:

```text
ConnectionRefusedError: [WinError 10061]
```

Nguyên nhân hiện tại là không có broker lắng nghe tại `localhost:1883`.

### Ưu tiên 2 – Chuẩn hóa telemetry payload

Cần thống nhất với TV3 payload cuối cùng.

Khuyến nghị:

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

Nếu nhóm quyết định dùng `driver_state`, cần bổ sung trường này vào:

- `Telemetry` model
- Pydantic schema
- `save_telemetry()`
- WebSocket payload
- database schema

### Ưu tiên 3 – MQTT → WebSocket

Mục tiêu cuối:

```text
TV3
 ↓ MQTT
Mosquitto
 ↓
consumer.py
 ├── validate payload
 ├── save PostgreSQL
 └── broadcast WebSocket
          ↓
      TV4 Dashboard
```

### Ưu tiên 4 – kiểm tra API telemetry

Cần kiểm tra lại `TelemetryResponse` vì model `Telemetry` hiện không trực tiếp chứa:

```text
device_code
model
name
```

trong khi response schema đang yêu cầu các trường này.

## 6. Lưu ý khi sửa

Không hard-code IP máy thành viên.

Dùng `.env` cho:

```env
DATABASE_URL=...
MQTT_HOST=...
MQTT_PORT=1883
FRONTEND_HOST=...
SECRET_KEY=...
```

Khi chuyển sang máy TV2, chỉ cần thay cấu hình môi trường tương ứng.
