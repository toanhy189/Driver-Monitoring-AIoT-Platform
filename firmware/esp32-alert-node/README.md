# ESP32 Alert Node

Board PlatformIO: **ESP32 DOIT DevKit V1**, Serial **115200 baud**. Firmware demo dùng môi trường `development`; các bài thử phần cứng dưới đây dùng `test`.

## Chọn bài thử

Mở `include/config.h`, sửa dòng sau rồi **Build và Upload lại**:

```cpp
constexpr TestMode TEST_MODE = TestMode::Button;
```

Thay giá trị sau `TestMode::` bằng một giá trị dưới đây. Mỗi lần chỉ chạy một bài
thử, theo thứ tự tài liệu. Bài thực sự được chọn nằm trong `include/config.h`.

| Giá trị | GPIO | Kết quả mong đợi |
|---|---|---|
| Led | D26 | Sáng 500 ms, tắt 500 ms; in LED ON/OFF |
| Button | D27 INPUT_PULLUP, D26 | Nhấn nối D27 xuống GND: PRESSED, LED sáng; thả: RELEASED, LED tắt; đọc mỗi 150 ms |
| Buzzer | D25 | Buzzer active bật 300 ms, nghỉ 2000 ms |
| Motor | D33 | Motor bật 400 ms, nghỉ 2500 ms |
| Wifi | Không thêm dây | In IP hoặc timeout sau 20 giây; nhấn EN để thử lại |
| Mqtt | Không thêm dây | Kết nối broker, gửi ONLINE, in topic và nội dung tin nhận |

Rút USB trước khi thay dây. Đấu theo tài liệu: LED nối tiếp 330 ohm; nút D27 xuống
GND; buzzer/motor qua transistor với điện trở base khoảng 1 kohm, motor có diode.
Xác định đúng B/C/E và điện áp định mức của từng tải trước khi cấp nguồn;
motor đồng xu chưa được xác nhận là loại 5 V. Không nối motor/buzzer trực tiếp
vào GPIO. Đầu ra tắt khi khởi động; chỉ bài được chọn mới bật tải.

## Mục 6.3 — lắp và test motor rung

Vị trí dưới đây dùng **nửa A–E của breadboard 30 hàng**, giữ nguyên buzzer ở F–J:

| Phần mạch | Vị trí |
|---|---|
| Transistor 2 | E=C5, B=C6, C=C7; D5 về GND chung |
| Ba điện trở 330 Ω mới | D6–D8, E8–E9, B9–B10 |
| Dây điều khiển | D33 ESP32 → A10 |
| Motor | Dây đỏ → C12, dây đen → B7 qua đầu nối chắc chắn |
| Diode 1N4007 | Đầu có vạch bạc → D12, đầu không vạch → D7 |
| Nguồn motor đúng điện áp | Cực dương → A12, cực âm → GND chung với ESP32 |

Nguồn motor tách cực dương khỏi VIN/3V3 và dải nguồn buzzer. **Chưa biết điện áp
motor thì chưa cấp điện.** Kiểm tra dòng khởi động và khả năng mạch transistor
theo hướng dẫn đầy đủ trước khi thử.

Để nguồn motor ngắt khi Upload. Trong `include/config.h`, chọn:

```cpp
constexpr TestMode TEST_MODE = TestMode::Motor;
```

Lưu, Build, Upload rồi mở Monitor **115200 baud**. Sau khi thấy `MOTOR ON/OFF`
và kiểm tra mạch/nguồn, bật nguồn motor. Kết quả: rung **400 ms**, nghỉ **2500 ms**,
lặp lại; không cần nhấn nút TEST. `src/tests/main.cpp` đã có bài test này.

**Dây thử tạm E7–E5:** rút USB/ngắt nguồn,
thêm một dây đực–đực E7→E5 để bỏ qua transistor và thử motor khoảng 1 giây với
nguồn phù hợp. Giữ nguyên dây D5→GND. Dây thử làm motor có thể chạy liên tục,
không theo code; **ngắt nguồn rồi tháo E7–E5 trước khi thử chu kỳ Motor**.
Motor rung với dây thử chưa chứng minh phần điều khiển bằng transistor hoạt động.

## Kết nối để demo với Backend

Firmware chính nằm trong `src/app/`, môi trường PlatformIO **development**. Các bài thử tải ở trên thuộc `src/tests/`, chỉ chạy khi chọn môi trường **test**; không dùng chúng thay firmware demo.

1. Kiểm tra mạch/nguồn và [bảng phần cứng](../../hardware/README.md) trước khi nạp/bật tải.
2. Copy `include/network_config.example.h` thành `include/network_config.h`.
3. Điền Wi-Fi 2,4 GHz, IP LAN laptop, MQTT port **1884**, username/password đã cấp cho Alert Node. Broker dự án bắt buộc xác thực.
4. `DEVICE_CODE` trong `include/config.h` phải khớp thiết bị đã đăng ký và provision. File credential được Git bỏ qua.

```powershell
pio run -d firmware/esp32-alert-node -e development
# Chỉ sau khi xác nhận mạch, thay COM4 bằng cổng thực tế:
pio run -d firmware/esp32-alert-node -e development -t upload --upload-port COM4
pio device monitor -d firmware/esp32-alert-node --port COM4 --baud 115200
```

Firmware gửi heartbeat mỗi 5 giây; nhận command/config, trả ACK; tự reconnect và đăng ký lại topic. Lệnh có TTL/kiểm tra giờ, chống thực thi trùng request_id; cấu hình có revision, lưu NVS và phản hồi APPLIED/REJECTED. Firmware hỏi NTP ở host broker trong LAN trước nguồn Internet dự phòng.

Gửi lệnh bằng React hoặc API Backend để có kiểm tra quyền và lịch sử. MQTT consumer chạy sẵn trong Backend, không mở thêm script consumer/publisher cũ. Xem [luồng command/config](flow.md), [10 bước demo](../../README.md#4-demo-theo-mục-84-của-đề-bài).

Khi cần thử từng linh kiện độc lập, chọn TestMode trong `include/config.h` rồi dùng `-e test` ở cả Build và Upload. Mạch của nhóm chưa được nghiệm thu chỉ từ kết quả biên dịch; không tự suy nguồn tải hay chân transistor từ GPIO.
