# Edge AI – MQTT Payload Specification

## 1. TELEMETRY

**TOPIC:** `TELEMETRY_TOPIC`

**PAYLOAD:**
```json
{
  "message_id": "uuid-telemetry-001",
  "device_code": "EDGE_AI_001",
  "model_version": "1.0.0",
  "timestamp": "2026-10-19T15:00:00+00:00",
  "driver_state": "ATTENTIVE",
  "candidate_state": "ATTENTIVE",
  "face_detected": true,
  "ear": 0.285,
  "perclos": 0.05,
  "eyes_closed": false,
  "head_pose": {
    "yaw": 0.02,
    "pitch": -0.01,
    "roll": 1.5
  }
}
```

Gửi định kỳ mỗi giây, chứa trạng thái người lái đã xác nhận, trạng thái ứng viên và các thông số nhận diện khuôn mặt, mắt, hướng đầu.

- `driver_state`: Trạng thái đã xác nhận, thuộc `ATTENTIVE`, `DISTRACTED`, `DROWSY` hoặc `UNKNOWN`.
- `candidate_state`: Trạng thái ứng viên đang được theo dõi để xác nhận.
- `face_detected`: Có phát hiện khuôn mặt hay không.
- `ear`: Giá trị Eye Aspect Ratio trung bình của hai mắt.
- `perclos`: Tỷ lệ thời gian mắt nhắm trong cửa sổ tính toán.
- `eyes_closed`: Trạng thái mắt nhắm tại frame hiện tại.
- `head_pose`: Góc hoặc tỷ lệ ước lượng hướng đầu, gồm `yaw`, `pitch` và `roll`.

Các thông số không thể tính toán có thể nhận giá trị `null`, tùy cách triển khai hàm `publish_telemetry()`.

## 2. STATE_CHANGED

**TOPIC:** `EVENT_TOPIC`

**PAYLOAD:**
```json
{
  "message_id": "uuid-event-001",
  "sequence_number": 1,
  "device_code": "EDGE_AI_001",
  "timestamp": "2026-10-19T15:00:05+00:00",
  "event_type": "STATE_CHANGED",
  "previous_state": "ATTENTIVE",
  "state": "DISTRACTED"
}
```

Gửi khi trạng thái ứng viên đã duy trì đủ thời gian xác nhận và khác trạng thái đã xác nhận trước đó.

Các trường:
- `message_id`: UUID định danh duy nhất của event.
- `sequence_number`: Số thứ tự event trong phiên chạy Edge AI.
- `previous_state`: Trạng thái đã xác nhận trước đó; có thể là `null` khi xác nhận trạng thái lần đầu.
- `state`: Trạng thái mới được xác nhận.

**Lưu ý:** Code hiện tại không gửi trường `previous_state_duration_ms`. Backend nên tự xác định khoảng thời gian của từng trạng thái dựa trên các mốc thời gian của event, nếu cần.

## 3. DROWSY_THRESHOLD_REACHED

**TOPIC:** `EVENT_TOPIC`

**PAYLOAD:**
```json
{
  "message_id": "uuid-event-002",
  "sequence_number": 2,
  "device_code": "EDGE_AI_001",
  "timestamp": "2026-10-19T15:00:10+00:00",
  "event_type": "DROWSY_THRESHOLD_REACHED",
  "state": "DROWSY",
  "state_duration_ms": 3000
}
```

Gửi một lần khi trạng thái `DROWSY` được duy trì liên tục đủ thời gian quy định.

- `state`: Trạng thái đạt ngưỡng.
- `state_duration_ms`: Thời gian duy trì trạng thái được tính bởi Edge AI, tính bằng mili giây.

Giá trị cấu hình hiện tại: `THRESHOLD_SECONDS["DROWSY"] = 3.0`.

Thời gian chỉ được tính khi `candidate_state` và `confirmed_state` cùng là `DROWSY`. Bộ đếm được đặt lại nếu trạng thái ứng viên hoặc trạng thái xác nhận thay đổi.

## 4. DISTRACTED_THRESHOLD_REACHED

**TOPIC:** `EVENT_TOPIC`

**PAYLOAD:**
```json
{
  "message_id": "uuid-event-003",
  "sequence_number": 3,
  "device_code": "EDGE_AI_001",
  "timestamp": "2026-10-19T15:00:15+00:00",
  "event_type": "DISTRACTED_THRESHOLD_REACHED",
  "state": "DISTRACTED",
  "state_duration_ms": 3000
}
```

Gửi một lần khi trạng thái `DISTRACTED` được duy trì liên tục đủ thời gian quy định.

Giá trị cấu hình hiện tại: `THRESHOLD_SECONDS["DISTRACTED"] = 3.0`.

Điều kiện phát event và cách tính thời gian tương tự `DROWSY_THRESHOLD_REACHED`.

## 5. SESSION_ENDED

**TOPIC:** `EVENT_TOPIC`

**PAYLOAD:**
```json
{
  "message_id": "uuid-event-004",
  "sequence_number": 4,
  "device_code": "EDGE_AI_001",
  "timestamp": "2026-10-19T15:05:00+00:00",
  "event_type": "SESSION_ENDED",
  "final_state": "ATTENTIVE"
}
```

Gửi trong khối `finally` khi phiên Edge AI đã khởi tạo MQTT client thành công và chương trình bắt đầu kết thúc.

- `final_state`: Trạng thái đã xác nhận tại thời điểm kết thúc; có thể là `null` nếu chưa xác nhận được trạng thái nào.
- `sequence_number`: Số thứ tự tiếp theo trong chuỗi event của phiên chạy.

Backend có thể sử dụng event này để đóng bản ghi trạng thái người lái đang mở hoặc đánh dấu phiên giám sát đã kết thúc.

**Lưu ý:** Event này thể hiện quá trình Edge AI kết thúc, không đồng nghĩa chương trình luôn đóng bình thường. Code hiện tại chưa phân biệt nguyên nhân kết thúc như người dùng thoát, lỗi camera hay lỗi xử lý. Ngoài ra, việc gọi `publish_event()` trước `mqtt_client.close()` chưa tự đảm bảo Backend đã nhận được event; cần kiểm tra cơ chế gửi, hàng đợi offline và xác nhận publish trong implementation MQTT.

## 6. DEVICE_STATUS – ONLINE

**TOPIC:** `STATUS_TOPIC`

**PAYLOAD:**
```json
{
  "device_code": "EDGE_AI_001",
  "model_version": "1.0.0",
  "status": "ONLINE",
  "timestamp": "2026-10-19T15:00:00+00:00"
}
```

Thông báo thiết bị đang trực tuyến. Theo tài liệu cấu hình MQTT, trạng thái này được gửi khi kết nối Broker thành công, với QoS 1 và `retain=true`.

Việc gửi thực tế phụ thuộc vào implementation của `MQTTClient`.

## 7. DEVICE_STATUS – OFFLINE

**TOPIC:** `STATUS_TOPIC`

**PAYLOAD:**
```json
{
  "device_code": "EDGE_AI_001",
  "model_version": "1.0.0",
  "status": "OFFLINE",
  "timestamp": "2026-10-19T15:05:00+00:00"
}
```

Thông báo thiết bị ngoại tuyến khi chương trình đóng kết nối bình thường hoặc khi Broker phát Last Will do mất kết nối bất thường, tùy cấu hình MQTT.

**Lưu ý:** `main.py` hiện tại không trực tiếp gọi `publish_status("OFFLINE")` trong `finally`. Việc gửi trạng thái `OFFLINE` chủ động hoặc qua Last Will phụ thuộc vào `MQTTClient`.

## 8. DEVICE_STATUS – CAMERA_ERROR

**TOPIC:** `STATUS_TOPIC`

**PAYLOAD:**
```json
{
  "device_code": "EDGE_AI_001",
  "model_version": "1.0.0",
  "status": "CAMERA_ERROR",
  "timestamp": "2026-10-19T15:10:00+00:00"
}
```

Được yêu cầu gửi khi camera không đọc được frame liên tiếp đủ số lần giới hạn.

Cấu hình hiện tại:
- `MAX_CAMERA_FAILURES = 5`.
- Mỗi lần đọc frame thất bại, bộ đếm tăng lên.
- Khi bộ đếm đạt giới hạn, chương trình gọi `mqtt_client.publish_status("CAMERA_ERROR")` rồi thoát vòng lặp.

Khả năng gửi thành công phụ thuộc vào trạng thái kết nối và implementation của MQTT client.

## 9. BACKEND ACK – SAVED

**TOPIC:** `ACK_TOPIC`

**PAYLOAD:**
```json
{
  "message_id": "uuid-telemetry-001",
  "status": "SAVED"
}
```

Backend gửi ACK sau khi lưu message thành công.

Edge AI có thể dùng `message_id` để tìm message tương ứng trong hàng đợi SQLite và xóa message đã được xác nhận.

ACK này là xác nhận ở tầng ứng dụng, không phải MQTT PUBACK.

## 10. BACKEND ACK – FAILED

**TOPIC:** `ACK_TOPIC`

**PAYLOAD:**
```json
{
  "message_id": "uuid-event-001",
  "status": "FAILED"
}
```

Minh họa trường hợp Backend không lưu được message.

Cách xử lý khi nhận `FAILED`, bao gồm giữ message trong SQLite, ghi log và retry, phụ thuộc vào implementation của bộ xử lý ACK. Không nên mặc định rằng mọi lỗi đều được xử lý giống nhau nếu chưa kiểm tra code.

---

## Tổng hợp payload

| Payload | Topic | Thời điểm gửi |
|---|---|---|
| `TELEMETRY` | `TELEMETRY_TOPIC` | Định kỳ mỗi giây |
| `STATE_CHANGED` | `EVENT_TOPIC` | Khi trạng thái xác nhận thay đổi |
| `DROWSY_THRESHOLD_REACHED` | `EVENT_TOPIC` | Duy trì `DROWSY` đủ 3 giây |
| `DISTRACTED_THRESHOLD_REACHED` | `EVENT_TOPIC` | Duy trì `DISTRACTED` đủ 3 giây |
| `SESSION_ENDED` | `EVENT_TOPIC` | Khi phiên Edge AI kết thúc sau khi MQTT client được khởi tạo |
| `ONLINE` | `STATUS_TOPIC` | Khi MQTT kết nối thành công, tùy implementation |
| `OFFLINE` | `STATUS_TOPIC` | Khi đóng kết nối hoặc Broker phát Last Will |
| `CAMERA_ERROR` | `STATUS_TOPIC` | Camera lỗi liên tiếp đủ giới hạn |
| ACK – `SAVED` | `ACK_TOPIC` | Backend xác nhận lưu thành công |
| ACK – `FAILED` | `ACK_TOPIC` | Backend báo lưu thất bại |

## Lưu ý triển khai

1. `device_code`, `model_version`, UUID và timestamp trong tài liệu chỉ là giá trị minh họa; dữ liệu thực tế được lấy từ cấu hình hoặc sinh khi chạy.
2. Tên topic thực tế phụ thuộc vào các biến cấu hình như `TELEMETRY_TOPIC`, `EVENT_TOPIC`, `STATUS_TOPIC` và `ACK_TOPIC`.
3. `sequence_number` được tăng khi tạo event và có phạm vi theo phiên chạy hiện tại; code hiện tại khởi tạo lại từ `0` mỗi lần chạy.
4. `STATE_CHANGED` không chứa `previous_state_duration_ms`; Backend cần tự tính thời lượng nếu nghiệp vụ yêu cầu.
5. `SESSION_ENDED` là event ở tầng ứng dụng, khác với trạng thái MQTT `OFFLINE`. Một event báo kết thúc phiên không thay thế Last Will.
6. MQTT PUBACK xác nhận Broker nhận publish ở tầng MQTT; ACK `SAVED` xác nhận Backend xử lý và lưu message ở tầng ứng dụng.
7. Các payload ACK và DEVICE_STATUS ở trên là mẫu hợp đồng dữ liệu. Cần đối chiếu `MQTTClient`, `publish_event()`, `publish_telemetry()` và bộ xử lý ACK để xác nhận mọi trường và hành vi đều khớp với implementation thực tế.