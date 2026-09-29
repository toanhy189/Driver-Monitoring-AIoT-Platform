# ESP32 alert node — các bài thử tuần 1

Firmware tuần 1 dùng PlatformIO (thêm Arduino.h; PubSubClient đã khai báo
trong platformio.ini). Board: ESP32 DOIT DevKit V1; Serial: **115200 baud**.

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
lặp lại; không cần nhấn nút TEST. `src/main.cpp` đã có bài test này.

**Dây thử tạm E7–E5:** rút USB/ngắt nguồn,
thêm một dây đực–đực E7→E5 để bỏ qua transistor và thử motor khoảng 1 giây với
nguồn phù hợp. Giữ nguyên dây D5→GND. Dây thử làm motor có thể chạy liên tục,
không theo code; **ngắt nguồn rồi tháo E7–E5 trước khi thử chu kỳ Motor**.
Motor rung với dây thử chưa chứng minh phần điều khiển bằng transistor hoạt động.

## Wi-Fi và MQTT

Copy `include/network_config.example.h` thành `include/network_config.h`,
điền SSID, mật khẩu, IP laptop TV2 và cổng broker. Nếu cần tài khoản broker, điền
MQTT_USER và MQTT_PASSWORD; nếu không thì để trống. File network_config.h được
Git bỏ qua. Chỉ giữ giá trị mẫu trong file .example.h. Khi thiếu file riêng,
firmware dùng mẫu và in lời nhắc ở Serial.

- Wi-Fi 2,4 GHz, cùng mạng với laptop TV2.
- Device ID: alert-01.
- Subscribe: driver/alert-01/command.
- Publish: driver/alert-01/status, nội dung ONLINE mỗi lần kết nối MQTT thành công.
- Chờ khoảng 5 giây trước lần thử MQTT đầu tiên; thử lại sau khoảng 5 giây.
- Mất Wi-Fi: thử kết nối lại. Khi mạng/broker trở lại: đăng ký topic và gửi ONLINE lại.
- Callback chỉ in đúng số byte nhận. BUZZER_TEST cũng **chỉ được in**, không bật tải.
- Tuần 1 chưa có ACK, heartbeat hay xử lý lệnh điều khiển tải.

## Build, Upload và Serial

Trong PlatformIO, chọn project firmware/esp32-alert-node rồi dùng Build, Upload,
Monitor. Trong terminal PlatformIO ở thư mục gốc repository:

```powershell
pio run -d firmware/esp32-alert-node
pio run -d firmware/esp32-alert-node -t upload
pio device monitor -d firmware/esp32-alert-node
```

Build kiểm tra biên dịch; cần cắm board và Upload để chạy. Chọn cổng COM thực tế
của board, Serial 115200 baud. Khi mở cả repository, cập nhật IntelliSense sau
khi đổi thư viện bằng:

```powershell
pio run -d firmware/esp32-alert-node -t compiledb
```

Để kiểm tra MQTT, TV2 subscribe topic status trước khi ESP32 kết nối, sau đó
publish BUZZER_TEST lên topic command. Serial cần có IP, connected,
subscribe=OK, publish=OK và đúng tin nhận. Buzzer/motor tiếp tục tắt trong bài MQTT.
