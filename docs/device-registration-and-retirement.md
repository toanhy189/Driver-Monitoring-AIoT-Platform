# Quy trình đăng ký, phân loại và ngừng sử dụng thiết bị

Tài liệu mô tả quy tắc phân loại thiết bị khi đăng ký mới, điều kiện xóa hồ sơ tạo nhầm và quy trình ngừng sử dụng (`Decommission`) đối với thiết bị đã vận hành.

---

## 1. Phân loại thiết bị bắt buộc khi đăng ký

Tại màn hình **Thiết bị → Đăng ký thiết bị**, quản trị viên (`Admin`) chọn rõ vai trò phần cứng của node:

| Phân loại trên giao diện | Giá trị `device_type` | Chức năng trong hệ thống |
| --- | --- | --- |
| **Camera AI** | `VISION_NODE` | Thu thập và gửi số đo, trạng thái tài xế, sự kiện AI, video clip; đóng vai trò nguồn phát trong liên kết cảnh báo tự động |
| **Bộ cảnh báo ESP32** | `ALERT_NODE` | Nhận lệnh điều khiển LED/còi/motor, lưu cấu hình nhịp cảnh báo, gửi heartbeat, phản hồi `ACK` và hỗ trợ cập nhật OTA |

- Trường `device_code` có thể nhập cụ thể để khớp với thiết bị đã nạp sẵn cấu hình (chỉ gồm chữ cái, chữ số, dấu gạch ngang `-` hoặc gạch dưới `_`), hoặc để trống để Backend tự động sinh mã duy nhất dạng `vision-<12 ký tự>` / `alert-<12 ký tự>`.
- Sau khi tạo hồ sơ (`REGISTERED`), thiết bị đi qua bước **Cấp thông tin kết nối** (`PROVISIONED` — tạo tài khoản và quyền ACL MQTT đúng theo `device_type`) rồi mới **Kích hoạt** (`ACTIVE`).

```json
{
  "device_code": "vision-02",
  "name": "Camera buồng lái 02",
  "model": "USB Webcam HD",
  "device_type": "VISION_NODE"
}
```

---

## 2. Xóa hồ sơ đăng ký nhầm vs. Ngừng sử dụng thiết bị

Hệ thống phân biệt rõ hai thao tác dựa trên việc thiết bị đã từng phát sinh dữ liệu hay chưa:

### 2.1. Xóa đăng ký nhầm (`DELETE /api/devices/{id}`)
- Chỉ khả dụng khi hồ sơ vừa tạo còn ở trạng thái `REGISTERED`, `OFFLINE`, **chưa cấp tài khoản MQTT**, chưa gán cho người dùng nào khác và chưa phát sinh bất kỳ bản ghi số đo, sự kiện, cảnh báo, video, lệnh hay cấu hình nào.
- Giúp Admin dọn sạch các hồ sơ gõ nhầm thông tin ngay sau khi tạo mà không làm rác danh sách. Thao tác vẫn được ghi nhận vào `audit_logs`.

### 2.2. Ngừng sử dụng vĩnh viễn (`POST /api/devices/{id}/decommission`)
- Áp dụng cho mọi thiết bị đã từng cấp kết nối MQTT hoặc đã có dữ liệu lịch sử trong hệ thống.
- Khi Admin xác nhận trong hộp thoại **Xác nhận ngừng sử dụng**:
  1. Backend thu hồi ngay tài khoản và quyền kết nối của thiết bị trên Mosquitto Broker (ngắt kết nối hiện tại và chặn đăng nhập lại bằng mật khẩu cũ).
  2. Chuyển `lifecycle_state` sang `DECOMMISSIONED` và đưa thiết bị sang tab **Đã ngừng sử dụng** trên giao diện.
  3. Bảo toàn nguyên vẹn toàn bộ lịch sử số đo, cảnh báo, lệnh và kiểm toán trước đó để phục vụ tra cứu và truy vết.
