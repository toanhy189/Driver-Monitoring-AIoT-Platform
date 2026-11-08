# Hợp đồng dữ liệu AI và video

Nguồn triển khai: edge-ai/service/message/publisher.py, edge-ai/mqtt_client.py, backend/app/services/mqtt_service.py và backend/app/api/routes/videos.py. Policy bản nộp: driver-bench-20261107-v1.

## Bản tin MQTT

AI gửi driver/{device_code}/telemetry, events, status; nhận storage_ack. Mã trong payload phải khớp topic và Vision Node đã đăng ký. Timestamp có múi giờ; model_version gắn trước khi lưu SQLite. Retry giữ nguyên message_id/nội dung; metadata vận chuyển live/backfill nằm ngoài hash nội dung bất biến.

| Event | Xử lý |
|---|---|
| STATE_CHANGED | Lưu trạng thái/lịch sử, không tự phát lệnh tải |
| DROWSY_THRESHOLD_REACHED | Xét policy, episode, mức và điều kiện dispatch |
| DISTRACTED_THRESHOLD_REACHED | Policy v1 xét cảnh báo như thiết kế đã thống nhất; nhánh legacy có thể POLICY_PENDING |
| RISK_SUSPENDED | Ngắt đợt nguy cơ theo đúng phiên/episode |
| MONITORING_FAULT | Ghi nhận lỗi giám sát, không suy diễn là tài xế buồn ngủ |
| SESSION_ENDED | Kết thúc đúng phiên; không phát tải mới, xử lý command chưa gửi theo policy |

Event v1 mang policy_version, session_id, session_started_at, sequence_number, model_version; event threshold cần episode_id, episode_start_event_id, observed_at, level và state_duration_ms. Xem schema thực tế trong backend/app/schemas/rules.py.

BE lưu dữ liệu và receipt trong cùng giao dịch; sau commit mới gửi:

```json
{"message_id":"ID-ban-tin","status":"SAVED"}
```

Cùng ID/nội dung được xác nhận lại mà không lưu trùng; ID trùng nhưng nội dung khác bị từ chối. PUBACK của MQTT không thay SAVED. Bản tin chưa lưu hợp lệ không được xóa khỏi queue.

Rule cần cờ môi trường và binding bật, đúng loại node, thiết bị ACTIVE/ONLINE, phiên/thứ tự hợp lệ, event/quan sát còn mới và không có dispatch chưa rõ kết quả. Backfill chỉ lưu lịch sử. [Thiết kế và bảo mật](final-architecture-security.md) mô tả các kiểm soát.

## Video

POST /api/videos/upload là multipart: file MP4, device_code, state và message_id của clip. Xác thực HTTP Basic bằng credential MQTT của Vision Node; worker hiện đã gửi auth riêng cho HTTP.

Thành công trả SAVED cùng danh tính upload theo contract; Edge kiểm tra phản hồi trước khi dọn file/queue. Không coi ACK SAVED của event là thành công upload video. Lỗi mạng/401/507 giữ file và thử lại theo chính sách; quota đầy không được xóa clip pending để báo thành công.

Video ghép với event theo clip_message_id/episode_start_event_id và message_id, không đoán liên kết theo thời gian. Có thể upload trước khi event đến. GET /api/devices/{id}/events/{event_id}/video trả liên kết/trạng thái tương ứng theo quyền; GET /api/devices/{id}/videos liệt kê clip. Xem/content dùng JWT và quyền thiết bị.

Backend lưu file vào AI_VIDEO_DIR (Compose: volume video_data), DB giữ metadata/hash. Xóa thủ công bằng DELETE /api/videos/{id}, chỉ vai trò có quyền trên thiết bị; tombstone ngăn retry làm clip đã xóa xuất hiện lại. GET /api/videos/storage dành cho Admin. Không có tác vụ tự xóa video theo tuổi.

## Readiness và kiểm thử

```powershell
python backend/scripts/setup_ai_ingest.py
python backend/tests/run_week4_isolated.py --regression
```

Readiness chỉ đọc. --apply --assign-user TEN_ADMIN thực sự cập nhật migration/ACL/đăng ký Vision Node, chỉ dùng trên trạng thái đã kiểm tra; không tự đổi credential hay lifecycle node đã có để vượt lỗi.

Runner tích hợp dùng DB/broker tạm và node giả lập. Kết quả tổng hợp cuối ở [verification](final-verification.md); log theo tuần và các báo cáo tiến độ được giữ cục bộ, Git ignore. Video camera và tải ESP32 thật cần minh chứng riêng.
