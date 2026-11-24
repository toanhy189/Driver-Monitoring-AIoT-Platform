# Backend — FastAPI

Dịch vụ Backend trung tâm viết bằng **FastAPI + SQLModel + PostgreSQL**, đảm nhiệm cung cấp REST API, luồng dữ liệu thời gian thực qua WebSocket, bộ lắng nghe MQTT tích hợp (`mqtt_consumer`), bộ quy tắc cảnh báo tự động (**Rule Engine**) và quản lý cập nhật Firmware từ xa (**OTA**).

---

## 1. Khởi chạy

- **Chạy cùng toàn bộ hệ thống (khuyến nghị):** Sử dụng Docker Compose tại thư mục gốc theo hướng dẫn trong [README dự án](../README.md).
- **Chạy trực tiếp trên máy khi phát triển Backend:** Khởi động sẵn PostgreSQL và Mosquitto bằng Compose (tạm dừng riêng container `backend` để tránh trùng cổng `8000`), sau đó tạo môi trường ảo riêng cho `backend`:

```powershell
python -m venv backend/.venv
./backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-test.txt
./backend/.venv/Scripts/python.exe -m uvicorn --app-dir backend app.main:app --reload
```

Khi chạy trực tiếp trên host, biến `DATABASE_URL` trong `.env` trỏ về `localhost:5433` (hoặc cổng cấu hình trong `POSTGRES_PORT`), `MQTT_HOST=localhost` và `MQTT_PORT=1884`. Trang tài liệu OpenAPI (Swagger UI) mở tại: <http://localhost:8000/docs>.

---

## 2. Danh sách nhóm API chính

| Phân hệ | Đường dẫn REST / WebSocket |
|---|---|
| **Xác thực & Phiên** | `POST /api/login`, `POST /api/logout`, `GET /api/me` |
| **Tài khoản cá nhân** | `POST /api/register`, `PUT /api/me`, `POST /api/me/password` |
| **Quản trị người dùng & Phân quyền** | `GET/POST /api/users`, `PATCH /api/users/{id}`, `PUT/DELETE /api/users/{id}/devices/{device_id}` |
| **Quản lý thiết bị** | `GET/POST /api/devices`, `GET /api/devices/{id}`, `DELETE /api/devices/{id}`, `PATCH /api/devices/{id}/hardware` |
| **Vòng đời thiết bị** | `POST /api/devices/{id}/{provision,activate,maintenance,decommission}` |
| **Số đo & Lịch sử thiết bị** | `GET /api/{id}/telemetry`, `GET /api/{id}/telemetry/history`, `GET /api/devices/{id}/{history,timeline,metrics}` |
| **Điều khiển & Cấu hình từ xa** | `POST /api/devices/{id}/commands`, `GET /api/commands`, `GET /api/commands/{request_id}`, `GET/PUT /api/devices/{id}/config` |
| **Cảnh báo & Liên kết tự động** | `GET /api/alerts`, `POST /api/alerts/{id}/acknowledge`, `GET/PUT /api/devices/{id}/rule` |
| **Video sự kiện** | `POST /api/videos/upload`, `GET /api/alerts/{id}/video`, `POST/GET /api/videos/{id}/playback`, `DELETE /api/videos/{id}` |
| **Cập nhật Firmware (OTA)** | `GET/POST /api/ota/firmware`, `POST /api/ota/firmware/{id}/{verify,release,withdraw}`, `POST /api/ota/deployments/{preview,}`, `GET /api/ota/deployments` |
| **Luồng dữ liệu Realtime** | `POST /api/ws-ticket`, `WS /ws/telemetry?ticket=...` |

- **Kiểm soát truy cập:** `Admin` có toàn quyền quản trị hệ thống; `Employee` và `Customer` chỉ được truy cập các thiết bị được gán trong bảng `user_devices` tương ứng với quyền hạn của vai trò.
- **Thu hồi phiên tức thời:** Khi đăng xuất, đổi mật khẩu, đổi vai trò hoặc khóa tài khoản, trường `session_version` tăng lên để vô hiệu hóa ngay các JWT và ticket WebSocket cũ.

---

## 3. Cơ chế xử lý dữ liệu và điều phối thiết bị

- **Chống lưu trùng bản tin AI:** Dữ liệu từ Vision Node trên `driver/{device_code}/{telemetry,events,status}` được ghi kèm biên nhận `ai_message_receipts` trong cùng một transaction DB trước khi phản hồi `storage_ack: SAVED`.
- **Rule Engine:** Xét đồng thời cờ hệ thống `RULE_ENGINE_ENABLED`, liên kết `rule_bindings` đang bật, trạng thái thiết bị `ACTIVE` / `ONLINE`, mã phiên làm việc và độ mới của sự kiện trước khi phát lệnh xuống ESP32.
- **Theo dõi lệnh & Cấu hình:** Lệnh kiểm tra `TEST_ALERT` chỉ chuyển sang hoàn tất khi cả 3 lệnh con (LED, còi, motor) nhận đủ phản hồi `COMPLETED`. Cấu hình thiết bị tách biệt bản mong muốn (`desired_config`) và bản đã xác nhận áp dụng trên NVS (`applied_config`).
- **Lưu trữ Video:** Cổng tải video sử dụng xác thực HTTP Basic bằng tài khoản MQTT của chính Vision Node; việc xem và xóa clip trên giao diện kiểm tra quyền người dùng theo JWT và giữ bản ghi đánh dấu xóa (`deleted_at`) để tránh tải lặp lại file cũ.

---

## 4. Chạy bộ kiểm thử Backend

```powershell
python -m pip install -r backend/requirements-test.txt
python -X utf8 -m unittest discover -s backend/tests -v
python -X utf8 backend/tests/run_week4_isolated.py --regression
python -X utf8 backend/tests/run_week4_isolated.py --restart-only
```

Các kịch bản kiểm thử tích hợp tự động khởi tạo PostgreSQL và Mosquitto tạm thời trong Docker, không làm thay đổi dữ liệu của môi trường đang chạy.

Tham khảo thêm: [Giao thức AI & Video](../docs/ai-ingest-video-contract.md) · [Kiến trúc & Bảo mật](../docs/final-architecture-security.md) · [Cập nhật Firmware OTA](../docs/firmware-ota.md).
