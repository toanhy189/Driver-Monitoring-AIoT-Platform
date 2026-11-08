# Nghiệm thu cuối: 5–7 phút demo và các ca chuẩn bị trước

## Trước buổi demo

- Sao lưu DB; giữ riêng `.env`, credential MQTT, model và clip dự phòng. Không quay màn hình lộ secret.
- TV1 xác nhận mạch/nguồn tải, flash firmware, giờ LAN và Wi-Fi. Chỉ bật nguồn tải sau kiểm tra mạch.
- TV2 kiểm tra đúng cặp Vision → Alert, policy v1 và trạng thái ACTIVE/ONLINE; không tự bật binding chưa được nhóm chốt.
- TV3 chạy model nhị phân đã khóa, kiểm tra hiệu chuẩn nhìn thẳng, camera/âm thanh, ánh sáng và kính.
- TV4 kiểm tra đăng nhập ba vai trò, socket, đồ thị, lệnh, alert, cấu hình và trình phát video.

## Kịch bản trên giao diện

| Bước | Thao tác | Dấu hiệu đạt | Minh chứng cần ghi |
|---|---|---|---|
| 1 | Đăng nhập Admin; tạo Customer/Employee dùng thử | Người dùng mới có đúng vai trò; public register chỉ Customer | Ảnh không có mật khẩu |
| 2 | Đăng ký node demo; cấp credential; gán thiết bị | REGISTERED → PROVISIONED; tài khoản MQTT riêng | Mã node và trạng thái; che secret |
| 3 | Kết nối node rồi kích hoạt | ACTIVE và ONLINE hiển thị độc lập | Heartbeat, thời gian, firmware/hardware |
| 4 | Employee xem node được gán; Customer thử gửi lệnh | Employee đúng phạm vi; Customer bị chặn | HTTP 403/404 khi truy cập trái quyền |
| 5 | Camera nhìn thẳng, quay đầu/nhắm mắt trong điều kiện thử trên bàn | Số đo và trạng thái lên React; local audio hoạt động | Video có đồng hồ và thời điểm ground truth |
| 6 | Quan sát mức 1/2/3 và lần nhắc | Đúng tải, duration, request_id và ACK; không chỉ nhìn trạng thái publish | Ghép event_id → alert_id → command_id → ACK |
| 7 | Đổi cấu hình rồi reboot ESP32 | Desired → APPLIED; revision không lùi; NVS giữ cấu hình | Revision trước/sau, config_id, Serial |
| 8 | Xem lịch sử event và clip tương ứng; xóa một clip đã chọn | Đúng event/video; chỉ người có quyền xóa; retry không làm clip xuất hiện lại | message_id/video_id, ảnh trước/sau |
| 9 | Dừng BE/broker có kiểm soát | Camera/local audio tiếp tục; SQLite/file vẫn giữ; không bật tải cũ sau reconnect | Pending trước/sau, outcome backfill, video upload |
| 10 | Bảo trì rồi ngừng sử dụng node thử | Thu hồi credential; mất kết nối; lịch sử vẫn còn | Trạng thái quản lý và lần reconnect bị từ chối |

Để tránh mất quyền thiết bị thật, dùng node thử cho bước thu hồi; thiết bị DECOMMISSIONED không dùng làm node demo tiếp theo.

## Đo thực tế cần điền

Mỗi tổ hợp ánh sáng tốt/yếu × có/không kính: người tham gia đồng ý, có nhãn quan sát, thời lượng, model/hash, FPS, CPU/RAM, p50/p95 xử lý, false alarm và thời gian phát hiện. Tách độ trễ vòng xử lý khỏi thời gian cửa sổ model 20 giây và thời gian policy. Không dùng NME landmark thay Accuracy/F1 trạng thái.

| Ca | Ngày / người thử | Kết quả | File minh chứng / ID |
|---|---|---|---|
| Camera + audio thật | 08/11/2026; TV3, không kính | Đạt thao tác nhắm/mở mắt và quay đầu với RF ứng viên + guard hiệu chuẩn; kính chưa đạt, chưa phải accuracy | `docs/final-ai-model.md`; `verification.json`: `camera-calibrated-no-glasses` |
| Ba mức + nhắc + hồi phục | Chưa ghi | Chưa nghiệm thu | |
| UNKNOWN / mất mặt / SESSION_ENDED | Chưa ghi | Chưa nghiệm thu | |
| Mất Internet, reboot ESP32, NTP LAN | Chưa ghi | Chưa nghiệm thu | |
| Mất BE/broker, gửi bù không kích tải muộn | 08/11/2026; TV3 | Camera/loa và gửi bù đạt: 180 MQTT + 14 clip về 0; phần không kích tải muộn trên ESP32 chưa nghiệm thu (rule tắt) | `verification.json`: `real-queue-recovery` |
| Config/NVS sau reboot, lệnh trùng, TTL hết hạn | Chưa ghi | Chưa nghiệm thu | |
| Restore DB tạm | 08/11/2026 | Đạt; 17 bảng phục hồi vào DB tạm, không ghi đè DB ứng dụng | `docs/evidence/final-20261108/verification.json` |
| Phát lại demo dự phòng | Chưa ghi | Chưa nghiệm thu | |

Video dự phòng hỗ trợ trình bày khi có sự cố; không thay thế yêu cầu demo trực tiếp của giảng viên.
