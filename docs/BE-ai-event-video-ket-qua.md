# Kết quả BE nhận event và video AI — 21/10/2026

Nhánh `feature/backend-ai-events-video`, dựa trên main `fd107db`. TV3 đã tách
publisher/video worker, bỏ main2.py và thêm SESSION_ENDED. BE cập nhật theo code
mới này; giữ nguyên source AI, FE và firmware.

## Thay đổi

- Nhận/lưu SESSION_ENDED và final_state, xác nhận SAVED; không tạo cảnh báo/lệnh.
- Giữ giao dịch event + receipt, chống trùng và chẩn đoán lỗi theo nguyên nhân.
- Thêm API upload MP4 có xác thực tài khoản MQTT của Vision Node; chống trùng theo
  device/message_id, giới hạn dung lượng, hash, dọn file khi commit lỗi, quyền đọc
  theo thiết bị được gán. Video có thể đến trước event; không công khai thư mục lưu.
- Thêm migration_ai_videos.sql, volume video_data và công cụ setup_ai_ingest.py.
- Công cụ setup được thử chạy lại hai lần; không đổi mật khẩu hoặc tạo trùng quyền gán.

Hợp đồng request/response, mã lỗi, luồng lưu file và hướng dẫn TV3:
[ai-ingest-video-contract.md](ai-ingest-video-contract.md).

## Minh chứng kiểm tra

| Kiểm tra | Kết quả và minh chứng |
|---|---|
| BE unit | **34 đạt**, 27 ca tích hợp bỏ qua có chủ đích trong unit discovery; [unit-output.txt](evidence/week3/unit-output.txt) |
| Tích hợp PostgreSQL/MQTT/HTTP/WS thật | **26/26 đạt, không bỏ qua**; [integration-results.json](evidence/week3/integration-results.json), [output](evidence/week3/integration-output.txt) |
| Quyền MQTT | **1/1 đạt** trên broker thử riêng; [acl-results.json](evidence/week3/acl-results.json) |
| AI thực tế không mở camera | main.py + publisher tạo telemetry, threshold và SESSION_ENDED; SQLite gửi bù và xóa sau SAVED; [edge-queue-output.txt](evidence/week3/edge-queue-output.txt) |
| FE build | **Đạt**; [frontend-build-output.txt](evidence/week3/frontend-build-output.txt) |
| FE tests | **54/59 đạt**. Năm test của main chưa theo URL tương đối và mock window mới: commands (2), merge-compatibility (1), week3 (2). Source/tests FE trùng nguyên origin/main fd107db; đợt BE này không sửa FE. [frontend-tests-output.txt](evidence/week3/frontend-tests-output.txt) |
| Môi trường máy hiện tại | Sau yêu cầu áp dụng của người dùng: đủ bảng, đúng vision-01, quyền AI/BE sẵn sàng, giữ DM-000002; [runtime-readiness.json](evidence/week3/runtime-readiness.json) |

Các ca mới 22–26 kiểm tra SESSION_ENDED, schema diagnostics, xác thực broker thật,
401/403/409, video đến trước event, quyền tải file, giới hạn header/file, rollback,
upload đồng thời và chạy lại setup. File thử chỉ dùng header MP4 phục vụ kiểm tra
giao nhận; không dùng clip khuôn mặt thật. Các ca 01–21 giữ kiểm tra lệnh/config/ACK,
HTTP/WS, Rule Engine, restart và lưu lịch sử của bản BE trước.

## Đã áp dụng trên máy hiện tại

Đã sao lưu DB và cấu hình broker vào thư mục `.local-backups` được Git ignore trước
khi áp dụng. Cập nhật DB/ACL ngày 21/10 được người dùng yêu cầu rõ; thay thế giới hạn
chưa áp dụng của đợt kiểm tra ngày 19/10 trong báo cáo tuần 3 cũ.

- Bổ sung ai_message_receipts và ai_videos bằng migration; giữ các bản ghi cũ.
- Cập nhật role backend/edge-ai, bao gồm topic riêng và storage_ack.
- Đăng ký vision-01, gán cho Admin admin_demo; giữ nguyên DM-000002.
- Các tài khoản khác cần được gán thiết bị theo quy trình quản lý.
- RULE_ENGINE_ENABLED vẫn false; DISTRACTED vẫn POLICY_PENDING để chờ nhóm thống nhất.
- Không có DB/container thử còn sót sau kiểm tra.

## Phần TV3 cần nối và giới hạn

TV3 cần thêm HTTP Basic `auth=(MQTT_USERNAME, MQTT_PASSWORD)` vào requests.post
upload như [hợp đồng](ai-ingest-video-contract.md). Mã AI hiện tại chưa gửi auth nên
nhận 401; worker giữ file để gửi lại. Event MQTT không phụ thuộc HTTP upload.
Event AI hiện thiếu model_version: BE nhận null; bộ lọc phiên bản sẽ không lấy các
event đó. Cần TV3 bổ sung phiên bản thật khi chốt payload.

Chưa sửa code AI, chưa thử ảnh camera/clip thật hoặc phần cứng ESP32 trong đợt này.
Kiểm tra định dạng upload chỉ kiểm tra header MP4; không phải đánh giá chất lượng
nhận diện hay khả năng phát mọi video. Chưa có tự xóa video theo tuổi; cần quản lý
dung lượng và sao lưu cả storage cùng PostgreSQL.
