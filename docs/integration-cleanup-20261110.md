# Bản tích hợp và dọn code ngày 10/11/2026

## Phạm vi

Đã hợp nhất các commit của nhóm trên `origin/main`: `d7f44a1`, `4ba9c06`, `ce933de` với AI mắt/miệng v2 và cảnh báo cúi đầu.

- Giữ dữ liệu mẫu, tài khoản/phân công thiết bị và MQTT username mà thành viên nhóm vừa sửa. Seed chỉ áp dụng khi tạo DB mới; không nạp lại vào DB đang dùng.
- Giữ sửa giao diện thống kê rỗng và nút clip liên kết. Gộp thêm cách gắn response với thiết bị/tab/bộ lọc để tránh dùng kết quả cũ khi đổi tab.
- PostgreSQL host mặc định 5433 theo bản nhóm; `POSTGRES_PORT` cho phép giữ cổng khác trên máy đã cài. Container Backend vẫn dùng `postgres:5432`.
- Gỡ nhánh CEW, prototype binary-eye và hiệu chuẩn mắt theo tư thế cúi chưa đạt khỏi runtime, launcher và hướng dẫn chạy. Nguồn cũ được lưu riêng cục bộ trước khi dọn.
- Giữ CNN/RF v2, hiệu chuẩn mắt nhìn thẳng v5, quy tắc cúi đầu, huấn luyện/đánh giá và kiểm thử tương ứng. Backend/Frontend còn đọc trường thử nghiệm cũ để lịch sử đã lưu không lỗi.
- CI cài thêm dependency CPU của AI v2 để kiểm thử nhánh suy luận. Bộ kiểm tra DB bổ sung trường hợp seed mới rồi áp dụng migration theo thứ tự triển khai.

## Lệnh chính

```powershell
./edge-ai/run-multisignal-v2.ps1 -Demo
```

Nhìn thẳng 5 giây đầu để lấy mốc; Q thoát. Thêm `-Check` kiểm tra model/profile mà không mở camera/mạng. `-EyeTrial` và `-HeadTrial` là các lượt kiểm tra riêng không gửi MQTT/HTTP/ESP32; điều kiện kính mặc định dùng cùng profile đã kiểm tra trên laptop hiện tại.

Trên máy khác cần nhận bundle/model tin cậy và profile phù hợp riêng. Git không chứa dataset, trọng số, video, mật khẩu hoặc profile cá nhân.

## Kết quả kiểm tra sau khi gộp

| Phần | Kết quả |
|---|---|
| AI | 168 kiểm thử đạt; kiểm tra thêm đường nạp multisignal đạt |
| Backend | 93 đạt, 68 bỏ qua ở lượt unit vì cần môi trường riêng |
| Frontend | 79 kiểm thử đạt, build Vite đạt |
| Trình duyệt Edge | Snapshot/WebSocket v1/v2, tín hiệu cúi, mất mặt, đổi tab thống kê và clip liên kết đạt; dùng API giả lập |
| PostgreSQL + MQTT + HTTP riêng | 5 ca luồng mới, 36 ca hồi quy và 12 ca core đạt |
| Khởi động lại Backend trong Docker riêng | 1 ca persistence/WebSocket/ACK đạt |
| DB mới | `create.sql` + seed của nhóm + migration chạy được; kiểm tra tài khoản, node, MQTT username, gán thiết bị và loại lệnh đạt |
| Firmware ESP32 | Build `development` đạt; RAM 14,4%, flash 60,5% |
| Compose | Cấu hình chính, monitoring và TLS hợp lệ; image Backend/Frontend build đạt |
| Bản đang phục vụ | Đã cập nhật Backend/Frontend, kiểm tra schema API và asset web đạt |

Lệnh demo và thử mắt riêng đều nạp runtime `eye-mouth-v2-posture-e22b141325835ab9`, ngưỡng guard kính khoảng 0,250258 và bật quy tắc cúi. Không thay trọng số hoặc ngưỡng sau khi dọn.

## Đối chiếu DB thật và giới hạn

Đọc DB thật lúc khoảng 23:01 ngày 10/11 theo giờ Việt Nam: `alert-01` ONLINE, binding `vision-01` → `alert-01` bật. DB có 93 bản ghi `HEAD_DOWN_RISK` của runtime trên trong lượt chạy khoảng 22:43–22:44; các lệnh 128–133 liên kết sự kiện DROWSY của runtime đó có ACK COMPLETED.

Đây là bằng chứng nhận/lưu/giao lệnh của lượt trước khi dọn. Nó không thay thế quan sát từng tải vật lý hoặc nghiệm thu một lượt camera mới sau merge. Phiên camera v5 đã kiểm tra trên một người/kính/setup; không suy ra Accuracy/F1 hoặc chất lượng trên người khác. Quy tắc cúi là cảnh báo tư thế và có thể kích hoạt khi chủ động nhìn xuống.

DB, broker, video, dataset và profile cục bộ được giữ. Bản cập nhật đang chạy chỉ thay container Backend/Frontend, không nạp lại firmware hoặc seed DB.
