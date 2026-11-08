# Bản nộp và nghiệm thu cuối — 08/11/2026

## Phạm vi đã chốt với TV3

- Model học máy phân loại buồn ngủ nhị phân; quy tắc hướng đầu tạo DISTRACTED. UNKNOWN thể hiện thiếu quan sát. Không gọi đây là model học máy ba lớp.
- Giữ artifact đã đánh giá làm mốc đối chiếu. Ca camera thật ngày 08/11 phát hiện báo nhầm DROWSY khi mở mắt; **chưa nghiệm thu model**. Thử nghiệm sửa lỗi phải ở thư mục riêng, giữ kết quả cũ và kiểm tra lại trước khi thay artifact. DMD thuộc hướng phát triển.
- Policy `driver-bench-20261107-v1`: ngưỡng 3/6/10 giây, tải mức 1 LED+còi, mức 2/3 cả ba tải; thời lượng 1/2/3 giây. Mức 3 nhắc lại 5 giây với quan sát mới và kiểm soát dispatch đang chờ. ATTENTIVE ổn định 2 giây kết thúc đợt. UNKNOWN là lỗi giám sát riêng. Không áp dụng cooldown 30 giây cho luồng này.
- Video trên Backend chỉ xóa thủ công. Có dung lượng và cảnh báo đầy; clip Edge chưa SAVED không được tự xóa. Dọn bản sao cục bộ sau SAVED là bước hoàn tất upload, không phải tác vụ xóa lịch sử Backend.
- Đồng hồ LAN: Docker chrony trên laptop, ESP32 hỏi giờ laptop qua UDP 123. Không tự đổi Windows Firewall.

## Đối chiếu yêu cầu giảng viên

Nguồn: **ĐỀ BÀI ĐỒ ÁN KẾT THÚC HỌC PHẦN.pdf**, bản người dùng cung cấp trong Downloads. Các kết quả thiết bị thật phải do nhóm điền sau nghiệm thu.

| Nội dung | Phần triển khai / minh chứng | Điều kiện kết luận hoàn thành |
|---|---|---|
| Node vật lý, cảm biến, cơ cấu chấp hành | Webcam + laptop Vision; firmware ESP32 điều khiển LED/còi/rung | Có ESP32 thật, video chạy tải và sơ đồ đúng mạch |
| Khuyến nghị từ hai node cho nhóm 4 người | Vision Node và Alert Node có mã, credential và vai trò riêng | Trình bày rõ Vision là laptop; không khẳng định có hai ESP32 |
| Backend và giao diện tự xây | FastAPI, React, PostgreSQL, MQTT/WebSocket | Chạy demo quản lý bằng React; Grafana chỉ theo dõi vận hành |
| Tài khoản, đăng nhập/đăng xuất, hồ sơ/mật khẩu, trạng thái | `/register`, `/login`, `/logout`, `/me`, `/me/password`; Admin tạo/khóa/đổi vai trò | Kiểm thử API và thao tác giao diện |
| Phân quyền | Admin toàn hệ thống; Employee thao tác thiết bị được gán; Customer xem thiết bị được gán | Test từ chối API, WebSocket và MQTT trái quyền |
| Vòng đời và thu hồi | REGISTERED → PROVISIONED → ACTIVE ↔ MAINTENANCE → DECOMMISSIONED; thu hồi MQTT | Thiết bị đã thu hồi không kết nối lại được bằng credential cũ |
| Telemetry, đồ thị, lịch sử, cảnh báo | MQTT → DB → WebSocket → React; truy vấn lịch sử, ACK cảnh báo | Camera thật và dashboard khớp dữ liệu |
| Điều khiển/cấu hình, xác nhận | request_id, command dispatch, ACK; desired/applied config và revision | Kiểm tra config lưu NVS, khởi động lại và chống trùng trên board |
| AI nâng cao | NTHU + đặc trưng thời gian + RF/SVM + baseline | Báo cáo CV đúng phạm vi; bổ sung người/camera mới và độ trễ thực |
| Hoạt động LAN khi mất Internet | Broker/BE/DB cục bộ; giờ LAN; âm thanh AI độc lập | Tắt Internet vẫn giữ Wi-Fi LAN, khởi động ESP32 và thử tải |
| Mất broker/BE | SQLite gửi bù, HTTP upload nền, TTL và backfill không bật tải cũ | Quan sát local audio thật, reconnect và không có cảnh báo muộn |
| Bảo mật, dữ liệu riêng | Hash, JWT thu hồi phiên, ACL, secret ngoài Git, audit, quyền video; có cổng HTTPS xác minh CA | MQTT trong LAN chưa TLS; browser cần trust CA hợp lệ để dùng HTTPS |
| Triển khai | Docker Compose; migration cộng thêm; backup trước nâng cấp | Build và smoke test dịch vụ; thử phục hồi trên DB tạm |
| Monitoring/CI | Prometheus/Grafana phụ trợ; workflow kiểm thử/build | Chỉ ghi CI đạt khi có run GitHub thành công; không dùng dashboard Grafana thay React |
| Báo cáo, slide, minh chứng, release | Tài liệu kiến trúc, hardware, runbook, bảng nghiệm thu | Nhóm bổ sung ảnh thực tế, tên thành viên, kết quả thử; chốt tag sau nghiệm thu |

## Các bước chạy và demo

Xem [runbook](final-runbook.md), [kiến trúc và bảo mật](final-architecture-security.md), [phần cứng](../hardware/README.md), [kịch bản nghiệm thu](../tests/final-acceptance.md).

Không thay các kết quả camera/loa/ESP32 thật bằng test dùng ESP32 giả lập. Không đổi ngưỡng policy chỉ để demo đạt.
