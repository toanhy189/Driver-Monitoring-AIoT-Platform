# Cách tạo docker
## 1. Tạo 1 bản sao .env của .env.example
Cấu trúc thư mục sẽ như sau:
```text
Driver-Monitoring-AIoT-Platform/
│
├── .env
├── .env.example
├── backend/
├── frontend/
├── ...
└── deployment/
```
## 2. Tìm và thay đổi các trường này trong .env theo DB local trên máy
```bash
    POSTGRES_USER=postgres
    POSTGRES_PASSWORD=MAT_KHAU_DB
    POSTGRES_DB=device_monitor
```
## 3. Tiếp tìm và thay đổi dòng này trong .env
```bash
    DATABASE_URL=postgresql+psycopg://postgres:MAT_KHAU_DB@localhost:5432/device_monitor
```
thành
```bash
    DATABASE_URL=postgresql+psycopg://postgres:MAT_KHAU_DB@postgres:5432/device_monitor
```
(@localhost ---> @postgres)


Lúc dev local trên máy thì đổi lại localhost nha, postgres này là một container của Docker, không phải PostgreSQL local trên máy.

## 3. Chạy lệnh dưới đây để build các Container trong Docker
```bash
    docker compose --env-file .env -f deployment/docker-compose.yml up --build
```
## 4. Từ các lần sau, chạy Container chỉ cần lệnh sau:
```bash
    docker compose --env-file .env -f deployment/docker-compose.yml up
```

