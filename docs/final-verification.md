# Kết quả kiểm tra bản hoàn thiện — 08/11/2026

Nguồn tổng hợp: [verification.json](evidence/final-20261108/verification.json). Các log chi tiết mới giữ cục bộ trong `edge-ai/ml-runs/final-completion-20261108/`; giữ nguyên kết quả ML cũ.

| Kiểm tra | Kết quả | Phạm vi |
|---|---|---|
| Backend unit | 60 đạt; 52 skip trong lần discover 112 test trên CI | Những ca cần DB/broker không chạy trong lượt unit |
| Policy live | 3 đạt | PostgreSQL/MQTT thật tạm; ESP32 giả lập |
| Hồi quy tích hợp cũ | 35 đạt, 1 skip trong lượt regression; ca skip đã chạy riêng và đạt | Docker restart, WebSocket và persistence đạt trong container tạm |
| Core cuối | 11 đạt | Tài khoản, thu hồi JWT/vé, assignment, RBAC, metadata, quota và xóa video |
| Edge AI | 110 đạt sau công cụ hiệu chuẩn | Gồm 9 ca kiểm tra hiệu chuẩn và hủy/kiểm tra riêng; test không mở camera và không bật loa/tải |
| Frontend | 63 đạt; production build đạt | Kiểm thử Node và Vite |
| Trình duyệt thật | 6 bước đạt, không có page error | Đã kiểm tra hồ sơ cập nhật khi mở lại form; Customer QA riêng đã khóa sau test |
| Firmware | Development build đạt | Chưa flash; người dùng yêu cầu chờ kiểm tra mạch |
| Docker | Backend/React/broker/PostgreSQL/NTP chạy | Migration cộng thêm đã áp dụng sau backup |
| Monitoring | Backend và AI target UP trong lúc camera chạy; Grafana database OK | AI exporter bind loopback; camera dừng và dữ liệu quá hạn thì AI target DOWN là đúng |
| NTP | Probe UDP localhost đạt; offset 5,725 ms trong một mẫu | Chưa chứng minh đường Wi-Fi từ ESP32; không thay firewall |
| HTTPS | TLS 1.3, xác minh CA/hostname đạt | React 200, API yêu cầu JWT 401; chưa cài CA vào Windows |
| Backup | Restore thành công 17 bảng vào DB tạm | DB ứng dụng không bị ghi đè |
| Tính toàn vẹn model | `run-submission.ps1 -Check` đạt đúng phiên bản | Chỉ kiểm tra nạp artifact, không chứng minh độ chính xác |
| Camera thật | RF đối chiếu **chưa đạt**: người dùng mở mắt nhưng vẫn báo DROWSY | Có log score/đặc trưng; xem [chẩn đoán](ai-camera-review-20261108.md) |
| Hiệu năng camera | FPS trung vị 28,85; RSS đỉnh khoảng 360,8 MiB | 37 snapshot trong một phiên tại laptop này; estimator p95 khoảng 89,39 ms, khác thời gian chờ cửa sổ 20 giây |
| Upload video | Có upload HTTPS thành công và xóa mục queue sau phản hồi hợp lệ | Clip giữ riêng trên máy; không phải minh chứng chất lượng AI |
| Chẩn đoán ML | 18 test ML mechanics đạt sau bổ sung score/feature diagnostics | Là một phần của bộ AI, không cộng thành 18 test mới |
| CI GitHub | Đủ 6 job đạt trên `58853cb` | [Run 42450603218](https://github.com/toanhy189/Driver-Monitoring-AIoT-Platform/actions/runs/42450603218); phần hiệu chuẩn sau đó cần run riêng |
| Hiệu chuẩn mắt thật | Có kính bị từ chối; không kính có thể thử tiếp sau phân tích lại v2 | Chỉ số mắt, không phải metrics DROWSY; báo cáo cũ và dữ liệu giữ riêng |

Không cộng các lượt unit/integration thành một con số “test duy nhất” vì chúng có thể chạy lại cùng chức năng ở lớp khác nhau. Không dùng kiểm thử giả lập để tuyên bố phần tải vật lý hoặc chất lượng AI trên người mới đã đạt.

## Những thay đổi có thể ảnh hưởng cách dùng

- Đăng xuất hoặc đổi mật khẩu thu hồi các phiên JWT hiện tại của tài khoản. Khóa/đổi vai trò cũng làm phiên cũ hết hiệu lực.
- Admin xem và nhận realtime toàn hệ thống; Employee/Customer tiếp tục chịu assignment. Không tự tạo schema company/tenant.
- Public register vẫn chỉ tạo Customer. Admin có API/UI tạo tài khoản theo vai trò và quản lý assignment.
- Backend có thể trả 507 khi kho video đầy. Không tự xóa lịch sử; Edge giữ file chưa SAVED và thử lại.
- Xóa thủ công tạo tombstone; upload retry cùng message_id không khôi phục clip đã xóa.
- Firmware mới có revision cấu hình và đọc lại định dạng NVS cũ; hành vi reboot thực cần TV1 nghiệm thu.
- NTP thêm cổng UDP 123 theo chấp thuận của người dùng. Monitoring chỉ bind loopback. HTTPS thử nghiệm thêm cổng 8443; không đổi Windows trust/firewall.

## Công việc nhóm còn cần làm

TV1 xác nhận mạch/nguồn và chuẩn bị credential trước khi flash. TV2 phối hợp node/binding/clock/ACK, TV3 xử lý lỗi nhận biết trên camera, kiểm tra ứng viên và xác nhận audio; TV4 quan sát React/lịch sử/video. Nhóm hoàn tất kịch bản 10 bước, clip dự phòng, ảnh mạch, nội dung báo cáo/slide và tag release sau rehearsal.

CI trên GitHub chỉ được ghi “đạt” khi kiểm tra được run của nhánh mới; build/test local không thay kết quả CI.
