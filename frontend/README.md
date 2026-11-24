# Frontend — React / Vite

Ứng dụng giao diện Web quản lý và giám sát hệ thống, xây dựng bằng **React + Vite**, giao tiếp với Backend qua REST API và nhận dữ liệu trực tiếp qua WebSocket.

---

## 1. Khởi chạy

- **Chạy qua Docker Compose (mặc định):** Truy cập tại `http://localhost:5173` sau khi bật cụm dịch vụ theo [README dự án](../README.md).
- **Chạy trực tiếp bằng Vite khi phát triển giao diện** (từ thư mục gốc của repository):

```powershell
npm --prefix frontend ci
npm --prefix frontend run dev
```

*(Nếu container `frontend` của Docker đang chiếm cổng `5173`, có thể tạm dừng service `frontend` trong Compose hoặc đổi cổng chạy Vite và cập nhật biến `FRONTEND_HOST` tương ứng).*

---

## 2. Các phân hệ chức năng trên giao diện

- **Tài khoản & Phiên làm việc:** Đăng nhập, đăng ký tài khoản `Customer`, cập nhật thông tin cá nhân, đổi mật khẩu và đăng xuất.
- **Quản trị hệ thống (`Admin`):** Quản lý danh sách người dùng, khóa/mở khóa tài khoản, gán/thu hồi thiết bị, đăng ký mới và chuyển đổi vòng đời thiết bị (`REGISTERED` → `PROVISIONED` → `ACTIVE` ↔ `MAINTENANCE` → `DECOMMISSIONED`), liên kết tự động Camera–ESP32 và quản lý kho **Firmware / OTA**.
- **Giám sát thời gian thực:** Chọn thiết bị `Vision Node` để theo dõi trạng thái tài xế, các chỉ số `EAR`, `PERCLOS`, `MAR`, tư thế đầu, biểu đồ chuỗi thời gian và thanh diễn biến trạng thái (Timeline).
- **Lịch sử, Cảnh báo & Video:** Tra cứu lịch sử số đo/sự kiện/lệnh theo khoảng thời gian, phát trực tiếp hoặc tải clip `.mp4` gắn với cảnh báo và đánh dấu đã xem cho từng tài khoản.
- **Điều khiển & Cấu hình từ xa (`Admin` / `Employee`):** Gửi lệnh **Kiểm tra cảnh báo** (`TEST_ALERT`) theo dõi phản hồi `ACK`, chỉnh thông số thời gian bật/tắt (ms) cho 3 mức cảnh báo và đối chiếu trạng thái `Đã lưu` (`desired`) với `Đã áp dụng` (`applied`).

### Tổ chức mã nguồn chính
- `src/App.jsx`: Điều phối phiên đăng nhập, kết nối WebSocket (qua vé một lần `/api/ws-ticket`) và định tuyến màn hình.
- `src/pages/` & `src/components/`: Tách bạch các thành phần xử lý dữ liệu và hiển thị theo từng nghiệp vụ.
- `src/services/permissions.js`: Định nghĩa bảng quyền hiển thị trên giao diện theo vai trò (song song với lớp kiểm tra quyền độc lập ở Backend).

---

## 3. Kiểm thử và đóng gói bản Production

```powershell
node --test frontend/tests/*.test.mjs
npm --prefix frontend run build
```

Tham khảo thêm: [Hợp đồng API FE–BE](../docs/week2-fe-be-contract.md) · [Phân quyền & Thống kê số đo](../docs/roles-and-device-metrics.md).
