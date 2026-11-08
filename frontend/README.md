# Frontend — React / Vite

Dashboard do nhóm tự xây, gọi REST API và nhận cập nhật qua WebSocket. Grafana chỉ là công cụ giám sát phụ trợ.

## Chạy

Cách chính dùng Docker: [README dự án](../README.md).

Chạy Vite khi phát triển, từ gốc repository:

```powershell
npm --prefix frontend ci
npm --prefix frontend run dev
```

Nếu frontend Docker đang dùng cổng 5173, dừng riêng service frontend hoặc chọn cổng Vite khác và cấu hình CORS/origin cho khớp. Không cần cài Python trong thư mục này.

## Chức năng

- Đăng nhập/đăng ký Customer, tài khoản cá nhân, đổi mật khẩu và đăng xuất.
- Admin quản lý tài khoản và assignment; xem thiết bị, cấp kết nối, kích hoạt, bảo trì, decommission.
- Dashboard chọn Vision Node, hiển thị EAR/PERCLOS, trạng thái và biểu đồ.
- Lịch sử telemetry, sự kiện, cảnh báo, lệnh và video có kiểm tra quyền.
- Employee/Admin gửi TEST_ALERT, theo dõi kết quả; sửa cấu hình desired/applied.
- WebSocket dùng ticket từ Backend, reconnect và tải lại snapshot khi cần.

`App.jsx` điều phối phiên và trang. Các cặp `Page/View` hoặc `Dashboard/DashboardView` tách xử lý dữ liệu với trình bày; cả hai phần đều đang dùng. Quyền UI tại `src/services/permissions.js`; Backend vẫn kiểm tra quyền độc lập.

Dữ liệu thiếu hiển thị dấu `—`; dữ liệu cũ được đánh dấu khi mất kết nối. Kết nối WebSocket không đồng nghĩa ESP32 ONLINE. FE không tự suy ra trạng thái tài xế từ EAR hoặc dùng dữ liệu mẫu để thay dữ liệu thật.

## API và cấu hình

- Prefix API mặc định `/api`; Docker Nginx proxy API và WebSocket về Backend.
- Native Vite dùng cấu hình trong `vite.config.js` và các biến `VITE_*` tương ứng.
- MQTT consumer nằm trong Backend, không chạy script MQTT riêng để cập nhật web.
- Contract: [FE–BE](../docs/week2-fe-be-contract.md), [AI/video](../docs/ai-ingest-video-contract.md).

## Kiểm tra

```powershell
node --test frontend/tests/*.test.mjs
npm --prefix frontend run build
```

Demo 10 bước: [README](../README.md#4-demo-theo-mục-84-của-đề-bài). Khi thử quyền Customer bằng API, phải dùng JWT Customer; ẩn nút trên giao diện chưa đủ chứng minh API đã chặn.
