# Frontend — hướng dẫn chạy và bàn giao tuần 1

## 1. Chức năng hiện có

Frontend dùng React/Vite, có Login và Dashboard:

- Đăng nhập qua `POST /api/login`, lưu JWT ở `localStorage.access_token`.
- Lấy thiết bị được phép xem từ `GET /api/devices` với Bearer token.
- Hiển thị trạng thái thiết bị, lần hoạt động cuối, EAR, PERCLOS và trạng thái tài xế.
- Nhận telemetry qua WebSocket; chưa có số đo thì hiện “Chưa có dữ liệu”.
- Tách kết nối Dashboard–BE khỏi trạng thái online/offline của thiết bị.

## 2. Cài đặt và cấu hình

Tạo `frontend/.env.local`:

```dotenv
VITE_BACKEND_HOST=http://localhost:8000
VITE_API_STR=/api
VITE_WS_URL=ws://localhost:8000/ws/telemetry
```

Vite hiện đọc file môi trường trong `frontend`. File `.env` ở gốc dự án dành
cho BE/deployment, không tự được FE đọc với cấu hình Vite hiện tại.
Các biến `VITE_*` được đưa vào trình duyệt: chỉ đặt URL/cấu hình công khai,
không chép mật khẩu DB hoặc `SECRET_KEY` của BE vào đây.

Chạy từ thư mục gốc dự án:

```powershell
cd frontend
npm install
npm run dev
```

Khi BE chạy trên máy TV2, thay `localhost` bằng IP máy TV2 ở cả HTTP và WebSocket:

```dotenv
VITE_BACKEND_HOST=http://<TV2_IP>:8000
VITE_API_STR=/api
VITE_WS_URL=ws://<TV2_IP>:8000/ws/telemetry
```

Khởi động lại Vite sau khi sửa cấu hình. TV2 cần cho phép origin của FE trong CORS.
FE chạy độc lập mở được Login, nhưng đăng nhập thật cần BE, DB và tài khoản đã tạo.

## 3. Đăng nhập và API thiết bị

Login gửi JSON `username`/`password` tới:

```text
POST ${VITE_BACKEND_HOST}${VITE_API_STR}/login
```

Sau khi nhận token, FE chuyển sang Dashboard. `GET /api/devices` dùng
`Authorization: Bearer <access_token>` để lấy thiết bị của tài khoản.
Dashboard đọc lại danh sách khoảng mỗi 10 giây sau khi lần gọi trước kết thúc,
và khi WebSocket kết nối thành công.

API thiết bị dùng `id` là số nguyên dương, `device_code` là mã dễ đọc.
FE dùng `id` để nhận diện record, dùng `device_code` để hiển thị; không tự
đổi ID `1` thành mã `vision-01` hoặc `alert-01`.

## 4. Kết nối máy chủ và trạng thái thiết bị

- `wsConnected`: Dashboard có kết nối WebSocket với BE hay không.
- `device.status` và `last_seen`: trạng thái/lần hoạt động cuối do BE cung cấp.
  Thiếu status hợp lệ thì hiện “Chưa xác định”.
- Mất WebSocket hoặc gọi API lỗi: giữ trạng thái gần nhất, đánh dấu dữ liệu cũ.
- Snapshot API thành công có thể làm mới thẻ ngay cả khi WebSocket chưa kết nối.
  FE không tự dùng thời hạn heartbeat riêng để đoán thiết bị offline.

Ví dụ: rút USB ESP32 nhưng BE vẫn chạy thì dòng kết nối máy chủ vẫn có thể báo
đã kết nối. Thẻ ESP32 chỉ chuyển offline khi BE trả trạng thái đó.

`DeviceStatusCard` nhận `deviceCode`, `name`, `status`, `lastSeen`, `isStale`.
Dashboard truyền đúng các props này, không dùng `connected` làm trạng thái thiết bị.

## 5. Telemetry và dữ liệu thiếu

FE hỗ trợ payload có ID số và mã thiết bị:

```json
{
  "device_id": 42,
  "device_code": "DM-000001",
  "ear": 0.21,
  "perclos": 0.35,
  "driver_state": "DROWSY"
}
```

Cũng nhận payload chỉ có mã theo tài liệu bàn giao trên `main`:

```json
{
  "device_code": "DM-000001",
  "ear": 0.21,
  "perclos": 0.35,
  "driver_state": "DROWSY"
}
```

- Cần ít nhất ID hợp lệ hoặc mã hợp lệ để xác định nguồn số đo.
- Nếu có `device_id`, phải là số nguyên dương. Chuỗi `"42"` hoặc `"vision-01"`
  không được dùng thay ID DB.
- `device_code` nếu có phải là chuỗi không rỗng. Thiếu mã thì hiện “Chưa có mã thiết bị”.
- Payload chỉ có mã được giữ `device_id: null` trong FE; không suy ra ID để gọi API.
- ID/mã ví dụ không phải dữ liệu cố định. TV2/TV3 cần chốt payload thực tế.
- EAR/PERCLOS thiếu, null hoặc sai kiểu số thì hiện `—`; giá trị `0` thật vẫn hiện 0.
- PERCLOS `0.35` hiển thị `35%`. Chưa có số đo không hiện `0%`.
- `driver_state` hỗ trợ `ATTENTIVE`, `DISTRACTED`, `DROWSY`; thiếu hoặc giá trị khác
  thì hiện “Chưa xác định”. FE không suy ra trạng thái tài xế từ EAR/PERCLOS.
- Mỗi tin thay thế toàn bộ bản số đo trước; trường thiếu không giữ giá trị của tin cũ.

Dashboard hiện hiển thị telemetry mới nhất và mã nguồn số đo; chưa có bộ chọn
luồng AI. Dữ liệu mẫu ban đầu đã được bỏ.

## 6. WebSocket và tình trạng tích hợp BE

FE dùng `VITE_WS_URL`, mặc định `ws://localhost:8000/ws/telemetry`.
Client truyền `onMessage(data)` và dùng đúng sự kiện `socket.onclose`.

BE trên `main` đã có `/ws/telemetry`, đăng ký ngoài prefix `/api`.
Tài liệu bàn giao trước đó ghi nhận log kết nối:

```text
WebSocket /ws/telemetry [accepted]
[WebSocket] Client connected. Total: 1
```

Log này chứng minh kết nối mở được, chưa chứng minh telemetry đã đi hết luồng.
Trong code đối chiếu khi ghép nhánh:

- BE đã có `driver_state` trong model, schema và hàm lưu telemetry.
- `mqtt/consumer.py` gọi hàm lưu DB nhưng chưa gọi `manager.broadcast_from_thread(...)`.
- Consumer chạy ở process riêng không chia sẻ danh sách WebSocket của FastAPI.
  TV2 cần nối MQTT vào cơ chế phát tin của process phục vụ WebSocket.
- `GET /api/{device_id}/telemetry` trả model Telemetry, trong khi response schema
  yêu cầu thêm `device_code`/`model`. TV2 cần hoàn thiện response và trường hợp
  chưa có dữ liệu. Dashboard hiện lấy số đo qua WebSocket, không gọi API này.

Ngoài JSON trực tiếp ở mục 5, FE đã chuẩn bị nhận envelope đề xuất:

```json
{
  "type": "telemetry.updated",
  "data": {
    "device_code": "DM-000001",
    "ear": 0.21,
    "perclos": 0.35,
    "driver_state": "DROWSY"
  }
}
```

`device.updated` là tin trạng thái thiết bị riêng, cũng là giao thức đề xuất.
`data` cần `status` và ID số (`id` hoặc `device_id`) hoặc `device_code`.
Nếu có cả ID và mã, cả hai phải khớp cùng thiết bị trong danh sách API.
Thiếu sự kiện này, FE vẫn đọc trạng thái qua API định kỳ.

## 7. Kiểm tra và bàn giao

Chạy trong thư mục `frontend`:

```powershell
node --test tests/*.test.mjs
npm run build
```

Test tự động kiểm tra nhận diện nguồn telemetry, dữ liệu thiếu, trạng thái tài xế,
callback WebSocket và hiển thị thẻ thiết bị. Build/test cục bộ không thay thế
kiểm thử tích hợp với BE và phần cứng.

Checklist thử chung với TV2/TV3:

- [ ] Đăng nhập thật, lấy đúng thiết bị của tài khoản.
- [ ] MQTT → BE lưu DB → WebSocket → Dashboard cập nhật liên tục, không reload.
- [ ] ID/mã đúng DB; EAR/PERCLOS/state đúng payload.
- [ ] Chưa có dữ liệu không hiện số đo mẫu hoặc kết luận “Tỉnh táo”.
- [ ] Rút nguồn ESP32: BE phát hiện offline và FE cập nhật đúng thiết bị.
- [ ] Ngắt BE: trạng thái kết nối đổi, thẻ báo dữ liệu cũ khi chưa cập nhật được.
- [ ] Hoàn thiện xác thực/phân quyền WebSocket, reconnect và phục hồi snapshot tuần 2.

WebSocket hiện chưa xác thực. Phiên đăng nhập sau refresh, dọn token khi logout
và xử lý lỗi đăng nhập đầy đủ cũng cần hoàn thiện trong phần tuần 2.

TV4 phụ trách giao diện, WebSocket client, tài liệu kiến trúc/ERD và kiểm thử
frontend với backend. Các API, cập nhật trạng thái thiết bị và phát telemetry
thật phối hợp với TV2; nguồn số đo/trạng thái tài xế phối hợp với TV3.
