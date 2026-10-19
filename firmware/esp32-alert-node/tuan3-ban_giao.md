# TV1-19 — Bàn giao firmware ESP32 alert node

> Tài liệu bàn giao riêng cho TV1-19. Tóm tắt source, cấu hình mẫu không chứa
> secret, sơ đồ chân, phiên bản firmware, schema MQTT, bằng chứng Serial/MQTT,
> video đính kèm `(chưa có)` và giới hạn QoS đã biết.

## 1. Phạm vi bàn giao

- Board: ESP32 DOIT DevKit V1.
- Môi trường firmware ứng dụng: PlatformIO `development` (`src/app/`).
- Device code: `alert-01`.
- Firmware version hiện được biên dịch trong source: `0.2.10`.
- Serial: `115200` baud.
- Topic MQTT và schema mẫu ở mục 4.
- Cấu hình mẫu chỉ dùng placeholders; không đưa SSID, mật khẩu Wi-Fi hay
  credential broker thật vào tài liệu, video, ảnh chụp hoặc repository.
- TV1-17: người dùng đã xác nhận thử reset bằng nút EN; log chuyển
  `IN_PROGRESS -> INTERRUPTED`, ACK `INTERRUPTED / REBOOTED`, và retry cùng ID
  trả lại kết quả mà không chạy tải lần nữa.
- TV1-18: checklist tích hợp trên board nằm ở mục 8 bên dưới; chỉ đánh dấu
  hoàn tất sau khi chạy đủ các bước trên phần cứng và chốt QoS ACK với BE.

## 2. Source cần bàn giao

Các file chính của môi trường `development`:

| File | Nội dung |
| --- | --- |
| `platformio.ini` | PlatformIO environments `development` và `test`; source filter. |
| `include/config.h` | Firmware version, device code, GPIO và MQTT topics. |
| `include/network_config.example.h` | Cấu hình mạng minh họa, không có secret. |
| `include/device_config.h`, `src/app/device_config.cpp` | Pin/timing thiết bị, parse và validate timing. |
| `include/config_store.h`, `src/app/config_store.cpp` | Lưu/đọc config timing trong NVS; kiểm tra magic/CRC. |
| `include/mqtt_client.h`, `src/app/mqtt_client.cpp` | Wi-Fi/MQTT, heartbeat, ACK, config routing, SNTP và reconnect. |
| `include/command_handler.h`, `src/app/command_handler.cpp` | Validate/điều khiển lệnh, ACK, thời gian chạy và trạng thái request. |
| `include/request_log.h`, `src/app/request_log.cpp` | Request log NVS, retry/dedupe, ring 16 record và phục hồi sau reboot. |
| `src/app/main.cpp` | Thứ tự khởi động an toàn, nạp config và phục hồi request log. |
| `TV1-19-HANDOFF.md`, `flow.md` | Hướng dẫn build/test, ví dụ payload và luồng ACK. |

Build và upload:

```powershell
pio run -d firmware/esp32-alert-node -e development
pio run -d firmware/esp32-alert-node -e development -t upload --upload-port COM4
pio device monitor -d firmware/esp32-alert-node -b 115200 --port COM4
```

Đóng Serial Monitor trước upload và thay `COM4` bằng cổng thực tế. Không dùng
`erase` trong thao tác bàn giao; thao tác đó có thể xóa NVS config và request log.

## 3. Cấu hình mẫu không secret

`include/network_config.example.h` là mẫu. Tạo file local
`include/network_config.h` (đã được Git ignore) để điền mạng thử nghiệm:

```cpp
#pragma once

constexpr char WIFI_SSID[] = "YOUR_WIFI_SSID";
constexpr char WIFI_PASSWORD[] = "YOUR_WIFI_PASSWORD";
constexpr char MQTT_HOST[] = "192.0.2.10";
constexpr int MQTT_PORT = 1883;
constexpr char MQTT_USER[] = "";
constexpr char MQTT_PASSWORD[] = "";
```

Địa chỉ `192.0.2.10` là địa chỉ tài liệu dành cho ví dụ, cần thay bằng địa chỉ
broker có thể truy cập từ ESP32. Không commit file local có credential. Nếu
broker yêu cầu auth, đặt user/password trong file local và không chụp/đính kèm
giá trị đó trong ảnh hoặc video bàn giao.

## 4. Pin map và tải

| Chức năng | ESP32 GPIO | Ghi chú kết nối |
| --- | ---: | --- |
| LED | D26 / GPIO26 | Điện trở nối tiếp theo sơ đồ mạch. |
| Buzzer | D25 / GPIO25 | Điều khiển qua transistor; không nối tải trực tiếp GPIO. |
| Motor | D33 / GPIO33 | Driver transistor và diode; dùng nguồn motor đúng định mức, chung GND. |
| Nút | D27 / GPIO27 | `INPUT_PULLUP`, nhấn nối chân xuống GND. |

Trước khi cấp nguồn tải, xác nhận pinout transistor B/C/E, chiều diode, điện áp
và dòng khởi động của motor/buzzer. Cố định motor khi thử. Tất cả đầu ra được
đặt `LOW` trong khởi động firmware.

## 5. MQTT topics và schema

Device code: `alert-01`.

| Topic | Hướng | Dùng cho |
| --- | --- | --- |
| `driver/alert-01/command` | BE → ESP32 | Lệnh bật/tắt thiết bị. |
| `driver/alert-01/ack` | ESP32 → BE | ACK nhận lệnh và trạng thái xử lý. |
| `driver/alert-01/status` | ESP32 → BE / broker LWT | `ALIVE` heartbeat/kết nối và `OFFLINE` LWT. |
| `driver/alert-01/config/update` | BE → ESP32 | Config timing JSON retained. |
| `driver/alert-01/config/applied` | ESP32 → BE | Kết quả `APPLIED`/`REJECTED`. |

### Command mẫu

```json
{
  "request_id": "handoff-led-001",
  "command": "LED_ON",
  "duration": 2000,
  "intensity": "WEAK"
}
```

`command` hỗ trợ `LED_ON`, `LED_OFF`, `BUZZER_ON`, `BUZZER_OFF`, `MOTOR_ON`,
`MOTOR_OFF`. Lệnh ON cần `request_id` không rỗng (tối đa 39 ký tự), duration
trong khoảng 1–60000 ms và intensity `WEAK`, `MEDIUM`, `STRONG` hoặc `CONSTANT`.
Các mã lỗi thường gặp gồm `INVALID_COMMAND`, `UNKNOWN_COMMAND`,
`INVALID_PAYLOAD`, `BUSY`, `STORAGE_ERROR` và `DUPLICATE_ID_MISMATCH`.

### ACK command mẫu

```json
{
  "request_id": "handoff-led-001",
  "device_code": "alert-01",
  "status": "COMPLETED",
  "elapsed_ms": 2000,
  "error": null
}
```

ACK theo luồng thông thường: `ACKNOWLEDGED` → `STARTED` → `COMPLETED`; lệnh sai
hoặc bận trả `FAILED`. Sau reboot khi request còn `IN_PROGRESS`, firmware trả
`INTERRUPTED` với `error: "REBOOTED"` và không chạy lại tải.

### Config mẫu

Mỗi config phải có ba thiết bị (`led`, `buzzer`, `motor`), mỗi thiết bị đủ các
mức `"1"`, `"2"`, `"3"` tương ứng `WEAK`, `MEDIUM`, `STRONG`. Giới hạn
`on_ms`: 50–5000; `off_ms`: 50–10000. `CONSTANT` giữ timing mặc định firmware.

```json
{
  "config_id": "handoff-config-001",
  "timings": {
    "led": {
      "1": {"on_ms": 100, "off_ms": 800},
      "2": {"on_ms": 300, "off_ms": 700},
      "3": {"on_ms": 700, "off_ms": 300}
    },
    "buzzer": {
      "1": {"on_ms": 100, "off_ms": 800},
      "2": {"on_ms": 300, "off_ms": 700},
      "3": {"on_ms": 700, "off_ms": 300}
    },
    "motor": {
      "1": {"on_ms": 100, "off_ms": 800},
      "2": {"on_ms": 300, "off_ms": 700},
      "3": {"on_ms": 700, "off_ms": 300}
    }
  }
}
```

Publish config lên `driver/alert-01/config/update` với QoS 1 và retained. Kết quả
được gửi đến `driver/alert-01/config/applied`:

```json
{
  "config_id": "handoff-config-001",
  "device_code": "alert-01",
  "status": "APPLIED"
}
```

Status heartbeat mẫu:

```json
{
  "device_code": "alert-01",
  "status": "ALIVE",
  "firmware_version": "0.2.10",
  "config_id": "handoff-config-001"
}
```

## 6. Log kiểm chứng Serial/MQTT

Trích log kiểm chứng TV1-17 bằng EN (rút gọn; không chứa Wi-Fi password hoặc
broker credential):

```text
[BOOT] reset_reason=1
[CONFIG] loaded config_id=cfg-nvs-001
[REQLOG] tv117-en-001 was IN_PROGRESS -> INTERRUPTED
[REQLOG] flash write #1
[WIFI] Connected; IP = <board-ip>
[MQTT] subscribe command=OK config=OK, publish=OK
[MQTT] Send ACK:
  "request_id": "tv117-en-001",
  "status": "INTERRUPTED",
  "elapsed_ms": 0,
  "error": "REBOOTED"
```

Đã có log MQTT kiểm chứng ring TV1-16: record `tv116-ring-01` được chấp nhận
lại và chạy như lệnh mới sau khi bị đẩy khỏi vòng:

```text
[CMD] WEAK on=200 off=800
[REQLOG] flash write #245
"status": "STARTED"
[REQLOG] flash write #246
"status": "COMPLETED",
"elapsed_ms": 100
```

`flash write #245/#246` lần lượt là lưu `IN_PROGRESS` và trạng thái hoàn tất.
Số bộ đếm là giá trị tại lượt test, không phải giới hạn hoặc số lần ghi cố định.
Khi bàn giao chính thức, lưu log đầy đủ của lần test mới nhất kèm ngày giờ,
request ID và PASS/FAIL; che địa chỉ IP nếu chính sách môi trường yêu cầu.

## 7. QoS và giới hạn đã biết

- Subscribe command/config yêu cầu QoS 1.
- Publish ACK command và `config/applied` hiện dùng `PubSubClient::publish()`,
  tức QoS 0. Không tuyên bố ACK QoS 1 được bảo đảm.
- Heartbeat/status online thường QoS 0.
- LWT `OFFLINE` được đăng ký ở QoS 1, retained. LWT chỉ được broker phát hiện
  khi client mất kết nối mà broker vẫn đang hoạt động. Broker ngừng chạy thì
  subscriber không thể nhận message trong thời gian broker offline.
- BE cần xác nhận chấp nhận QoS 0 cho ACK và retry theo cùng `request_id`, hoặc
  yêu cầu thay MQTT client/giao thức trước khi chốt giao nhận QoS 1.
- Wi-Fi retry hiện dùng chu kỳ cố định 5 giây; MQTT retry trong môi trường
  `development` dùng chu kỳ 5 giây. MQTT backoff exponential/jitter trước đây
  thuộc môi trường `test`, không đồng nghĩa đã áp dụng cho firmware development.
- Request log lưu 16 record; timestamp chỉ hỗ trợ dọn 24 giờ sau khi SNTP có
  thời gian hợp lệ. Không có SNTP thì chỉ dọn theo số lượng.
- Mất điện có thể xảy ra sau khi tải bắt đầu nhưng trước ACK; bản ghi
  `IN_PROGRESS` được phục hồi thành `INTERRUPTED / REBOOTED`, không tiếp tục tải.

## 8. Kiểm thử tích hợp TV1-10 đến TV1-18

Các bước dưới đây giữ lại quy trình và tiêu chí từ hướng dẫn firmware. Chạy trên
board với firmware `development`; subscriber phải nghe đúng broker đang dùng.
Trong Ubuntu terminal đã định nghĩa hàm `P` ở mục 5.

### TV1-10/11/12 — validate, lưu và nạp config

Tạo config hợp lệ retained với QoS 1; cả ba thiết bị phải có đủ mức `"1"`, `"2"`,
`"3"`:

```bash
valid_config='{"config_id":"handoff-config-test-001","timings":{"led":{"1":{"on_ms":100,"off_ms":800},"2":{"on_ms":300,"off_ms":700},"3":{"on_ms":700,"off_ms":300}},"buzzer":{"1":{"on_ms":100,"off_ms":800},"2":{"on_ms":300,"off_ms":700},"3":{"on_ms":700,"off_ms":300}},"motor":{"1":{"on_ms":100,"off_ms":800},"2":{"on_ms":300,"off_ms":700},"3":{"on_ms":700,"off_ms":300}}}}'
docker exec deployment-mosquitto-1 mosquitto_pub \
  -h 127.0.0.1 -p 1883 -q 1 -r \
  -t 'driver/alert-01/config/update' -m "$valid_config"
```

Kỳ vọng: `config/applied` trả `APPLIED`, status mang ID tương ứng, và Serial
hiện `[CONFIG] APPLIED config_id=handoff-config-test-001`. Đổi ID và một timing
thành ngoài giới hạn (ví dụ `on_ms: 6000`): kỳ vọng `REJECTED /
ON_MS_OUT_OF_RANGE`, ID/timing đã áp dụng không đổi. Nạp lại config hợp lệ
retained sau thử nghiệm.

Nhấn-thả EN, đợi thiết bị online; kiểm tra Serial
`[CONFIG] loaded config_id=handoff-config-test-001` và status vẫn mang ID đó.
Gửi lệnh LED WEAK mới, xác nhận timing mới được dùng. Một lệnh đang chạy giữ
timing đã chụp lúc bắt đầu; config mới chỉ áp dụng cho lệnh sau.

### TV1-13 đến TV1-17 — idempotency và phục hồi

- **TV1-13:** lệnh hợp lệ mới tạo hai ghi NVS bình thường: `IN_PROGRESS` trước
  khi bật tải và trạng thái cuối khi kết thúc. Không ghi trong idle/heartbeat/
  các nhịp HIGH/LOW.
- **TV1-14:** gửi lại cùng ID/payload sau reboot; ACK phát lại, tải không chạy
  lại. Đã có kết quả thử thực tế `COMPLETED`, `FAILED / BUSY` và
  `INTERRUPTED / REBOOTED`.
- **TV1-15:** đổi duration hoặc intensity nhưng giữ ID; kỳ vọng
  `FAILED / DUPLICATE_ID_MISMATCH`, không thay bản ghi gốc.
- **TV1-16:** ring tối đa 16 record; gửi 20 ID hoàn tất rồi gửi lại ID đầu, ID
  cũ được xử lý như mới sau khi bị đẩy khỏi ring. Với SNTP hợp lệ, record kết
  thúc quá 24 giờ được dọn khi lệnh mới bắt đầu; nếu không có thời gian thì
  chỉ giới hạn theo số lượng.
- **TV1-17:** reset EN hoặc ngắt nguồn khi lệnh đang chạy; boot chuyển record
  `IN_PROGRESS` thành `INTERRUPTED / REBOOTED`, tải không tự chạy lại và
  không phát `COMPLETED` giả. Đã được người dùng xác nhận qua EN.

### TV1-18 — tích hợp phần cứng và reconnect

1. Build/upload đúng `development`; status báo `alert-01`, version `0.2.10`;
   Serial xác nhận MQTT subscribe command/config thành công.
2. Chạy test config hợp lệ/sai nêu trên.
3. Với mạch đã kiểm tra an toàn, chạy LED, buzzer và motor bằng command; xác
   nhận ACK `ACKNOWLEDGED` → `STARTED` → `COMPLETED`, tải dừng theo duration.
   Kiểm tra thêm duration ngoài giới hạn/intensity sai nhận
   `FAILED / INVALID_PAYLOAD`; lệnh intensity thấp hơn khi cùng tải đang chạy
   nhận `FAILED / BUSY`.
4. Tắt Wi-Fi AP nhưng giữ broker hoạt động; chờ ít nhất 30 giây để broker phát
   LWT `OFFLINE`, bật AP lại, xác nhận subscribe lại và `ALIVE`. Restart broker
   kiểm tra reconnect và `ALIVE`; khi broker ngừng hoạt động thì subscriber
   không thể nhận LWT trong khoảng đó.
5. Rút/cắm nguồn hoặc reset EN khi lệnh đang chạy để xác nhận TV1-17.
6. Ghi mỗi trường hợp PASS/FAIL cùng thời gian, request ID, ACK, trạng thái tải
   và log Serial. Không ghi credential vào bằng chứng.

**QoS là điều kiện chốt:** command/config subscribe QoS 1; ACK command và
`config/applied` publish QoS 0 qua PubSubClient. Chỉ ghi TV1-06 PASS nếu BE
chấp nhận QoS 0 và retry cùng ID; nếu BE yêu cầu ACK QoS 1 thì ghi
`BLOCKED — cần thay client/giao thức`, không tuyên bố QoS 1 đã được bảo đảm.
TV1-18 chỉ được đánh dấu PASS sau khi chạy trên board và chốt điều kiện này.

## 9. Video bàn giao

**Trạng thái:** chưa có video được đính kèm trong workspace. Trước khi bàn giao
cuối, quay clip ngắn thể hiện liên tục:

1. Board/mạch và GPIO/tải đang thử (không quay credential hoặc màn hình có secret).
2. Serial Monitor ở 115200 baud: boot/version, Wi-Fi/MQTT kết nối, subscribe OK.
3. MQTT subscriber nhận một command, ACK và status tương ứng; tải bật/tắt theo
   thời lượng.
4. Nếu video bao gồm config, thể hiện `APPLIED` và `config_id`; nếu bao gồm
   reboot recovery, thể hiện log `IN_PROGRESS -> INTERRUPTED` và ACK
   `INTERRUPTED / REBOOTED`.
5. Thêm video vào nơi lưu trữ được nhóm cho phép và thay dòng dưới bằng đường
   dẫn chia sẻ đã kiểm tra quyền truy cập.

**Video URL/path:** _chưa đính kèm — cập nhật khi có file/link bàn giao._

## 10. Checklist bàn giao

- [ ] Source firmware, TV1-19-HANDOFF và flow mới nhất đã được bàn giao.
- [ ] Build/upload `development` thành công trên board mục tiêu.
- [ ] `network_config.h` chỉ được chia sẻ riêng qua kênh bảo mật; không nằm trong
      tài liệu/video/repository.
- [ ] Pin map và yêu cầu driver/nguồn đã được kiểm tra trên mạch thật.
- [ ] Đính kèm log Serial và MQTT có timestamp, request ID và kết quả test.
- [ ] Đính kèm video hoặc link đã kiểm tra quyền truy cập.
- [ ] BE xác nhận chấp nhận QoS 0 cho ACK hoặc ghi rõ yêu cầu thay đổi trước khi
      công bố giao nhận QoS 1.
- [ ] TV1-18 được tổng kết PASS/BLOCKED theo tiêu chí tại mục 8 của tài liệu này.
