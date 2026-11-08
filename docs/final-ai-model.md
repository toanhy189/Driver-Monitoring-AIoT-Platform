# AI bản nộp: model nhị phân và quy tắc hướng đầu

Phạm vi này đã được TV3 chốt ngày 08/11/2026. Không train lại trong đợt hoàn thiện triển khai.

## Pipeline

Camera → MediaPipe landmark → hình học mắt/hướng đầu theo pixel → đặc trưng thời gian → RF nhị phân → kết hợp quy tắc DISTRACTED → xác nhận trạng thái → policy → local audio + MQTT.

MediaPipe dùng mô hình thị giác có sẵn để tìm landmark. RF là mô hình nhóm huấn luyện trên đặc trưng; DISTRACTED dùng quy tắc hướng đầu. Không gọi toàn bộ pipeline là CNN tự huấn luyện, hay gọi xác suất RF là độ tin cậy của toàn bộ hệ thống. Khi thiếu dữ liệu, UNKNOWN chặn việc nối thời gian qua khoảng không quan sát được.

## Artifact khóa

| Thuộc tính | Giá trị |
|---|---|
| Model | `rf-nthu-full-20261107-8d459c63` |
| File riêng | `edge-ai/ml-runs/nthu-gap-history-20261107/full/selected.joblib` |
| SHA256 | `5e25b03d26a7577982d9c357d3f87fe2a1bf2a31c205b447b782ec5006ea7b0d` |
| Feature version | `ear-pose-pixel-blink-v3-gap-history` |
| Đặc trưng | 19; thống kê EAR/PERCLOS, nhắm mắt, chuyển động mí, yaw/pitch |
| RF | 300 cây, max_depth 10, min_samples_leaf 5, max_features sqrt; class_weight 0:1, 1:0.75 |
| Ngưỡng RF | 0.4 |
| Cửa sổ / bước | 20 giây / 2 giây; chỉ nhận cửa sổ đủ chất lượng |
| Môi trường | Python 3.13; sklearn 1.9.1; `requirements-lock.txt` |

Chỉ load joblib từ bundle tin cậy; định dạng này có thể thực thi code khi nạp. Hash giúp đối chiếu đúng bundle đã bàn giao.

## Dữ liệu và kết quả đã có

Nguồn NTHU-DDD tải qua Kaggle theo xác nhận của người dùng. **Chưa có URL bản Kaggle cụ thể**; cần TV3 ghi đúng trang đã tải vào báo cáo, không tự điền một bản mirror bất kỳ.

279 video, 14 người trong development, 5.551 cửa sổ đánh giá, 1.287 âm và 4.264 dương; 4 fold chia theo người. Nhãn lấy từ dataset/quy trình đã xây, không gán ATTENTIVE/DISTRACTED/DROWSY giả từ một bộ nhãn khác. Video lỗi/thiếu quan sát được kiểm tra qua các cổng chất lượng và báo cáo diagnostics.

| Cách tính | Accuracy | Macro F1 | Recall DROWSY | False positive rate |
|---|---:|---:|---:|---:|
| Gộp các cửa sổ OOF development | 92,51% | 0,8850 | 98,62% | 27,74% |
| Trung bình theo người | 93,17% | 0,8805 | 98,43% | 23,22% |

Các chỉ số được lấy từ kết quả đã có, không phải số đo camera mới. Cửa sổ chồng lấn không phải các thử nghiệm độc lập. `selection-frozen.json` ghi `heldout_already_inspected=true`, `selection_before_heldout=false`; vì vậy **không gọi các số này là kiểm thử cuối độc lập chưa từng được xem**. Cần người/phiên mới có nhãn để nghiệm thu khả năng khái quát.

FPR trên cửa sổ khác số lần cảnh báo nhầm trong một giờ; delay model khác inference latency và delay toàn hệ thống. Đánh giá DISTRACTED/quy tắc, UNKNOWN, ánh sáng/kính và phần tải thực còn cần ca nghiệm thu riêng.

## Cách chạy đúng bản nộp

Từ gốc repo, khi đã có `.venv` và bundle riêng:

```powershell
./edge-ai/run-submission.ps1 -Check
./edge-ai/run-submission.ps1
```

`-Check` không mở camera, không phát âm và không ghi hàng đợi. Lệnh thứ hai mở camera và tạo dữ liệu riêng trên máy. Script chọn rõ model ML trong tiến trình chạy; không âm thầm đổi baseline mặc định cho mọi người.

Artifact, dataset, CSV quan sát, clip và SQLite không đưa lên Git. Bàn giao model riêng kèm manifest/hash và môi trường khóa. DMD, mô hình ba lớp và các mô hình ảnh/chuỗi sâu hơn thuộc phát triển sau; cần nhãn, tài nguyên và đánh giá phù hợp trước khi thay bản nộp.
