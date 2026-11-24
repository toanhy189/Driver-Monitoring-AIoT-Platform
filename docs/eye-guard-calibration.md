# Hiệu chuẩn ngưỡng mắt đeo kính cho AI v2

Tài liệu hướng dẫn quy trình đo và tạo hồ sơ hiệu chuẩn cá nhân (`Calibration Profile`) cho nhánh phát hiện nhắm mắt kéo dài trên Vision Node.

---

## 1. Khi nào cần chạy hiệu chuẩn?

- Trên máy tính và góc đặt camera cố định đã có sẵn hồ sơ đạt chuẩn, chỉ cần chạy trực tiếp lệnh `./edge-ai/run-multisignal-v2.ps1 -Demo` mà không phải đo lại mỗi lần mở máy.
- Chỉ thực hiện hiệu chuẩn mới khi **thay đổi người ngồi trước camera, đổi gọng kính, đổi webcam, đổi độ phân giải hoặc thay đổi đáng kể vị trí đặt camera / ánh sáng**.
- Hồ sơ hiệu chuẩn có nhiệm vụ xác định mốc hướng đầu nhìn thẳng và ngưỡng chỉ số mở mắt `EAR` phù hợp cho nhánh bảo vệ nhắm mắt liên tục (`Eye Closure Guard`), hoạt động bổ trợ độc lập bên cạnh mạng CNN và Random Forest.

---

## 2. Các bước đo hiệu chuẩn trên máy trạm

Đảm bảo không có tiến trình nào khác đang giữ webcam, sau đó chạy lệnh từ thư mục gốc của dự án:

```powershell
./edge-ai/.venv/Scripts/python.exe -X utf8 edge-ai/calibrate_eye_guard.py --v2 --profile-id operator-01-webcam-0 --condition glasses
```

*(Chọn `--condition glasses` khi người lái đeo kính hoặc `--condition no-glasses` khi không đeo kính; `--profile-id` là tên định danh cho cấu hình người/camera đó).*

Khi cửa sổ **Eye calibration (local only)** xuất hiện, bấm phím số tương ứng để thực hiện tuần tự **4 lượt đo** (mỗi lượt có 2 giây chuẩn bị và tiếng bíp báo kết thúc):

| Phím | Thao tác thực hiện trước camera | Thời lượng đo | Vai trò dữ liệu |
| :---: | :--- | :---: | :--- |
| **`1`** | Nhìn thẳng tự nhiên, mở mắt và chớp mắt bình thường | `8 giây` | Lượt **FIT 1** (tính trung vị EAR mắt mở & mốc góc đầu) |
| **`2`** | Nhắm kín hai mắt giữ nguyên | `8 giây` | Lượt **FIT 2** (tính trung vị EAR mắt nhắm) |
| **`3`** | Nhìn thẳng, mở mắt và nói chuyện bình thường | `30 giây` | Lượt **Kiểm chứng 1** (đảm bảo nói/chớp mắt không báo giả) |
| **`4`** | Nhắm kín hai mắt giữ nguyên | `8 giây` | Lượt **Kiểm chứng 2** (kiểm tra độ lặp lại khi nhắm mắt) |

- Công cụ chỉ lưu tệp số đo `.csv` và báo cáo `report.json` vào thư mục cục bộ `edge-ai/ml-runs/eye-calibration/` (đã nằm trong `.gitignore`), không lưu hình ảnh khuôn mặt và không phát bản tin MQTT.

---

## 3. Tiêu chuẩn kiểm định tự động của Profile

1. **Cách tính ngưỡng (`v5`):** Ngưỡng `EAR` được xác định bằng trung điểm giữa trung vị `EAR` mắt mở (Lượt 1) và trung vị `EAR` mắt nhắm (Lượt 2), tạo biên an toàn đều về hai phía.
2. **Điều kiện đạt (`Quality Gate`):**
   - Khoảng cách phân bố giữa mắt mở và mắt nhắm tách biệt rõ ràng, dữ liệu liên tục không bị đứt quãng.
   - Trong suốt Lượt 1 và Lượt 3 (mở mắt & nói chuyện), bộ bảo vệ không phát sinh bất kỳ cảnh báo nhắm mắt giả nào.
   - Trong các lượt nhắm mắt (Lượt 2 và Lượt 4), tỷ lệ thời gian `EAR` nằm dưới ngưỡng đạt tối thiểu `90%`.
3. **Sử dụng Profile mới:** Khi kết quả cuối báo đạt, truyền đường dẫn `report.json` vừa sinh ra qua tham số `-CalibrationPath` cùng `-ProfileId` tương ứng cho `run-multisignal-v2.ps1`.

Tham khảo thêm: [Thiết kế luồng xử lý AI v2](luong-xu-ly-ai-v2.md) · [Theo dõi hướng đầu và cảnh báo cúi đầu](head-motion-v1.md).
