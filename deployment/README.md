# Chạy hệ thống bằng Docker Compose

Thực hiện lệnh từ thư mục gốc repo. Ubuntu/WSL trong VS Code dùng Bash; Windows
PowerShell có thể chạy các lệnh `docker compose` tương tự.

## Chuẩn bị môi trường

1. Nếu `.env` chưa có, sao chép `.env.example` thành `.env`. Không ghi đè `.env`
   đang dùng. Đặt `POSTGRES_PASSWORD` và `SECRET_KEY` riêng, không dùng giá trị
   mẫu trên môi trường dùng chung.
2. Đảm bảo `DATABASE_URL` dùng cùng user/password/database với `POSTGRES_*`.
   Khi chạy backend trực tiếp trên máy, host là `localhost:5432`; Compose tự
   đặt URL nội bộ backend thành `postgres:5432`.
3. Tạo credential MQTT nếu chưa được cấu hình:

   ```bash
   python deployment/mqtt/prepare_env.py
   ```

   Script cập nhật `.env`, không in password. Không commit hoặc chia sẻ `.env`.

## Chạy toàn bộ stack

```bash
docker compose --env-file .env -f deployment/docker-compose.yml config -q
docker compose --env-file .env -f deployment/docker-compose.yml up -d --build
docker compose --env-file .env -f deployment/docker-compose.yml ps
```

Compose khởi động PostgreSQL và Mosquitto, chờ điều kiện sẵn sàng, chạy migration
và MQTT setup trước backend; frontend khởi động cùng backend. Chờ PostgreSQL
`healthy`, `migrate` và `mqtt-setup` hoàn tất trước khi kiểm tra backend.

PostgreSQL trên volume mới chạy `database/create.sql` và `database/insert.sql`
qua `/docker-entrypoint-initdb.d`. Với DB đã có dữ liệu, service `migrate` áp
dụng lần lượt:

1. `database/migration_fe_be_week2.sql`
2. `database/migration_be_week3.sql`
3. `database/migration_ai_videos.sql`
4. `database/migration_link_alert_video.sql`

Không chạy `database/create.sql` thủ công lên DB đang có dữ liệu: file này xóa
schema `public`. Không xóa volume PostgreSQL để xử lý lỗi migration.

## Địa chỉ và health check

| Thành phần | Địa chỉ từ máy host | Địa chỉ trong Docker network |
| --- | --- | --- |
| Frontend/Nginx | `http://localhost:5173` | `frontend:80` |
| Backend/FastAPI | `http://localhost:8000` | `backend:8000` |
| PostgreSQL | `localhost:5432` | `postgres:5432` |
| Mosquitto MQTT | `localhost:1884` | `mosquitto:1883` |

Nginx của frontend phục vụ SPA và proxy `/api/` cùng `/ws/` tới backend. Health
endpoint của FastAPI là `GET /api/health`; kiểm tra trực tiếp bằng:

```text
Browser ──HTTP/WS──> Frontend Nginx :5173
                         ├── /api/ ──> Backend :8000 ──> PostgreSQL
                         └── /ws/  ──> Backend :8000
                                              └── MQTT ──> Mosquitto :1883

Edge AI / ESP32 ──MQTT──> Mosquitto (host port 1884)
Backend ──video files──> video_data volume
```

Sơ đồ thể hiện các service trong Compose; Edge AI và ESP32 là client ngoài
Compose. Automated integration tests dùng client mô phỏng và broker/DB tạm,
không chứng minh camera hoặc phần cứng thật đã nghiệm thu.

```bash
curl -fsS http://localhost:8000/api/health
```

Khi frontend container đang chạy, có thể kiểm tra thêm đường proxy:

```bash
curl -fsS http://localhost:5173/api/health
```

WebSocket dùng đường dẫn `/ws/` qua Nginx. Cấu hình frontend trong Docker hiện
cũng có thể kết nối trực tiếp tới backend trên host theo biến build
`VITE_WS_URL`; không suy ra proxy đã được kiểm thử chỉ từ việc health HTTP đạt.

## Chạy BE/FE trực tiếp trên máy

Khởi động các dịch vụ nền và migration:

```bash
docker compose --env-file .env -f deployment/docker-compose.yml up -d postgres mosquitto
docker compose --env-file .env -f deployment/docker-compose.yml run --rm migrate
docker compose --env-file .env -f deployment/docker-compose.yml up -d mqtt-setup
```

Backend chạy trên máy dùng `DATABASE_URL` tới `localhost:5432`,
`MQTT_HOST=localhost`, `MQTT_PORT=1884`. Sau đó cài dependency và chạy BE/FE
theo [hướng dẫn backend](../backend/README.md) và [hướng dẫn nhanh](../README.md).
Không thay đổi `.env` để dùng hostname nội bộ Compose khi backend chạy ngoài
Docker.

## Dữ liệu, sao lưu và giới hạn vận hành

- `postgres_data` lưu PostgreSQL; `mqtt_data` lưu dynamic security và retained
  message database; `video_data` gắn vào `/app/storage/videos` trong backend.
- Video được lưu thành file riêng, còn PostgreSQL lưu metadata. Không có tác vụ
  tự động dọn video/retention được cấu hình trong Compose; cần xác định chính
  sách lưu trữ và backup riêng trước khi dùng lâu dài.
- Repo không cấu hình lịch backup/restore. Sao lưu PostgreSQL và volume video
  thành các quy trình riêng; không đưa dump DB, video hay credential vào Git.
- Backend ghi log ra stdout/stderr theo JSON. Compose hiện không đặt chính sách
  giới hạn/rotation log; cấu hình retention tại Docker Engine hoặc nền tảng vận
  hành và không chia sẻ log thô có thể chứa thông tin nhạy cảm.
- Prometheus, Grafana và exporter chưa được khai báo trong Compose. Monitoring
  là đầu việc phối hợp, không thể khởi động bằng cách gọi tên service chưa tồn
  tại. Repo cũng chưa có workflow CI trong `.github/workflows/`.
- Các cổng host là dành cho môi trường phát triển; không mở trực tiếp ra Internet
  nếu chưa có kiểm soát truy cập, TLS và cấu hình triển khai phù hợp.

Để xem trạng thái/log, không in log thô khi có thể chứa dữ liệu nhạy cảm:

```bash
docker compose --env-file .env -f deployment/docker-compose.yml ps -a
docker compose --env-file .env -f deployment/docker-compose.yml logs --tail=100 backend
```

Chỉ chạy `logs` tại môi trường được phép; khử credential/PII trước khi lưu hoặc
chia sẻ output.

Tham khảo thêm [hướng dẫn MQTT](mqtt/README.md), [hướng dẫn backend](../backend/README.md)
và [hợp đồng event/video AI](../docs/ai-ingest-video-contract.md).
