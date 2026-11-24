# Giao thức dữ liệu Edge AI và lưu trữ Video sự kiện

Tài liệu mô tả cấu trúc trao đổi bản tin MQTT giữa Vision Node (`edge-ai`) và FastAPI Backend (`backend`), cơ chế biên nhận chống lưu trùng và quy trình tải/phát video sự kiện cảnh báo.

---

## 1. Luồng bản tin MQTT và biên nhận lưu trữ (`Storage ACK`)

Vision Node phát dữ liệu lên ba nhánh topic theo mã định danh riêng:
- `driver/{device_code}/telemetry`: Số đo định kỳ mỗi giây (`ear`, `perclos`, `driver_state`, `head_pose`, `model_version` và đối tượng mở rộng `ai_signals`).
- `driver/{device_code}/events`: Các sự kiện nghiệp vụ kèm `policy_version`, `session_id`, `sequence_number`, `episode_id`, `level` và `state_duration_ms`.
- `driver/{device_code}/status`: Trạng thái kết nối và thông tin phiên làm việc của tiến trình AI.

### Các loại sự kiện AI chính

| Mã sự kiện (`event_type`) | Ý nghĩa và cách Backend xử lý |
|---|---|
| `STATE_CHANGED` | Ghi nhận thời điểm chuyển đổi trạng thái tài xế vào lịch sử/timeline |
| `DROWSY_THRESHOLD_REACHED` | Sự kiện buồn ngủ chạm mốc thời gian 3s/6s/10s; đưa vào Rule Engine xét tạo cảnh báo và phát lệnh ESP32 |
| `DISTRACTED_THRESHOLD_REACHED` | Sự kiện mất tập trung chạm mốc thời gian cảnh báo theo policy `driver-bench-20261107-v1` |
| `RISK_SUSPENDED` | Tài xế hồi phục hoặc ngắt đợt nguy cơ hiện tại; hủy các phần lệnh tự động đang xếp hàng chưa gửi |
| `MONITORING_FAULT` | Lỗi thiếu góc quan sát kéo dài (`UNKNOWN ≥ 2 giây`); ghi nhận riêng, không quy thành buồn ngủ |
| `SESSION_ENDED` | Đóng phiên giám sát hiện tại và dọn các lệnh chờ thuộc phiên đó |

### Cơ chế chống trùng và xác nhận lưu DB
1. Trước khi phát MQTT, Edge AI lưu bản tin bất biến vào hàng đợi SQLite kèm khóa `message_id` và mã băm nội dung.
2. Backend ghi dữ liệu cùng bản ghi biên nhận vào bảng `ai_message_receipts` trong một giao dịch (transaction) duy nhất. Sau khi `COMMIT` thành công, Backend mới phản hồi lên `driver/{device_code}/storage_ack`:
   ```json
   { "message_id": "...", "status": "SAVED" }
   ```
3. Chỉ khi nhận được phản hồi `SAVED` khớp đúng `message_id`, Edge AI mới xóa bản tin khỏi SQLite. Nếu gửi lặp cùng `message_id` và nội dung, Backend trả lại `SAVED` mà không tạo bản ghi trùng.

---

## 2. Quy trình tải lên và phát Video sự kiện

### 2.1. Tải clip từ Edge AI lên Backend
- Worker nền tại Edge gửi yêu cầu ` multipart/form-data` tới `POST /api/videos/upload` gồm tệp `.mp4`, `device_code`, `state` và `message_id` định danh clip.
- **Xác thực thiết bị:** Endpoint yêu cầu HTTP Basic Auth bằng chính cặp tài khoản/mật khẩu MQTT của Vision Node đó.
- Backend kiểm tra dung lượng kho lưu trữ (`AI_VIDEO_TOTAL_MAX_BYTES`), lưu tệp vào Docker volume `video_data`, ghi metadata/SHA-256 vào bảng `ai_videos` và phản hồi `SAVED` để Edge dọn tệp tạm cục bộ.
- Clip được ghép chính xác với sự kiện và cảnh báo thông qua mã `clip_message_id` / `episode_start_event_id` (tuyệt đối không ghép đại theo khoảng thời gian gần đúng).

### 2.2. Xem và quản lý Video trên trình duyệt
- Người dùng mở clip từ trang **Cảnh báo → Xem video** hoặc tab **Diễn biến** của thiết bị (mọi bước đều kiểm tra JWT và quyền truy cập trên camera nguồn).
- Để tương thích mọi trình duyệt, `POST /api/videos/{id}/playback` chuyển mã nền sang định dạng chuẩn **H.264/MP4** (tối đa `1280×720`) qua FFmpeg, đồng thời vẫn giữ nút **Tải video gốc** qua `GET /api/videos/{id}/content`.
- Khi người có quyền (`Admin` / `Employee`) thực hiện xóa thủ công qua `DELETE /api/videos/{id}`, hệ thống xóa tệp vật lý và giữ dấu thời gian `deleted_at` (tombstone) để ngăn tác vụ gửi lại làm xuất hiện lại clip đã xóa.
