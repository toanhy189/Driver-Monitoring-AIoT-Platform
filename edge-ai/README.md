# Edge AI — Thu thập Camera, Suy luận và Huấn luyện

Phân hệ **Vision Node** chạy trên máy tính gắn webcam, thực hiện phát hiện điểm mốc khuôn mặt, phân tích trạng thái tài xế theo thời gian thực, phát âm thanh cảnh báo cục bộ, đồng bộ bản tin MQTT qua hàng đợi SQLite và tải video sự kiện lên Backend.

---

## 1. Khởi chạy nhanh

```powershell
# Kiểm tra gói mô hình v2 và hồ sơ hiệu chuẩn (không mở camera/mạng)
./edge-ai/run-multisignal-v2.ps1 -Demo -Condition glasses -Check

# Chạy phiên giám sát chính thức (camera, âm thanh cục bộ, MQTT và upload video)
./edge-ai/run-multisignal-v2.ps1 -Demo -Condition glasses
```

- Trong **5 giây đầu** khi cửa sổ camera mở lên, giữ đầu nhìn thẳng ổn định để hệ thống thiết lập mốc góc tư thế trung tính; nhấn phím **`Q`** để kết thúc phiên làm việc.
- **Lưu ý khi chạy trên máy mới:** Tải gói model và checksum tại [Release v1.0.0](https://github.com/toanhy189/Driver-Monitoring-AIoT-Platform/releases/tag/v1.0.0). Thư mục `edge-ai/ml-runs/` được loại trừ khỏi Git; sau khi đối chiếu SHA-256, giải nén `regions.pt`, `fusion.joblib`, `manifest.json` vào `edge-ai/ml-runs/multisignal-v2-20261110/selected/` (hoặc truyền `-BundlePath`), đồng thời dùng `-Condition no-glasses` hoặc tạo hồ sơ hiệu chuẩn kính riêng trên máy mới bằng `calibrate_eye_guard.py` (truyền qua `-CalibrationPath` và `-ProfileId`).
- Các cờ `-EyeTrial` và `-HeadTrial` hỗ trợ kiểm tra riêng từng nhánh mắt hoặc tư thế đầu trên máy cục bộ (lưu log chẩn đoán riêng, không gửi bản tin MQTT hay kích hoạt ESP32).
- Khi thay đổi người ngồi thử, webcam hoặc điều kiện đeo kính, thực hiện đo lại hồ sơ hiệu chuẩn theo hướng dẫn tại [docs/eye-guard-calibration.md](../docs/eye-guard-calibration.md).

---

## 2. Kiến trúc đường ống xử lý (AI Pipeline v2)

`Khung hình Webcam` → `MediaPipe FaceLandmarker` → `Hình học (EAR, MAR, Góc đầu) + Crop vùng mắt/miệng (96×96)` → `CNN MobileNetV3-Small` → `Random Forest v2 (cửa sổ 5 giây, 36 đặc trưng) + Guard nhắm mắt EAR + Quy tắc cúi đầu` → `Xác nhận độ bền trạng thái` → `Policy cảnh báo` → `Loa cục bộ + MQTT + Ghi clip MP4`.

- **Mạng CNN hai đầu (`ml/region_net.py`):** Phân loại vùng mắt (`NORMAL` / `SLEEPY`) và vùng miệng (`NORMAL` / `YAWN` / `TALKING_LAUGHING` — giúp phân biệt nói/cười với hành vi ngáp).
- **Mô hình kết hợp Random Forest (`ml/multisignal_v2_runtime.py`):** Tổng hợp 9 kênh tín hiệu × 4 đại lượng thống kê (`mean`, `std`, `p90`, `coverage`) trên cửa sổ 5 giây với ngưỡng trễ kép (hysteresis `0.85` / `0.75`).
- **Nhánh bảo vệ nhắm mắt & tư thế đầu:**
  - Nhắm mắt liên tục `≥ 1.0 giây` dưới ngưỡng hiệu chuẩn kích hoạt nguy cơ `EYE_CLOSURE_RISK`; mở mắt ổn định `≥ 1.0 giây` xóa cờ này.
  - Quay ngang vượt ngưỡng báo `DISTRACTED`; cúi đầu `≥ 12°` liên tục trong `3 giây` báo `DROWSY` (`HEAD_DOWN_RISK`).
  - Khi khuất mặt hoặc gián đoạn dữ liệu quá `0.5 giây`, hệ thống chuyển về `UNKNOWN` và ngắt bộ đếm liên tục.

Chi tiết thiết kế mô hình xem tại [docs/luong-xu-ly-ai-v2.md](../docs/luong-xu-ly-ai-v2.md) và [docs/head-motion-v1.md](../docs/head-motion-v1.md).

---

## 3. Hàng đợi bền vững MQTT & Tải Video nền

- **Định danh & Bảo mật:** Mọi gói tin phát theo không gian tên `driver/{AI_DEVICE_CODE}/...` bằng tài khoản MQTT riêng của Vision Node (`AI_MQTT_USERNAME` / `AI_MQTT_PASSWORD`).
- **SQLite Outbox (`service/storage/sqlite_queue.py`):** Bản tin số đo và sự kiện được gắn `message_id` bất biến, lưu vào SQLite trước khi gửi và chỉ xóa khỏi hàng đợi sau khi nhận phản hồi `storage_ack: SAVED` từ Backend. Khi mất kết nối rồi có mạng lại, các bản tin cũ được gửi bù kèm cờ lịch sử (`backfill`) để lưu DB mà không kích hoạt còi muộn trên ESP32.
- **Upload Video (`service/video/`):** Các đoạn clip `.mp4` được đóng gói và đẩy lên `/api/videos/upload` bởi worker chạy nền (sử dụng HTTP Basic Auth của thiết bị), hoàn toàn không làm nghẽn vòng lặp xử lý khung hình của camera.

> Các thư mục chứa dữ liệu cục bộ, video, tập dữ liệu huấn luyện và trọng số mô hình (`data/`, `recordings/`, `datasets/`, `ml-data/`, `ml-runs/`, `models/`) được loại trừ trong `.gitignore`.

---

## 4. Công cụ huấn luyện và đánh giá mô hình (`ml/`)

| Mô-đun | Chức năng |
|---|---|
| `ml/prepare_nthu.py`, `ml/nthu.py` | Kiểm tra tính toàn vẹn dữ liệu nguồn NTHU-DDD, đối chiếu số frame/nhãn và trích xuất đặc trưng |
| `ml/multisignal_data.py`, `ml/region_net.py` | Cắt vùng ảnh mắt/miệng `96×96`, kiểm tra chất lượng vùng ảnh và định nghĩa kiến trúc MobileNetV3-Small |
| `ml/multisignal_train.py` | Huấn luyện và fine-tune mạng CNN phân loại vùng mắt/miệng |
| `ml/multisignal_v2_train.py`, `ml/multisignal_v2_select.py` | Huấn luyện Random Forest 36 đặc trưng và chọn cặp ngưỡng vào/ra bằng replay theo thời gian |
| `ml/multisignal_evaluate.py`, `ml/multisignal_benchmark.py` | Đánh giá chỉ số phân loại, độ trễ phát hiện theo đợt nguy cơ và đo thời gian suy luận trên CPU |

---

## 5. Kiểm thử tự động và Prometheus Exporter

```powershell
# Chạy toàn bộ unit test của phân hệ Edge AI
./edge-ai/.venv/Scripts/python.exe -X utf8 -m unittest discover -s edge-ai/tests -v

# (Tùy chọn) Bật máy chủ xuất chỉ số FPS / độ trễ / RAM cho Prometheus tại cổng 9108
Push-Location edge-ai
./.venv/Scripts/python.exe -m service.metrics_server --host 127.0.0.1 --port 9108
Pop-Location
```
