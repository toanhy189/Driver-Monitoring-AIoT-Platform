# Theo dõi hướng đầu và cảnh báo cúi đầu kéo dài

## Chạy demo

```powershell
./edge-ai/run-multisignal-v2.ps1 -Demo
```

Nhìn thẳng và giữ đầu tương đối yên 5 giây đầu để lấy mốc. Sau đó cúi vừa phải, giữ mặt trong khung. Q thoát. Không cần profile hiệu chuẩn mắt khi cúi.

## Quy tắc đang dùng

`sustained-head-down-v1` là quy tắc tư thế theo yêu cầu demo. Cúi chủ động đọc bàn cũng có thể kích hoạt; đây không phải kết quả xác nhận người đó ngủ.

| Điều kiện | Xử lý |
|---|---|
| Góc cúi tương đối ≥12°, quan sát hợp lệ liên tục 3 giây | Ứng viên DROWSY, lý do `HEAD_DOWN_RISK` |
| Đã có nguy cơ, góc còn ≥8° | Giữ nguy cơ để tránh dao động sát ngưỡng |
| Góc dưới 8° liên tục 0,5 giây | Xóa nguy cơ tư thế; mắt/RF vẫn được xét |
| Mất mặt/ma trận, gap >0,5 giây, thời gian lùi | Ngắt bộ đếm ngay |
| Quay ngang >20°, nghiêng >15° hoặc pitch ngoài −15°..40° | Không dùng nhánh cúi; luồng hướng đầu/UNKNOWN vẫn hoạt động |

Policy chung xác nhận DROWSY thêm 0,5 giây. Sau đó tăng mức ở 3/6/10 giây: mức 1 LED+còi, mức 2/3 thêm motor; mức 3 đề nghị nhắc mỗi 5 giây. Cảnh báo IoT đầu tiên dự kiến khoảng 6,5 giây tính từ lúc cúi hợp lệ, không phải ngay giây thứ ba.

## Đo góc và đếm gật

MediaPipe cung cấp ma trận tư thế; SVD tách quay khỏi scale, rồi tính góc tương đối so với mốc nhìn thẳng ổn định. Khởi động cần nhìn thẳng; chương trình không tự biết tư thế ban đầu đã bị cúi. Chiều dọc dương đã đối chiếu trên camera hiện tại.

`head_motion` đo góc và đếm chu kỳ gật ở chế độ `OBSERVE_ONLY`. Một chu kỳ cần hạ ít nhất 12° rồi trở về gần mốc, dài 0,5–4 giây; hai chu kỳ trong 20 giây được ghi là lặp lại. Bộ đếm này không tự tạo DROWSY.

`head_down_policy` độc lập dùng tư thế hiện tại để tạo nguy cơ cúi kéo dài. Sau mất quan sát nó phải đếm lại 3 giây, dù bộ đếm gật đang chờ `REACQUIRING`; không cộng khoảng thiếu quan sát hoặc tạo gật giả khi bỏ che.

## Tích hợp AI → Backend → DB → web → ESP32

```text
Ma trận mặt → góc tương đối → head_down_policy → DROWSY/HEAD_DOWN_RISK
 → policy và event MQTT → Backend kiểm tra phiên/độ mới/binding
 → lệnh LED/còi/motor → ESP32 → ACK

ai_signals.head_motion + head_down_policy
 → telemetry MQTT → schema Backend → telemetry.ai_signals JSONB
 → API/WebSocket → khung hướng đầu và cảnh báo cúi trên web
```

Không thêm cột hoặc sửa giao thức firmware: migration `migration_ai_signals.sql` hiện có chứa JSONB. Runtime có mã riêng `eye-mouth-v2-posture-…`; trọng số CNN/RF và profile mắt nhìn thẳng giữ nguyên. Schema lịch sử vẫn đọc trường thử nghiệm cũ để không hỏng số đo đã lưu.

## Kiểm chứng và giới hạn

Đã kiểm thử thời gian cúi/hồi phục, thiếu quan sát, bộ phân loại mắt không bị thay đổi và các mức policy. Luồng PostgreSQL/MQTT/API cùng ESP32 mô phỏng kiểm tra lưu/đọc tín hiệu, ba lệnh tải và ACK. Cần xác nhận lại trên camera và tải vật lý mới; kết quả phiên mắt cũ không thay thế bước này.

### Phiên camera phát triển mới

Phiên `20261110T142255Z-glasses-head-trial` ghi đủ bảy lượt, 7.036 frame. Người dùng xác nhận mở mắt khi nhìn xuống, thực hiện đúng lượt gật mở/nhắm và gật nhiều nên không nhớ số lần. Do đó chưa tính được số chu kỳ đúng/sai hoặc recall.

- Nhìn xuống: góc dọc p10/median/p90 khoảng 13,10°/14,29°/15,88°; không tính thành chu kỳ gật. Chiều hạ đầu dương đã được đối chiếu trên setup này.
- Các lượt gật có chu kỳ được ghi nhận; có mất mặt/gián đoạn giữa các chu kỳ. Nhánh mắt khi vừa nhắm vừa gật chưa duy trì nguy cơ ổn định, nên chưa dùng riêng gật đầu để kích hoạt tải.
- Che camera: khoảng 5,99 giây `UNAVAILABLE`, không giữ góc hoặc chu kỳ cũ.
- Bản đầu ghi một chu kỳ ngay trong quá trình bỏ che camera. Đã bổ sung `REACQUIRING`: yêu cầu nhìn gần mốc ổn định trước khi đếm lại.
- Replay bộ đếm mới trên toàn bộ góc đã ghi không còn chu kỳ ở nhìn xuống, nói/hồi phục hoặc bỏ che; vẫn ghi chu kỳ ở lượt gật nhắm. Mất quan sát làm xóa lịch sử nên có thể bỏ sót gật, nhất là lượt mắt mở. Đây là dữ liệu đã dùng để sửa thuật toán, cần phiên mới để nghiệm thu.
- Hai bài kiểm thử bổ sung kiểm tra bộ phân tích không đếm thời gian gián đoạn và không đếm chuyển động khi lấy lại quan sát. Phần AI hiện có 172 bài tính cả hai bài bổ sung; chưa dùng con số này làm chỉ số độ chính xác nhận diện.

Không sửa hoặc ghi lại review đạt của profile mắt v5 dựa trên lượt thử gật này. Review mắt cũ chỉ áp dụng phạm vi đã ghi, không chứng minh nhắm mắt ở mọi góc cúi.

## Code chính

- [Góc đầu và chu kỳ gật](../edge-ai/service/head_motion.py).
- [Quy tắc cúi kéo dài](../edge-ai/service/head_down_risk.py).
- [Runtime v2](../edge-ai/ml/multisignal_v2_runtime.py).
- [Schema Backend](../backend/app/schemas/ai_signals.py).
- [Giao diện tín hiệu](../frontend/src/components/AiSignalsPanel.jsx).
- [Luồng AI tổng thể](luong-xu-ly-ai-v2.md).
