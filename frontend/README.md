# Frontend – Trạng thái & hướng bàn giao

## 1. Trạng thái hiện tại

Frontend React/Vite đã có:

- Login UI
- gọi `POST /api/login`
- lưu JWT vào `localStorage`
- chuyển sang Dashboard sau login
- Dashboard hiển thị Device Status
- Driver Status
- EAR
- PERCLOS
- WebSocket telemetry

Frontend chạy bằng Vite.

## 2. Login

Login gọi:

```text
POST ${VITE_BACKEND_HOST}${VITE_API_STR}/login
```

Ví dụ local:

```env
VITE_BACKEND_HOST=http://localhost:8000
VITE_API_STR=/api
```

JWT được lưu:

```text
localStorage.access_token
```

## 3. WebSocket

`frontend/src/services/websocket.js` hiện đã xử lý đúng callback:

```js
onMessage(data)
```

và:

```js
socket.onclose
```

Dashboard đang kết nối:

```text
ws://localhost:8000/ws/telemetry
```

thông qua:

```js
createTelemetrySocket(...)
```

Đã test thành công:

```text
WebSocket /ws/telemetry [accepted]
[WebSocket] Client connected. Total: 1
```

## 4. Dashboard

Dashboard hiện nhận telemetry bằng:

```js
onMessage: (data) => {
    setTelemetry(data);
}
```

Đang có fallback/sample data ban đầu để UI không trống:

```text
device_id: vision-01
ear: 0.28
perclos: 0.12
driver_state: ATTENTIVE
```

PERCLOS được đổi từ dạng tỷ lệ sang phần trăm:

```text
0.12 → 12%
```

## 5. Device ID → Device Code

Frontend dự kiến chuyển sang sử dụng:

```text
device_code
```

thay cho:

```text
device_id
```

ở dữ liệu giao tiếp bên ngoài.

Ví dụ:

```json
{
  "device_code": "DM-000001",
  "ear": 0.31,
  "perclos": 0.02,
  "driver_state": "ATTENTIVE"
}
```

Tuy nhiên cần thống nhất payload với TV2 và TV3 trước khi đổi toàn bộ component.

Không nên tự đổi khóa chính database `Device.id`.

## 6. Việc cần làm tiếp

Sau khi TV2 hoàn thành MQTT:

```text
MQTT
 ↓
Backend
 ↓
WebSocket
 ↓
Dashboard
```

cần bỏ dần sample data và kiểm tra dữ liệu thật.

Checklist:

- [ ] nhận `device_code`
- [ ] nhận EAR
- [ ] nhận PERCLOS
- [ ] nhận driver_state
- [ ] hiển thị Device connection status
- [ ] kiểm tra nhiều telemetry liên tiếp
- [ ] xử lý WebSocket disconnect
- [ ] xử lý reconnect nếu nhóm cần

## 7. Cấu hình IP

Không hard-code IP backend trong source.

Local:

```env
VITE_BACKEND_HOST=http://localhost:8000
VITE_API_STR=/api
VITE_WS_URL=ws://localhost:8000/ws/telemetry
```

Khi frontend chạy trên máy khác:

```env
VITE_BACKEND_HOST=http://<TV2_IP>:8000
VITE_API_STR=/api
VITE_WS_URL=ws://<TV2_IP>:8000/ws/telemetry
```

Sau khi sửa `.env`, cần restart Vite.

## 8. Phạm vi TV4

TV4 chủ yếu chịu trách nhiệm:

- Login UI
- Dashboard
- WebSocket client
- hiển thị telemetry
- tài liệu kiến trúc/ERD
- kiểm thử frontend với backend
