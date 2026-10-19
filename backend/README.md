# Backend tuần 2

Phần tuần 3, hướng xử lý và kết quả kiểm chứng: [Logic code TV2](../docs/TV2-tuan-3-huong-xu-ly-va-logic-code.md), [Báo cáo có minh chứng](../docs/TV2-tuan-3-bao-cao-ket-qua.md). Chạy `python backend/scripts/migrate_week3.py` cho DB đã có tuần 2 trước khi mở bản BE mới. Rule Engine tự gửi lệnh mặc định tắt (`RULE_ENGINE_ENABLED=false`) để chờ nhóm chốt chính sách.

Hợp đồng JSON, trạng thái lệnh/ACK và sự kiện realtime: [FE–BE tuần 2](../docs/week2-fe-be-contract.md).

Chạy tại thư mục gốc dự án theo [hướng dẫn nhanh](../README.md#3-chạy-nhanh-trên-windows). Với PostgreSQL đã có dữ liệu, chạy `database/migration_fe_be_week2.sql` trước khi mở BE; Docker Compose có service `migrate` chạy tự động trước backend.

## API cho FE

| Chức năng | API | Quyền |
| --- | --- | --- |
| Đăng nhập, phiên | `POST /api/login`, `GET /api/me` | Tài khoản hợp lệ |
| Thiết bị | `GET /api/devices`, `GET /api/devices/{id}` | Thiết bị đang gán |
| Đăng ký, vòng đời | `POST /api/devices`, `POST /api/devices/{id}/{provision,activate,maintenance,decommission}` | Admin và thiết bị được gán |
| Số đo mới nhất | `GET /api/{id}/telemetry` | Thiết bị đang gán |
| Kiểm tra cảnh báo | `POST /api/devices/{id}/commands` | Admin/Employee; Alert Node ACTIVE và online gần đây |
| Lịch sử lệnh | `GET /api/commands`, `GET /api/commands/{request_id}` | Thiết bị đang gán |
| Cấu hình | `GET/PUT /api/devices/{id}/config` | Xem: cả ba role; sửa: Admin/Employee |
| Cảnh báo | `GET /api/alerts`, `POST /api/alerts/{id}/acknowledge` | Xem: cả ba role; xác nhận: Admin/Employee |
| Realtime | `POST /api/ws-ticket`, `WS /ws/telemetry?ticket=...` | Ticket dùng một lần; sự kiện lọc theo `user_devices` |

BE vẫn nhận topic AI `driver/telemetry`, `driver/events`, `driver/status` và topic ESP32 `driver/{device_code}/status`, `driver/{device_code}/ack`. Một yêu cầu `TEST_ALERT` phát ba lệnh firmware hiện có và chỉ báo hoàn tất khi cả ba ACK `COMPLETED` đúng mã. FE/BE không cần sửa payload của TV1/TV3.

## Giới hạn tích hợp thiết bị

- `PUT /api/devices/{id}/config` lưu **desired** rồi gửi `config_id` và timings tới `driver/{device_code}/config/update` (retained, QoS 1). Firmware `development` nhận cấu hình, kiểm tra và lưu vào flash; lệnh đang chạy kết thúc trước khi áp dụng cấu hình mới. Firmware gửi `APPLIED` hoặc `REJECTED` tới `driver/{device_code}/config/applied`. BE chỉ đổi **applied** khi ACK `APPLIED` có đúng mã thiết bị và `config_id`; lỗi xuất hiện trong `GET config`.
- Broker Docker yêu cầu tài khoản và ACL. Xem hướng dẫn TV2-03 tại [deployment/mqtt/README.md](../deployment/mqtt/README.md). API provision trả thông tin đăng nhập một lần cho Admin.
- Với database cũ, Admin cần đăng ký `vision-01` và gán đúng tài khoản trước khi Dashboard hiện telemetry của AI. Migration không tự gán camera cho người dùng khác.
- Để thử MQTT và cấu hình trên phần cứng, build/upload môi trường PlatformIO `development`, dùng đúng `device_code`, broker và tài khoản MQTT. `TestMode::Button` chỉ áp dụng cho môi trường `test`.
- Kiểm thử tự động không thay cho thử lệnh, ACK và cấu hình trên ESP32 thật.
