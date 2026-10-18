# TV4-21 — Bàn giao FE tuần 2

**Dự án:** Driver Monitoring AIoT Platform

**Phạm vi:** luồng xử lý (sequence), vòng đời thiết bị (lifecycle) và ma trận quyền

**Ngày đối chiếu code:** 08/10/2026
**Người nhận:** TV1 (firmware), TV2 (backend), TV3 (AI), TV4 (frontend)

> **Cách đọc trạng thái:** “Đã có” nghĩa là đã thấy route hoặc logic trong code hiện tại. “FE đã chuẩn bị” nghĩa là màn hình đã gọi API theo hợp đồng tạm, nhưng chưa thể chạy trọn luồng vì BE/firmware chưa cung cấp đủ. Các sơ đồ bên dưới mô tả **luồng cần đạt**, không khẳng định mọi mũi tên đã hoạt động.

## 1. Phạm vi bàn giao nhanh

| Phần | FE hiện có | Phụ thuộc còn lại |
| --- | --- | --- |
| Đăng nhập, kiểm tra phiên | `POST /api/login`, `GET /api/me`; giữ phiên, đăng xuất | BE kiểm tra token và quyền cho mọi API |
| Danh sách thiết bị | `GET /api/devices`, tải/rỗng/lỗi/thử lại | BE chỉ trả thiết bị gán cho user; đang có |
| Chi tiết và vòng đời | Trang chi tiết, nút theo quyền, trạng thái quản lý/kết nối tách riêng | API detail/lifecycle và các trường `type`, `lifecycle_state`, `firmware_version` |
| Kiểm tra cảnh báo và lịch sử lệnh | Form `TEST_ALERT`, theo dõi theo `request_id`, lịch sử | API command, DB command, MQTT publish/ACK, sự kiện WS |
| Cấu hình cảnh báo | Form thời gian bật/tắt LED/còi/rung theo mức 1–3; hiển thị cấu hình đã lưu/thiết bị | GET/PUT config, `config_id`, `applied_config_id`, JSON thống nhất với TV1/TV2 |
| Dashboard AI | Chọn thiết bị, EAR/PERCLOS/trạng thái, xử lý thiếu/cũ dữ liệu | Telemetry hợp lệ có device ID, dữ liệu head pose/face/quality khi TV3 và BE cung cấp |
| Realtime | Một socket chung trong vùng đăng nhập, reconnect, dọn khi logout | WS xác thực, lọc theo thiết bị được gán, BE phát các loại sự kiện |

`id` số trong DB dùng nội bộ để gọi API; giao diện ưu tiên hiển thị `device_code` và tên thiết bị. `device_code` không thay cho việc BE kiểm tra thiết bị có thuộc user đang đăng nhập hay không.

## 2. Sequence — đăng nhập, chọn thiết bị và xem số đo

```mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant FE as Frontend
    participant BE as Backend API
    participant DB as PostgreSQL
    participant WS as WebSocket
    U->>FE: Nhập username/password
    FE->>BE: POST /api/login (JSON)
    BE-->>FE: access_token hoặc lỗi
    FE->>BE: GET /api/me (Bearer token)
    BE-->>FE: user và role
    FE->>BE: GET /api/devices (Bearer token)
    BE->>DB: Tra thiết bị đang gán cho user
    DB-->>BE: Danh sách được phép xem
    BE-->>FE: Danh sách thiết bị
    U->>FE: Chọn một thiết bị để xem số đo
    FE->>BE: GET /api/{device_id}/telemetry
    BE->>DB: Lấy số đo mới nhất của thiết bị được gán
    DB-->>BE: Telemetry hoặc rỗng
    BE-->>FE: Snapshot để hiển thị
    FE->>WS: Mở kết nối realtime
    Note over WS,FE: Cần TV2 xác thực socket và lọc tin theo user/device trước khi dùng thật
    WS-->>FE: telemetry.updated đúng thiết bị
    FE-->>U: EAR/PERCLOS/trạng thái + thời điểm cập nhật
```

**Quy tắc FE:** Khi có nhiều thiết bị, Dashboard dùng thiết bị người dùng chọn và chỉ gắn telemetry có đúng `device_id`/`device_code`. Không có mặt thì hiện “Không thấy mặt”; thiếu hoặc cũ dữ liệu thì hiện trạng thái tương ứng, không tự điền ATTENTIVE hay confidence giả. Khi socket nối lại, trang đang mở GET snapshot lại. Bộ lọc FE chỉ để hiển thị; BE vẫn phải kiểm tra quyền với HTTP lẫn WS.

**Tình trạng BE:** `GET /api/devices` đã lọc qua bảng gán `user_device`. `GET /api/{device_id}/telemetry` đã có route, nhưng response schema cần TV2 đối chiếu để trả đúng dữ liệu FE cần. `/ws/telemetry` hiện chưa xác thực kết nối, manager có khả năng broadcast chung, và MQTT consumer chưa phát telemetry qua WS. Chưa dùng WS hiện tại để đưa dữ liệu riêng của khách hàng vào demo nhiều tài khoản.

## 3. Sequence — gửi lệnh kiểm tra cảnh báo và chờ ACK

```mermaid
sequenceDiagram
    autonumber
    actor U as Admin hoặc Employee
    participant FE as Frontend
    participant BE as Backend
    participant DB as PostgreSQL
    participant MQ as MQTT broker
    participant ESP as ESP32 Alert Node
    U->>FE: Bấm Gửi lệnh kiểm tra
    FE->>BE: POST /api/devices/{id}/commands, action TEST_ALERT
    BE->>BE: Xác thực role, quyền thiết bị, type, ACTIVE, online và dữ liệu mới
    BE->>DB: Tạo request_id và lưu PENDING
    BE->>MQ: Publish lệnh kèm request_id
    MQ-->>ESP: Chuyển lệnh
    BE->>DB: Cập nhật SENT nếu chưa có ACK mới hơn
    BE-->>FE: request_id, trạng thái hiện tại
    FE-->>U: Đã gửi, chờ thiết bị phản hồi
    ESP->>ESP: Thử LED, còi và motor
    ESP->>MQ: ACK ACCEPTED / COMPLETED / FAILED kèm request_id
    MQ->>BE: Chuyển ACK
    BE->>DB: Đối chiếu request_id + device, lưu trạng thái cuối
    BE-->>FE: command.updated hoặc FE GET lại lệnh
    FE-->>U: Kết quả của đúng request_id
```

- HTTP thành công hoặc trạng thái `SENT` chỉ cho biết yêu cầu đã được BE nhận/gửi; **chưa** chứng minh ESP32 đã chạy xong.
- `ACK ACCEPTED` nghĩa là thiết bị nhận/chấp nhận lệnh. Chỉ hiển thị “Thiết bị đã hoàn tất” khi BE ghi `ACKNOWLEDGED` cùng `ack_status=COMPLETED`. `FAILED` và `TIMEOUT` hiện đúng lỗi; FE không tự đặt kết quả cuối.
- FE ghép lịch sử theo `request_id` và thiết bị; ACK đến sớm không bị response `SENT` cũ ghi đè. Refresh lấy lại lịch sử từ DB. Không tự gửi lại POST khi reconnect để tránh lệnh trùng.
- `TEST_ALERT` thử LED, còi và motor trong một lệnh; **không chọn severity**. Mức 1–3 thuộc cảnh báo buồn ngủ/cấu hình theo severity. Thời lượng và JSON hiện là hợp đồng tạm, TV1/TV2 cần chốt.
- TV2 cần cung cấp `POST /api/devices/{id}/commands`, `GET /api/commands`, `GET /api/commands/{request_id}`, lưu DB, MQTT/ACK, và kiểm tra quyền ở server. Các route này chưa có trong BE hiện tại.

## 4. Sequence — đổi cấu hình mong muốn và xác nhận thiết bị áp dụng

```mermaid
sequenceDiagram
    autonumber
    actor U as Admin hoặc Employee
    participant FE as Frontend
    participant BE as Backend
    participant DB as PostgreSQL
    participant MQ as MQTT broker
    participant ESP as ESP32 Alert Node
    FE->>BE: GET /api/devices/{id}/config
    BE-->>FE: desired + applied và mã cấu hình
    U->>FE: Sửa thời gian bật/tắt theo mức 1–3
    FE->>FE: Kiểm tra số nguyên, đơn vị ms, giới hạn
    FE->>BE: PUT /api/devices/{id}/config
    BE->>BE: Kiểm tra role, thiết bị, dữ liệu
    BE->>DB: Lưu desired với config_id mới
    BE->>MQ: Gửi cấu hình cho ESP32
    BE-->>FE: config_id, trạng thái chờ
    FE-->>U: Cấu hình đã lưu; chờ thiết bị áp dụng
    MQ-->>ESP: Chuyển cấu hình
    ESP->>ESP: Áp dụng cấu hình
    ESP->>MQ: Status có applied_config_id
    MQ->>BE: Chuyển status
    BE->>DB: Lưu applied khi ID khớp
    BE-->>FE: config.updated hoặc FE GET lại config
    FE-->>U: Thiết bị đã áp dụng khi hai mã khớp
```

`desired` là **cấu hình đã lưu trên hệ thống**; `applied` là **cấu hình thiết bị xác nhận đang dùng**. Thiết bị offline vẫn có thể có desired mới và applied cũ. Lệnh kiểm tra cảnh báo có thời lượng riêng, nên không dùng lệnh đó để chứng minh cấu hình mặc định đã đổi nếu các tham số riêng ghi đè cấu hình.

FE hiện gọi tạm `GET/PUT /api/devices/{id}/config` và dùng `timings.{led,buzzer,motor}.{1,2,3}.{on_ms,off_ms}`. TV1/TV2 chưa chốt JSON, giới hạn và route thật; hai bên phải thống nhất trước khi đánh dấu phần này PASS.

## 5. Lifecycle — trạng thái quản lý khác trạng thái kết nối

```mermaid
stateDiagram-v2
    [*] --> REGISTERED: Đăng ký
    REGISTERED --> PROVISIONED: Cấp thông tin kết nối
    PROVISIONED --> ACTIVE: Kích hoạt
    ACTIVE --> MAINTENANCE: Chuyển sang bảo trì
    MAINTENANCE --> ACTIVE: Kích hoạt lại nếu BE cho phép
    REGISTERED --> DECOMMISSIONED: Ngừng sử dụng nếu BE cho phép
    PROVISIONED --> DECOMMISSIONED: Ngừng sử dụng nếu BE cho phép
    ACTIVE --> DECOMMISSIONED: Ngừng sử dụng
    MAINTENANCE --> DECOMMISSIONED: Ngừng sử dụng
    DECOMMISSIONED --> [*]
```

Sơ đồ là **đề xuất tuần 2**; TV2 phải chốt chính xác các chuyển trạng thái hợp lệ, đặc biệt kích hoạt lại sau bảo trì và quyền ngừng sử dụng ở từng trạng thái. BE hiện chưa lưu/trả `lifecycle_state`.

| Trường | Giá trị | Ý nghĩa |
| --- | --- | --- |
| `lifecycle_state` | `REGISTERED`, `PROVISIONED`, `ACTIVE`, `MAINTENANCE`, `DECOMMISSIONED` | Thiết bị đang ở bước quản lý nào |
| `status`/connectivity | `ONLINE`, `OFFLINE`, chưa xác định | Thiết bị còn liên lạc gần đây không |
| `last_seen` | Timestamp hoặc `null` | Lần liên lạc hợp lệ cuối; `null` hiển thị “Chưa ghi nhận” |

Ví dụ `ACTIVE + OFFLINE`: đã được phép hoạt động nhưng hiện mất liên lạc. Heartbeat chỉ cập nhật kết nối và `last_seen`, không tự chuyển thiết bị đang bảo trì về `ACTIVE`. `DECOMMISSIONED` cần BE thu hồi quyền kết nối broker và chặn command/config theo policy. FE không tự cấp credential.

FE đã chuẩn bị các route tạm `GET /api/devices/{id}`, `POST /api/devices`, `POST /api/devices/{id}/{provision|activate|maintenance|decommission}`. BE hiện chỉ có `GET /api/devices`; `Device` hiện chưa có `type`, `lifecycle_state`, `firmware_version`. Vì thiếu `type` và lifecycle, FE chưa thể xác nhận điều kiện để bật nút gửi `TEST_ALERT` cho Alert Node.

## 6. Ma trận quyền FE hiện tại

Role lấy từ `GET /api/me`. Đây là **ma trận tạm đúng với `frontend/src/services/permissions.js`**, dùng tên role BE hiện trả (`Admin`, `Employee`, `Customer`). Chỉ người có quyền mới thấy thao tác tương ứng. TV2 phải áp dụng cùng chính sách ở BE; ẩn nút không ngăn được request thủ công.

| Chức năng | Admin | Employee | Customer |
| --- | :---: | :---: | :---: |
| Xem Dashboard và thiết bị được gán | Có | Có | Có |
| Xem lịch sử lệnh | Có | Có | Có |
| Gửi lệnh kiểm tra cảnh báo | Có | Có | Không |
| Xem cấu hình | Có | Có | Có |
| Sửa cấu hình | Có | Có | Không |
| Đăng ký/provision/activate/maintenance | Có | Không | Không |
| Decommission | Có | Không | Không |
| Xem lịch sử cảnh báo | Có | Có | Có |
| Đánh dấu cảnh báo đã xem | Có | Có | Không |

**Phạm vi dữ liệu:** Customer chỉ được xem thiết bị, telemetry, lệnh và cảnh báo thuộc phạm vi BE cấp cho tài khoản. Admin/Employee cũng phải chịu giới hạn thiết bị theo chính sách BE chốt; role rộng không mặc nhiên có quyền xem dữ liệu của mọi người. BE hiện đã lọc `GET /api/devices` theo bảng gán user-device; các API mới và WS cần áp dụng kiểm tra tương ứng.

**Điểm cần TV2 xử lý trước khi demo nhiều tài khoản:** `POST /api/users` hiện trả danh sách user mà chưa có dependency xác thực; `/ws/telemetry` cũng chưa xác thực. Hai đường này phải được bảo vệ theo quyền đã chốt.

**Hai loại ACK khác nhau:** “Đánh dấu cảnh báo đã xem” là thao tác người dùng trên alert. `ACK COMPLETED` của command là kết quả ESP32 thực hiện lệnh; không dùng một trạng thái để thay cho trạng thái kia.

## 7. Hợp đồng API và sự kiện thực tế (Đã tích hợp thành công)

| Nhóm | Trạng thái BE | Chi tiết tích hợp FE–BE |
| --- | --- | --- |
| **Auth** | `POST /api/login`, `GET /api/me` | Đã có; phân quyền theo 3 role `Admin`, `Employee`, `Customer`. Trả 401 khi token hết hạn/không hợp lệ. |
| **Device** | `GET /api/devices`, `GET /api/devices/{id}`, `POST /api/devices`, `POST /api/devices/{id}/{provision,activate,maintenance,decommission}` | Đã có; trả về đầy đủ `type`, `lifecycle_state`, `firmware_version`, `status`, `last_seen`. Lọc theo bảng gán `user_devices`. |
| **Telemetry** | `GET /api/{device_id}/telemetry` | Đã có; trả về snapshot số đo `ear`, `perclos`, `driver_state`, `face_detected`, `confidence`. Chỉ áp dụng cho Vision Node. |
| **Command** | `POST /api/devices/{id}/commands`, `GET /api/commands`, `GET /api/commands/{request_id}` | Đã có; hỗ trợ `TEST_ALERT`, tách 3 dispatches cho LED/còi/motor, nhận đủ 3 ACK chuyển `COMPLETED`. |
| **Config** | `GET /api/devices/{id}/config`, `PUT /api/devices/{id}/config` | Đã có; hỗ trợ `desired_config` và `applied_config`. UI hiển thị `Chờ thiết bị áp dụng` chuẩn xác. |
| **Alert** | `GET /api/alerts`, `POST /api/alerts/{id}/acknowledge` | Đã có; xem danh sách cảnh báo và đánh dấu đã xem. |
| **WebSocket** | `POST /api/ws-ticket`, `/ws/telemetry?ticket={ticket}` | Đã có; xác thực ticket một lần, lọc dữ liệu theo user-device, đẩy các sự kiện `telemetry.updated`, `device.updated`, `command.updated`, `alert.created`, `config.updated`. |

Envelope WS thực tế: `{ "type": "command.updated", "data": { "request_id": "cmd-1", "device_id": 2, "status": "ACKNOWLEDGED", "ack_status": "COMPLETED" } }`.

## 8. Báo cáo nghiệm thu hoàn thiện Tuần 2 (TV4-01 đến TV4-09)

1. **TV4-01 (Phân quyền 3 Role):** PASS — Đã test thực tế trên PostgreSQL thật, kiểm tra Admin, Employee, Customer và lọc đúng thiết bị được gán.
2. **TV4-02 (Cô lập dữ liệu):** PASS — Đăng xuất xóa sạch token, ngắt WebSocket cũ; đăng nhập tài khoản khác xin ticket mới, không sót số đo hay thiết bị của người khác.
3. **TV4-03 (Xử lý mã lỗi & Customer View-Only):** PASS — Banner 404 hiển thị chuẩn khi truy cập thiết bị không tồn tại; Customer ẩn toàn bộ nút lệnh/config/vòng đời.
4. **TV4-04 (Lệnh TEST_ALERT & ACK):** PASS — Lệnh tạo `cmd-1` nhận đủ 3 ACK hoàn tất, lưu DB PostgreSQL, F5 vẫn còn nguyên.
5. **TV4-05 (Cấu hình Remote Config):** PASS — Lưu config mong muốn tạo `config_id` mới, UI hiển thị `Chờ thiết bị áp dụng`, không tự ý báo đã áp dụng khi thiết bị chưa xác nhận.
6. **TV4-06 & TV4-07 (Dữ liệu AI & Nguồn Vision Node):** PASS — Khi thiếu số đo hiện `—` và `Chưa có dữ liệu`; số đo chỉ lấy từ Vision Node (`vision-01`).
7. **TV4-08 (Ghi chép kết quả):** PASS — Đã hoàn thành lập bảng kiểm thử chi tiết tại `tests/week3-integration-results.md`.
8. **TV4-09 (Cập nhật tài liệu bàn giao):** PASS — Đã loại bỏ toàn bộ thông tin "BE chưa có API", đồng bộ 100% với hợp đồng API thật.

**Bằng chứng và chi tiết log/ảnh:** Xem tại `tests/week3-integration-results.md`.
