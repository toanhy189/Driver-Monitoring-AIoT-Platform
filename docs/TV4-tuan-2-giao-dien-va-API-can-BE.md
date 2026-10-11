# TV4 tuần 2 — Giao diện đã làm và API cần từ backend

**Đối chiếu code ngày:** 08/10/2026

**Mục đích:** gửi TV2 chốt API/JSON để tích hợp FE tuần 2.
**Quy ước:** `{id}` là ID số trong DB để gọi API; giao diện hiển thị `device_code` và tên thiết bị. Các URL/JSON ghi **tạm** là đề xuất FE đang dùng, chưa phải hợp đồng BE đã xác nhận.

## 1. Bảy giao diện FE đã dựng

| Giao diện | API cần dùng | Tình trạng BE hiện tại |
| --- | --- | --- |
| Đăng nhập/kiểm tra phiên | `POST /api/login`, `GET /api/me` | Đã có |
| Tổng quan: danh sách thiết bị, EAR/PERCLOS, trạng thái tài xế | `GET /api/devices`, `GET /api/{id}/telemetry`, `/ws/telemetry` | Hai route HTTP đã có; telemetry cần khớp response; WS chưa xác thực/phát sự kiện từ consumer |
| Danh sách thiết bị và form đăng ký | `GET /api/devices`, `POST /api/devices` | GET đã có; POST chưa có |
| Chi tiết thiết bị và nút quản lý vòng đời | `GET /api/devices/{id}`, 4 POST lifecycle | Chưa có |
| Form kiểm tra cảnh báo và lịch sử lệnh | POST command, GET lịch sử, GET kết quả một lệnh | Chưa có |
| Cấu hình cảnh báo | `GET/PUT /api/devices/{id}/config` | Chưa có |
| Lịch sử cảnh báo và nút “Đã xem” | `GET /api/alerts`, POST acknowledge | Chưa có |

FE hiện dùng role từ `GET /api/me`: `Admin` được quản lý thiết bị, gửi lệnh, sửa cấu hình và đánh dấu cảnh báo đã xem; `Employee` được gửi lệnh, sửa cấu hình, đánh dấu đã xem; `Customer` chỉ xem các dữ liệu được cấp quyền. BE phải kiểm tra quyền và phạm vi thiết bị cho từng request. Phần camera video trực tiếp chưa phải một màn hình/API đã tích hợp trong tuần 2.

## 2. API thiết bị

### Đã có: `GET /api/devices`

FE cần **mảng** thiết bị được gán cho user đang đăng nhập. Mỗi phần tử hiện phải có ít nhất `id` số dương và `device_code` chuỗi; UI dùng thêm `name`, `model`, `status`, `last_seen`. Để hiện đủ tuần 2 và bật lệnh đúng thiết bị, TV2 cần bổ sung `type`, `lifecycle_state`, `firmware_version` (có thể `null` nếu chưa biết). BE hiện chưa trả ba trường này.

### Chưa có: `GET /api/devices/{id}`

FE cần **một object** của đúng thiết bị được phép xem, ví dụ:

```json
{
  "id": 1,
  "device_code": "alert-01",
  "name": "V1-A01 của An",
  "model": "Thiết bị cảnh báo V1",
  "type": "ALERT_NODE",
  "lifecycle_state": "ACTIVE",
  "status": "ONLINE",
  "last_seen": "2026-10-08T09:30:00Z",
  "firmware_version": null
}
```

`lifecycle_state` là trạng thái quản lý (`REGISTERED`, `PROVISIONED`, `ACTIVE`, `MAINTENANCE`, `DECOMMISSIONED`); `status` là kết nối (`ONLINE`, `OFFLINE` hoặc chưa xác định). `ACTIVE + OFFLINE` là hợp lệ. Nếu `type` hoặc `lifecycle_state` chưa có, FE không thể xác nhận đủ điều kiện bật lệnh `TEST_ALERT`.

### Chưa có: đăng ký và đổi vòng đời

| Method + URL FE đang gọi | Request | Response FE cần |
| --- | --- | --- |
| `POST /api/devices` | `{ "device_code": "alert-02", "name": "Cảnh báo 2", "model": "Alert V1" }` | Trả thành công; nên trả thiết bị vừa tạo. FE sau đó GET lại danh sách. |
| `POST /api/devices/{id}/provision` | Không có body | Trả thành công; FE GET lại detail để thấy `PROVISIONED`. |
| `POST /api/devices/{id}/activate` | Không có body | Trả thành công; FE GET lại detail để thấy `ACTIVE`. |
| `POST /api/devices/{id}/maintenance` | Không có body | Trả thành công; FE GET lại detail để thấy `MAINTENANCE`. |
| `POST /api/devices/{id}/decommission` | Không có body | Trả thành công; FE GET lại detail để thấy `DECOMMISSIONED`. |

FE không tự đổi trạng thái sau khi bấm nút; chỉ cập nhật theo dữ liệu BE trả/lần GET mới. TV2 cần chốt chuyển trạng thái nào hợp lệ và xử lý credential broker khi provision/decommission.

## 3. API kiểm tra cảnh báo và lịch sử lệnh — đều chưa có

| Method + URL FE đang gọi | FE gửi | Response FE cần |
| --- | --- | --- |
| `POST /api/devices/{id}/commands` | `{"action":"TEST_ALERT","buzzer_ms":1000,"vibration_ms":1000,"led_mode":"FLASH"}` | **Một lệnh** có `request_id` không rỗng, trạng thái ban đầu (`PENDING`/`SENT`) và thiết bị tương ứng. |
| `GET /api/commands` | Không có body | **Mảng** lệnh được phép xem, lưu trong DB để refresh vẫn còn. |
| `GET /api/commands?device_id={id}` | Không có body | Mảng lệnh của thiết bị đó. |
| `GET /api/commands/{request_id}` | Không có body | **Một lệnh** với trạng thái/ACK mới nhất của đúng `request_id`. |

Mẫu object cho response POST/GET command:

```json
{
  "request_id": "cmd-001",
  "device_id": 1,
  "device_code": "alert-01",
  "action": "TEST_ALERT",
  "created_by_name": "Demo Admin",
  "created_at": "2026-10-08T09:30:00Z",
  "status": "ACKNOWLEDGED",
  "ack_status": "COMPLETED",
  "error_message": null,
  "latency_ms": 420
}
```

`request_id` là trường FE **bắt buộc** kiểm tra. Bảng dùng `device_id`/`device_code`, `action`, `created_by_name` hoặc `created_by`, `created_at`, `status`, `ack_status`, `error_message` hoặc `error_code`; `latency_ms` có thể thiếu. Trạng thái FE đã nhận: `PENDING`, `SENT`, `ACKNOWLEDGED`, `FAILED`, `TIMEOUT`; ACK có thể là `ACCEPTED`, `COMPLETED`, `FAILED`. Chỉ `ACKNOWLEDGED + COMPLETED` được hiện “Thiết bị đã hoàn tất”. Response HTTP `SENT` không chứng minh ESP32 đã chạy xong. Lệnh `TEST_ALERT` thử LED, còi và motor; form này không chọn severity. Giới hạn `0–10000 ms` và JSON trên là tạm, TV1/TV2 cần chốt.

## 4. API cấu hình cảnh báo — chưa có

| Method + URL FE đang gọi | Response FE cần |
| --- | --- |
| `GET /api/devices/{id}/config` | Object có trường `desired` (**bắt buộc có key**, có thể `null`), `applied`, `config_id`, `applied_config_id`. |
| `PUT /api/devices/{id}/config` | FE gửi `{ "timings": ... }`; BE trả ít nhất `{ "config_id": "cfg-012" }` để FE theo dõi lần lưu này. |

FE hiện dùng cấu trúc **tạm** `timings.{led,buzzer,motor}.{1,2,3}.{on_ms,off_ms}`. Mỗi đầu ra cần đủ cả ba mức; mỗi thời gian là số nguyên mili giây. Mẫu GET khi cấu hình đã lưu nhưng thiết bị chưa áp dụng:

```json
{
  "config_id": "cfg-012",
  "applied_config_id": null,
  "desired": {
    "timings": {
      "led": {
        "1": {"on_ms": 500, "off_ms": 500},
        "2": {"on_ms": 400, "off_ms": 400},
        "3": {"on_ms": 300, "off_ms": 300}
      },
      "buzzer": {
        "1": {"on_ms": 0, "off_ms": 0},
        "2": {"on_ms": 500, "off_ms": 500},
        "3": {"on_ms": 1000, "off_ms": 500}
      },
      "motor": {
        "1": {"on_ms": 0, "off_ms": 0},
        "2": {"on_ms": 0, "off_ms": 0},
        "3": {"on_ms": 1000, "off_ms": 500}
      }
    }
  },
  "applied": null
}
```

Sau khi ESP32 báo đã áp dụng, `applied_config_id` phải khớp `config_id` và `applied` chứa cấu trúc `timings` của cấu hình đang chạy. Các con số mẫu chỉ minh họa định dạng, **không phải nhịp cảnh báo đã được nhóm chốt**. TV1/TV2 cần xác nhận JSON, giới hạn và ý nghĩa `0 ms` trước khi đánh dấu PASS.

## 5. API lịch sử cảnh báo — chưa có

| Method + URL FE đang gọi | Response FE cần |
| --- | --- |
| `GET /api/alerts` | **Mảng** cảnh báo của các thiết bị người dùng được phép xem. |
| `POST /api/alerts/{alert_id}/acknowledge` | Nên trả object cảnh báo đã cập nhật; nếu trả rỗng, FE sẽ GET lại danh sách. |

Mẫu một cảnh báo:

```json
{
  "alert_id": "alert-001",
  "device_id": 1,
  "device_code": "alert-01",
  "alert_type": "DROWSINESS_WARNING",
  "severity": 3,
  "created_at": "2026-10-08T09:30:00Z",
  "status": "NEW",
  "acknowledged_at": null,
  "request_id": "cmd-001"
}
```

`alert_id` bắt buộc là chuỗi không rỗng hoặc số nguyên dương. FE cũng đọc `type` thay `alert_type`, `timestamp` thay `created_at`, và `acknowledged: true/false` nếu BE chọn cách đó. Nút “Đã xem” dành cho Admin/Employee; đây là xác nhận của người dùng về **cảnh báo**, không phải ACK của ESP32 về **lệnh**.

## 6. Tổng quan/telemetry và WebSocket cần hoàn thiện

### Route đã có: `GET /api/{id}/telemetry`

FE muốn nhận số đo gần nhất của đúng thiết bị được gán, hoặc trạng thái không có dữ liệu rõ ràng. Ví dụ:

```json
{
  "device_id": 1,
  "device_code": "vision-01",
  "recorded_at": "2026-10-08T09:30:00Z",
  "ear": 0.25,
  "perclos": 0.18,
  "driver_state": "ATTENTIVE",
  "face_detected": true,
  "angle_x": 1.2,
  "angle_y": -2.1,
  "angle_z": 0.5,
  "confidence": 0.91
}
```

Các trường AI chưa có thì trả `null` hoặc thống nhất bỏ field; FE sẽ hiện `—`/“Chưa đủ dữ liệu”. `face_detected: false` phải hiện “Không thấy mặt”, không tự gán `ATTENTIVE`. BE hiện có route này, nhưng `TelemetryResponse` yêu cầu `device_code`/`model` trong khi object `Telemetry` được route trả trực tiếp chưa có các trường đó; TV2 cần đối chiếu để tránh lỗi response validation. `face_detected` cũng chưa có trong schema/model hiện tại.

### Route WS đã có: `/ws/telemetry`, nhưng luồng tuần 2 chưa hoàn chỉnh

FE đã chuẩn bị nhận tin theo dạng `{ "type": "command.updated", "data": { ... } }` với các type `telemetry.updated`, `device.updated`, `command.updated`, `alert.created`, `config.updated`. Ví dụ:

```json
{
  "type": "command.updated",
  "data": {
    "request_id": "cmd-001",
    "device_id": 1,
    "device_code": "alert-01",
    "status": "ACKNOWLEDGED",
    "ack_status": "COMPLETED"
  }
}
```

BE hiện chưa xác thực WS, chưa lọc tin theo user-device và consumer chưa phát các event này. TV2/TV4 cần chốt cách xác thực WS phù hợp trình duyệt (ví dụ ticket ngắn hạn), rồi kiểm tra hai Customer khác nhau không nhận tin của nhau. Reconnect FE đã có, nhưng phải GET snapshot lại từ API chính thức để dữ liệu không mất hoặc bị cũ.

## 7. Điểm cần TV2 chốt trước khi nghiệm thu

1. Tên route/JSON chính thức cho device detail, đăng ký, lifecycle, command, config, alert; FE hiện dùng địa chỉ tạm ở trên.
2. Field `type`, `lifecycle_state`, `firmware_version`; cách tính `ONLINE/OFFLINE` từ `last_seen`; quyền thiết bị theo user.
3. Trạng thái DB command và ACK firmware (`ACCEPTED`/`COMPLETED`/`FAILED`), timeout, `request_id`, giới hạn tham số `TEST_ALERT`.
4. Cấu trúc thời gian bật/tắt theo severity 1–3 và tín hiệu `applied_config_id` từ ESP32.
5. Dữ liệu telemetry/AI có timestamp và định danh thiết bị; response khi chưa có số đo.
6. WS xác thực, lọc theo quyền, phát sự kiện; lỗi HTTP 401/403/404/409/422 có `detail` dễ hiểu.

**Nguồn code FE:** `frontend/src/App.jsx`, `frontend/src/services/{devices,commands,config,alerts,telemetryApi,permissions,realtime}.js`, `frontend/src/pages/`, `frontend/src/components/Dashboard.jsx`, `frontend/src/components/TestAlertSection.jsx`.

**Nguồn code BE:** `backend/app/api/routes/{users,devices,websocket}.py`, `backend/app/models/{device,telemetry}.py`, `backend/app/schemas/{device,telemetry,user}.py`.
