# Backend tuần 2 và tuần 3

## Nhận event và video AI (21/10/2026)

[Hợp đồng event/video, xác thực, cách đồng bộ môi trường và kiểm tra](../docs/ai-ingest-video-contract.md).
BE nhận thêm SESSION_ENDED, trả SAVED sau khi lưu DB; API upload MP4 dùng HTTP Basic
bằng tài khoản MQTT của Vision Node. AI cần thêm `auth=(MQTT_USERNAME, MQTT_PASSWORD)`
vào requests.post upload. Chạy `python backend/scripts/setup_ai_ingest.py` để kiểm tra
DB/thiết bị/ACL; `--apply --assign-user TEN_ADMIN` áp dụng migration và cấu hình thật.

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
| Lịch sử số đo/lệnh, diễn biến, thống kê | `GET /api/devices/{id}/{telemetry/history,history,timeline,metrics}` | Thiết bị đang gán; lọc thời gian/phiên bản AI, UTC, phân trang |
| Biểu đồ AI của TV4 | `GET /api/{id}/telemetry/history` | Thiết bị đang gán; giữ response biểu đồ và thứ tự tăng dần |
| Chính sách cảnh báo | `GET/PUT /api/devices/{id}/rule` | Admin được gán cả nguồn Vision Node và đích Alert Node |

AI mới dùng `driver/{device_code}/telemetry`, `/events`, `/status`. BE nhận `message_id` và `device_code`, lưu dữ liệu cùng biên nhận trong một giao dịch, rồi gửi `{message_id, status: "SAVED"}` tới `driver/{device_code}/storage_ack`. Gửi lại cùng tin không lưu trùng. Các topic AI chung và cặp `event_id/device_id` cũ vẫn được nhận để giữ tương thích.

Topic ESP32 giữ nguyên. Một yêu cầu `TEST_ALERT` phát ba lệnh firmware hiện có và chỉ báo hoàn tất khi cả ba ACK `COMPLETED` đúng mã. `DISTRACTED_THRESHOLD_REACHED` được lưu với kết quả `POLICY_PENDING`, chưa tự điều khiển tải khi nhóm chưa chốt chính sách.

## Áp dụng bản đồng bộ AI tuần 3

Code đã được kiểm tra trên broker và DB thử riêng. Trạng thái môi trường đang dùng được ghi ở [runtime-readiness.json](../docs/evidence/week3/runtime-readiness.json); kiểm tra đó chỉ đọc, chưa áp dụng migration/ACL mới.

Sau khi nhóm duyệt áp dụng, chạy từ thư mục gốc:

```powershell
python backend/scripts/migrate_week3.py
docker compose --env-file .env -f deployment/docker-compose.yml build mqtt-setup
docker compose --env-file .env -f deployment/docker-compose.yml run --rm mqtt-setup
```

Migration bổ sung bảng `ai_message_receipts`; setup cập nhật ACL của hai role BE/AI đã có, giữ mật khẩu và không bật lại tài khoản bị thu hồi. Khởi động lại BE sau khi áp dụng. Luồng AI có SQLite nằm ở `edge-ai/main2.py`; cấu hình lấy từ `.env`, file hàng đợi được giữ riêng trên máy.

Để chạy lại kiểm thử mà không sửa broker đang dùng:

```powershell
python backend/tests/run_week3_isolated.py
```

## Giới hạn tích hợp thiết bị

- `PUT /api/devices/{id}/config` lưu **desired** rồi gửi `config_id` và timings tới `driver/{device_code}/config/update` (retained, QoS 1). Thời gian bật phải từ 50–5000 ms; tắt từ 50–10000 ms, khớp firmware TV1 trên main tại `5e06f10`. Firmware lưu vào flash và gửi `APPLIED` hoặc `REJECTED` tới `config/applied`. Lệnh đang chạy giữ timing đã lấy khi bắt đầu; lệnh mới lấy timing mới. BE chỉ đổi **applied** khi ACK `APPLIED` đúng thiết bị và `config_id`.
- Broker Docker yêu cầu tài khoản và ACL. Xem hướng dẫn TV2-03 tại [deployment/mqtt/README.md](../deployment/mqtt/README.md). API provision trả thông tin đăng nhập một lần cho Admin.
- Với database cũ, Admin cần đăng ký `vision-01` và gán đúng tài khoản trước khi Dashboard hiện telemetry của AI. Migration không tự gán camera cho người dùng khác.
- Để thử MQTT và cấu hình trên phần cứng, build/upload môi trường PlatformIO `development`, dùng đúng `device_code`, broker và tài khoản MQTT. `TestMode::Button` chỉ áp dụng cho môi trường `test`.
- Kiểm thử tự động không thay cho thử lệnh, ACK và cấu hình trên ESP32 thật.
