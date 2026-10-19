# Chạy hệ thống bằng Docker Compose

Thực hiện các lệnh tại **thư mục gốc dự án**.

## Lần đầu

1. Sao chép `.env.example` thành `.env`. Điền `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `DATABASE_URL` và `SECRET_KEY`. File `.env` được Git bỏ qua.
2. Chạy `python deployment/mqtt/prepare_env.py`. Script tạo mật khẩu MQTT ngẫu nhiên trong `.env` và không in mật khẩu ra màn hình.
3. Chạy `docker compose --env-file .env -f deployment/docker-compose.yml up -d --build`.

Compose tạo PostgreSQL, chạy migration, khởi tạo tài khoản MQTT rồi mới mở BE và FE. Nếu chỉ cần DB và broker để chạy BE trên Windows:

```powershell
docker compose --env-file .env -f deployment/docker-compose.yml up -d postgres mqtt-setup
```

Khi BE chạy trên Windows, dùng `DATABASE_URL` trỏ tới `localhost:5432`, `MQTT_HOST=localhost`, `MQTT_PORT=1884` trong `.env`. Trong container, Compose tự đổi địa chỉ sang `postgres:5432` và `mosquitto:1883`; bạn không cần sửa `.env` qua lại.

## Những lần sau

```powershell
docker compose --env-file .env -f deployment/docker-compose.yml up -d
```

Dữ liệu PostgreSQL nằm trong volume `postgres_data`; cấu hình tài khoản Mosquitto nằm trong volume `mqtt_data`. Đừng xóa hai volume này nếu muốn giữ dữ liệu và tài khoản.

Broker Docker mở cổng **1884** trên Windows vì máy phát triển có Mosquitto riêng ở cổng 1883. Xem [hướng dẫn TV2-03](mqtt/README.md) để thử quyền MQTT, lấy tài khoản cho ESP32 và cấu hình Edge AI.


Phần BE tuần 3 bổ sung `database/migration_be_week3.sql`; service migrate chạy file này sau migration tuần 2. Nếu chạy BE trực tiếp trên Windows, dùng `python backend/scripts/migrate_week3.py` trước khi khởi động lại BE. Hợp đồng và minh chứng: [TV2 tuần 3](../docs/TV2-tuan-3-huong-xu-ly-va-logic-code.md). Docker BE chạy một worker vì ticket/kết nối WebSocket đang giữ trong RAM của process.
