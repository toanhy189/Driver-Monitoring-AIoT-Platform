# Tài khoản MQTT cho TV2-03

Broker Mosquitto trong Docker yêu cầu đăng nhập. ACL là danh sách quy định tài khoản nào được gửi hoặc đọc từng topic. Broker Docker mở ở **cổng 1884 trên máy Windows** để không đụng Mosquitto cài sẵn đang dùng cổng 1883; bên trong Docker vẫn là cổng 1883.

## Chạy lần đầu

Tại thư mục gốc dự án, sau khi tạo `.env` từ `.env.example` và điền cấu hình DB:

```powershell
python deployment/mqtt/prepare_env.py
docker compose --env-file .env -f deployment/docker-compose.yml up -d mqtt-setup
python backend/tests/test_mqtt_security_integration.py -v
```

Lệnh đầu tạo mật khẩu ngẫu nhiên trong `.env` riêng của máy. Lệnh thứ hai tạo dữ liệu tài khoản trong Docker volume `mqtt_data`, bật broker và tạo hai tài khoản `backend`, `vision-01`. Chạy lại setup cập nhật ACL của hai role này, không đổi mật khẩu hoặc bật lại tài khoản bị thu hồi. Bài test cuối kiểm tra đăng nhập ẩn danh bị từ chối, quyền đọc/ghi đúng topic và thu hồi thiết bị ngắt kết nối ngay. Chỉ chạy trên broker đã được duyệt áp dụng bộ quyền mới.

Nếu chạy BE bằng Docker Compose, `mqtt-setup` tự chạy trước BE. Nếu chạy BE bằng Uvicorn trên Windows, giữ `MQTT_HOST=localhost` và `MQTT_PORT=1884` trong `.env`. Khi đổi `.env`, khởi động lại BE để nạp cấu hình mới.

## Tài khoản và quyền

| Tài khoản | Được gửi | Được đọc |
| --- | --- | --- |
| `backend` | `driver/+/command`, `driver/+/config/update`, `driver/+/storage_ack` | `driver/#` |
| `vision-01` (Edge AI mặc định) | `driver/vision-01/telemetry`, `/events`, `/status`; thêm ba topic chung cũ để tương thích | Chỉ `driver/vision-01/storage_ack` |
| Vision Node khác do API provision | Chỉ telemetry/events/status theo mã của chính nó | Chỉ storage_ack theo mã của chính nó |
| Mỗi thiết bị `alert-...` | Chỉ `status`, `ack`, `telemetry`, `heartbeat`, `config/applied` của chính nó | Chỉ `command`, `config/update` của chính nó |

Topic TV1 giữ nguyên. TV3 đã chuyển thư mục sang `edge-ai` và dùng topic theo mã thiết bị. `edge-ai/config.py` lấy tài khoản, host/cổng và `AI_DEVICE_CODE` từ `.env`; cài thư viện bằng `edge-ai/requirements.txt`. Nếu Admin đăng ký thiết bị mặc định `vision-01`, nút cấp thông tin kết nối trả tài khoản AI đã tạo. MQTT trên cổng 1884 vẫn là kết nối không mã hóa; chỉ sử dụng trong mạng nội bộ tin cậy.

## Nâng từ ACL cũ

Sau khi duyệt thay đổi quyền, build image `mqtt-setup` mới và chạy `docker compose --env-file .env -f deployment/docker-compose.yml run --rm mqtt-setup`. Chỉ pull code chưa cập nhật được ACL đang lưu tại broker. Setup mới dùng `modifyRole` để cập nhật role đã có; không cần xóa Docker volume hay cấp lại mật khẩu.

Luồng SQLite cần migration bổ sung `ai_message_receipts` trước khi mở BE mới. AI chỉ xóa bản lưu tạm sau khi nhận `SAVED` từ BE; đây là xác nhận lưu dữ liệu, khác ACK thực hiện lệnh từ ESP32.

Kiểm tra toàn bộ trên môi trường riêng, không sửa broker đang dùng: `python backend/tests/run_week3_isolated.py`. Script tạo broker, tài khoản, network và DB thử, chạy các ca rồi dọn tài nguyên thử.

## Cấp tài khoản cho ESP32

Admin mở trang chi tiết thiết bị và bấm **Cấp thông tin kết nối**. Hộp thoại hiện tên đăng nhập và mật khẩu MQTT **một lần**. Chép chúng vào `firmware/esp32-alert-node/include/network_config.h` (file này được Git bỏ qua), cùng IP laptop chạy broker và cổng `1884`. Không đưa mật khẩu vào file mẫu hay Git. Nếu cần cấp lại mật khẩu cho thiết bị đã cấp, cần bổ sung luồng xoay mật khẩu riêng; nút cấp hiện chỉ dùng cho thiết bị ở trạng thái `REGISTERED`.

Khi bấm **Ngừng sử dụng**, BE thu hồi tài khoản của thiết bị trong broker. Broker ngắt kết nối MQTT đang mở của tài khoản ấy; tài khoản cũ không đăng nhập lại được. Với `vision-01`, tài khoản được vô hiệu hóa và không được bước khởi tạo tự bật lại sau khi khởi động.

Lưu ý: broker Mosquitto cài riêng trên Windows ở cổng 1883 vẫn chạy theo cấu hình riêng của nó. Bài test trên kiểm tra broker Docker ở cổng 1884. Nếu ESP32 còn dùng 1883 hoặc chưa nhận mật khẩu, nó chưa kết nối vào broker Docker bảo mật.
