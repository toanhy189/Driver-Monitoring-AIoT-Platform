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
| Motor | D33 | Motor bật 400 ms, nghỉ khoảng 3 giây giữa hai lần bật |
| Wifi | Không thêm dây | In IP hoặc timeout sau 20 giây; nhấn EN để thử lại |
| Mqtt | Không thêm dây | Kết nối broker, gửi ONLINE, in topic và nội dung tin nhận |

Rút USB trước khi thay dây. Đấu theo tài liệu: LED nối tiếp 330 ohm; nút D27 xuống
GND; buzzer/motor qua transistor với điện trở base khoảng 1 kohm, motor có diode.
Xác định đúng B/C/E và nguồn của từng tải trước khi cấp điện. Người dùng cung
cấp thông số motor **5 V**, chữ trên transistor là **`2N2222 / A331`**; nguồn
cấp thực tế, dòng tải và pinout đúng linh kiện vẫn cần xác nhận. Không nối
motor/buzzer trực tiếp vào GPIO. Đầu ra tắt khi khởi động; chỉ bài được chọn
mới bật tải trong môi trường `test`. `TEST_MODE` không chọn bài tự chạy cho
firmware `development`.

## Mục 6.3 — lắp và test motor rung

Vị trí dưới đây dùng **nửa A–E của breadboard 30 hàng**, giữ nguyên buzzer ở F–J.
Đường GND tại hàng transistor được đưa trực tiếp tới **A5** trong lượt chỉnh;
A5/C5/D5 cùng nhóm điện. Bảng ghi chức năng mong muốn tại từng hàng, **không
xác nhận thứ tự chân transistor chỉ từ chữ `2N2222 A331`**:

| Phần mạch | Vị trí |
|---|---|
| Transistor 2 | Ba chân tại C5/C6/C7; cần xác nhận đúng E=C5, B=C6, C=C7 theo pinout của linh kiện |
| GND driver | GND ESP32 → A5; cực âm nguồn motor cùng GND. D5 → thanh GND cũng tương đương nếu đã nối chung GND thật |
| Ba điện trở 330 Ω mới | D6–D8, E8–E9, B9–B10 |
| Thay cả chuỗi điện trở nếu dùng 1 kΩ | Một điện trở A6–A10; không dùng đồng thời với chuỗi ba điện trở |
| Dây điều khiển | D33 ESP32 → A10 |
| Motor | Dây đỏ → C12, dây đen → B7 qua đầu nối chắc chắn |
| Diode 1N4007 | Đầu có vạch bạc → D12, đầu không vạch → D7 |
| Nguồn motor 5 V riêng, đủ dòng (phương án tham chiếu) | Cực dương → A12, cực âm → GND chung với ESP32; nguồn thực tế còn cần xác nhận |

Nguồn motor tách cực dương khỏi VIN/3V3 và dải nguồn buzzer. Chưa đo dòng tải
hoặc xác nhận pinout thì chưa chốt nguồn/mạch demo. Dây cầu chia cùng một nguồn
phải nối **+ với +, − với −**; không nối thanh đang có VIN sang thanh đang có GND.
Hai thanh khác bên thường không nối điện sẵn. Xem [mô tả nguồn, vị trí dây và
LED thử](../../hardware/README.md) trước khi phục hồi nhánh motor.

Để nguồn motor ngắt khi Upload. Trong `include/config.h`, chọn:

```cpp
constexpr TestMode TEST_MODE = TestMode::Motor;
```

Sau khi kiểm tra mạch và nguồn, Build/Upload bằng **`-e test`**, rồi mở Monitor
**115200 baud**. `src/tests/main.cpp` in `[MOTOR] Before ON`, `[MOTOR] ON` và
`[MOTOR] OFF`. GPIO LOW 500 ms trước mỗi lần ON, HIGH 400 ms, rồi LOW 2500 ms;
hai lần ON cách nhau khoảng 3 giây nghỉ. Đây là bài tự lặp, chỉ bật nguồn motor
khi đã sẵn sàng kiểm thử; không dùng thay firmware `development` nhận lệnh web.

**Tháo dây nối tạm E7–E5**, giữ dây âm motor tại B7; không chuyển sang B5.
Những đường nối đó bỏ qua transistor và có thể làm motor chạy liên tục ngoài
lệnh. Phép thử LED ở GPIO33 đã được người dùng xác nhận nháy rồi tắt; người dùng
cũng báo motor có rung sau lượt chỉnh, nhưng cần kiểm tra lại bật/tắt đúng lệnh,
nguồn và trạng thái mạch trước khi nghiệm thu. Cách đấu và tháo bộ LED thử được
ghi tại [tài liệu phần cứng](../../hardware/README.md); không tháo nhầm LED chính GPIO26.

## Kết nối để demo với Backend

Firmware chính nằm trong `src/app/`, môi trường PlatformIO **development**. Các bài thử tải ở trên thuộc `src/tests/`, chỉ chạy khi chọn môi trường **test**; không dùng chúng thay firmware demo.

1. Kiểm tra mạch/nguồn và [bảng phần cứng](../../hardware/README.md) trước khi nạp/bật tải.
2. Copy `include/network_config.example.h` thành `include/network_config.h`.
3. Điền Wi-Fi 2,4 GHz, IP LAN laptop, MQTT port **1884**, username/password đã cấp cho Alert Node. Broker dự án bắt buộc xác thực.
4. `DEVICE_CODE` trong `include/config.h` phải khớp thiết bị đã đăng ký và provision. File credential được Git bỏ qua.

```powershell
$taskPio = "$env:USERPROFILE\.platformio\penv\Scripts\pio.exe"
& $taskPio device list
& $taskPio run -d firmware/esp32-alert-node -e development
# Thay COM7 bằng cổng USB-SERIAL CH340/USB-Serial hiện có; không chọn Bluetooth.
$taskPort = 'COM7'
# Chỉ upload sau khi xác nhận mạch, ngắt nguồn tải và đóng Serial Monitor:
& $taskPio run -d firmware/esp32-alert-node -e development -t upload --upload-port $taskPort
& $taskPio device monitor -d firmware/esp32-alert-node --port $taskPort --baud 115200
```

Đoạn PowerShell dùng vị trí PlatformIO thường gặp khi cài qua VS Code trên
Windows. Nếu đã có `pio` trong PATH, có thể dùng `pio` thay `& $taskPio`; hệ điều
hành khác dùng `pio` tại môi trường đã cài. **COM7 chỉ là ví dụ từng được nhận**;
đổi cáp/cổng USB có thể đổi số COM. Đổi cáp không đổi chương trình trên ESP32.
Nếu không thấy USB–Serial trong `device list`, kiểm tra USB/cáp/driver trước,
không nạp lại firmware chỉ vì cổng COM cũ không tồn tại.

Firmware gửi heartbeat mỗi 5 giây; nhận command/config, trả ACK; tự reconnect và đăng ký lại topic. Lệnh có TTL/kiểm tra giờ, chống thực thi trùng request_id; cấu hình có revision, lưu NVS và phản hồi APPLIED/REJECTED. Firmware hỏi NTP ở host broker trong LAN trước nguồn Internet dự phòng.

Gửi lệnh bằng React hoặc API Backend để có kiểm tra quyền và lịch sử. MQTT consumer chạy sẵn trong Backend, không mở thêm script consumer/publisher cũ. Xem [luồng command/config](flow.md), [10 bước demo](../../README.md#4-demo-theo-mục-84-của-đề-bài).

Khi cần thử từng linh kiện độc lập, chọn TestMode trong `include/config.h` rồi dùng `-e test` ở cả Build và Upload. Mạch của nhóm chưa được nghiệm thu chỉ từ kết quả biên dịch; không tự suy nguồn tải hay chân transistor từ GPIO.
