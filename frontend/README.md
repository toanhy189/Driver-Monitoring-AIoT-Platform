# Frontend — dữ liệu thiết bị và telemetry

## Cấu trúc FE đang nhận

Theo API hiện tại, `GET /api/devices` trả danh sách với `id` là số nguyên dương
và `device_code` là mã thiết bị. FE dùng `id` để nhận diện record, dùng
`device_code` để hiển thị. Không đổi ID `1` thành mã `vision-01` bằng quy tắc tự đặt.

Telemetry gửi đến FE dùng `device_id` để chỉ ID số đó:

```json
{
  "device_id": 42,
  "device_code": "DM-000001",
  "ear": 0.21,
  "perclos": 0.35,
  "driver_state": "DROWSY"
}
```

Đây là cấu trúc FE đã chuẩn bị hỗ trợ; TV2/TV3 cần xác nhận và bổ sung phần BE
còn thiếu trước khi thử tích hợp. ID/mã trong ví dụ không phải dữ liệu cố định.

- `device_id` bắt buộc là số nguyên dương; chuỗi `"vision-01"` hoặc `"42"`
  không được dùng thay ID DB. Payload sai sẽ hiện lỗi dữ liệu, không hiện số đo cũ.
- `device_code` là chuỗi BE cung cấp. Nếu thiếu/null, FE hiện chưa có mã;
  không dùng `device_id` làm mã hiển thị.
- EAR/PERCLOS thiếu, null hoặc không phải số hữu hạn thì hiện `—`.
  PERCLOS `0.35` hiện 35%; `0` thật vẫn hiện 0%.
- `driver_state` chỉ nhận `ATTENTIVE`, `DISTRACTED`, `DROWSY`. Thiếu hoặc sai
  giá trị thì hiện “Chưa xác định”; FE không phân loại tài xế từ EAR/PERCLOS.
- Mỗi tin telemetry là một bản số đo mới, không phải bản cập nhật từng trường.
  Trường thiếu sẽ không giữ giá trị của tin trước.

Socket hiện hỗ trợ JSON telemetry trực tiếp như trên hoặc envelope đề xuất:

```json
{
  "type": "telemetry.updated",
  "data": {
    "device_id": 42,
    "device_code": "DM-000001",
    "ear": 0.21,
    "perclos": 0.35,
    "driver_state": "DROWSY"
  }
}
```

`device.updated` là tin trạng thái thiết bị riêng: ID số nằm trong `id` hoặc
`device_id`, mã nằm trong `device_code`. Nếu chỉ có mã thì phải ghi đúng trường
`device_code`. Nếu gửi cả ID và mã, cả hai phải khớp cùng record từ API.
FE không nhận mã chuỗi trong trường ID để cập nhật online/offline.

## Phần cần TV2/TV3 hoàn thiện

- Thống nhất và cung cấp `driver_state` trong luồng nhận/lưu/trả telemetry.
- BE ánh xạ mã MQTT sang ID DB và trả đúng cặp ID/mã.
- Endpoint telemetry phải trả đủ các trường schema yêu cầu.
- Cung cấp WebSocket để FE nhận dữ liệu thật; thống nhất URL và envelope.

Thay đổi FE này chưa sửa database, backend hay firmware. Dashboard hiện hiển thị
bản telemetry mới nhất nhận được và mã nguồn số đo; chưa có bộ chọn luồng AI.

## Kiểm tra

Chạy ở thư mục `frontend`:

```powershell
node --test tests/telemetry.test.mjs
npm run build
```

Các kiểm tra trên xác nhận xử lý dữ liệu và build. Luồng MQTT → BE → DB → WS → FE
vẫn cần thử với dịch vụ thật để đánh dấu PASS tuần 1.
