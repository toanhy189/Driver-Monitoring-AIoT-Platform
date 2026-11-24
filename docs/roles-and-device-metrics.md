# Phân quyền vai trò, trạng thái đã xem và tổng hợp biểu đồ

Tài liệu mô tả chi tiết mô hình phân quyền 3 vai trò, cơ chế lưu trạng thái xác nhận đã xem cảnh báo theo từng cá nhân, cách liên kết thống kê lệnh giữa Camera–ESP32 và thuật toán tổng hợp dữ liệu biểu đồ.

---

## 1. Mô hình vai trò và phạm vi truy cập

- **Admin:** Đại diện quản trị viên hệ thống, có quyền giám sát toàn bộ thiết bị, quản lý tài khoản, gán thiết bị, điều khiển vòng đời, cấu hình liên kết tự động và quản lý Firmware OTA. Hệ thống duy trì một tài khoản Admin duy nhất thông qua ràng buộc chỉ mục `users_single_admin_idx` ở tầng cơ sở dữ liệu (có công cụ khôi phục khẩn cấp qua terminal máy chủ tại `backend/scripts/recover_admin.py`).
- **Employee:** Nhân viên điều hành vận tải, truy cập các thiết bị được gán trong bảng `user_devices`; có quyền gửi lệnh kiểm tra cảnh báo, chỉnh cấu hình nhịp tải, xóa video và xác nhận cảnh báo.
- **Customer:** Người dùng cá nhân / tài xế, truy cập ở chế độ xem đối với các thiết bị được gán (xem trực tiếp số đo, biểu đồ, cấu hình hiện tại, phát video cảnh báo) và đánh dấu đã xem cảnh báo của riêng mình.

> **Lưu ý tách biệt hai loại liên kết:** Bảng `user_devices` quy định **người dùng nào được phép truy cập thiết bị nào**, còn bảng `rule_bindings` quy định **Camera nào điều khiển ESP32 nào**. Việc Admin ghép một Camera với một ESP32 không tự động mở rộng quyền xem thiết bị của Customer.

---

## 2. Trạng thái "Đã xem" theo từng tài khoản (`alert_reads`)

- Bảng `alert_reads` lưu khóa chính ghép `(alert_id, user_id)` kèm thời điểm `acknowledged_at`.
- Khi một người dùng bấm **Đánh dấu đã xem**, thao tác này chỉ ghi nhận riêng cho tài khoản đang đăng nhập:
  - Không làm thay đổi trạng thái đã xem của các tài khoản khác cùng theo dõi thiết bị.
  - Không thay đổi trạng thái diễn biến gốc của đợt cảnh báo (`system_status`: đang diễn ra / đã kết thúc) và không can thiệp vào lệnh hay phản hồi `ACK` trên mạch ESP32.

---

## 3. Liên kết cảnh báo, lịch sử lệnh và độ trễ

- Một cảnh báo sinh ra từ Camera (`VISION_NODE`) liên kết tới lệnh phát ra trên mạch ESP32 (`ALERT_NODE`) qua khóa ngoại `commands.alert_id → alerts.id`. Nhờ liên kết trực tiếp này, lịch sử vẫn tra cứu chính xác ngay cả khi sau đó Admin đổi sang ghép Camera với một chiếc ESP32 khác.
- Khi bấm **Xem lệnh** tại một dòng cảnh báo, giao diện mở lịch sử theo `GET /api/commands?device_id=...&alert_id=...` (yêu cầu người dùng có quyền xem cả thiết bị nguồn và thiết bị nhận).
- **Phân loại trạng thái hủy lệnh chờ (`cancellation_status`):**
  - `CANCELLED`: Toàn bộ đầu ra bị hủy ngay trong hàng đợi (do đợt nguy cơ đã kết thúc sớm) trước khi phát MQTT.
  - `PARTIALLY_CANCELLED`: Một phần lệnh con đã gửi đi, các phần chưa gửi còn lại được hủy an toàn.
- **Hai chỉ số thời gian trong thống kê:**
  - `http_duration_ms`: Thời gian Backend xử lý yêu cầu HTTP đối với các lệnh gửi thủ công từ giao diện Web.
  - Thời gian hoàn tất lệnh: Hiệu số `completed_ack_at - created_at`, phản ánh trọn vẹn chu trình từ lúc phát sinh lệnh đến khi thiết bị bật tải xong và trả đủ `ACK COMPLETED`.

---

## 4. Tổng hợp dữ liệu biểu đồ (`chart=true`)

Endpoint `GET /api/{device_id}/telemetry/history?chart=true` trả về dữ liệu đã được gom nhóm thông minh theo khoảng thời gian để biểu đồ hiển thị mượt mà trên khoảng lịch sử dài:
- `total_samples`: Tổng số bản ghi thực tế trong khung thời gian lọc.
- `chart_points`: Tối đa **200 điểm chia khoảng (buckets)** (hoặc giữ nguyên điểm gốc nếu tổng mẫu `≤ 200`), mỗi khoảng chứa giá trị trung bình (`avg`), nhỏ nhất (`min`) và lớn nhất (`max`) của `EAR`, `PERCLOS`, `MAR`.
- `timeline_segments`: Tối đa **60 đoạn trạng thái liên tiếp** gần nhất (tự động ngắt đoạn nếu khoảng cách giữa hai mẫu vượt quá 5 giây).
- Giao diện vẽ đường trung bình kèm dải biên độ mờ `min–max` và ghép nối liền mạch các mẫu mới đến từ WebSocket dựa trên mốc `snapshot_at`.
