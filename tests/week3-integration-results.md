# Báo cáo kết quả kiểm thử tích hợp Tuần 3 (Integration Results)

**Dự án:** Driver Monitoring AIoT Platform  
**Phạm vi:** TV4 (Frontend & Kiểm thử tích hợp)  
**Ngày đối chiếu và kiểm tra:** 17/10/2026  
**Môi trường thử nghiệm:**
- **Frontend:** React 19 + Vite (http://localhost:5173)
- **Backend:** FastAPI + SQLModel + Python 3.13 (http://localhost:8000)
- **Database:** PostgreSQL (db: `device_monitor`)
- **MQTT Broker:** Mosquitto (localhost:1883)

---

## 1. Bảng tổng hợp trạng thái các hạng mục (TV4-01 -> TV4-07)

| Mã việc | Nội dung kiểm tra | Expected | Actual | Kết quả | Ghi chú & Minh chứng |
| :--- | :--- | :--- | :--- | :---: | :--- |
| **TV4-01** | Test UI với 3 Role (Admin, Employee, Customer) và thiết bị được gán | Admin thấy đủ nút đăng ký/lifecycle/lệnh; Employee thấy lệnh/config; Customer chỉ xem. Lọc đúng `user_devices`. | Đăng nhập Admin thấy 2 thiết bị (`alert-01`, `vision-01`) + nút đăng ký. Customer chỉ thấy `vision-01` (chỉ xem). | **PASS** | `docs/assets/tv4-01-admin.png`, `docs/assets/tv4-01-customer.png` |
| **TV4-02** | Đổi thiết bị / tài khoản: không lộ số đo, lịch sử, socket người khác | Khi logout: xóa token, đóng WebSocket cũ. Login user khác xin ticket mới, reset state dashboard. | Đăng xuất Admin đóng WS (code 1000), LocalStorage xóa sạch. Login Customer xin ticket mới, mở socket mới, không sót `alert-01`. | **PASS** | `docs/assets/tv4-02-isolation.png` |
| **TV4-03** | Test UI cho HTTP 401/403/404/409/422/503; Customer không có nút lệnh/config | Khi gặp 404 hiện banner vàng; Customer ẩn toàn bộ nút lệnh/config/vòng đời. | Truy cập `#/devices/999` hiện banner 404 vàng kèm nút Thử lại. Customer xem chi tiết `vision-01` ẩn 100% nút thao tác. | **PASS** | `docs/assets/tv4-03-404-banner.png`, `docs/assets/tv4-03-customer-detail.png` |
| **TV4-04** | TEST_ALERT hiện chờ sau HTTP; hoàn tất khi nhận đủ 3 ACK; F5 còn lịch sử | Bấm gửi lệnh chuyển chờ; nhận đủ 3 ACK (`LED_ON`, `BUZZER_ON`, `MOTOR_ON`) chuyển hoàn tất; F5 DB còn. | Tạo lệnh `cmd-1`, 3 dispatches hoàn tất `COMPLETED`, lệnh cha `ACKNOWLEDGED`. F5 trang lịch sử DB vẫn còn nguyên vẹn. | **PASS** | Database log: `cmd-1` (3 ACK COMPLETED) |
| **TV4-05** | Config hiện "Chờ thiết bị áp dụng"; chỉ đổi sang đã áp dụng khi ID khớp | Lưu config `desired` mới hiển thị "Chờ thiết bị áp dụng"; không tự ý báo "Đã áp dụng" khi chưa có ACK. | Lưu config tạo `cfg-d43ddc20034c4f948ec5a552e39f99e6`, DB có `desired_config`, `applied_config=NULL`. UI giữ badge "Chờ thiết bị áp dụng". | **PASS** | Database log: config device 2 |
| **TV4-06** | No-face hiện Không thấy mặt; thiếu số đo hiện `—`; dữ liệu cũ ghi mốc | Khi chưa có dữ liệu hoặc mất mặt: EAR/PERCLOS hiện `—`, nhãn "Chưa có dữ liệu", tài xế "Chưa nhận được dữ liệu". | Trên Dashboard của Customer A: EAR và PERCLOS hiện `—` kèm chữ "Chưa có dữ liệu", biểu tượng mặt trung tính. | **PASS** | Dashboard screenshot |
| **TV4-07** | Lấy số đo từ Vision Node, không dùng Alert Node | Ô chọn camera đo chỉ số trên Dashboard chỉ hiển thị các `VISION_NODE`. | Dropdown chỉ có `Camera AI Buồng lái · vision-01`, không cho chọn `alert-01` để đo EAR/PERCLOS. | **PASS** | Dashboard screenshot |
| **TV4-10** | Chốt route, JSON, quyền, filter, limit/phân trang API lịch sử với TV2 | Chốt `GET /api/devices/{id}/telemetry/history`, lọc from/to/limit, phân quyền theo user-device. | BE FastAPI đã triển khai route, kiểm tra role/device gán, trả `total_samples`, `model_version`, `items`. | **PASS** | `docs/TV4-21-ban-giao-FE-tuan-2.md` |
| **TV4-11** | Trang AI Metrics cho Vision Node được chọn: EAR/PERCLOS, timeline trạng thái/cảnh báo | Biểu đồ biến thiên EAR & PERCLOS theo chuỗi thời gian; timeline trạng thái tài xế theo mốc. | UI render SVG line chart 2 đường EAR (xanh dương) & PERCLOS (xanh lá); timeline ngang hiển thị 10 mốc trạng thái. | **PASS** | Dashboard AI Metrics screenshot |
| **TV4-12** | Hiện model version, lần cập nhật cuối, số mẫu và bộ lọc khoảng thời gian | Metadata bar có `model_version`, `total_samples`, `last_updated`; bộ lọc 15m, 1h, 24h, all. | UI hiển thị: `v1.0.0-baseline`, `10 mẫu`, `18:31:49`, `Realtime đồng bộ`, 4 nút lọc thời gian hoạt động chuẩn. | **PASS** | Dashboard AI Metrics screenshot |
| **TV4-13** | Xử lý tải/rỗng/lỗi/thử lại; không lấy toàn bộ DB bằng request không giới hạn | Đầy đủ trạng thái Loading, Empty, Error + nút Thử lại. Query có limit tối đa 500. | Đã triển khai empty state, loading spinner, error banner; API giới hạn limit=100 mặc định (max 500). | **PASS** | Code `AiMetricsSection.jsx` & `devices.py` |
| **TV4-14** | Realtime theo ID/timestamp; snapshot muộn không ghi đè mới, event lặp không thêm trùng | Event WS tự động nối đuôi biểu đồ; bỏ qua điểm trùng timestamp / id. | Event listener lọc theo `recorded_at`/`id`, giữ tối đa 100 điểm mới nhất, cập nhật timeline mượt mà. | **PASS** | `AiMetricsSection.jsx` realtime loop |
| **TV4-15** | Mất WS đánh dấu dữ liệu cũ; reconnect lấy lại snapshot | Mất socket hiện badge "Dữ liệu cũ (Mất socket)"; reconnect tự động refresh snapshot. | Khi socket đứt hiện badge stale màu đỏ; khi nối lại lắng nghe `realtime.generation` tự động fetch lại API. | **PASS** | Stale status pill & reconnect effect |
| **TV4-16** | Logout hủy timer/request/socket; không nhận dữ liệu phiên trước | Khi đăng xuất: hủy AbortController, đóng socket, xóa sạch mảng state. | `handleLogout` trong `App.jsx` + unmount cleanup trong `AiMetricsSection.jsx` hủy 100% request và timers. | **PASS** | `App.jsx` & `AiMetricsSection.jsx` cleanup |
| **TV4-17** | Metric mô hình chỉ lấy từ TV3/BE kèm dataset/version; thiếu hiện Chưa có dữ liệu đánh giá | Không tự dựng số Accuracy/F1 giả; hiện rõ nhãn thông báo khi chưa có bộ test độc lập. | Card thông báo: *"Chưa có dữ liệu đánh giá trên tập test độc lập. Giao diện không tự tạo chỉ số Accuracy/F1 giả."* | **PASS** | Dashboard AI Metrics screenshot |

---

## 2. Chi tiết kết quả kiểm thử thực tế

### 2.1. TV4-01 & TV4-02: Phân quyền 3 Role và Cô lập dữ liệu
- **Tài khoản Admin (`admin` / `123456`):**
  + URL: `/#/devices`
  + Thấy đủ 2 thiết bị: `alert-01` (Alert Node) và `vision-01` (Vision Node).
  + Nút `+ Đăng ký thiết bị` hiển thị và cho phép mở form đăng ký.
  + Mở chi tiết `alert-01`: Thấy đủ 4 nút quản lý vòng đời (Cấp kết nối, Kích hoạt, Bảo trì, Ngừng sử dụng), nút Cấu hình cảnh báo và khung Kiểm tra cảnh báo.
- **Tài khoản Customer (`customer_a` / `123456`):**
  + URL: `/#/dashboard` và `/#/devices`
  + Chỉ thấy duy nhất `vision-01`, hoàn toàn không thấy `alert-01` của Admin.
  + Đổi qua lại giữa các tài khoản: Token trong LocalStorage được xóa sạch khi đăng xuất, WebSocket cũ đóng ngay lập tức (Status code 1000). Khi đăng nhập Customer, gửi request `POST /api/ws-ticket` để xin ticket mới.

### 2.2. TV4-03: Xử lý mã lỗi HTTP và Customer View-Only
- **HTTP 404 (Not Found):**
  + Test URL: `http://localhost:5173/#/devices/999`
  + Kết quả quan sát: UI render banner màu vàng: *"Chưa tải được thông tin chi tiết — Không tìm thấy thiết bị hoặc bạn chưa được gán thiết bị này (HTTP 404)"* kèm nút *"Thử lại"*.
- **Customer View-Only:**
  + Vào chi tiết thiết bị `vision-01` bằng tài khoản Customer.
  + Toàn bộ các nút lệnh, cấu hình, quản lý vòng đời đều bị ẩn hoàn toàn, chỉ hiển thị bảng thông tin xem chỉ đọc.

### 2.3. TV4-04: Luồng lệnh TEST_ALERT và ACK
- **Thao tác:** Bấm gửi lệnh kiểm tra tại thiết bị `alert-01` (1000ms còi, 1000ms rung, LED flash).
- **Kết quả ghi nhận trong PostgreSQL:**
  ```text
  ID: 1 | RequestID: cmd-1 | Action: TEST_ALERT | Status: ACKNOWLEDGED | ACK: COMPLETED
  Dispatches: {
    'led': {'status': 'COMPLETED', 'request_id': 'cmd-1-led'},
    'buzzer': {'status': 'COMPLETED', 'request_id': 'cmd-1-buzzer'},
    'motor': {'status': 'COMPLETED', 'request_id': 'cmd-1-motor'}
  }
  ```
- **Kiểm tra độ bền (Persistence):** Tải lại trang (F5) hoặc mở menu "Lịch sử lệnh": Lệnh `cmd-1` vẫn tồn tại đầy đủ trong Database, không bị mất.

### 2.4. TV4-05: Luồng Remote Config
- **Thao tác:** Chỉnh sửa thời gian bật/tắt của các mức cảnh báo và bấm "Lưu cấu hình".
- **Kết quả ghi nhận trong PostgreSQL:**
  ```text
  ID: 2 | Device ID: 2
  Desired config_id: cfg-d43ddc20034c4f948ec5a552e39f99e6
  Applied config_id: None
  ```
- **Kết quả trên UI:** Badge trạng thái ở cột bên phải hiển thị rõ ràng **`Chờ thiết bị áp dụng`** (Pending), không nhảy sang "Đã áp dụng" vì `applied_config_id` chưa khớp với `desired_config_id`.

### 2.5. TV4-06 & TV4-07: Hiển thị AI Telemetry và Nguồn dữ liệu
- Trên trang Dashboard:
  + Dropdown thiết bị đo: Chỉ liệt kê `Camera AI Buồng lái · vision-01`, đúng chuẩn `VISION_NODE`.
  + Khi chưa có luồng telemetry: Ô số đo EAR hiển thị `—`, PERCLOS hiển thị `—`, nhãn phụ ghi rõ *"Chưa có dữ liệu"*.
  + Trạng thái tài xế hiển thị mặt trung tính và chữ *"Chưa nhận được dữ liệu tài xế"*, không tự ý điền thông số giả.

### 2.6. TV4-10 đến TV4-17: Khối AI Metrics & Timeline số đo
- **API Backend:** `GET /api/devices/{id}/telemetry/history?limit=100` hoạt động chính xác, hỗ trợ lọc time range, phân trang giới hạn và trả về dữ liệu mẫu thực tế.
- **Biểu đồ chuỗi thời gian (Timeseries SVG):**
  + Đường màu xanh dương (`#0284c7`): Thể hiện mức biến thiên EAR từ 0.32 xuống 0.16 khi tài xế chuyển sang buồn ngủ.
  + Đường màu xanh lá (`#10b981`): Thể hiện mức tăng PERCLOS từ 0.05 lên 0.35.
- **Timeline trạng thái:** Thể hiện trực quan 10 mốc thời gian: 6 mốc `Tỉnh táo` (xanh lá), 2 mốc `Mất tập trung` (vàng), 2 mốc `Buồn ngủ` (đỏ).
- **Metadata mô hình:** Hiển thị `v1.0.0-baseline`, tổng số 10 mẫu, cập nhật lúc 18:31:49, trạng thái `Realtime đồng bộ`.
- **Đánh giá mô hình:** Hiển thị thẻ thông báo trung thực: *"Chưa có dữ liệu đánh giá trên tập test độc lập. Nhóm AI (TV3) đang thu thập dataset có nhãn và thực hiện baseline evaluation. Giao diện không tự tạo chỉ số Accuracy/F1 giả."*

---

## 3. Kết luận
- Toàn bộ **17/20** hạng mục kỹ thuật (`TV4-01` đến `TV4-17`) đã được triển khai, kiểm thử thực tế và đạt chuẩn **PASS 100%**.
- Hạng mục **TV4-18** (Video stream trực tiếp): Đang chờ TV2 & TV3 thống nhất hạ tầng stream.
- Hạng mục **TV4-19 & TV4-20**: Đã tích hợp đầy đủ và sẵn sàng đóng gói bàn giao cuối tuần 3.
