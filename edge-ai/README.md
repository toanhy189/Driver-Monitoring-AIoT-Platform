# Edge AI — camera, suy luận và huấn luyện

## Chạy camera

Xem [hướng dẫn cài đặt và chạy](../README.md#34-chạy-edge-ai) và [model card](../docs/final-ai-model.md). Môi trường đã khóa: Python 3.13, requirements-lock.txt.

```powershell
./edge-ai/.venv/Scripts/python.exe -X utf8 edge-ai/main.py --check
./edge-ai/.venv/Scripts/python.exe -X utf8 edge-ai/main.py
```

--check không mở camera/loa hoặc kết nối MQTT/HTTP. Lệnh thứ hai mở camera, ghi clip, cảnh báo local và gửi dữ liệu theo .env. Bấm Q để thoát. Mặc định AI_MODEL_MODE=baseline; ML phải nạp artifact riêng.

Bản RF kết hợp eye guard hiệu chuẩn đã đạt lượt chức năng không kính tại laptop nhóm: nhắm mắt có DROWSY/âm thanh, mở lại hồi phục ATTENTIVE, quay đầu vừa phải có DISTRACTED. Có kính chưa đạt; không dùng ca cá nhân thay metrics trên người mới. Artifact đối chiếu cũ giữ để so sánh, không dùng nhầm launcher khi demo.

Để chạy ứng viên, copy bundle đúng hash và dùng run-camera-trial.ps1 với file hiệu chuẩn đúng thiết bị/người. [Hiệu chuẩn](../docs/eye-guard-calibration.md) chỉ áp dụng cho guard, không đổi đặc trưng RF hoặc policy. Ngưỡng EAR cho feature là 0,20; guard mặc định 0,20 hoặc lấy từ file hiệu chuẩn được chấp nhận.

## Luồng xử lý

Camera → MediaPipe landmark → hình học mắt/hướng đầu → đặc trưng theo thời gian → RF nhị phân + quy tắc → xác nhận trạng thái → policy → local audio + MQTT.

- MediaPipe là mô hình thị giác có sẵn; RF do nhóm train trên đặc trưng. DISTRACTED dùng quy tắc hướng đầu.
- UNKNOWN thể hiện thiếu quan sát; gap/mất mặt ngắt bộ đếm liên tục. Không nối thời gian trước và sau khoảng mất mặt.
- Head rule hiện tại hợp lệ có thể báo DISTRACTED khi RF chưa đủ cửa sổ.
- Guard tùy chọn: nhắm liên tục ≥1 giây tạo nguy cơ; mở liên tục ≥1 giây xóa nguy cơ guard. RF/hướng đầu vẫn tham gia quyết định cuối.
- main.py nạp cấu hình, camera và worker; service/alert_policy.py điều phối episode/mức/nhắc; ml/runtime.py suy luận và ghép trạng thái.

## MQTT, video và dữ liệu riêng

- Topic theo AI_DEVICE_CODE; credential AI_MQTT_USERNAME/AI_MQTT_PASSWORD phải thuộc đúng Vision Node.
- Mỗi bản tin có message_id; retry giữ nguyên ID/nội dung, model_version được gắn trước khi lưu SQLite.
- Worker gửi MQTT có backoff/giới hạn inflight; storage_ack SAVED mới xóa queue. Bản lỗi giữ để kiểm tra.
- Clip được đóng/thêm queue; upload ở worker nền, không chờ HTTP trong vòng lặp camera.
- Upload dùng HTTP Basic của Vision Node. MQTT ACK SAVED không đồng nghĩa video đã upload.
- Clip pending giữ ở recordings/; chỉ dọn sau HTTP SAVED hợp lệ. Giới hạn clip/dung lượng không được xóa clip chưa gửi.
- Offline replay có metadata backfill, Backend chỉ lưu lịch sử; policy v1 kiểm tra độ mới trước phát tải.

Các file data/, recordings/, datasets/, ml-data/, ml-runs/, models/ theo .gitignore. Không commit gương mặt, SQLite, log quan sát, dataset hay joblib. Backend giữ video theo chính sách xóa thủ công.

## Chính sách cảnh báo

driver-bench-20261107-v1: DROWSY/DISTRACTED đã xác nhận tăng mức ở 3/6/10 giây; thời lượng 1/2/3 giây, mức 1 LED+còi, mức 2/3 cả ba tải. Mức 3 đề nghị nhắc mỗi 5 giây khi có quan sát mới; Backend kiểm tra command đang chờ.

ATTENTIVE ổn định 2 giây kết thúc episode. UNKNOWN ngắt tính liên tục, lỗi giám sát có thông báo riêng từ 2 giây và giới hạn nhắc lỗi 30 giây. SESSION_ENDED đóng đúng phiên. Đây là tham số thử nghiệm đồ án, không phải ngưỡng an toàn đã chứng nhận.

## Huấn luyện và tái hiện

Code ml/ được giữ để chuẩn bị dữ liệu, trích xuất, train và đánh giá:

| Công cụ | Mục đích |
|---|---|
| ml/prepare_nthu.py | Kiểm tra ZIP development/holdout, chuẩn bị manifest và dữ liệu NTHU |
| ml/nthu.py | Audit/trích xuất feature cho NTHU |
| ml/extract.py, ml/features.py | Landmark, đặc trưng thời gian, cache và cổng chất lượng |
| ml/nthu_train.py | Chọn ứng viên trên development rồi đánh giá với plan đã khóa |
| ml/train.py, ml/optimize.py | Baseline/RF/SVM và các thử nghiệm tối ưu |
| ml/nthu_diagnostics.py, ml/evaluate_events.py | Chẩn đoán và đánh giá phù hợp nhãn |
| ml/runtime.py | Kiểm tra artifact/schema/version, suy luận và ghép trạng thái |

Xem tham số trước khi chạy; các bước trích xuất/train có thể tốn hàng giờ:

```powershell
Push-Location edge-ai
./.venv/Scripts/python.exe -m ml.prepare_nthu --help
./.venv/Scripts/python.exe -m ml.nthu --help
./.venv/Scripts/python.exe -m ml.nthu_train --help
Pop-Location
```

Quy trình: xác nhận nguồn/nhãn → chia theo người/phiên → trích xuất feature cùng phiên bản hình học → GroupKFold trên development → khóa lựa chọn/artifact → đánh giá tách biệt. Không chia ngẫu nhiên cửa sổ cùng video sang cả train và test. Holdout đã từng xem phải được công bố; không gọi là kiểm thử độc lập mới.

Artifact bàn giao riêng kèm hash, feature schema, version, manifest/plan, môi trường và metrics. Nguồn dataset, phạm vi CV và giới hạn ở [model card](../docs/final-ai-model.md). Nhánh ba lớp/DMD là hướng phát triển, bản nộp chốt nhị phân + quy tắc.

## Kiểm thử và monitoring

```powershell
./edge-ai/.venv/Scripts/python.exe -X utf8 -m unittest discover -s edge-ai/tests -v
```

Test cơ chế không chứng minh accuracy hoặc tải ESP32 thật. Camera/loa cần quan sát thực tế; đo latency vòng xử lý riêng với độ dài cửa sổ RF và thời gian policy.

Exporter tùy chọn, chạy từ edge-ai:

```powershell
./.venv/Scripts/python.exe -m service.metrics_server --host 127.0.0.1 --port 9108
```

Dữ liệu quá hạn trả 503; không điền số đo giả khi camera dừng. [Runbook](../docs/final-runbook.md) có hướng dẫn monitoring và HTTPS.
