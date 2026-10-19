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

Gửi định kỳ mỗi giây, chứa trạng thái người lái và các thông số nhận diện khuôn mặt, mắt, hướng đầu. Khi không phát hiện khuôn mặt hoặc không tính được thông số, các trường tương ứng có thể nhận giá trị `null`.

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
  "state": "DISTRACTED",
  "previous_state_duration_ms": 5000
}
```

Gửi khi trạng thái đã xác nhận thay đổi. `previous_state_duration_ms` biểu thị thời gian duy trì trạng thái trước đó.

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

Gửi một lần khi trạng thái `DROWSY` được duy trì liên tục đủ 3 giây.

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

Gửi một lần khi trạng thái `DISTRACTED` được duy trì liên tục đủ 3 giây.

## 5. DEVICE_STATUS – ONLINE

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

Gửi khi Edge AI kết nối MQTT Broker thành công. Message được publish với QoS 1 và `retain=true`.

## 6. DEVICE_STATUS – OFFLINE

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

Được gửi chủ động khi chương trình đóng kết nối bình thường. Nếu kết nối bị mất bất thường, MQTT Broker có thể phát Last Will với trạng thái `OFFLINE`.

## 7. DEVICE_STATUS – CAMERA_ERROR

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

Thông báo lỗi camera khi không đọc được frame liên tiếp quá số lần cho phép. Trong code hiện tại, message này chỉ được gửi nếu MQTT client đang kết nối.

## 8. BACKEND ACK – SAVED

**TOPIC:** `ACK_TOPIC`

**PAYLOAD:**
```json
{
  "message_id": "uuid-telemetry-001",
  "status": "SAVED"
}
```

Backend gửi ACK sau khi lưu message thành công. Edge AI sử dụng `message_id` để xác định message tương ứng trong hàng đợi SQLite và xóa message đã được xác nhận.

## 9. BACKEND ACK – FAILED

**TOPIC:** `ACK_TOPIC`

**PAYLOAD:**
```json
{
  "message_id": "uuid-event-001",
  "status": "FAILED"
}
```

Payload minh họa cho trường hợp Backend không lưu được message. Với code hiện tại, Edge AI chỉ ghi log cảnh báo và giữ message trong SQLite; chưa có cơ chế xử lý lỗi chi tiết theo nguyên nhân.

---

## Tổng hợp

| Payload | Topic | Thời điểm gửi |
|---|---|---|
| TELEMETRY | `TELEMETRY_TOPIC` | Định kỳ mỗi giây |
| STATE_CHANGED | `EVENT_TOPIC` | Khi trạng thái xác nhận thay đổi |
| DROWSY_THRESHOLD_REACHED | `EVENT_TOPIC` | Duy trì DROWSY đủ 3 giây |
| DISTRACTED_THRESHOLD_REACHED | `EVENT_TOPIC` | Duy trì DISTRACTED đủ 3 giây |
| ONLINE | `STATUS_TOPIC` | MQTT kết nối thành công |
| OFFLINE | `STATUS_TOPIC` | Đóng kết nối bình thường hoặc Last Will |
| CAMERA_ERROR | `STATUS_TOPIC` | Camera lỗi liên tiếp quá giới hạn |
| ACK – SAVED | `ACK_TOPIC` | Backend xác nhận lưu thành công |
| ACK – FAILED | `ACK_TOPIC` | Backend từ chối hoặc không lưu được message |

**Lưu ý triển khai:** Các giá trị `device_code`, `model_version`, UUID và timestamp trong tài liệu chỉ là ví dụ. Khi chạy thực tế, chúng được lấy từ cấu hình và sinh động. Tên topic chính xác phụ thuộc vào các biến trong `config.py`. ACK ứng dụng cần được phân biệt với MQTT PUBACK: PUBACK xác nhận việc nhận message ở tầng MQTT, còn ACK `SAVED` xác nhận Backend đã lưu dữ liệu.