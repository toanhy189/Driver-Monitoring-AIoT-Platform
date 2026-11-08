# Luồng ESP32 Alert Node

Gửi lệnh qua React/Backend; Backend lưu lệnh và kiểm tra quyền trước khi publish. Firmware `src/app/` nhận MQTT và phản hồi; không dùng publisher/consumer độc lập để thay luồng demo.

```mermaid
sequenceDiagram
    participant UI as React
    participant BE as FastAPI
    participant MQ as Mosquitto
    participant ESP as ESP32
    UI->>BE: POST commands, JWT
    BE->>BE: Kiểm tra quyền, lifecycle, kết nối; lưu lệnh
    BE->>MQ: driver/{code}/command
    MQ->>ESP: request_id, command, duration, TTL
    ESP->>ESP: Kiểm tra payload, giờ, hạn và request_id
    ESP->>MQ: ACKNOWLEDGED / STARTED hoặc FAILED
    ESP->>ESP: Chạy tải theo duration
    ESP->>MQ: COMPLETED hoặc INTERRUPTED / FAILED
    MQ->>BE: driver/{code}/ack
    BE->>BE: Đối chiếu request_id; cập nhật DB
    BE->>UI: command.updated qua WebSocket
```

## Command và ACK

- Command firmware: LED_ON/OFF, BUZZER_ON/OFF, MOTOR_ON/OFF.
- `TEST_ALERT` là yêu cầu cấp Backend, tách thành ba lệnh con; hoàn tất khi đủ ba COMPLETED.
- Firmware kiểm tra mã lệnh, duration/intensity, đồng hồ và expires_at_ms; lỗi gửi FAILED với nguyên nhân.
- Gửi lại cùng request_id không được chạy tải thêm lần nữa; request_id của lần cảnh báo mới phải khác.
- Luồng chạy tải dùng vòng lặp không chặn; hết duration thì tắt tải và gửi COMPLETED. Lệnh ưu tiên cao có thể ngắt lệnh đang chạy và trả INTERRUPTED.
- ACK thiết bị hiện publish QoS 0; Backend theo dõi timeout. Gửi MQTT thành công chưa chứng minh tải đã hoàn tất.

## Cấu hình và kết nối

Backend gửi config_id, revision và timings qua `driver/{code}/config/update` (retained, QoS 1). ESP32 kiểm tra, lưu NVS và trả APPLIED/REJECTED qua `config/applied`. Applied chỉ được cập nhật sau phản hồi khớp thiết bị/config_id; revision cũ không được ghi đè cấu hình mới.

Heartbeat mỗi 5 giây; khi mất Wi-Fi/MQTT, firmware thử reconnect và subscribe lại. Đồng hồ hỏi NTP ở laptop LAN trước nguồn dự phòng. Board chưa đồng bộ giờ có thể từ chối lệnh; kiểm tra Serial thay vì bỏ kiểm tra TTL.

Xem [hướng dẫn firmware](README.md) và [demo 10 bước](../../README.md#4-demo-theo-mục-84-của-đề-bài). Không thử tải trước khi xác nhận mạch.
