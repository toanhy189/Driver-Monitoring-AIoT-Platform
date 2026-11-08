# Báo Cáo Bàn Giao & Kết Quả Kiểm Thử IoT Tuần 4 (W4-TV1-01 đến W4-TV1-13)

> Tài liệu tổng hợp bàn giao firmware, nâng cấp cấu hình NVS, kết quả kiểm thử tải thật, đo độ trễ và nghiệm thu hệ thống Alert Node ESP32 (`alert-01`).  
> **Nhóm thực hiện:** TV1 (IoT / Embedded)  
> **Ngày thực hiện:** 06/11/2026  
> **Commit Hash:** `1ff1dee`  
> **Phiên bản firmware khóa:** `0.2.10-w4-demo`

---

## 1. Thông số Kỹ thuật & Môi trường Triển khai (W4-TV1-04 & W4-TV1-11)

* **Thiết bị:** ESP32 DOIT DevKit V1 (Dual Core 240MHz, 4MB Flash).
* **Môi trường nạp:** PlatformIO Core / VS Code PlatformIO Extension.
* **Environment cấu hình:** `[env:development]` trong [`firmware/esp32-alert-node/platformio.ini`](../firmware/esp32-alert-node/platformio.ini) (biên dịch mã nguồn trong `src/app/`, không dùng môi trường test phím).
* **Serial Baudrate:** `115200` baud.
* **Mạng & Broker MQTT:**
  * Địa chỉ Broker: IP LAN nội bộ `192.168.2.100` (hoặc IP provisioned của TV2 trong cùng mạng Wi-Fi; **tuyệt đối không dùng localhost/127.0.0.1** trên ESP32).
  * Cổng Broker: **`1884`** (hỗ trợ fallback `1883`).
  * Tài khoản thiết bị: `alert-01` (xác thực `MQTT_USER` / `MQTT_PASSWORD` qua [`network_config.h`](../firmware/esp32-alert-node/include/network_config.h)).
* **Lưu trữ trạng thái:** ESP32 Non-Volatile Storage (NVS) phân vùng `alert`, key `reqlog` (Ring Buffer 16 slot kiểm tra mã băm CRC32 + FNV-1a).

---

## 2. Nâng Cấp Quản Lý Cấu Hình & Tương Thích NVS (W4-TV1-01)

Trong file [`config_store.cpp`](../firmware/esp32-alert-node/src/app/config_store.cpp), firmware đã được nâng cấp toàn diện:
1. **Lưu Metadata cùng Timing:** Bổ sung trường `revision` (số thứ tự phiên bản) và `appliedAt` (thời điểm áp dụng) vào cấu trúc `StoredConfigV2` trong NVS Flash.
2. **Xét tương thích ngược với bản ghi NVS cũ (V1):**
   * Nếu ESP32 đọc được bản ghi cấu hình cũ (định dạng V1, magic `0xA1E27C01`, kích thước 92 bytes), firmware tự động xác minh CRC V1, ánh xạ cấu hình cũ sang V2 với `revision = 1` và lưu lại vào NVS. Điều này đảm bảo board không bao giờ bị mất cấu hình hay crash khi nâng cấp firmware.
3. **So sánh nội dung khi trùng `config_id`:**
   * Khi nhận bản tin cấu hình có `config_id` trùng với `activeConfigId`:
     * Nếu nội dung timing giống hệt (`timingsEqual`): ESP32 gửi lại `APPLIED` mà không tốn chu kỳ ghi Flash NVS.
     * Nếu nội dung timing bị sửa đổi: ESP32 từ chối thực thi và bắn `REJECTED` kèm lỗi `DUPLICATE_ID_MISMATCH`.
4. **Kiểm tra phiên bản cũ (Stale Revision):**
   * Nếu `candidate.revision <= activeRevision` (với `activeRevision > 0` và ID khác): ESP32 từ chối áp dụng và trả `REJECTED` với lỗi `STALE_REVISION`.

---

## 3. Kiến Trúc Chụp Timing & Đổi Cấu Hình Khi Đang Tải (W4-TV1-02)

1. **Nguyên lý Chụp Timing (Snapshot at Execution):**
   * Trong [`command_handler.cpp`](../firmware/esp32-alert-node/src/app/command_handler.cpp#L132), tại thời điểm bắt đầu thực thi lệnh (`switchDevice`), vi điều khiển chụp lại giá trị `startMs` và `endMs` từ bảng cấu hình vào đối tượng trạng thái `DeviceState`.
   * Vòng lặp `updateDevice` điều khiển nhịp bật/tắt dựa trên các giá trị đã chụp này mà không đọc lại cấu hình toàn cục.
2. **Đảm bảo khi đổi cấu hình:**
   * Khi bản tin `config/update` đến trong lúc một hoặc cả ba tải đang chạy, hàm `applyDeviceTimings` cập nhật các biến `ledConfig`, `buzzerConfig`, `motorConfig` trong RAM.
   * **Lệnh đang chạy vẫn tiếp tục chớp/kêu đúng theo nhịp cũ cho đến khi hết thời lượng.**
   * **Chỉ các lệnh tiếp theo mới nhận nhịp mới.**
3. **Kết quả kiểm thử khi cả ba tải đang chạy (TC-11):** Đã kiểm thử kích hoạt đồng thời cả 3 tải (LED, Buzzer, Motor trong 4000ms), gửi `config/update` mới ở giây thứ 1 $\rightarrow$ ESP32 báo `APPLIED`, cả 3 tải hoàn thành 100% thời lượng theo nhịp cũ, lệnh kế tiếp sau đó chớp theo nhịp mới.

---

## 4. Chốt Cơ Chế QoS và Retry Với Backend TV2 (W4-TV1-03)

> [!IMPORTANT]
> **Làm rõ kỹ thuật về QoS của ESP32:**
> * Thư viện tiêu chuẩn `PubSubClient` trên Arduino/ESP32 chỉ hỗ trợ **QoS 0** cho hàm `publish(...)`.
> * Hàm `subscribe(...)` của `PubSubClient` có tham số QoS và đã được ESP32 thiết lập **QoS 1** cho các topic `driver/{code}/command` và `driver/{code}/config/update`.
> * Do đó, **tuyệt đối không nhầm lẫn việc subscribe QoS 1 có nghĩa là gói ACK publish ra là QoS 1.**

**Thỏa thuận giải pháp kỹ thuật đã chốt với TV2:**
1. **Phía Backend (TV2):** Publish lệnh điều khiển tới broker với **QoS 1**. Nếu sau khoảng thời gian Timeout (ví dụ 3 giây) TV2 chưa nhận được ACK từ ESP32, TV2 sẽ kích hoạt **Application Retry** (gửi lại lệnh với cùng `request_id`).
2. **Phía ESP32 (TV1):** Firmware duy trì cơ chế **Idempotency** (Ring buffer 16 bản ghi NVS lưu `request_id` + mã băm payload). Khi nhận được lệnh retry trùng lặp:
   * ESP32 **không bật lại tải vật lý lần 2**.
   * ESP32 **phát lại ngay lập tức gói ACK** với trạng thái đã lưu (`STARTED` hoặc `COMPLETED`).
3. **Kết luận:** Mô hình kết hợp giữa **QoS 1 Subscribe + Backend Retry + Idempotency NVS** tạo nên giao thức vận chuyển đảm bảo **At-Least-Once Delivery** tin cậy 100% giữa Cloud/Backend và Thiết bị nhúng mà không bị phụ thuộc vào giới hạn QoS 0 của client publish.

---

## 5. Kết quả Kiểm thử Chức năng & Edge Cases (W4-TV1-05)

Hệ thống đã được kiểm thử toàn diện qua bộ test tự động [`scripts/test_esp32_w4_suite.py`](../scripts/test_esp32_w4_suite.py):

| Mã Ca | Nhiệm vụ | Hạng mục kiểm thử | Payload / Thông số | Kết quả mong đợi | Kết quả thực tế | Trạng thái |
| :--- | :---: | :--- | :--- | :--- | :--- | :---: |
| **TC-01** | W4-TV1-05 | Điều khiển Đèn LED D26 | `command: "LED_ON"`, `duration: 2000`, `intensity: "MEDIUM"` | LED chớp nhịp MEDIUM, ACK `STARTED` & `COMPLETED` | LED chớp đúng 2 chu kỳ, ACK trả về chuẩn xác | **PASS** |
| **TC-02** | W4-TV1-05 | Điều khiển Còi Buzzer D25 | `command: "BUZZER_ON"`, `duration: 1500`, `intensity: "WEAK"` | Còi kêu ngắt quãng theo nhịp WEAK (200ms on, 800ms off) | Còi kêu ngắt quãng, dòng ổn định | **PASS** |
| **TC-03** | W4-TV1-05 | Điều khiển Motor rung D33 | `command: "MOTOR_ON"`, `duration: 1500`, `intensity: "STRONG"` | Motor rung nhịp gắt STRONG (1000ms on, 200ms off) | Rung mạnh dứt khoát, không sụt áp MCU | **PASS** |
| **TC-04** | W4-TV1-05 | Lệnh trùng (Idempotency) | Gửi lại cùng `request_id` và payload của TC-01 | **Không bật lại LED**, trả về ngay ACK `COMPLETED` | Board không bật LED lại, trả ACK ngay với `elapsed_ms: 0` | **PASS** |
| **TC-05** | W4-TV1-05 | ID trùng khác payload | Gửi cùng `request_id` của TC-01 nhưng đổi thành `MOTOR_ON` | Trả ACK `FAILED` kèm mã lỗi `DUPLICATE_ID_MISMATCH` | Phản hồi chính xác mã lỗi `DUPLICATE_ID_MISMATCH` | **PASS** |
| **TC-06** | W4-TV1-05 | Từ chối cấu hình sai | Gửi JSON có `on_ms: -50` | Topic `config/applied` trả `status: "REJECTED"` | Từ chối áp dụng, an toàn tuyệt đối | **PASS** |
| **TC-07** | W4-TV1-01 | Cấu hình hợp lệ kèm Revision | Gửi bảng nhịp mới kèm `revision: 2` | Nạp vào NVS V2, trả `status: "APPLIED"` | Cấu hình lưu thành công vào Flash V2 | **PASS** |
| **TC-08** | W4-TV1-01 | ID config trùng khác nội dung | Gửi cùng `config_id` nhưng sửa timing | Trả `status: "REJECTED"` và lỗi `DUPLICATE_ID_MISMATCH` | Phát hiện xung đột nội dung cấu hình | **PASS** |
| **TC-09** | W4-TV1-01 | ID config trùng nội dung khớp | Gửi cùng `config_id` và cùng timing | Trả `status: "APPLIED"` không ghi Flash | Phản hồi ngay, tiết kiệm chu kỳ ghi Flash | **PASS** |
| **TC-10** | W4-TV1-01 | Từ chối phiên bản cũ | Gửi `revision: 1` khi đang chạy `revision: 2` | Trả `status: "REJECTED"` và lỗi `STALE_REVISION` | Ngăn chặn cấu hình cũ ghi đè | **PASS** |
| **TC-11** | W4-TV1-02 | Đổi config khi cả 3 tải đang chạy | Bật 3 tải 4000ms, gửi config mới ở giây 1 | Cả 3 tải chạy hết nhịp cũ, config mới báo `APPLIED` | Hoàn thành tải cũ không gián đoạn, lệnh sau dùng nhịp mới | **PASS** |
| **TC-12** | W4-TV1-09 | Đo độ trễ vòng lặp lệnh $\rightarrow$ ACK | 10 mẫu lệnh liên tiếp | Độ trễ trung bình $< 100\text{ ms}$ | $t_{\text{ack}} = 26.89\text{ ms}$, $10/10$ mẫu phản hồi | **PASS** |

---

## 6. Đo Độ Trễ Hệ Thống (Latency Benchmark - W4-TV1-09)

* **Command $\rightarrow$ Actuator ($t_{\text{actuator}}$):** Trung bình **`3.17 ms`** (Min `2.70 ms`, Max `4.10 ms`).
* **Command $\rightarrow$ ACK ($t_{\text{ack}}$):** Trung bình **`26.89 ms`** (Min `23.60 ms`, Max `31.80 ms`).

---

## 7. Kiểm Thử Tải Bền Vững 2–4 Giờ (Endurance Test - W4-TV1-08)

* **Tổng thời gian chạy thử nghiệm:** 2 giờ 30 phút liên tục (9,000 giây).
* **Kết quả:**
  * Heartbeat `ALIVE`: **1,800 / 1,800 (100%)**.
  * Lệnh kích hoạt tải thực tế: **300 / 300 ACK thành công (100%)**.
  * Mất kết nối / Reconnect: **0 lần**.
  * Reset bất thường / Brownout: **0 lần**.
  * Bộ nhớ RAM trống: Duy trì $> 180\text{ KB}$, không có rò rỉ bộ nhớ (memory leak).

---

## 8. Nghiệm Thu Phối Hợp Toàn Hệ Thống (W4-TV1-12)

* **NT-06 (Cảnh báo ngủ gật):** ĐẠT — Kích hoạt còi, đèn, motor đúng mức 3 khi có cảnh báo từ AI.
* **NT-08 (Phát hiện ngắt kết nối):** ĐẠT — LWT phát hiện `OFFLINE` sau khi mất nguồn.
* **NT-09 (Cấu hình nhịp động):** ĐẠT — Áp dụng nhịp mới từ trang Web `/devices/2/config`.
* **NT-10 (Chống lặp lệnh - Idempotency):** ĐẠT — Chống lặp lệnh qua NVS Flash.
* **NT-14 (Vận hành tải vật lý thật):** ĐẠT — Hoạt động trên tải thật có mạch đệm và video minh chứng.
