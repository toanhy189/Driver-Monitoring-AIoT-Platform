# Edge AI — camera, suy luận và huấn luyện

## Chạy camera

Đường chạy chính của demo:

```powershell
./edge-ai/run-multisignal-v2.ps1 -Demo
```

Thêm `-Check` để kiểm tra artifact/profile mà không mở camera/mạng. Nhìn thẳng 5 giây đầu để lấy mốc; Q thoát. Launcher chọn RF/CNN v2, profile kính v5 đã kiểm tra trên laptop hiện tại và quy tắc cúi đầu kéo dài. Hai chế độ `-EyeTrial` / `-HeadTrial` dùng để kiểm tra riêng, không gửi dữ liệu hay lệnh tới ESP32.

Xem [cài đặt và bàn giao artifact](../README.md#34-chạy-edge-ai), [luồng AI v2](../docs/luong-xu-ly-ai-v2.md) và [hiệu chuẩn nhìn thẳng khi đổi setup](../docs/eye-guard-calibration.md). Không cần hiệu chuẩn cúi. Dataset, trọng số và profile cá nhân được bàn giao riêng, không nằm trên Git.

Profile kính v5 đã thử mắt/ngáp/quay đầu/mất mặt trên cùng setup. Quy tắc cúi mới còn cần xác nhận phiên camera/tải thật; không dùng kết quả phiên mắt cũ thay cho bước này. Baseline và RF đời trước vẫn được giữ để đọc artifact và đối chiếu.

## Luồng xử lý

Camera → MediaPipe → EAR/MAR/hướng đầu + CNN vùng mắt/miệng → RF v2 theo thời gian + guard mắt + quy tắc cúi → xác nhận trạng thái → policy → local audio + MQTT.

- MediaPipe là mô hình thị giác có sẵn; RF do nhóm train trên đặc trưng. DISTRACTED dùng quy tắc hướng đầu.
- UNKNOWN thể hiện thiếu quan sát; gap/mất mặt ngắt bộ đếm liên tục. Không nối thời gian trước và sau khoảng mất mặt.
- Head rule hiện tại hợp lệ có thể báo DISTRACTED khi RF chưa đủ cửa sổ.
- Guard tùy chọn: nhắm liên tục ≥1 giây tạo nguy cơ; mở liên tục ≥1 giây xóa nguy cơ guard. RF/hướng đầu vẫn tham gia quyết định cuối.
- Cúi ≥12° liên tục 3 giây tạo `DROWSY/HEAD_DOWN_RISK`; nhánh này đo tư thế, có thể kích hoạt khi chủ động nhìn xuống. Mất quan sát ngắt thời gian.
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
| ml/runtime.py | Kiểm tra artifact/schema/version, suy luận và ghép trạng thái RF cũ |
| ml/multisignal_v2_train.py, ml/multisignal_v2_select.py | Fit RF và chọn ngưỡng v2 trên development/validation |
| ml/multisignal_v2_runtime.py | Runtime CNN + RF v2, guard và tư thế |

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
