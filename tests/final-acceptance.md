# Kịch bản kiểm thử tích hợp và nghiệm thu hệ thống

Tài liệu tổng hợp danh sách kiểm tra chuẩn bị trước buổi bảo vệ, kịch bản nghiệm thu 10 bước đầu-cuối và phương pháp đo các chỉ tiêu phi chức năng của hệ thống.

---

## 1. Công tác chuẩn bị trước buổi trình diễn

- **Hạ tầng & Dữ liệu:** Khởi động cụm Docker Compose (`postgres`, `mosquitto`, `backend`, `frontend`, `time-server`, `ota-gateway`), sao lưu sẵn cơ sở dữ liệu và kiểm tra dung lượng trống cho kho video.
- **Phần cứng ESP32 (`Alert Node`):** Kiểm tra chắc chắn đường nối `GND` chung, mạch đệm transistor/diode của còi và motor rung, cấp nguồn qua cáp USB truyền dữ liệu ổn định và xác nhận thiết bị gửi heartbeat `ONLINE` cùng giờ NTP hợp lệ.
- **Camera & Edge AI (`Vision Node`):** Chạy kiểm tra cấu hình bằng `./edge-ai/run-multisignal-v2.ps1 -Demo -Condition glasses -Check`, bố trí góc đặt camera thấy rõ toàn bộ khuôn mặt và cằm trong điều kiện ánh sáng ổn định.
- **Phân quyền & Liên kết:** Mở sẵn 3 phiên trình duyệt độc lập cho 3 vai trò (`Admin`, `Employee`, `Customer`); kiểm tra thiết bị thử nghiệm đã được gán cho `Employee` / `Customer` và liên kết `vision-01` → `alert-01` đã sẵn sàng trong mục **Cảnh báo tự động**.

---

## 2. Kịch bản nghiệm thu chức năng đầu-cuối (10 bước)

| Bước | Quy trình kiểm tra | Kết quả đạt yêu cầu | Minh chứng đối chiếu |
|---|---|---|---|
| **1** | Đăng nhập trên 3 vai trò `Admin`, `Employee`, `Customer` | Hiển thị đúng menu và phạm vi thao tác; đăng ký công khai chỉ tạo `Customer` | Giao diện 3 vai trò & phản hồi `/api/me` |
| **2** | Đăng ký thiết bị mới, cấp thông tin kết nối và gán người dùng | Chuyển trạng thái `REGISTERED → PROVISIONED`; sinh tài khoản MQTT riêng | Trạng thái thiết bị trên Web & bảng `devices` |
| **3** | Kết nối phần cứng và bấm **Kích hoạt** | Trạng thái quản lý `ACTIVE` và kết nối `ONLINE` hiển thị độc lập | Nhịp heartbeat, `last_seen`, phiên bản firmware |
| **4** | Kiểm tra phân quyền thao tác lệnh qua API | `Employee` gửi được lệnh trên node được gán; `Customer` gọi API nhận `HTTP 403` | Kết quả trả về trên Swagger `/docs` |
| **5** | Chạy Edge AI thu thập dữ liệu từ webcam thực tế | Số đo `EAR`, `PERCLOS`, `MAR`, tư thế đầu và biểu đồ cập nhật trực tiếp qua WebSocket | Cửa sổ camera song song với Dashboard |
| **6** | Giữ trạng thái buồn ngủ / mất tập trung qua các mốc 3s, 6s, 10s | Kích hoạt đúng tải trên ESP32 theo Mức 1/2/3, tạo cảnh báo và trả đủ `ACK COMPLETED` | Tải vật lý chạy thật + chuỗi `event → alert → command` |
| **7** | Thay đổi cấu hình nhịp bật/tắt từ xa và khởi động lại ESP32 | `desired` cập nhật trước, chuyển sang `APPLIED` sau phản hồi từ board; giữ cấu hình trong NVS | Số `revision` tăng và log Serial sau reboot |
| **8** | Mở xem video sự kiện cảnh báo và đánh dấu đã xem | Phát đúng clip liên kết với `message_id` của sự kiện; `Customer` bấm **Đánh dấu đã xem** | Trình phát video trên Web & bảng `alert_reads` |
| **9** | Thử nghiệm ngắt kết nối mạng / dừng tạm thời Broker | Edge AI tiếp tục kêu loa cục bộ và lưu vào SQLite; khi nối lại tự động đồng bộ bù mà không bật còi cũ | Số bản ghi chờ về `0` sau khi có mạng lại |
| **10** | Thực hiện cập nhật OTA (nâng cao) và **Ngừng sử dụng** thiết bị ở cuối buổi | OTA nâng phiên bản thành công (`CONFIRMED`); sau `Decommission` tài khoản MQTT cũ bị từ chối kết nối | Tiến trình OTA & log từ chối kết nối của Broker |

---

## 3. Phương pháp đo các chỉ tiêu phi chức năng

| Chỉ tiêu đánh giá | Phương pháp đo và thu thập số liệu | Ghi chú kỹ thuật |
|---|---|---|
| **Độ trễ số đo tới Dashboard** | Đối chiếu mốc thời gian `recorded_at` tại nguồn phát với thời điểm Backend lưu (`received_at`) và cập nhật giao diện (cùng đồng hồ máy chủ) | Tính trung vị (`p50`) và phân vị `p95` trên chuỗi mẫu liên tục |
| **Độ trễ thực thi lệnh điều khiển** | Tính hiệu số `completed_ack_at - created_at` trong bảng `commands` (tổng thời gian từ lúc tạo lệnh đến khi nhận đủ `ACK COMPLETED`) | Khoảng thời gian này bao gồm cả thời lượng bật tải vật lý (`duration_ms`) |
| **Tốc độ xử lý AI & Tài nguyên** | Sử dụng công cụ `ml.multisignal_benchmark` hoặc exporter Prometheus để ghi nhận thời gian xử lý mỗi mẫu (ms) và mức RAM đỉnh (`RSS`) | Tách biệt thời gian suy luận 1 khung hình (~20–22 ms trên CPU) với độ dài cửa sổ trượt 5 giây |
| **Độ tin cậy khi mất kết nối & Chống trùng** | Tạm dừng Broker trong lúc camera chạy, đối chiếu tổng số `message_id` sinh ra ở Edge với số biên nhận `SAVED` trong PostgreSQL sau khi khôi phục | Kiểm chứng cơ chế `ai_message_receipts` và `request_id` không lưu lặp hay kích tải lặp |
