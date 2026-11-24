# Cấu hình xác thực và phân quyền MQTT (ACL)

Mosquitto Broker trong dự án bắt buộc xác thực bằng tài khoản riêng cho từng thành phần và áp dụng danh sách kiểm soát truy cập (**ACL**) theo đúng không gian topic của từng thiết bị. Trên máy host, Broker mở ở **cổng `1884`** (tránh xung đột với dịch vụ Mosquitto mặc định cổng `1883` nếu máy đã cài sẵn); bên trong mạng Docker vẫn giao tiếp qua cổng `1883`.

---

## 1. Khởi tạo tài khoản hệ thống lần đầu

Tại thư mục gốc dự án, sau khi tạo `.env` từ `.env.example`:

```powershell
python deployment/mqtt/prepare_env.py
docker compose --env-file .env -f deployment/docker-compose.yml up -d mqtt-setup
python backend/tests/test_mqtt_security_integration.py -v
```

- `prepare_env.py`: Sinh mật khẩu ngẫu nhiên cho các tài khoản hệ thống (`admin`, `backend`, `vision-01`) vào file `.env` cục bộ.
- `mqtt-setup`: Khởi tạo dữ liệu Dynamic Security trong volume `mqtt_data`, cấu hình quyền cho `backend` và `vision-01` mà không ghi đè mật khẩu của các thiết bị đang hoạt động.
- `test_mqtt_security_integration.py`: Kiểm tra tự động việc chặn kết nối ẩn danh, chặn đọc/ghi chéo topic giữa các thiết bị và ngắt kết nối ngay khi thu hồi quyền.

---

## 2. Ma trận phân quyền theo Topic

| Định danh MQTT | Quyền Publish (Gửi) | Quyền Subscribe (Nhận) |
| --- | --- | --- |
| **`backend`** | `driver/+/command`, `driver/+/config/update`, `driver/+/storage_ack`, `driver/+/ota/request` | `driver/#` |
| **`vision-01`** (mặc định) | `driver/vision-01/{telemetry,events,status}` *(kèm 3 topic tương thích ngược)* | `driver/vision-01/storage_ack` |
| **`Vision Node` đăng ký mới** | Chỉ `driver/{code}/{telemetry,events,status}` của chính thiết bị đó | Chỉ `driver/{code}/storage_ack` của chính thiết bị đó |
| **`Alert Node` (`alert-...`)** | Chỉ `driver/{code}/{status,ack,telemetry,heartbeat,config/applied,ota/status}` của chính nó | Chỉ `driver/{code}/{command,config/update,ota/request}` của chính nó |

---

## 3. Cấp phát và thu hồi quyền kết nối thiết bị

- **Cấp thông tin kết nối (`Provision`):** Khi Admin bấm **Cấp thông tin kết nối** trên trang chi tiết thiết bị đang ở trạng thái `REGISTERED`, Backend tạo tài khoản/mật khẩu riêng và gán đúng role ACL trên Mosquitto, sau đó hiển thị mật khẩu **một lần duy nhất** để cấu hình vào `.env` (với Vision Node) hoặc `include/network_config.h` (với ESP32).
- **Thu hồi kết nối (`Decommission`):** Khi Admin xác nhận **Ngừng sử dụng**, Backend xóa/vô hiệu hóa ngay tài khoản MQTT của thiết bị trên Broker. Phiên kết nối đang mở bị ngắt lập tức và thiết bị không thể đăng nhập lại bằng thông tin xác thực cũ.
