# Kiến trúc hệ thống, mô hình dữ liệu và bảo mật

Tài liệu trình bày sơ đồ kiến trúc tổng thể, luồng xử lý dữ liệu đầu-cuối, vòng đời quản lý thiết bị, lược đồ cơ sở dữ liệu quan hệ (ERD) và các lớp kiểm soát bảo mật của hệ thống.

---

## 1. Kiến trúc triển khai tổng thể

```mermaid
flowchart LR
  C[Webcam USB / Laptop] --> A[Vision Node / Python Edge AI]
  A -->|MQTT: telemetry, events, status| M[Mosquitto Broker]
  A -->|HTTP Basic Auth: upload MP4| B[FastAPI Backend]
  M <-->|MQTT: command, config, ACK, OTA| E[ESP32 Alert Node]
  M <--> B
  B <--> P[(PostgreSQL 16)]
  B --> V[(Volumes: video_data / firmware_data)]
  R[React + Nginx] <-->|REST API / WebSocket| B
  U[Admin / Employee / Customer] --> R
  E --> O[LED / Còi / Motor rung]
  T[Chrony NTP LAN] -->|UDP 123| E
```

- **Tầng Edge & Thiết bị vật lý:** Tiến trình Python chạy trực tiếp trên máy trạm để truy cập webcam độ trễ thấp; vi điều khiển **ESP32** kết nối cùng mạng Wi-Fi 2.4 GHz điều khiển cơ cấu chấp hành và đồng bộ giờ qua dịch vụ NTP nội bộ.
- **Tầng Trung tâm (Docker Compose):** Đóng gói PostgreSQL, Mosquitto, FastAPI, Nginx/React, dịch vụ thời gian `chrony` và tùy chọn mở rộng HTTPS / OTA Gateway / Prometheus-Grafana.

---

## 2. Luồng thu thập dữ liệu và đồng bộ bù khi mất mạng

```mermaid
sequenceDiagram
  participant AI as Vision Node (Edge AI)
  participant SQ as Hàng đợi SQLite
  participant MQ as Mosquitto Broker
  participant BE as FastAPI Backend
  participant DB as PostgreSQL
  participant FE as Giao diện React
  AI->>SQ: Ghi bản tin kèm message_id và model_version
  AI->>AI: Phát âm thanh cảnh báo cục bộ độc lập mạng
  SQ->>MQ: Worker đẩy bản tin lên topic thiết bị
  MQ->>BE: Nhận telemetry / events
  BE->>DB: Đối chiếu biên nhận chống trùng và lưu transaction
  DB-->>BE: Commit thành công
  BE-->>MQ: Phản hồi storage_ack: SAVED
  MQ-->>AI: Xác nhận đúng message_id
  AI->>SQ: Dọn bản tin đã SAVED khỏi hàng đợi
  BE-->>FE: Đẩy dữ liệu mới qua WebSocket
```

- Khi mất kết nối tới Broker hoặc Backend, Edge AI vẫn tiếp tục phân tích hình ảnh, phát cảnh báo âm thanh tại chỗ và xếp hàng bản tin/video trên ổ cứng cục bộ. Khi mạng khôi phục, dữ liệu cũ được gửi bù để bảo toàn lịch sử mà không phát lại lệnh kích hoạt tải muộn xuống ESP32.
- Luồng tải video sự kiện (`.mp4`) hoạt động trên worker HTTP riêng biệt, liên kết chính xác với sự kiện qua `clip_message_id` / `episode_start_event_id`.

---

## 3. Luồng điều khiển thiết bị và xác nhận (`Command` & `ACK`)

```mermaid
sequenceDiagram
  participant S as Giao diện Web / Rule Engine
  participant BE as FastAPI Backend
  participant DB as PostgreSQL
  participant MQ as Mosquitto Broker
  participant E as ESP32 Alert Node
  S->>BE: Yêu cầu điều khiển hoặc sự kiện vượt ngưỡng
  BE->>BE: Kiểm tra quyền, liên kết thiết bị, trạng thái ACTIVE/ONLINE
  BE->>DB: Tạo bản ghi lệnh và các dispatch con kèm request_id
  BE->>MQ: Publish lệnh kèm thời hạn TTL
  MQ->>E: Nhận bản tin command
  E->>E: Kiểm tra đồng hồ NTP, hạn TTL, tham số và chống trùng request_id
  E-->>MQ: Gửi ACK đã nhận / bắt đầu thực thi
  E->>E: Bật đầu ra và tự ngắt khi hết duration
  E-->>MQ: Gửi ACK COMPLETED
  MQ->>BE: Nhận kết quả theo request_id
  BE->>DB: Cập nhật trạng thái hoàn tất và độ trễ
  BE-->>S: Cập nhật giao diện qua WebSocket
```

---

## 4. Mô hình trạng thái vòng đời thiết bị

```mermaid
stateDiagram-v2
  [*] --> REGISTERED
  REGISTERED --> PROVISIONED: Cấp thông tin xác thực MQTT
  PROVISIONED --> ACTIVE: Kích hoạt đưa vào vận hành
  ACTIVE --> MAINTENANCE: Chuyển bảo trì hoặc cập nhật OTA
  MAINTENANCE --> ACTIVE: Kiểm tra và kích hoạt lại
  REGISTERED --> DECOMMISSIONED: Ngừng sử dụng
  PROVISIONED --> DECOMMISSIONED: Thu hồi kết nối
  ACTIVE --> DECOMMISSIONED: Thu hồi kết nối
  MAINTENANCE --> DECOMMISSIONED: Thu hồi kết nối
  DECOMMISSIONED --> [*]: Vô hiệu hóa tài khoản MQTT
```

- Trạng thái quản lý (`lifecycle_state`) được theo dõi độc lập với trạng thái kết nối mạng (`ONLINE` / `OFFLINE`). Thiết bị ở chế độ `MAINTENANCE` vẫn có thể `ONLINE` để nhận gói cập nhật OTA nhưng không nhận lệnh cảnh báo tự động thường ngày.

---

## 5. Lược đồ quan hệ dữ liệu chính (ERD)

```mermaid
erDiagram
  users ||--o{ user_devices : duoc_gan
  devices ||--o{ user_devices : pham_vi
  devices ||--o{ telemetry : so_do
  devices ||--o{ ai_events : su_kien
  devices ||--o{ ai_message_receipts : bien_nhan
  devices ||--o{ alerts : canh_bao
  users ||--o{ alert_reads : da_xem
  alerts ||--o{ alert_reads : nguoi_xem
  alerts o|--o{ commands : sinh_lenh
  devices ||--o{ commands : nhan_lenh
  command_types ||--o{ commands : phan_loai
  devices ||--o{ ai_videos : video_clip
  devices ||--o| configs : cau_hinh
  devices ||--o| rule_bindings : camera_nguon
  devices ||--o{ rule_bindings : esp_nhan
  devices ||--o| rule_runtime : trang_thai_phien
  users ||--o{ audit_logs : nhat_ky
  firmware_artifacts ||--o{ ota_deployments : phien_ban
  ota_deployments ||--o{ ota_device_jobs : dot_cap_nhat
  devices ||--o{ ota_device_jobs : thiet_bi_nhan
  ota_device_jobs ||--o{ ota_job_events : dien_bien_ota
```

Chi tiết định nghĩa cột, khóa ngoại và chỉ mục xem tại `database/create.sql` cùng các tệp `database/migration_*.sql`.

---

## 6. Các mối đe dọa chính và biện pháp kiểm soát bảo mật

| Mối đe dọa / Rủi ro | Biện pháp kiểm soát trong hệ thống |
|---|---|
| **Truy cập trái phép thiết bị hoặc video của người khác** | Kiểm tra phân quyền vai trò kết hợp bảng `user_devices` tại mọi endpoint REST API, vé WebSocket dùng một lần và trình phát video |
| **Lộ mật khẩu người dùng hoặc sử dụng lại phiên cũ** | Băm mật khẩu có salt bằng `pwdlib`; tăng `session_version` để thu hồi tức thời các JWT cũ khi đăng xuất, đổi mật khẩu, khóa hoặc đổi vai trò |
| **Giả mạo thiết bị hoặc gửi chéo topic MQTT** | Cấp tài khoản/mật khẩu MQTT riêng cho từng node khi `Provision`; cấu hình ACL trên Mosquitto khóa chặt quyền đọc/ghi vào đúng `driver/{device_code}/...` |
| **Bản tin lặp hoặc sự kiện cũ làm kích hoạt còi muộn** | Chống lưu trùng bằng `ai_message_receipts`, chống chạy lặp bằng bộ nhớ `request_id` trên NVS, kiểm tra hạn `TTL` và chặn kích tải đối với dữ liệu đồng bộ bù (`backfill`) |
| **Can thiệp gói cập nhật Firmware OTA** | Xác minh chữ ký số **RSA-2048** và mã băm **SHA-256** ở cả Backend và ESP32; tải ảnh qua kết nối HTTPS đi kèm token ngắn hạn theo từng công việc |
| **Rò rỉ thông tin nhạy cảm lên kho mã nguồn** | Tách biệt toàn bộ mật khẩu, khóa ký, cấu hình Wi-Fi và dữ liệu cá nhân vào `.env`, `network_config.h`, `.local-backups/` nằm trong `.gitignore`; ghi `audit_logs` cho các thao tác quản trị |
