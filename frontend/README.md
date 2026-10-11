# Frontend — hướng dẫn chạy và tích hợp

## 1. Chức năng hiện có

Frontend dùng React/Vite, có Login, Dashboard, danh sách và chi tiết thiết bị:

- Đăng nhập qua `POST /api/login`, xác nhận token bằng `GET /api/me`, rồi lưu JWT ở `localStorage.access_token`.
- Lấy thiết bị được phép xem từ `GET /api/devices` với Bearer token.
- Hiển thị trạng thái thiết bị, lần hoạt động cuối, EAR, PERCLOS và trạng thái tài xế.
- Nhận telemetry qua WebSocket; chưa có số đo thì hiện “Chưa có dữ liệu”.
- Tách kết nối Dashboard–BE khỏi trạng thái online/offline của thiết bị.
- Trang thiết bị đọc danh sách thật từ BE; các API chi tiết/vòng đời đang theo hợp đồng tạm ở mục 7.

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

Sau khi nhận token, FE gọi `GET /api/me` để lấy user/role. Chỉ khi API này thành công,
FE mới lưu token và mở Dashboard. Khi tải lại trang, FE kiểm tra token đã lưu qua `/api/me`:
401 thì xóa phiên, còn lỗi mạng thì hiện nút thử lại và giữ token. `GET /api/devices` dùng
`Authorization: Bearer <access_token>` để lấy thiết bị của tài khoản.
Dashboard đọc lại danh sách khoảng mỗi 10 giây sau khi lần gọi trước kết thúc,
và khi WebSocket kết nối thành công.

API thiết bị dùng `id` là số nguyên dương, `device_code` là mã dễ đọc.
FE dùng `id` để nhận diện record, dùng `device_code` để hiển thị; không tự
đổi ID `1` thành mã `vision-01` hoặc `alert-01`.

Các lệnh gọi HTTP dùng chung `src/services/api.js`. Hàm `apiRequest()` tự ghép
địa chỉ BE với `/api`, gửi JSON, gắn token khi được truyền vào và trả lỗi có
`status` để màn hình xử lý:

```js
await apiRequest("/devices", { token, signal });
await apiRequest("/login", { method: "POST", body: { username, password } });
```

Chỉ truyền phần đường dẫn sau `/api`; ví dụ dùng `/devices`, không dùng
`/api/devices`. Login hiện lỗi 401 thành “Sai tên đăng nhập hoặc mật khẩu”.
Nếu API thiết bị trả 401, Dashboard xóa token và trở về Login; lỗi 403 chỉ
hiện thông báo thiếu quyền. Nút Đăng xuất xóa token/user và unmount Dashboard để
đóng WebSocket, hủy request và timer. Dashboard hiển thị role đúng như `/api/me` trả về.
Quyền FE tạm thời được gom trong `src/services/permissions.js`, dùng đúng tên role BE:

| Role | Xem Dashboard/config | Gửi lệnh, sửa config | Quản lý thiết bị | Ngừng sử dụng |
| --- | --- | --- | --- | --- |
| `Admin` | Có | Có | Có | Có |
| `Employee` | Có | Có | Chưa cấp | Không |
| `Customer` | Có | Không | Không | Không |

Role khác ba giá trị này không mở Dashboard. `Customer` được ghi rõ là chỉ xem.
Các nút gửi lệnh, sửa cấu hình và quản lý vòng đời đã có trên FE, nhưng nhiều API
tương ứng chưa được BE triển khai. BE vẫn phải kiểm tra quyền khi nhận API thao tác:
ẩn nút trên FE không ngăn được người dùng tự gửi request.

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
- Dashboard chọn thiết bị từ `GET /api/devices` của tài khoản; chỉ số đo có ID/mã
  khớp thiết bị đang chọn mới được hiển thị. Nếu chỉ có một thiết bị, FE chọn sẵn.
- `face_detected=false` hiện “Không thấy mặt”, kể cả khi payload ghi
  `driver_state=ATTENTIVE`. `confidence=null` hiện `—`; góc đầu X/Y/Z chỉ
  hiện khi BE cung cấp giá trị số.
- FE thử `GET /api/{device_id}/telemetry` để đọc số đo gần nhất khi chọn thiết bị
  và sau reconnect. Khi mất WebSocket, số đo đang có được ghi là dữ liệu cũ, kèm
  thời gian cập nhật cuối nếu payload có `recorded_at` hoặc FE ghi được giờ nhận.

Dữ liệu mẫu ban đầu đã được bỏ.

## 6. WebSocket và tình trạng tích hợp BE

FE dùng `VITE_WS_URL`, mặc định `ws://localhost:8000/ws/telemetry`.
Client truyền `onMessage(data)` và dùng đúng sự kiện `socket.onclose`.
App mở một kết nối cho khu vực đã đăng nhập. Mất kết nối thì thử lại sau
1, 2, 4… tối đa 30 giây; reconnect sẽ tải lại snapshot của trang đang xem.
Logout hủy timer và đóng socket. JSON telemetry trực tiếp vẫn được nhận;
envelope `telemetry.updated`, `device.updated`, `command.updated`,
`config.updated`, `alert.created` được phân loại theo `type`. Khi nhận
`alert.created`, trang Cảnh báo tải lại danh sách qua API có phân quyền.

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
  chưa có dữ liệu. Dashboard có gọi API này để khôi phục số đo, nhưng vẫn hiển
  thị lỗi nếu response chưa đúng schema.

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
`data` cần ít nhất một trường thay đổi như `status` hoặc `lifecycle_state`, cùng
ID số (`id` hoặc `device_id`) hoặc `device_code`.
Nếu có cả ID và mã, cả hai phải khớp cùng thiết bị trong danh sách API.
Thiếu sự kiện này, FE vẫn đọc trạng thái qua API định kỳ.
WebSocket BE hiện chưa xác thực và manager phát tin cho mọi kết nối. FE lọc dữ
liệu theo thiết bị đã lấy từ API để hiển thị, nhưng TV2 phải xác thực WebSocket
và lọc theo quyền ở BE trước khi dùng cho dữ liệu riêng của nhiều tài khoản.

## 7. Trang thiết bị tuần 2 (hợp đồng API tạm)

Từ Dashboard chọn **Thiết bị** để mở danh sách; chọn **Xem chi tiết** để mở đúng
ID số trong DB. Danh sách dùng `GET /api/devices` đã có, tải lại sau mỗi 10 giây
và cập nhật record cùng ID khi nhận `device.updated`. Cột loại dùng `model` hiện
có của BE. Thiếu `lifecycle_state` hoặc `firmware_version` thì hiện “Chưa cung cấp”;
`last_seen` thiếu thì hiện “Chưa ghi nhận”. Hai trạng thái quản lý và kết nối
được hiển thị riêng.

Các API FE đã chuẩn bị gọi dưới đây **chưa có trên BE** khi viết phần này:

| Hành động | Request FE gửi |
| --- | --- |
| Xem chi tiết | `GET /api/devices/{id}` |
| Đăng ký | `POST /api/devices` với JSON `device_code`, `name`, `model` |
| Cấp thông tin kết nối | `POST /api/devices/{id}/provision` |
| Kích hoạt | `POST /api/devices/{id}/activate` |
| Bảo trì | `POST /api/devices/{id}/maintenance` |
| Ngừng sử dụng | `POST /api/devices/{id}/decommission` |

Trang chi tiết vẫn hiển thị thông tin chọn từ danh sách nếu API chi tiết trả 404,
nhưng ghi rõ nguồn đó. Lỗi 404/405 hoặc lỗi quyền được hiển thị, không đổi trạng
thái thiết bị trên FE. Khi thao tác thành công, FE gọi lại API chi tiết để lấy
trạng thái chính thức. Nút ngừng sử dụng có bước xác nhận tên thiết bị.

Theo quyền FE tạm thời, `Admin` thấy đăng ký và các thao tác vòng đời;
`Employee`/`Customer` chỉ xem trong phần này. BE vẫn phải kiểm tra quyền và chốt
request/response thực tế trước khi tích hợp.

## 8. Test Alert và lịch sử lệnh (hợp đồng API tạm)

Trang chi tiết của Alert Node có nút **Kiểm tra cảnh báo** phía trên thông số.
Bấm nút mới mở form nhập thời lượng còi/rung và chế độ LED. `TEST_ALERT`
thử cả LED, còi và motor, không chọn mức cảnh báo; mức 1–3 thuộc
`DROWSINESS_WARNING`.
**Gửi lệnh kiểm tra** mới gọi API (`TEST_ALERT`). Nút gửi chỉ bật khi user là
`Admin`/`Employee` và BE trả `type: "ALERT_NODE"`, `lifecycle_state: "ACTIVE"`,
`status: "ONLINE"`, `last_seen` hợp lệ. Thiếu điều kiện sẽ hiện lý do; FE không
tự đoán loại thiết bị hoặc timeout heartbeat. `Customer` có thể xem lịch sử
nhưng không gửi lệnh. BE phải kiểm tra quyền và thiết bị một lần nữa.

| Việc | Request FE dùng; TV2 chưa triển khai |
| --- | --- |
| Kiểm tra cảnh báo | `POST /api/devices/{id}/commands` |
| Lịch sử | `GET /api/commands` hoặc `?device_id={id}` |
| Theo dõi một lệnh | `GET /api/commands/{request_id}` |

Body Test Alert và giới hạn 0–10000 ms hiện là **mẫu tạm** trong
`src/services/commands.js`; TV1/TV2/TV4 cần chốt các trường và giới hạn trước
khi thử phần cứng. FE gửi giá trị người dùng nhập trong form. BE phải tạo
`request_id`, lưu lệnh, nhận ACK từ ESP32 và trả trạng thái thật. FE chỉ hiện
“Thiết bị đã hoàn tất” với `status=ACKNOWLEDGED` và `ack_status=COMPLETED`.
Trong khi chờ WebSocket có xác thực, FE gọi API kết quả mỗi 5 giây và tải lại
lịch sử mỗi 10 giây; không tự gửi lại POST khi mất mạng.

## 9. Cấu hình cảnh báo (hợp đồng API tạm)

Từ chi tiết Alert Node, chọn **Cấu hình cảnh báo**. Form bên trái có ba tab mức
1–3, mỗi tab chỉnh thời gian bật/tắt (ms) của LED, còi và motor; khi lưu FE gửi
cả ba mức. Bên phải hiển thị cấu hình mong muốn và cấu hình thiết bị đã xác nhận
ở mức đang xem. `Customer` chỉ xem;
`Admin`/`Employee` được sửa. Giới hạn 0–10000 ms là đề xuất, cần TV1/TV2 xác nhận.

FE gọi `GET/PUT /api/devices/{id}/config` với Bearer token. TV1/TV2 **chưa chốt
JSON**; cấu trúc tạm mà FE đang đọc/gửi là:

```json
{
  "timings": {
    "led": {
      "1": { "on_ms": 700, "off_ms": 1000 },
      "2": { "on_ms": 500, "off_ms": 500 },
      "3": { "on_ms": 300, "off_ms": 300 }
    },
    "buzzer": {
      "1": { "on_ms": 300, "off_ms": 1000 },
      "2": { "on_ms": 500, "off_ms": 500 },
      "3": { "on_ms": 800, "off_ms": 300 }
    },
    "motor": {
      "1": { "on_ms": 300, "off_ms": 1000 },
      "2": { "on_ms": 500, "off_ms": 500 },
      "3": { "on_ms": 800, "off_ms": 300 }
    }
  }
}
```

Đây là **ví dụ về cấu trúc PUT**, không phải cấu hình đang chạy trên thiết bị.
GET cần trả `{ "config_id": "cfg-002", "desired": { "timings": ... },
"applied_config_id": "cfg-001", "applied": { "timings": ... } }`; `desired`
có thể là `null` khi chưa cấu hình, `applied` có thể là `null` khi chưa có
giá trị thiết bị đã xác nhận. PUT cần trả `config_id` mới do BE tạo. FE chỉ báo
**đã áp dụng** khi GET trả `applied_config_id` trùng `config_id`; trước đó hiện
**chờ thiết bị áp dụng** và kiểm tra lại mỗi 10 giây.

BE hiện chưa có route này. Admin/Employee có thể nhập bản nháp để xem form;
nút Lưu chỉ bật sau khi GET trả cấu hình hợp lệ. Customer chỉ xem. Firmware
hiện mới giữ các thời gian trong code.
TV1/TV2 cần chốt JSON, giới hạn và cách severity ánh xạ vào ba mức trước khi
thử end-to-end. Nút gửi lệnh kiểm tra hiện truyền thời lượng riêng, nên không
dùng nó để chứng minh cấu hình mặc định đã đổi.

## 10. Lịch sử cảnh báo (hợp đồng API tạm)

Trang **Cảnh báo** gọi `GET /api/alerts`, có trạng thái đang tải, rỗng, lỗi và
nút tải lại. Danh sách gộp theo `alert_id`, hiện thiết bị, loại, mức, thời gian,
trạng thái và `request_id` liên quan nếu BE cung cấp. Khi nhận `alert.created`,
FE gọi lại API để chỉ hiển thị cảnh báo tài khoản được phép xem.

`Admin`/`Employee` có nút **Đã xem** khi BE cho biết cảnh báo còn mở; nút gọi
`POST /api/alerts/{alert_id}/acknowledge`. `Customer` chỉ xem. Xác nhận đã
xem cảnh báo không phải ACK hoàn tất lệnh thiết bị. Cả hai route và JSON alert
vẫn cần TV2 chốt và triển khai; BE phải kiểm tra quyền.

## 11. Kiểm tra và bàn giao

Chạy trong thư mục `frontend`:

```powershell
node --test tests/*.test.mjs
npm run build
```

Test tự động kiểm tra nhận diện nguồn telemetry, dữ liệu thiếu, trạng thái tài xế,
callback WebSocket, quyền gửi lệnh, trạng thái lệnh và validate cấu hình. Build/test cục bộ không thay thế
kiểm thử tích hợp với BE và phần cứng.

Checklist thử chung với TV2/TV3:

- [ ] Đăng nhập thật, lấy đúng thiết bị của tài khoản.
- [ ] MQTT → BE lưu DB → WebSocket → Dashboard cập nhật liên tục, không reload.
- [ ] ID/mã đúng DB; EAR/PERCLOS/state đúng payload.
- [ ] Chưa có dữ liệu không hiện số đo mẫu hoặc kết luận “Tỉnh táo”.
- [ ] Rút nguồn ESP32: BE phát hiện offline và FE cập nhật đúng thiết bị.
- [ ] Ngắt BE: trạng thái kết nối đổi, thẻ báo dữ liệu cũ khi chưa cập nhật được.
- [ ] Hoàn thiện xác thực/phân quyền WebSocket ở BE và thử reconnect/khôi phục
  snapshot với BE thật.

WebSocket hiện chưa xác thực; TV2/TV4 cần thống nhất cách xác thực trước khi dùng
để truyền dữ liệu riêng hoặc thao tác điều khiển.

TV4 phụ trách giao diện, WebSocket client, tài liệu kiến trúc/ERD và kiểm thử
frontend với backend. Các API, cập nhật trạng thái thiết bị và phát telemetry
thật phối hợp với TV2; nguồn số đo/trạng thái tài xế phối hợp với TV3.
