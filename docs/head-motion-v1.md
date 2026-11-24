# Theo dõi chuyển động đầu và quy tắc cảnh báo cúi đầu kéo dài

Tài liệu mô tả phương pháp tính góc tư thế đầu tương đối từ ma trận 3D của MediaPipe, bộ đếm chu kỳ gật đầu và quy tắc phát hiện hành vi cúi đầu kéo dài (`sustained-head-down-v1`).

---

## 1. Khởi chạy và nguyên tắc lấy mốc góc chuẩn

```powershell
./edge-ai/run-multisignal-v2.ps1 -Demo
```

- Khi bắt đầu phiên camera, người ngồi giữ tư thế **nhìn thẳng ổn định trong 5 giây đầu** để hệ thống ghi nhận góc tham chiếu trung tính.
- Từ ma trận biến đổi khuôn mặt 3D (`facial_transformation_matrixes`) của MediaPipe, mô-đun `head_motion.py` phân rã phép quay bằng **SVD** để tách riêng góc quay thực tế khỏi hệ số thu phóng, sau đó tính độ lệch tương đối so với mốc nhìn thẳng ban đầu.

---

## 2. Quy tắc phát hiện cúi đầu kéo dài (`sustained-head-down-v1`)

Quy tắc này bổ sung lớp bảo vệ tư thế cho trường hợp tài xế cúi gục đầu kéo dài ngay cả khi vùng mắt bị gọng kính che khuất:

| Điều kiện góc tư thế | Hành vi xử lý của hệ thống |
|---|---|
| Góc cúi tương đối **`≥ 12°`** duy trì liên tục trong **`3.0 giây`** | Kích hoạt trạng thái ứng viên `DROWSY` với mã lý do `HEAD_DOWN_RISK` |
| Đang trong trạng thái nguy cơ và góc cúi còn **`≥ 8°`** | Duy trì trạng thái nguy cơ (cơ chế trễ hysteresis chống dao động quanh ngưỡng `12°`) |
| Nâng đầu về góc **`< 8°`** ổn định trong **`0.5 giây`** | Xóa cờ nguy cơ tư thế đầu (các nhánh mắt và Random Forest vẫn xét bình thường) |
| Mất khuôn mặt hoặc gián đoạn dữ liệu **`> 0.5 giây`** | Đặt lại bộ đếm thời gian cúi về `0` ngay lập tức |
| Góc quay ngang `> 20°` hoặc nghiêng đầu `> 15°` | Chuyển sang luồng đánh giá quay đầu mất tập trung (`DISTRACTED`) thay vì nhánh cúi thẳng |

- Sau khi đạt `3.0 giây` cúi đầu hợp lệ, bộ xác nhận trạng thái chung kiểm tra thêm `0.5 giây` trước khi bắt đầu tính chu kỳ leo thang cảnh báo IoT ở các mốc `3 / 6 / 10 giây` (tương ứng Mức 1: LED + còi; Mức 2 & 3: LED + còi + motor rung).
- Song song đó, bộ đếm chu kỳ gật đầu trong `head_motion` ghi nhận các nhịp hạ đầu `≥ 12°` rồi ngẩng lên trong khoảng `0.5–4.0 giây` ở chế độ quan sát (`OBSERVE_ONLY`, có bước chờ `REACQUIRING` sau khi che/mở lại camera để tránh đếm nhầm chuyển động lọt vào khung hình).

---

## 3. Luồng tích hợp từ Edge AI tới Giao diện và ESP32

```text
Ma trận tư thế 3D → Góc lệch tương đối → head_down_policy → DROWSY (HEAD_DOWN_RISK)
  → AlertPolicy & Sự kiện MQTT → Backend Rule Engine kiểm tra liên kết / TTL
  → Phát lệnh MQTT xuống ESP32 → Bật LED / Còi / Motor → Phản hồi ACK COMPLETED
```

- Dữ liệu chi tiết của góc đầu và trạng thái quy tắc cúi được đóng gói trực tiếp vào cột JSONB `telemetry.ai_signals` đã có sẵn trên PostgreSQL để đẩy qua REST API / WebSocket lên giao diện giám sát.

### Mã nguồn liên quan
- Tính toán góc 3D & chu kỳ gật: [edge-ai/service/head_motion.py](../edge-ai/service/head_motion.py)
- Quy tắc cúi đầu kéo dài: [edge-ai/service/head_down_risk.py](../edge-ai/service/head_down_risk.py)
- Kết hợp suy luận v2: [edge-ai/ml/multisignal_v2_runtime.py](../edge-ai/ml/multisignal_v2_runtime.py)
- Kiểm tra dữ liệu Backend: [backend/app/schemas/ai_signals.py](../backend/app/schemas/ai_signals.py)
