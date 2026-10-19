# Hợp đồng FE–BE tuần 2

Tài liệu này ghi lại API **đang có trong code**. FE gọi JSON dưới `/api`; các request cần đăng nhập dùng `Authorization: Bearer <access_token>`. Mã thiết bị trên URL là `id` số của DB. `device_code` như `alert-01` dùng để nhận diện thiết bị với MQTT và trên giao diện.

## Quyền và lỗi HTTP

| Quyền | Admin | Employee | Customer |
| --- | --- | --- | --- |
| Xem thiết bị được gán, lệnh, cảnh báo, cấu hình | Có | Có | Có |
| Gửi lệnh kiểm tra, sửa cấu hình, đánh dấu cảnh báo đã xem | Có | Có | Không |
| Đăng ký và đổi vòng đời thiết bị | Có | Không | Không |

BE lọc dữ liệu theo `user_devices` còn hiệu lực và kiểm tra quyền trên từng request. `401` là phiên không hợp lệ; `403` là thiếu quyền; `404` là không tìm thấy hoặc thiết bị không được gán; `409` là xung đột trạng thái; `422` là JSON/tham số sai; `503` có thể xảy ra khi broker provisioning/revoke không sẵn sàng. FE hiển thị lỗi theo HTTP status và `detail`, không quyết định quyền thay BE.

## Phiên và thiết bị

| API | Request | Response chính |
| --- | --- | --- |
| `POST /api/login` | `{ "username": "...", "password": "..." }` | `{ "access_token": "...", "token_type": "bearer" }` |
| `GET /api/me` | Bearer token | `{ "id": 1, "username": "...", "role": "Admin" }` và thông tin user khác |
| `GET /api/devices` | Bearer token | Mảng `DeviceResponse` của thiết bị được gán |
| `GET /api/devices/{id}` | Bearer token | Một `DeviceResponse` |
| `POST /api/devices` | `{ "device_code": "alert-01", "name": "...", "model": "..." }` | `201` + `{ "message": "Device registered", "device": DeviceResponse }` |
| `POST /api/devices/{id}/{provision,activate,maintenance,decommission}` | Bearer token | `DeviceResponse` sau thao tác |

`DeviceResponse` có `id`, `device_code`, `name`, `model`, `type`, `lifecycle_state`, `status`, `last_seen`, `firmware_version`. `lifecycle_state` nhận `REGISTERED`, `PROVISIONED`, `ACTIVE`, `MAINTENANCE`, `DECOMMISSIONED`. `status` nhận `ONLINE`/`OFFLINE`; hai trường độc lập. Thời gian trả về có múi giờ UTC. API provision chỉ báo thành công khi BE thật sự cấp được credential; lỗi broker trả `503` và không chuyển thiết bị sang `PROVISIONED`.

## Lệnh kiểm tra và ACK

`POST /api/devices/{id}/commands` nhận:

```json
{ "action": "TEST_ALERT", "buzzer_ms": 1000, "vibration_ms": 1000, "led_mode": "FLASH" }
```

Hai thời lượng phải là số nguyên `1–10000`; `led_mode` là `ON` hoặc `FLASH`. BE kiểm tra role, thiết bị `ALERT_NODE`, `ACTIVE` và heartbeat còn mới. Response `201` là bản ghi lệnh gồm `request_id`, `device_id`, `device_code`, `action`, `status`, `ack_status`, `error_message`, `created_at`. **HTTP 201 chỉ xác nhận request đã được xử lý ở BE**: `status` trong body vẫn có thể là `FAILED` nếu publish MQTT thất bại. FE phải đọc cả body. BE phát ba lệnh con LED/còi/motor theo giao thức firmware hiện tại; chỉ đặt `ACKNOWLEDGED` + `COMPLETED` khi cả ba ACK `COMPLETED` đúng mã. `ACCEPTED` là thiết bị đã nhận, chưa hoàn tất. `TIMEOUT` là chưa có kết quả cuối, không tự gửi lại POST. Nếu ACK cuối đến muộn, BE có thể sửa `TIMEOUT` thành hoàn tất; một ACK con đến muộn chưa đủ để sửa trạng thái đó.

`GET /api/commands?device_id={id}` trả tối đa 100 lệnh gần nhất; `GET /api/commands/{request_id}` trả một lệnh. FE dùng `request_id` để ghép HTTP, polling và WebSocket; mã này không cần hiện trong bảng người dùng. Lịch sử vẫn lấy lại từ DB sau khi tải lại trang.

## Cấu hình và cảnh báo

`GET /api/devices/{id}/config` trả:

```json
{
  "config_id": "cfg-...",
  "applied_config_id": null,
  "desired": { "config_id": "cfg-...", "timings": { "led": { "1": { "on_ms": 1000, "off_ms": 1000 } } } },
  "applied": null
}
```

`timings` thực tế bắt buộc có **led, buzzer, motor** và cả ba mức `1`, `2`, `3`, mỗi mức có `on_ms` và `off_ms` là số nguyên `0–10000`. `PUT /api/devices/{id}/config` nhận `{ "timings": ... }` và trả `{ "config_id": "cfg-...", "status": "PENDING_APPLICATION" }`. FE chỉ hiển thị **đã áp dụng** khi BE trả cả `applied` và `applied_config_id` khớp `config_id`. Firmware development hiện nhận `config/update`, lưu flash và gửi APPLIED/REJECTED tới `config/applied`. BE publish QoS 1 retained, có revision để phân biệt cấu hình cũ; chỉ cập nhật applied sau ACK APPLIED đúng thiết bị và config_id. Xem [hợp đồng tuần 3](TV2-tuan-3-huong-xu-ly-va-logic-code.md).

`GET /api/alerts` trả mảng gồm `alert_id`, `device_id`, `device_code`, `alert_type`, `severity`, `created_at`, `status`. `POST /api/alerts/{alert_id}/acknowledge` chỉ nhận cảnh báo `NEW` và trả cảnh báo đã cập nhật `status: "ACKNOWLEDGED"`; thao tác này chỉ đánh dấu đã xem, không thay ACK của lệnh. Rule Engine tuần 3 lưu liên kết sự kiện/cảnh báo/lệnh. request_id chỉ được trả khi có lệnh liên quan và user có quyền xem thiết bị nhận lệnh; nếu chưa có hoặc không có quyền thì là null.

## Realtime và giới hạn kiểm thử

FE gọi `POST /api/ws-ticket` bằng Bearer token, sau đó mở `/ws/telemetry?ticket=...`. Ticket dùng một lần; reconnect phải xin ticket mới. BE gửi sự kiện theo thiết bị được gán cho user: `telemetry.updated`, `device.updated`, `command.updated`, `alert.created`, `config.updated`. Gói tin có dạng `{ "type": "command.updated", "data": { "request_id": "cmd-...", "device_id": 2, "status": "ACKNOWLEDGED", "ack_status": "COMPLETED" } }`. FE tải lại snapshot khi kết nối lại và ghép theo ID để tránh trùng hoặc lùi trạng thái.

Các topic/payload MQTT AI và ESP32 đang dùng được giữ nguyên. Test FE/BE tự động kiểm tra hợp đồng HTTP, quyền, ghép ACK và định tuyến topic; kiểm chứng còi/đèn/motor và cấu hình **đã áp dụng trên phần cứng** vẫn cần TV1/TV3 thử với thiết bị thật.
