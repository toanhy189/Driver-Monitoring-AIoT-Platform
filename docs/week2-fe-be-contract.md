# Hợp đồng giao tiếp Frontend – Backend (REST API & WebSocket)

Tài liệu đặc tả các điểm cuối JSON dưới tiền tố `/api` và giao thức sự kiện thời gian thực qua WebSocket giữa giao diện React và FastAPI Backend.
- Các yêu cầu cần xác thực truyền header `Authorization: Bearer <access_token>`.
- Tham số định danh thiết bị trên đường dẫn URL sử dụng khóa chính số nguyên (`id` trong DB); trường chuỗi `device_code` (như `vision-01`, `alert-01`) dùng để hiển thị và định tuyến bản tin MQTT.

---

## 1. Phân quyền và quy ước mã trạng thái HTTP

| Nhóm thao tác | Admin | Employee | Customer |
| --- | --- | --- | --- |
| Xem thiết bị trong phạm vi, số đo, lịch sử lệnh, cảnh báo, cấu hình, video | Có | Có | Có |
| Đánh dấu cảnh báo đã xem (cho tài khoản cá nhân) | Có | Có | Có |
| Gửi lệnh kiểm tra cảnh báo, chỉnh cấu hình nhịp tải, xóa video | Có | Có | Không |
| Quản lý người dùng, đăng ký/vòng đời thiết bị, liên kết tự động, OTA | Có | Không | Không |

- **Mã phản hồi chuẩn:** `401` (chưa đăng nhập hoặc phiên đã bị thu hồi), `403` (không đủ quyền thực hiện), `404` (không tồn tại hoặc thiết bị nằm ngoài phạm vi được gán), `409` (xung đột phiên bản/trạng thái), `422` (dữ liệu đầu vào sai định dạng), `503` (dịch vụ phụ thuộc tạm thời chưa sẵn sàng).

---

## 2. Xác thực phiên và Quản lý thiết bị

| Endpoint | Dữ liệu gửi lên | Phản hồi chính |
| --- | --- | --- |
| `POST /api/login` | `{ "username": "...", "password": "..." }` | `{ "access_token": "...", "token_type": "bearer" }` |
| `GET /api/me` | Bearer token | Thông tin hồ sơ và vai trò của người dùng hiện tại |
| `GET /api/devices` | Bearer token | Danh sách `DeviceResponse` thuộc phạm vi truy cập |
| `GET /api/devices/{id}` | Bearer token | Chi tiết một `DeviceResponse` |
| `POST /api/devices` | `{ "device_code": "alert-01", "name": "...", "model": "...", "device_type": "ALERT_NODE" }` | `201` + đối tượng thiết bị vừa khởi tạo |
| `POST /api/devices/{id}/{provision,activate,maintenance,decommission}` | Bearer token | Trạng thái thiết bị cập nhật (riêng `provision` trả kèm thông tin tài khoản MQTT một lần) |

---

## 3. Gửi lệnh kiểm tra và đối chiếu `ACK`

`POST /api/devices/{id}/commands` nhận payload:

```json
{
  "action": "TEST_ALERT",
  "buzzer_ms": 1000,
  "vibration_ms": 1000,
  "led_mode": "FLASH"
}
```

- Thời lượng `buzzer_ms` và `vibration_ms` là số nguyên trong khoảng `1–10000` (ms); `led_mode` nhận `ON` hoặc `FLASH`.
- Backend kiểm tra quyền người gửi, loại thiết bị `ALERT_NODE`, vòng đời `ACTIVE` và kết nối `ONLINE`, sau đó phát 3 lệnh con tương ứng (LED, còi, motor).
- Trạng thái lệnh tổng chỉ chuyển sang hoàn tất (`status: "ACKNOWLEDGED"`, `ack_status: "COMPLETED"`) khi nhận đủ cả 3 phản hồi `COMPLETED` từ ESP32.
- Tra cứu lịch sử qua `GET /api/commands?device_id={id}` (lọc thêm `alert_id` khi đi từ trang Cảnh báo) hoặc xem chi tiết một lệnh tại `GET /api/commands/{request_id}`.

---

## 4. Cấu hình nhịp cảnh báo từ xa (`Desired` / `Applied`)

`GET /api/devices/{id}/config` trả về cấu hình mong muốn và cấu hình thiết bị thực tế đã áp dụng:

```json
{
  "config_id": "cfg-...",
  "applied_config_id": "cfg-...",
  "desired": {
    "config_id": "cfg-...",
    "timings": { "led": { "1": { "on_ms": 500, "off_ms": 500 } } }
  },
  "applied": {
    "config_id": "cfg-...",
    "timings": { "led": { "1": { "on_ms": 500, "off_ms": 500 } } }
  }
}
```

- Đối tượng `timings` luôn bao gồm đủ 3 đầu ra (`led`, `buzzer`, `motor`) trên cả 3 mức cảnh báo (`1`, `2`, `3`), với `on_ms` từ `50–5000` ms và `off_ms` từ `50–10000` ms.
- `PUT /api/devices/{id}/config` lưu bản `desired`, tăng số `revision` và gửi bản tin `config/update` (retained, QoS 1) xuống ESP32. Giao diện chỉ báo **Đã áp dụng** khi ESP32 ghi NVS thành công và gửi phản hồi `APPLIED` khớp đúng `config_id`.

---

## 5. Luồng cập nhật thời gian thực qua WebSocket

1. Giao diện gọi `POST /api/ws-ticket` (kèm Bearer token) để lấy mã vé `ticket` ngắn hạn dùng một lần.
2. Mở kết nối tới `/ws/telemetry?ticket=...`.
3. Backend chỉ đẩy các sự kiện thuộc phạm vi thiết bị mà người dùng được phép xem: `telemetry.updated`, `device.updated`, `command.updated`, `alert.created`, `alert.updated`, `config.updated`.
4. Khi mất mạng và kết nối lại, giao diện xin vé mới, tải lại bản chụp lịch sử (`snapshot`) và gộp dữ liệu theo định danh bản ghi để không tạo điểm trùng lặp trên biểu đồ.
