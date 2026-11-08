# Triển khai bằng Docker Compose

Dùng **deployment/docker-compose.yml** từ thư mục gốc repository. Stack chính: FastAPI, React/Nginx, PostgreSQL 16, Mosquitto 2 và NTP LAN. MQTT consumer đã tích hợp trong Backend.

## Chuẩn bị và chạy

```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
python deployment/mqtt/prepare_env.py
docker compose --env-file .env -f deployment/docker-compose.yml config --quiet
docker compose --env-file .env -f deployment/docker-compose.yml up -d --build
docker compose --env-file .env -f deployment/docker-compose.yml ps -a
```

Trước khi chạy, cấu hình DB/SECRET_KEY riêng trong .env như [README](../README.md). Không ghi đè .env của nhóm. Các tác vụ migrate/mqtt-init/mqtt-setup kết thúc Exited (0) là bình thường.

| Dịch vụ | Máy host | Mạng container |
|---|---|---|
| React | localhost:5173 | frontend:80 |
| API | localhost:8000 | backend:8000 |
| PostgreSQL | localhost:5432 | postgres:5432 |
| MQTT | localhost:1884 | mosquitto:1883 |
| NTP | IP laptop:123/UDP | time-server:123/UDP |

Nginx phục vụ SPA và proxy /api, /ws tới Backend. Các cổng này dành cho môi trường demo LAN.

## Schema và migration

Volume PostgreSQL mới khởi tạo từ database/create.sql và database/insert.sql. Seed chỉ dùng minh họa; đổi mật khẩu mẫu trước khi dùng chung. Volume đã tồn tại không tự nạp lại seed.

Service migrate chạy tuần tự, có kiểm tra lỗi:

1. database/old/migration_be_week3.sql
2. database/old/migration_ai_videos.sql
3. database/migration_ai_policy_v1.sql
4. database/migration_final_core.sql

Hai migration trong old/ **vẫn đang dùng**, cần giữ để nâng cấp và chạy test. Không chạy create.sql lên DB đang có dữ liệu; không dùng down -v để sửa lỗi.

## Dữ liệu và sao lưu

- postgres_data: database.
- mqtt_data: tài khoản, ACL và dữ liệu broker.
- video_data: file video, tách khỏi metadata trong PostgreSQL.

Sao lưu cả database và video nếu cần giữ lịch sử đầy đủ. Ví dụ dùng container mặc định của Compose:

```powershell
New-Item -ItemType Directory -Force .local-backups | Out-Null
docker compose --env-file .env -f deployment/docker-compose.yml exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/driver-backup.dump'
docker cp deployment-postgres-1:/tmp/driver-backup.dump .local-backups/driver-backup.dump
```

File nhị phân được copy bằng docker cp, tránh chuyển qua redirection của PowerShell 5.1. Backup chứa dữ liệu riêng, không commit. Kiểm tra restore trên DB tạm trước khi dùng; không thử restore ghi đè DB ứng dụng.

## Khởi động lại và kiểm tra

```powershell
docker compose --env-file .env -f deployment/docker-compose.yml up -d
docker compose --env-file .env -f deployment/docker-compose.yml logs --tail 80 backend
docker compose --env-file .env -f deployment/docker-compose.yml logs --tail 30 time-server
python deployment/time/check_ntp.py
```

Khi code đổi, dùng --build cho service liên quan. Khi .env đổi, recreate service bằng up -d --force-recreate; lệnh restart không tự nạp biến mới. NTP startup dọn PID cũ của chính dịch vụ để container có thể restart; không đổi giờ laptop.

## HTTPS và monitoring tùy chọn

Xem [runbook](../docs/final-runbook.md) cho tạo CA/certificate, exporter AI, token metrics và Grafana. Overlay:

- deployment/docker-compose.tls.yml: HTTPS/WSS qua localhost:8443.
- deployment/docker-compose.monitoring.yml: Prometheus localhost:9090, Grafana localhost:3000.

Trước monitoring, cài python-dotenv hoặc requirements Backend, rồi chạy python deployment/prepare_final_env.py để tạo secret cục bộ. Nếu dùng nhiều overlay, giữ đầy đủ các -f tương ứng khi cập nhật service. Không cài CA vào Windows hoặc sửa firewall tự động.

CI tại [.github/workflows/ci.yml](../.github/workflows/ci.yml) kiểm thử/build; chưa tự triển khai lên laptop. Hướng dẫn chạy AI và demo nằm trong [README](../README.md).
