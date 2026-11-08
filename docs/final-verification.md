# Kết quả kiểm tra bản hoàn thiện — 08/11/2026

Nguồn tổng hợp: [verification.json](evidence/final-20261108/verification.json). Các log chi tiết mới giữ cục bộ trong `edge-ai/ml-runs/final-completion-20261108/`; giữ nguyên kết quả ML cũ.

| Kiểm tra | Kết quả | Phạm vi |
|---|---|---|
| Backend unit | 59 đạt; 52 skip trong lần discover 111 test | Những ca cần DB/broker không chạy trong lượt unit |
| Policy live | 3 đạt | PostgreSQL/MQTT thật tạm; ESP32 giả lập |
| Hồi quy tích hợp cũ | 35 đạt, 1 skip | Ca Docker restart chưa chạy trong runner này |
| Core cuối | 11 đạt | Tài khoản, thu hồi JWT/vé, assignment, RBAC, metadata, quota và xóa video |
| Edge AI | 94 đạt | Không mở camera và không bật loa/tải |
| Frontend | 63 đạt; production build đạt | Kiểm thử Node và Vite |
| Trình duyệt thật | 5 bước đạt, không có page error | Edge headless; React/FastAPI Docker; Customer QA riêng đã khóa sau test |
| Firmware | Development build đạt | Chưa flash; người dùng yêu cầu chờ kiểm tra mạch |
| Docker | Backend/React/broker/PostgreSQL/NTP chạy | Migration cộng thêm đã áp dụng sau backup |
| Monitoring | Backend target UP; Grafana database OK | AI target DOWN do camera/exporter chưa chạy; không giả số đo |
| NTP | Probe UDP localhost đạt; offset 5,725 ms trong một mẫu | Chưa chứng minh đường Wi-Fi từ ESP32; không thay firewall |
| HTTPS | TLS 1.3, xác minh CA/hostname đạt | React 200, API yêu cầu JWT 401; chưa cài CA vào Windows |
| Backup | Restore thành công 17 bảng vào DB tạm | DB ứng dụng không bị ghi đè |
| Model bản nộp | `run-submission.ps1 -Check` đạt đúng phiên bản | Không mở camera, không nối mạng |

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

TV1 xác nhận mạch/nguồn và chuẩn bị credential trước khi flash. TV2 phối hợp node/binding/clock/ACK, TV3 kiểm thử camera+audio và người/phiên mới, TV4 quan sát React/lịch sử/video. Nhóm hoàn tất kịch bản 10 bước, clip dự phòng, ảnh mạch, nội dung báo cáo/slide và tag release sau rehearsal.

CI trên GitHub chỉ được ghi “đạt” khi kiểm tra được run của nhánh mới; build/test local không thay kết quả CI.
