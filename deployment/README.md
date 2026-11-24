# Hướng dẫn triển khai bằng Docker Compose

Hệ thống trung tâm được đóng gói và khởi chạy từ thư mục gốc của dự án thông qua tệp **`deployment/docker-compose.yml`**, bao gồm: **FastAPI Backend** (tích hợp sẵn MQTT consumer), **React / Nginx**, **PostgreSQL 16**, **Eclipse Mosquitto 2** và dịch vụ đồng bộ thời gian **NTP LAN** (`chrony`).

---

## 1. Chuẩn bị cấu hình và khởi chạy

```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
python deployment/mqtt/prepare_env.py
docker compose --env-file .env -f deployment/docker-compose.yml config --quiet
docker compose --env-file .env -f deployment/docker-compose.yml up -d --build
docker compose --env-file .env -f deployment/docker-compose.yml ps -a
```

Trước khi chạy, cập nhật mật khẩu DB và `SECRET_KEY` trong `.env`. Ba container khởi tạo `migrate`, `mqtt-init` và `mqtt-setup` là tác vụ chạy một lần nên trạng thái `Exited (0)` sau khi hoàn tất là bình thường.

| Thành phần | Cổng trên máy Host | Địa chỉ nội bộ trong Docker |
|---|---|---|
| Giao diện Web (Nginx + React) | `localhost:5173` | `frontend:80` |
| Backend REST API & WebSocket | `localhost:8000` | `backend:8000` |
| PostgreSQL 16 | `localhost:5433` (`POSTGRES_PORT`) | `postgres:5432` |
| Mosquitto MQTT Broker | `localhost:1884` | `mosquitto:1883` |
| Máy chủ thời gian NTP LAN | `<IP-LAN-laptop>:123/UDP` | `time-server:123/UDP` |

Nginx đảm nhận phục vụ giao diện SPA và chuyển tiếp (reverse proxy) các đường dẫn `/api` và `/ws` sang container `backend`.

---

## 2. Khởi tạo cơ sở dữ liệu và Migration

- Khi Docker volume `postgres_data` còn trống (lần chạy đầu tiên), PostgreSQL tự động nạp cấu trúc bảng từ `database/create.sql` và dữ liệu mẫu từ `database/insert.sql`.
- Mỗi lần khởi động stack, dịch vụ `migrate` chạy tuần tự các bản nâng cấp cộng thêm (`IF NOT EXISTS`) trước khi `backend` mở cổng:
  1. `database/old/migration_be_week3.sql`
  2. `database/old/migration_ai_videos.sql`
  3. `database/migration_ai_policy_v1.sql`
  4. `database/migration_final_core.sql`
  5. `database/migration_ai_signals.sql`
  6. `database/migration_roles_metrics.sql`
  7. `database/migration_ota.sql`

> **Lưu ý:** Không chạy trực tiếp `database/create.sql` lên cơ sở dữ liệu đang vận hành vì file khởi tạo gốc có lệnh làm mới schema.

---

## 3. Quản lý Volume dữ liệu và Sao lưu

Bốn Docker volume bền vững lưu trữ dữ liệu tách biệt khỏi vòng đời container:
- `postgres_data`: Dữ liệu các bảng quan hệ PostgreSQL.
- `mqtt_data`: Danh sách tài khoản thiết bị và bảng phân quyền topic (Dynamic Security / ACL) của Mosquitto.
- `video_data`: Các tệp video `.mp4` và bản chuyển mã xem trên trình duyệt.
- `firmware_data`: Các gói nhị phân `.bin` trong kho Firmware OTA.

Lệnh sao lưu nhanh cơ sở dữ liệu ra thư mục cục bộ `.local-backups/`:

```powershell
New-Item -ItemType Directory -Force .local-backups | Out-Null
docker compose --env-file .env -f deployment/docker-compose.yml exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/driver-backup.dump'
docker cp deployment-postgres-1:/tmp/driver-backup.dump .local-backups/driver-backup.dump
```

Khi thay đổi mã nguồn, thêm cờ `--build` cho dịch vụ cần cập nhật; khi thay đổi biến trong `.env`, dùng `up -d --force-recreate` để container nạp lại biến môi trường mới.

---

## 4. Các cấu hình mở rộng (HTTPS, Monitoring và OTA Gateway)

### 4.1. Bật cổng HTTPS cục bộ (`8443`)
Sinh chứng chỉ CA/TLS nội bộ và bật lớp phủ `docker-compose.tls.yml`:

```powershell
python deployment/tls/prepare_certs.py
docker compose --env-file .env -f deployment/docker-compose.yml -f deployment/docker-compose.tls.yml up -d --no-deps frontend
```

### 4.2. Bật cụm giám sát Prometheus & Grafana
Sinh khóa bảo vệ `/metrics`, nạp lại biến môi trường mới cho `backend` và khởi chạy `docker-compose.monitoring.yml` (`Prometheus` tại `127.0.0.1:9090`, `Grafana` tại `127.0.0.1:3000`):

```powershell
python deployment/prepare_final_env.py
docker compose --env-file .env -f deployment/docker-compose.yml -f deployment/docker-compose.monitoring.yml up -d --force-recreate backend prometheus grafana
```

### 4.3. Bật HTTPS Gateway phục vụ cập nhật Firmware OTA (`9443`)
Sau khi cấu hình khóa công khai tại `deployment/ota/public.pem` và cập nhật `OTA_ENABLED=true`, `OTA_PUBLIC_BASE_URL` trong `.env`, khởi tạo lại `backend` để nhận cấu hình mới và bật cổng tải firmware riêng cho ESP32:

```powershell
docker compose --env-file .env -f deployment/docker-compose.yml --profile ota up -d --force-recreate backend ota-gateway
docker compose --env-file .env -f deployment/docker-compose.yml exec -T backend python scripts/setup_ota_acl.py
```

Xem hướng dẫn chi tiết về quy trình tạo khóa và cập nhật OTA tại [docs/firmware-ota.md](../docs/firmware-ota.md).
