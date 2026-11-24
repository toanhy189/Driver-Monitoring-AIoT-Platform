# Firmware — ESP32 Alert Node

Chương trình nhúng cho mạch **ESP32 DOIT DevKit V1** (tốc độ Serial **115200 baud**), được quản lý và biên dịch bằng PlatformIO.

`platformio.ini` khóa nền tảng `espressif32@7.1.3` để dùng Arduino 2.0.17 như môi trường đã kiểm tra. Giữ phiên bản này khi build trên máy mới/CI; Arduino 3.x thay đổi API mbedTLS mà phần OTA hiện đang sử dụng.

- Môi trường **`development`** (`src/app/`): Firmware vận hành chính thức, kết nối Wi-Fi/MQTT, đồng bộ thời gian NTP, điều khiển tải, lưu cấu hình vào NVS và phản hồi `ACK`.
- Môi trường **`ota-release`** / **`ota-demo-043`**: Các bản build phục vụ quy trình ký số và cập nhật firmware từ xa qua mạng (OTA).
- Môi trường **`test`** (`src/tests/`): Bộ bài kiểm tra độc lập từng linh kiện phần cứng trên breadboard.

---

## 1. Chế độ kiểm tra phần cứng độc lập (`-e test`)

Khi mới lắp mạch, có thể kiểm tra riêng từng đầu ra bằng cách mở `include/config.h`, chỉnh giá trị `TEST_MODE` rồi biên dịch với môi trường `test`:

```cpp
constexpr TestMode TEST_MODE = TestMode::Led;
```

| Giá trị `TestMode` | Chân GPIO | Hành vi kiểm tra mong đợi |
|---|---|---|
| `Led` | `D26` (`GPIO26`) | Đèn LED sáng `500 ms`, tắt `500 ms` lặp lại; in trạng thái `LED ON/OFF` ra Serial |
| `Button` | `D27` (`INPUT_PULLUP`), `D26` | Nhấn nút nối `D27` xuống `GND`: Serial in `PRESSED` và LED sáng; nhả nút: `RELEASED` và LED tắt |
| `Buzzer` | `D25` (`GPIO25`) | Còi báo động kêu `300 ms`, nghỉ `2000 ms` |
| `Motor` | `D33` (`GPIO33`) | Motor rung chạy `400 ms`, nghỉ khoảng `3 giây` giữa hai chu kỳ |
| `Wifi` | Không cần thêm dây | Thử kết nối Wi-Fi, in địa chỉ IP nhận được hoặc báo timeout sau 20 giây |
| `Mqtt` | Không cần thêm dây | Kết nối tới MQTT broker, gửi trạng thái `ONLINE` và in các bản tin nhận được |

> **Lưu ý:** Đấu nối còi và motor qua mạch đệm transistor + điện trở cực Base `~1 kΩ` (motor có gắn song song diode chống ngược dòng `1N4007`) theo đúng hướng dẫn tại [hardware/README.md](../../hardware/README.md). Hằng số `TEST_MODE` chỉ có tác dụng khi nạp bằng cờ `-e test`, không ảnh hưởng tới bản chạy chính `-e development`.

---

## 2. Cấu hình mạng và nạp Firmware vận hành chính (`-e development`)

1. Sao chép file mẫu `include/network_config.example.h` thành `include/network_config.h` (file này nằm trong `.gitignore` để bảo mật thông tin mạng).
2. Điền tên/mật khẩu Wi-Fi 2.4 GHz, địa chỉ IP LAN của máy tính chạy Mosquitto broker, cổng **`1884`**, cùng `mqtt_username` và `mqtt_password` đã cấp riêng cho thiết bị trên giao diện Admin.
3. Đảm bảo `DEVICE_CODE` trong `include/config.h` khớp với mã thiết bị đã đăng ký (ví dụ `alert-01`).
4. Biên dịch, nạp chương trình và mở Serial Monitor theo dõi:

```powershell
$pio = "$env:USERPROFILE\.platformio\penv\Scripts\pio.exe"
& $pio device list
& $pio run -d firmware/esp32-alert-node -e development

# Thay COM7 bằng cổng USB-Serial thực tế hiển thị trong danh sách thiết bị
$port = "COM7"
& $pio run -d firmware/esp32-alert-node -e development -t upload --upload-port $port
& $pio device monitor -d firmware/esp32-alert-node --port $port --baud 115200
```

*(Nếu đã cấu hình `pio` sẵn trong biến môi trường `PATH`, có thể gọi trực tiếp `pio` thay cho `& $pio`).*

### Cơ chế hoạt động của Firmware chính
- **Heartbeat & Tự phục hồi:** Gửi gói tin trạng thái định kỳ mỗi **5 giây** kèm phiên bản firmware/phần cứng; tự động kết nối lại Wi-Fi/MQTT và đăng ký lại các topic khi mạng khôi phục.
- **Xử lý lệnh an toàn:** Kiểm tra thời hạn hiệu lực lệnh (`TTL` / `expires_at_ms`) dựa trên đồng hồ NTP nội bộ, lưu nhật ký 16 `request_id` gần nhất vào bộ nhớ NVS để chống chạy lặp lệnh trùng, điều khiển đóng/ngắt tải không chặn vòng lặp (`non-blocking`) và gửi `ACK` (`ACCEPTED` → `COMPLETED` / `FAILED`).
- **Lưu trữ cấu hình bền vững:** Nhận cấu hình nhịp bật/tắt 3 mức qua `config/update`, kiểm tra `revision`, ghi vào Flash **NVS** để giữ nguyên sau khi mất điện và phản hồi `APPLIED` / `REJECTED`.

Xem chi tiết luồng bản tin tại [flow.md](flow.md).

---

## 3. Hỗ trợ cập nhật Firmware từ xa (OTA)

- Bản `development` đóng vai trò firmware nền (`0.4.0`), `ota-release` tương ứng bản `0.4.1`, và `ota-demo-043` dùng để đóng gói bản `0.4.3` phục vụ trình diễn nâng cấp qua mạng.
- Chức năng OTA sử dụng file cấu hình tin cậy cục bộ `include/ota_trust.h` (chứa khóa công khai RSA-2048 để xác minh chữ ký manifest, chứng chỉ CA và địa chỉ HTTPS tải firmware). Nếu chưa tạo `ota_trust.h`, tính năng OTA tự động vô hiệu hóa nhưng các luồng nhận lệnh/cấu hình thường ngày vẫn chạy bình thường.
- Quy trình tạo khóa ký, đóng gói file `.bin` + `.manifest.json` và thực hiện cập nhật trên giao diện Web được trình bày đầy đủ tại [docs/firmware-ota.md](../../docs/firmware-ota.md).
