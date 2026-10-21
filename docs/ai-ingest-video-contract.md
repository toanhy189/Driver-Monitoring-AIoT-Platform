# BE nhận event và video từ Edge AI

Cập nhật 21/10/2026. Đối chiếu AI trên `main` tại `fd107db`: `main.py`,
`service/message/publisher.py`, `service/video/worker.py`. Tài liệu này bổ sung
bàn giao tuần 3; không thay chính sách cảnh báo chưa được nhóm xác nhận.

## 1. Event qua MQTT

AI gửi `driver/{device_code}/events`, nhận `driver/{device_code}/storage_ack`.
`device_code` trong JSON phải trùng topic và thiết bị VISION_NODE đã đăng ký.
`message_id` là khóa chống trùng; BE vẫn nhận tên cũ `event_id`/`device_id`.
Timestamp phải có múi giờ. Giữ nguyên ID và nội dung khi gửi lại.

| Loại | Trường riêng | Kết quả BE |
|---|---|---|
| STATE_CHANGED | state, previous_state (tùy chọn) | Lưu lịch sử, không tạo lệnh |
| DROWSY_THRESHOLD_REACHED | state=DROWSY, state_duration_ms | Xét rule; bật lệnh cần cả cờ môi trường và binding hợp lệ |
| DISTRACTED_THRESHOLD_REACHED | state=DISTRACTED, state_duration_ms | Lưu POLICY_PENDING; chờ nhóm chốt chính sách |
| SESSION_ENDED | final_state, có thể null khi chưa xác định | Lưu trạng thái cuối, không tạo cảnh báo/lệnh |

BE lưu event và receipt trong cùng giao dịch PostgreSQL. Sau commit mới gửi:

```json
{"message_id":"ID-ban-tin","status":"SAVED"}
```

Gửi lại cùng ID/nội dung: trả SAVED, không tạo thêm event/cảnh báo. Cùng ID
nhưng nội dung khác: từ chối và ghi MESSAGE_ID_CONFLICT. Không dùng MQTT PUBACK
để kết luận BE đã lưu. SESSION_ENDED cũng được xác nhận để không kẹt hàng đợi.

Các log chẩn đoán gồm UNKNOWN_DEVICE, DEVICE_NOT_ALLOWED, TOPIC_SOURCE_MISMATCH,
INVALID_SCHEMA, MESSAGE_ID_CONFLICT và lỗi DB với SQLSTATE. Log schema chỉ chứa
tên trường/loại lỗi; không in mật khẩu hoặc toàn bộ bản tin. BE không gửi SAVED
khi dữ liệu bị từ chối hoặc giao dịch thất bại.

AI hiện chưa gửi model_version trên event; BE giữ null. Bộ lọc model_version
chỉ trả event có phiên bản tương ứng. TV3 cần bổ sung phiên bản thật khi chốt
payload; BE không tự suy ra từ telemetry hoặc đặt một phiên bản giả.

## 2. Upload video bằng HTTP

`POST /api/videos/upload`, dạng `multipart/form-data`:

| Trường | Nội dung |
|---|---|
| file | File `.mp4`, Content-Type `video/mp4` |
| device_code | Mã Vision Node đã ACTIVE |
| state | ATTENTIVE, DISTRACTED, DROWSY hoặc UNKNOWN |
| message_id | ID của STATE_CHANGED bắt đầu đoạn video, dài 1–80 ký tự |

**Xác thực:** HTTP Basic bằng username/password MQTT của chính Vision Node.
BE xác nhận đăng nhập với broker hiện tại, nên tài khoản bị thu hồi không upload
được. Không dùng tài khoản broker admin/backend để upload. Dùng HTTPS khi triển
khai ngoài mạng phát triển tin cậy. Password không nằm trong URL, JSON hoặc DB video.

TV3 bổ sung một tham số vào `requests.post` hiện có:

```python
from config import MQTT_USERNAME, MQTT_PASSWORD

response = requests.post(
    BACKEND_URL,
    auth=(MQTT_USERNAME, MQTT_PASSWORD),
    files={"file": (os.path.basename(video_path), video_file, "video/mp4")},
    data={"device_code": device_code, "state": state, "message_id": message_id},
    timeout=(5, 120),
)
```

Đoạn này là hướng dẫn tích hợp; thay đổi BE không tự sửa chương trình của TV3.
AI trên main hiện chưa truyền thông tin xác thực trong HTTP upload, nên sẽ nhận
401 cho đến khi bổ sung `auth`. Hàng đợi video hiện có sẽ giữ file để gửi lại.
Nếu AI chạy máy khác BE, BACKEND_HOST phải là địa chỉ máy BE, không phải localhost.

Response mới: HTTP 201. Gửi lại cùng thiết bị/message_id, cùng file/state: HTTP 200,
cùng video_id và duplicate=true. Cùng ID nhưng file/state khác: HTTP 409.

```json
{
  "video_id": 1,
  "device_id": 7,
  "message_id": "ID-state-changed",
  "state": "DROWSY",
  "size_bytes": 12345,
  "created_at": "2026-10-21T00:00:00Z",
  "event_received": false,
  "content_url": "/api/videos/1/content",
  "status": "SAVED",
  "duplicate": false
}
```

Video có thể đến trước event do hai đường truyền độc lập. Khi đó BE lưu metadata
và event_received=false; lần truy vấn sau tự đối chiếu event đã đến chưa. Nếu
event đã có mà thuộc thiết bị khác/khác state/khác loại thì từ chối upload.
Response HTTP thành công xác nhận file và metadata đã lưu, không xác nhận MQTT event
đã lưu. AI tiếp tục chờ storage_ack riêng cho event.

Request phải có Content-Length để giới hạn tổng phần multipart trước khi parser
ghi file tạm. requests.post với files tự tạo header này; upload chunked không có
Content-Length nhận HTTP 411.

Lỗi: 401 thiếu/sai tài khoản; 403 tài khoản không thuộc thiết bị; 404 thiết bị chưa
đăng ký; 409 sai lifecycle hoặc trùng ID khác nội dung; 413 quá dung lượng;
415 sai định dạng/header MP4; 422 sai trường form; 503 broker/storage/DB chưa sẵn sàng.

Giới hạn mặc định 100 MiB/file, chỉnh bằng AI_VIDEO_MAX_BYTES. BE kiểm tra header
container MP4, không giải mã để chứng nhận toàn bộ video hợp lệ. Tên file lưu do BE
sinh, không dùng đường dẫn AI gửi. File tạm được dọn khi lỗi; nếu DB commit thất bại
thì file mới không được giữ như một video đã lưu.

## 3. Xem video và lưu trữ

- GET /api/devices/{id}/videos?limit=20&offset=0: danh sách metadata.
- GET /api/videos/{video_id}/content: nội dung MP4.
- Hai API đọc dùng Bearer token web, lọc theo user_devices hiện hành.
  Không có quyền xem thiết bị thì trả 404; không công khai thư mục video.
- File nằm trong AI_VIDEO_DIR; DB chỉ lưu metadata/hash và khóa liên kết.
- Compose lưu file ở volume video_data; cần sao lưu cả volume và PostgreSQL.
- `.env`, thư mục storage và video thật không được đưa lên Git.
- Chưa có chính sách tự xóa video theo tuổi; quản trị cần theo dõi dung lượng
  và thống nhất thời gian lưu trước khi chạy lâu dài.

## 4. Đồng bộ môi trường

Kiểm tra chỉ đọc, không thay đổi DB/ACL:

```powershell
python backend/scripts/setup_ai_ingest.py
```

Áp dụng cho môi trường đã có DB tuần 2, chọn đúng tài khoản Admin thực tế:

```powershell
python backend/scripts/setup_ai_ingest.py --apply --assign-user TEN_ADMIN
```

Lệnh apply thực sự thay đổi DB và quyền broker: chạy migration tuần 2, tuần 3,
video; cập nhật role backend/edge-ai theo cấu hình; xác nhận credential có hiệu lực;
đăng ký AI_DEVICE_CODE nếu chưa có và gán thiết bị cho Admin được chỉ định. Các thiết
bị khác giữ nguyên. Không reset DB, không đổi mật khẩu, không bật lại tài khoản bị
thu hồi và không tự thay lifecycle của thiết bị đã có. Chạy lại không tạo bản ghi trùng.
Các tài khoản khác cần được gán thiết bị theo quy trình quản lý của nhóm.

Sau đó restart BE. Khi BE chạy bằng Compose, build lại backend/mqtt-setup để dùng
code mới; migration của Compose có thêm migration_ai_videos.sql. Thiết lập nguồn
AI vẫn cần lệnh setup hoặc API đăng ký/gán thiết bị, không tự tạo trong lúc nhận tin.

Giữ RULE_ENGINE_ENABLED=false đến khi nhóm chốt điều kiện/mức cảnh báo và thiết bị
nhận lệnh. Không dùng việc bật rule để sửa lỗi giao nhận event.

## 5. Kiểm tra lại

```powershell
python backend/tests/run_week3_isolated.py
```

Bộ kiểm tra dùng PostgreSQL và broker tạm riêng, tạo credential thử rồi tự dọn.
Bao gồm event/receipt trùng, commit lỗi, SESSION_ENDED, client AI và SQLite thật
(không mở camera), HTTP upload có đăng nhập broker thật, giới hạn file, rollback,
quyền đọc, upload đồng thời và luồng lệnh/config/ACK cũ.

Minh chứng: docs/evidence/week3/integration-results.json, integration-output.txt,
edge-queue-output.txt và acl-results.json. Kiểm tra header video không thay cho
thử phát video camera thật; phần nhận diện ảnh và phần cứng ESP32 vẫn cần TV3/TV1
xác nhận trên thiết bị của mình.
