# Hiệu chuẩn mắt nhìn thẳng cho AI v2

## Khi nào cần

Trên laptop và setup đã kiểm tra, chạy `./edge-ai/run-multisignal-v2.ps1 -Demo`; không đo lại mỗi lần. Chỉ hiệu chuẩn mới khi đổi người, kính, camera, độ phân giải, vị trí hoặc ánh sáng đến mức profile cũ không còn phù hợp. Không có bước hiệu chuẩn mắt khi cúi.

Profile chỉ đặt ngưỡng cho guard nhắm mắt kéo dài. Nó không fine-tune CNN/RF, không đổi policy 3/6/10 giây và không chứng minh quan sát được mắt qua kính phản sáng.

## Thực hiện khi đổi setup

Đóng cửa sổ AI cũ. Tại gốc repo:

```powershell
./edge-ai/.venv/Scripts/python.exe -X utf8 edge-ai/calibrate_eye_guard.py --v2 --profile-id operator-01-webcam-0 --condition glasses
```

`profile-id` là nhãn do người vận hành đặt cho người/camera/setup, không phải nhận dạng khuôn mặt. Chọn đúng condition `glasses` hoặc `no-glasses`.

Chọn cửa sổ **Eye calibration (local only)** rồi làm bốn lượt, chờ bíp kết thúc từng lượt:

| Phím | Thao tác | Thời gian đo |
|---|---|---:|
| 1 | Nhìn thẳng, mắt mở/chớp tự nhiên | 8 giây |
| 2 | Nhắm kín cả hai mắt | 8 giây |
| 3 | Nhìn thẳng, mắt mở và nói bình thường | 30 giây |
| 4 | Nhắm kín cả hai mắt | 8 giây |

Mỗi lượt có 2 giây chuẩn bị. Q/Esc hủy; phiên dở không được chấp nhận. Chỉ lưu CSV/JSON riêng dưới `edge-ai/ml-runs/eye-calibration/`; không ghi mặt/video, không MQTT/HTTP hoặc ESP32. Đường dẫn report thực được in ở terminal khi kết thúc.

## Cổng chất lượng

- Chỉ hai lượt FIT đầu tính ngưỡng v5 từ trung vị mở/nhắm; hai lượt sau dùng kiểm tra, không điều chỉnh ngưỡng.
- Cần đủ quan sát liên tục và phân bố mở/nhắm phân biệt được. Gap hoặc số đo lỗi không được điền bằng giá trị cũ.
- Mở/chớp/nói không được tạo nhắm kéo dài; lượt nhắm cần đủ độ phủ quy định. Không đạt thì `REJECTED`, không sửa status hoặc nới ngưỡng để ép đạt.
- Profile khóa mã node, nhãn setup, camera, độ phân giải, condition và phiên bản hình học. Loader từ chối profile sai hoặc review `FAILED`.
- `READY_FOR_TRIAL` cho phép thử phiên mới, chưa phải nghiệm thu. Cần kiểm tra mở/chớp → nhắm → mở → nói/ngáp → quay đầu → che/bỏ che trước khi dùng điều khiển tải.

Khi có profile mới hợp lệ, truyền đường dẫn report thật qua `-CalibrationPath` cùng `-ProfileId` và `-Condition` phù hợp vào launcher. Không gõ tên thư mục mẫu. Không copy profile của người khác rồi coi là đã hiệu chuẩn cho mình.

[Kết quả kính v5 hiện tại và giới hạn](ai-v2-quality-calibration.md) · [Luồng AI](luong-xu-ly-ai-v2.md) · [Quy tắc cúi đầu](head-motion-v1.md).
