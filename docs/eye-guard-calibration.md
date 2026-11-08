# Kiểm tra và hiệu chuẩn số đo mắt khi đeo kính

## Vì sao cần đo riêng

Lượt thử ngày 08/11 vẫn không nhận DROWSY khi người dùng báo đã nhắm mắt. Trong các mẫu debug khoảng 1 Hz có EAR hợp lệ, giá trị nhỏ nhất khoảng 0,223, cao hơn ngưỡng cố định 0,20; nhiều đoạn mất mặt. Chưa thể coi bộ đếm nhắm mắt đã hoạt động đúng chỉ vì có âm thanh. Âm còn có thể từ cảnh báo mất quan sát hoặc DISTRACTED.

Hiệu chuẩn này chỉ dành cho **quy tắc nhắm mắt liên tục** đã được TV3 đồng ý thử. EAR/PERCLOS và feature đầu vào RF giữ nguyên ngưỡng huấn luyện; joblib và policy 3/6/10 giây giữ nguyên. Nếu landmark không phân biệt được mắt mở/nhắm qua kính thì hiệu chuẩn không giải quyết được.

## Đo khoảng 45–60 giây

Đóng cửa sổ Driver Monitoring trước. Từ gốc project:

```powershell
./edge-ai/.venv/Scripts/python.exe edge-ai/calibrate_eye_guard.py --condition glasses
```

Giữ nguyên kính, góc camera và vị trí ngồi trong cả lượt. Các phím chỉ có tác dụng khi cửa sổ **Eye calibration (local only)** đang được chọn:

1. Bấm **1**, giữ mắt mở tự nhiên và nhìn thẳng.
2. Hết lượt, bấm **2**, nhắm mắt đến tiếng bíp kết thúc.
3. Bấm **3**, giữ mắt mở để kiểm tra riêng.
4. Bấm **4**, nhắm mắt để kiểm tra riêng; hết lượt cửa sổ tự đóng.

Mỗi lượt có 2 giây chuẩn bị và 5 giây đo. Bíp cao báo đã nhận phím; bíp thấp báo xong lượt. Không bấm lượt tiếp khi máy còn đo. Q/Esc hoặc đóng cửa sổ sẽ hủy, báo cáo không được dùng làm hiệu chuẩn đạt.

Công cụ chỉ dùng camera để tính số. Không ghi ảnh/video, mở MQTT/HTTP, sửa `.env`, tự áp dụng ngưỡng hay điều khiển ESP32. CSV quan sát và JSON kết quả ở thư mục riêng có mã phiên dưới `edge-ai/ml-runs/eye-calibration/`, được Git ignore.

## Điều kiện chấp nhận một bản thử

- Mỗi giai đoạn đủ ít nhất 80% thời gian quan sát hợp lệ. Hai mốc không hợp lệ hoặc gap quá 0,5 giây không được tính nối tiếp.
- Ngưỡng được tính **chỉ từ hai lượt đầu**: trung điểm giữa percentile 10 của mắt mở và percentile 90 của mắt nhắm. Chỉ tính nếu hai phía cách nhau ít nhất `max(0,02; 10% EAR trung vị mắt mở)`.
- Hai lượt sau không dùng để điều chỉnh ngưỡng. Lượt mở cho phép chớp mắt tự nhiên nhưng phải không kích hoạt eye guard. Lượt nhắm phải kích hoạt guard và có ít nhất 90% thời gian đo thành mắt nhắm. Tỷ lệ thời gian dưới ngưỡng ở lượt mở vẫn được báo cáo, không đánh đồng từng lần chớp ngắn với nhắm kéo dài.
- Hủy giữa chừng, dữ liệu không tách biệt hoặc kiểm tra sau thất bại: `REJECTED`, không tự chọn số khác để báo đạt.

Đây là cổng kiểm tra kỹ thuật cho một phiên mắt mở/nhắm, **không phải tiêu chuẩn an toàn, độ chính xác DROWSY hoặc kiểm thử trên người mới**. Bốn lượt dựa trên thao tác do người dùng làm theo hướng dẫn; cần xác nhận đã thực hiện đúng. Khi đổi người/kính/góc camera, cần kiểm tra lại thay vì dùng chung ngưỡng cá nhân.

Schema `v2` sửa tiêu chí lượt mở của bản đầu: bản đầu loại cả một số lượt có chớp mắt tự nhiên dù bộ đếm không kích hoạt. Khi xem lại dữ liệu cũ phải ghi thành báo cáo mới, giữ báo cáo cũ và công bố đây là phân tích lại sau sửa tiêu chí; không gọi là lượt nghiệm thu mới.

## Chạy lại bản kết hợp

Nếu `report.json` là `READY_FOR_TRIAL`, dùng đúng file đó để kiểm tra nạp trước:

```powershell
./edge-ai/run-camera-trial.ps1 -CalibrationPath 'DUONG_DAN_REPORT_JSON' -Check
```

Sau khi xem kết quả và sẵn sàng mở camera/loa:

```powershell
./edge-ai/run-camera-trial.ps1 -CalibrationPath 'DUONG_DAN_REPORT_JSON'
```

Script khóa đúng hash của RF ứng viên, bật quy tắc mắt cho tiến trình thử và khôi phục biến môi trường khi thoát. Không thay `run-submission.ps1` vốn dùng RF đối chiếu cũ. Bản thử AI chính có ghi clip và upload theo cấu hình hiện có; bước hiệu chuẩn ở trên chỉ ghi số liệu. API/broker và credential vẫn cần cấu hình như runbook. Để dùng HTTPS, cấu hình `BACKEND_HOST` và `REQUESTS_CA_BUNDLE` đúng CA riêng trước khi chạy.

Runtime từ chối file hiệu chuẩn bị từ chối, chưa hoàn tất, sai thiết bị hoặc khác phiên bản mã hình học mắt. File đúng schema chỉ có nghĩa nạp được; vẫn phải thử chớp mắt tự nhiên, nhắm kéo dài, mở lại, quay đầu và mất mặt. Nếu không đạt, giữ báo cáo lỗi và chưa chốt bản nộp.

## Kết quả hiện có ngày 08/11

Có kính: dữ liệu chưa tách biệt ổn định, hiệu chuẩn bị từ chối. Không kính: sau phân tích lại v2, đã thực hiện **một lượt camera mới** với ngưỡng riêng 0,2282818141; người dùng xác nhận DROWSY + âm thanh khi nhắm mắt, ATTENTIVE khi mở lại và DISTRACTED khi quay đầu vừa phải. Chỉ nghiệm thu các thao tác trong điều kiện đó. Kết quả và giới hạn ở [báo cáo camera](ai-camera-review-20261108.md); không áp dụng file cá nhân cho người khác hoặc tuyên bố đã xử lý kính.
