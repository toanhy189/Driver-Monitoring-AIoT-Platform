# Edge AI – Chạy chương trình, huấn luyện và MQTT

**Cập nhật camera 08/11/2026:** RF đang thử báo DROWSY khi người dùng mở mắt, nhìn thẳng. Model chưa đạt nghiệm thu; các số CV bên dưới không thay kết quả này. Xem [chẩn đoán và bước tiếp theo](../docs/ai-camera-review-20261108.md). Artifact đối chiếu, ngưỡng và policy hiện được giữ nguyên.

## Tuần 4: policy cảnh báo đã thống nhất ngày 07/11/2026

Luồng camera hiện dùng `service/alert_policy.py`, phiên bản
`driver-bench-20261107-v1`. Các hàm event cũ trong `main.py` được giữ để tương
thích kiểm thử cũ; không điều khiển lịch cảnh báo của camera hiện tại.

- DROWSY/DISTRACTED đã xác nhận: mức 1 ở 3 giây (LED+còi, 1 giây), mức 2 ở
  6 giây (cả ba tải, 2 giây), mức 3 ở 10 giây (cả ba tải, 3 giây).
- Mức 3 đề nghị nhắc mỗi 5 giây với quan sát mới. BE quyết định dispatch;
  không xếp thêm command khi lần trước còn chưa rõ kết quả. Các lần nhắc
  dùng ID mới, cùng episode; retry giữ nguyên ID và nội dung.
- ATTENTIVE ổn định 2 giây kết thúc đợt. Khi ứng viên đã đổi, ngừng đề nghị
  nhắc bằng trạng thái cũ ngay trong lúc xác nhận hồi phục.
- UNKNOWN ngắt thời gian liên tục ngay; từ 2 giây có cảnh báo lỗi giám sát
  riêng, nhắc lỗi tối đa một lần/30 giây. Không ghi là tài xế đã hồi phục.
- Mất quan sát tạo đoạn mới khi xác nhận lại; không cộng qua khoảng thiếu.
  DROWSY được ưu tiên trong bước kết hợp dự đoán và hướng đầu.
- `SESSION_ENDED` đóng đúng phiên; command chưa gửi bị hủy. Command đang
  chạy tự kết thúc theo duration. Event phiên cũ không dừng phiên mới.

Đây là cấu hình thử nghiệm đồ án. Thời gian trên tính từ trạng thái đã được
AI xác nhận; không phải độ trễ từ lúc mắt thật bắt đầu nhắm. Model hiện có
cửa sổ 20 giây/bước dự đoán 2 giây; phải đo tổng độ trễ riêng.

### Chạy và kiểm tra môi trường

Từ thư mục gốc project, dùng Python 3.13 trên Windows:

```powershell
python -m venv edge-ai/.venv
./edge-ai/.venv/Scripts/python.exe -m pip install -r edge-ai/requirements-lock.txt
./edge-ai/.venv/Scripts/python.exe -X utf8 edge-ai/main.py --check
./edge-ai/.venv/Scripts/python.exe -X utf8 edge-ai/main.py
```

`--check` nạp MediaPipe thật và xử lý ảnh trống; không mở webcam, phát âm,
kết nối MQTT/HTTP hoặc ghi queue người dùng. Nếu đặt chế độ ML, lệnh cũng
kiểm tra artifact và thư viện đúng phiên bản. `requirements-lock.txt` là
snapshot môi trường đã dùng cho artifact cục bộ; CI dùng requirements để
kiểm tra code trong môi trường cài mới, không tự tải dataset/artifact riêng.

Giữ model camera mặc định như cấu hình hiện có. Để thử riêng artifact v3:

```powershell
$env:AI_MODEL_MODE = "ml"
$env:AI_MODEL_PATH = (Resolve-Path "edge-ai/ml-runs/nthu-gap-history-20261107/full/selected.joblib").Path
./edge-ai/.venv/Scripts/python.exe -X utf8 edge-ai/main.py --check
./edge-ai/.venv/Scripts/python.exe -X utf8 edge-ai/main.py
```

Artifact bị Git bỏ qua và cần chuyển riêng giữa thành viên. Việc nạp được
artifact không đồng nghĩa đã nghiệm thu độ chính xác trên camera/người mới.

### Backend và firmware cần đi cùng

Chạy migration mới trước khi dùng event v1:

```powershell
docker compose --env-file .env -f deployment/docker-compose.yml run --rm migrate
docker compose --env-file .env -f deployment/docker-compose.yml up -d --build backend
```

Trong Swagger, Admin được gán hai thiết bị cập nhật
`PUT /api/devices/{vision_device_id}/rule` với ID ESP32 thật:

```json
{
  "target_device_id": 2,
  "enabled": false,
  "policy": {"policy_version": "driver-bench-20261107-v1"}
}
```

`2` là ví dụ. Preset tự trả đúng bảng mức, tuổi event 5 giây và không có
cooldown khóa command. Không trộn ngưỡng legacy vào preset v1. Khi nghiệm thu
trên bàn, bật cả `RULE_ENGINE_ENABLED` và binding; thiết bị phải ACTIVE/ONLINE.
Code không tự sửa `.env`, bật rule hoặc đổi binding đang có.

BE lưu thứ tự/phiên/episode vào bảng `rule_runtime`. Event gửi bù chỉ lưu
lịch sử. Command được kiểm tra lại trước khi publish, có hạn theo event 5
giây và quan sát 2 giây. Firmware mới kiểm tra `expires_at_ms`, từ chối
`CLOCK_NOT_SYNCED`, `CLOCK_SKEW`, `COMMAND_EXPIRED`, và tự tắt theo duration.
Firmware dùng SNTP bất đồng bộ; mạng thử cần cho board đồng bộ UTC. Build
thành công chưa thay thế việc flash, kiểm tra đồng hồ, ACK và tải thật.

`_delivery.mode` là metadata truyền (`live`/`backfill`), tách khỏi nội dung
event bất biến và hash chống trùng. BE cũ chưa hiểu metadata này không đủ
điều kiện chạy policy mới. Queue cũ được giữ và đánh dấu gửi bù khi khởi động.
MQTT worker có giới hạn số bản tin đang chờ ACK, dành chỗ cho dữ liệu mới,
backoff và giữ bản tin lỗi ở trạng thái DEAD để kiểm tra. Không xóa dữ liệu
chưa được SAVED chỉ để giải phóng hàng đợi.

### Video, lưu trữ và quyền truy cập

- Mặc định mới: `edge-ai/recordings/`, không phụ thuộc thư mục gọi chương trình.
  Clip cũ ở `recordings/` khác vẫn giữ nguyên, không tự đoán ID để import.
- Ngân sách vận hành mới: clip tối đa khoảng 60 giây hoặc 32 MiB, ngân sách
  thư mục 1 GiB. Đây là giới hạn ứng dụng, không phải filesystem quota cứng;
  frame cuối/header có thể thêm dung lượng. Có thể cấu hình trong `.env.example`.
- Hết ngân sách thì tạm ngừng ghi và thử lại; camera, ML và cảnh báo tiếp tục.
  Không xóa clip pending. Chỉ dọn sau xác nhận HTTP SAVED hợp lệ như trước.
- Event mang `episode_start_event_id` và `clip_message_id`; chia clip tạo
  STATE_CHANGED có `reason=CLIP_ROTATED`, không được dùng để khôi phục nguy cơ.
- `GET /api/devices/{id}/events/{event_id}/video` kiểm tra quyền thiết bị và
  trả video liên quan hoặc trạng thái chờ/chưa có. Upload trước event vẫn được.
- Video phục vụ xem lại cảnh báo, không tự biến thành nhãn train. Quyền xem
  tiếp tục qua JWT và thiết bị được gán; upload dùng credential Vision Node.
- Chưa áp dụng chính sách tự xóa video Backend theo số ngày. Cần chốt thời
  hạn lưu với nhóm; không tự xóa video cá nhân/clip pending trong đợt sửa này.

### Đo hiệu năng, đánh giá và tái sử dụng kết quả

`data/events.jsonl` ghi event mới; `data/performance.jsonl` ghi FPS, RAM,
CPU tiến trình và p50/p95 từng bước. Hai log quay vòng khoảng 5 MiB, không
thay queue lưu bền và không được đưa lên Git. CPU có thể vượt 100% khi dùng
nhiều lõi. `estimator` đo lần predict thật, không tính lần trả dự đoán cache.

Exporter tùy chọn, chạy từ `edge-ai`:

```powershell
./.venv/Scripts/python.exe -m service.metrics_server
```

Đọc `http://127.0.0.1:9108/metrics`; dữ liệu thiếu/cũ hơn 30 giây trả 503.
Đây là exporter cho AI, chưa phải chứng minh cả hệ thống monitoring đã triển khai.

So sánh rules/RF/SVM không train lại, chạy từ `edge-ai`:

```powershell
./.venv/Scripts/python.exe -m ml.week4 compare-rules --features ml-data/nthu-gap-history/development/features.csv --predictions ml-runs/nthu-gap-history-20261107/development_oof_predictions.csv --output ml-runs/new-comparison.json
```

Kết quả đã bổ sung ở `ml-runs/week4-completion-20261107/rules-oof-comparison.json`:
4.826 cửa sổ chung, baseline quyết định được 86,94%; 725 cửa sổ từ chối được
báo riêng. Đây vẫn là development OOF, không phải test người mới.

Đánh giá cảnh báo theo thời gian cần CSV nhãn UTC có cột
`session_id,start,end,state`; không lấy tên clip dự đoán làm nhãn thật:

```powershell
./.venv/Scripts/python.exe -m ml.evaluate_events --events data/events.jsonl --truth path/to/reviewed-utc-intervals.csv --output ml-runs/new-event-evaluation.json
```

Công cụ tính số đợt báo nhầm/giờ ATTENTIVE được gán nhãn, đợt bỏ sót và độ
trễ tới event AI. Độ trễ tới tải thật vẫn cần timestamp dispatch/ACK và minh
chứng phần cứng. Không suy ra các chỉ số này từ Accuracy hay NME.

### Phần ba nhãn: công cụ sẵn sàng, dữ liệu thật chưa đủ

Model NTHU v3 đang có vẫn là nhị phân. DISTRACTED của luồng đang chạy đến từ
quy tắc hướng đầu. Chưa đánh dấu hoàn thành yêu cầu dataset/model ba nhãn.

`ml.week4 prepare-states` nhận các feature CSV đã audit và CSV khoảng nhãn:
`subject_id,video_id,video_sha256,start_s,end_s,state,reviewer,source,label_method,split`.
`state` phải gồm ATTENTIVE/DISTRACTED/DROWSY; `label_method` là manual_review
hoặc dataset_original; `split` là train/validation/test và không trùng người.
Không tự đổi nhãn không-buồn-ngủ thành ATTENTIVE hoặc giảm-tỉnh-táo thành DISTRACTED.

```powershell
./.venv/Scripts/python.exe -m ml.week4 prepare-states --features ml-data/nthu-gap-history/development/features.csv --annotations path/to/reviewed-labels.csv --output ml-data/three-state-reviewed/features.csv
./.venv/Scripts/python.exe -m ml.week4 train-states --features ml-data/three-state-reviewed/features.csv --output ml-runs/three-state-new
```

Công cụ kiểm tra checksum, schema cửa sổ, nguồn nhãn, khoảng chồng nhau và rò
rỉ người/video. RF/SVM fit trên cửa sổ train không chồng; chọn bằng validation,
đóng băng lựa chọn trước đánh giá test. Artifact ba nhãn có định dạng riêng
`driver-state-v1`, được runtime nhận khi chủ động chọn. Chỉ có kiểm thử dữ liệu
tổng hợp cho nhánh này; chưa có kết quả train ba nhãn trên dữ liệu thật.

### Kiểm thử và phần nghiệm thu còn lại

```powershell
./edge-ai/.venv/Scripts/python.exe -X utf8 -m unittest discover -s edge-ai/tests -v
python -m unittest discover -s backend/tests -p test_ai_policy_v1.py -v
```

CI tại `.github/workflows/edge-ai.yml` chạy không cần camera/broker. Workflow
chưa được coi là đã chạy trên GitHub chỉ vì có file cấu hình. Các ca mới
bao gồm mô phỏng 30 phút bằng đồng hồ giả, tăng mức, UNKNOWN/hồi phục, gửi
bù, chống trùng, hủy/expiry và lưu runtime qua phiên DB mới. Nghiệm thu camera,
loa, ánh sáng/kính, SNTP/ESP32 thật, tải lặp và Docker/PostgreSQL/MQTT thật
phải ghi riêng. Benchmark landmark đã sửa cách tính; cần chạy lại với CSV gốc
trước khi dùng số 100%/8,08 ms cũ trong báo cáo.

Ba ca phần mềm mới đã chạy đạt với PostgreSQL và broker có xác thực thật,
ESP32 giả lập và MP4 tổng hợp. Có kiểm tra chính worker AI: SAVED, reconnect,
gửi bù, phản hồi FAILED cho schema lỗi và giữ bản tin DEAD. Chạy lại riêng
các ca này khi sửa hợp đồng/worker (Docker cần hoạt động):

```powershell
python backend/tests/run_week4_isolated.py
```

Script tạo DB, broker, tài khoản và container tạm, rồi dọn đúng các tài nguyên
thử đó. Minh chứng ở `ml-runs/week4-completion-20261107/live-integration.json`.
Bộ tuần 3 cũ được giữ kết quả; không chạy lại toàn bộ để có minh chứng này.

## Huấn luyện phát hiện buồn ngủ: UTA-RLDD → RF/SVM

### Phạm vi và trạng thái

Đã có công cụ chuẩn bị manifest, trích xuất, train/đánh giá và nạp model tùy chọn.
Dataset, đặc trưng và artifact train được lưu cục bộ trong các thư mục Git bỏ qua;
không đóng gói cùng repository. Mặc định camera vẫn dùng quy tắc hiện tại
(`AI_MODEL_MODE=baseline`). Test tổng hợp kiểm tra code; kết quả nhận biết phải
đọc từ report của một lần train trên dữ liệu thật.

### Kết quả tối ưu v2 — đã train trên dữ liệu thật

Đã xử lý lại đủ **18 người / 36 video** từ ba ZIP ban đầu, giữ nhãn gốc.
Có 10.683 cửa sổ 10 giây đạt chất lượng; sau khi tạo cùng điểm kết thúc hợp lệ
cho các cửa sổ 5/10/20 giây, còn **10.459 điểm so sánh**. Không gán nhãn tay.

Tìm kiếm 4-fold GroupKFold trên **14 người development**, thử 126 cấu hình
model/cửa sổ/bộ đặc trưng (504 lượt fit CV) và **1.278 tổ hợp ngưỡng**.
RF được chọn theo chính sách CV đã lưu trước khi xem dự đoán test mới:

- **20 giây**, bộ `eyes` gồm **13 đặc trưng**, 150 cây, depth 6, leaf 15,
  `max_features=sqrt`, ngưỡng điểm RF 0,50.
- Refit trên 14 người development với **841 cửa sổ train không chồng lấn**.
- Phiên bản: `rf-uta-v2-20261104-7c16ac6d` (ngày trong mã phiên bản là UTC).
- `DISTRACTED` vẫn dùng quy tắc hướng đầu; bộ `eyes` chỉ phân loại buồn ngủ.

Các số dưới đây dùng **2.223 cửa sổ hợp lệ của 4 người test cũ**. Đây là kiểm tra
hồi quy vì kết quả của những người đó đã được xem ở v1, chưa phải nghiệm thu
độc lập trên người mới:

| Phương pháp v2 | Accuracy | Macro F1 | Recall DROWSY | FPR trên ALERT |
|---|---:|---:|---:|---:|
| Baseline với hình học pixel | 55,02% | 0,4759 | 17,79% | 9,49% |
| **RF được chọn bằng CV** | **64,96%** | **0,6478** | **73,82%** | **43,50%** |
| SVM | 62,35% | 0,5968 | 90,23% | 64,24% |

**Chưa đạt mục tiêu thử nghiệm.** RF có CV mean-person recall 69,87% và FPR
31,58%, chưa đồng thời đạt recall >=75% và FPR <=30%. Trên kiểm tra hồi quy,
RF còn bỏ sót 284/1.085 cửa sổ DROWSY và báo nhầm 495/1.138 cửa sổ ALERT.
Các cửa sổ chồng lấn và dùng nhãn cả video; những số đếm này không phải số vụ
buồn ngủ hoặc số cảnh báo thực tế. Cần thử camera và người mới trước khi nghiệm thu.
Baseline đã sửa hệ tọa độ nhưng ngưỡng quy tắc vẫn là ngưỡng demo, chưa hiệu chuẩn
lại; không coi baseline mới là đã được đánh giá đầy đủ trên camera.

Mốc v1 RF là 60,61% accuracy / 52,24% recall. V2 thay cửa sổ, gate chất lượng và
quy trình chọn/refit model nên không được xem mức chênh lệch là phép so sánh
từng cửa sổ giống nhau hoặc bằng chứng chỉ riêng sửa hình học tạo ra cải thiện.

Kết quả tại `edge-ai/ml-runs/uta-optimized-v2/`: `comparison.md`, `report.json`,
`selected.joblib`, `rf.joblib`, `svm.joblib`, `optimization-plan.json`,
`selection-frozen.json`, `cv-trials.csv/json`, `ablation-summary.csv`,
`test_predictions.csv` và bốn hình tổng hợp. Đã nạp lại artifact và xác nhận đủ
2.223 dự đoán khớp. **47/47 test code đạt**; camera thật chưa được mở để kiểm thử.

`cache-integrity.json` xác minh đủ frame/thời lượng của 36 video; `14/0` gặp lỗi
native và `21/0` gặp lỗi retrieve trong một lượt đọc, đã được xử lý lại hoàn chỉnh.
Không dùng phần video bị cắt do các lỗi đó làm dữ liệu train. Audit nguồn ZIP,
hash code, manifest, trích xuất và log test nằm cùng thư mục kết quả, đều được Git bỏ qua.

Chạy thử model v2 từ **thư mục gốc project**:

```powershell
$env:AI_MODEL_MODE = 'ml'
$env:AI_MODEL_PATH = (Resolve-Path 'edge-ai/ml-runs/uta-optimized-v2/selected.joblib').Path
./edge-ai/.venv/Scripts/python.exe -X utf8 edge-ai/main.py
```

Kiểm tra log có `Loaded ML model rf-uta-v2-20261104-7c16ac6d`. Model cần khoảng
20 giây quan sát hợp lệ để làm đầy cửa sổ đầu tiên; `UNKNOWN` lúc khởi động
không phải lỗi. Mặc định cấu hình vẫn là `AI_MODEL_MODE=baseline`.

### Lượt tiếp theo ngày 07/11/2026: chuẩn bị NTHU-DDD và kế hoạch tinh chỉnh

Đã kiểm kê ba bản ZIP Kaggle NTHU-DDD có sẵn trong `D:/dataset`: `archive (1).zip`,
`archive.zip`, `archive (2).zip`; không tải thêm qua mạng. Người dùng xác nhận nguồn
Kaggle; chưa có URL listing cụ thể hay checksum từ tác giả để xác thực bản sao.
Tham khảo [nghiên cứu mô tả nhãn từng frame](https://www.csie.ntu.edu.tw/~fuh/personal/DetectionofDriverDrowsinessUsingMulti-TaskLearning.pdf)
và [nghiên cứu các điều kiện NTHU](https://arxiv.org/html/1910.09722v1).

- **376 video / 22 người**, video và nhãn sau giải nén khoảng **5,84 GiB**, lưu tại
  `edge-ai/datasets/NTHU-DDD/`. Có ngày/đêm, kính thường, không kính và kính râm.
- **355 video AVI** có số nhãn khớp số frame trong header, đọc được frame đầu,
  CRC ZIP và SHA-256 đã kiểm tra. Đây là sẵn sàng cho bước trích xuất có kiểm tra
  decode/PTS đầy đủ, chưa phải chứng nhận mọi frame hay landmark đều hợp lệ.
- **21 video cách ly**: một AVI lệch số nhãn; cả 20 MP4 của bốn người trong ZIP
  evaluation có số frame header nhiều hơn nhãn hai frame. Không tự cắt/giãn/dịch
  nhãn. Bản ghi nằm ở `ml-data/nthu-20261107-prepared/quarantine.csv`.
- Do toàn bộ MP4 evaluation đang cách ly, kế hoạch mới giữ riêng **4 người AVI**
  `nthu-002/005/031/033` (**76 video**) và dùng **14 người** còn lại (**279 video**)
  làm development. Split ngẫu nhiên seed 20261107, chỉ dựa kiểm kê/tính toàn vẹn,
  trước trích xuất và xem dự đoán. Các vai trò trong audit ban đầu mô tả nhóm ZIP;
  **split thí nghiệm cuối** nằm trong `ml-runs/ai-next-20261107/plan.json`.

`ml.prepare_nthu` ghép video với `*_drowsiness.txt`, giữ nguyên nhãn từng frame,
namespace người theo dataset, chặn trùng người/nguồn giữa các nhóm, không ghi đè
file, có giới hạn dung lượng và cách ly frame/label lệch. Mã 0 là **không buồn ngủ**,
không tự suy ra ATTENTIVE; không dùng tên video hay nhãn mắt/hướng đầu thay nhãn
buồn ngủ. Dataset này có định dạng nhãn khác UTA nên **không đưa manifest mới
thẳng vào `ml.extract` hoặc `ml.train` hiện tại**; cần adapter nhãn theo cửa sổ.

Từ thư mục **edge-ai**, kiểm kê hoặc chuẩn bị trên thư mục output/root mới:

```powershell
./.venv/Scripts/python.exe -X utf8 -m ml.prepare_nthu --development-zip 'D:/dataset/archive (1).zip' --development-zip 'D:/dataset/archive.zip' --holdout-zip 'D:/dataset/archive (2).zip' --output-dir ml-data/nthu-catalog-next --max-gib 8
# Thêm --extract --root datasets/NTHU-DDD-next để giải nén vào nơi mới.
```

Kế hoạch và chẩn đoán lưu riêng tại `ml-runs/ai-next-20261107/`:
`plan.md`, `plan.json`, `diagnosis.json`, `development.csv`, `fresh-heldout.csv`.
Đầu tiên viết adapter nhãn frame, audit decode/PTS và coverage theo kính/ánh sáng;
train NTHU riêng bằng GroupKFold theo người. Sau đó thử regularization/class weight
RF/SVM, chuẩn hóa EAR nhân quả, cửa sổ và nhịp lấy mẫu. Chốt model/ngưỡng bằng
development rồi mới mở tập người mới. UTA test cũ giữ vai trò hồi quy; không trộn
âm thầm nhãn cả video UTA với nhãn frame NTHU. Calibration nếu làm phải tách người
và được đánh giá riêng; nó không bảo đảm tăng accuracy.

Đây là **chuẩn bị dữ liệu và kế hoạch**, chưa train model mới, chưa có số accuracy
mới. Video IR ban đêm cũng không chứng minh webcam RGB hoạt động trong tối.
Model v2 và mặc định camera baseline được giữ như trước. Code test: **53/53 đạt**.
Dataset, nhãn, manifest và report cục bộ tiếp tục được `.gitignore` bỏ qua.

### Pipeline NTHU v1 — adapter nhãn frame và train tách người

Đã triển khai `ml/nthu.py` và `ml/nthu_train.py`, thay cho bước adapter còn thiếu
ở kế hoạch chuẩn bị phía trên. Các module này không thay runtime camera hay rule BE.

- `ml.nthu` giải mã toàn video, yêu cầu số frame bằng số nhãn và PTS tăng nghiêm
  ngặt, rồi dùng chung `extract_video`/`FeatureWindow` với UTA và runtime.
- Nhãn cửa sổ lấy từ các frame trong chính khoảng thời gian đã quan sát: tỷ lệ
  DROWSY <=20% là lớp âm, >=80% là lớp dương; đoạn pha trộn được đếm riêng.
- Cache riêng từng video, checksum nguồn, phiên bản detector, feature và cấu hình.
  Không ghép CSV train nếu còn job trích xuất thất bại. Các cửa sổ thiếu landmark
  không được coi là mắt mở; báo coverage theo năm điều kiện.
- `select` chỉ nhận role development, thử 24 cấu hình RF/SVM trên GroupKFold
  4 folds, dùng cửa sổ train không chồng lấn. Chọn ngưỡng từ điểm out-of-fold,
  lưu `selection-frozen.json` và hash artifact trước khi mở tập held-out.
- `evaluate` chỉ nhận role fresh_heldout; kiểm tra plan/manifest/model hash,
  báo chỉ số từng người/điều kiện, confusion matrix và so với UTA v2 giữ nguyên.
  Test tổng hợp kiểm tra code không phải bằng chứng accuracy trên người thật.

Các lệnh từ thư mục **edge-ai**, theo đúng thứ tự:

```powershell
./.venv/Scripts/python.exe -X utf8 -m ml.nthu --manifest ml-runs/ai-next-20261107/development.csv --output-dir ml-data/nthu-v1/development --workers 4
./.venv/Scripts/python.exe -X utf8 -m ml.nthu_train select --features ml-data/nthu-v1/development/features.csv --plan ml-runs/ai-next-20261107/plan.json --run-dir ml-runs/nthu-v1-20261107
./.venv/Scripts/python.exe -X utf8 -m ml.nthu --manifest ml-runs/ai-next-20261107/fresh-heldout.csv --output-dir ml-data/nthu-v1/heldout --workers 4
./.venv/Scripts/python.exe -X utf8 -m ml.nthu_train evaluate --features ml-data/nthu-v1/heldout/features.csv --plan ml-runs/ai-next-20261107/plan.json --run-dir ml-runs/nthu-v1-20261107 --reference-model ml-runs/uta-optimized-v2/selected.joblib
```

Đầu ra: `ml-runs/nthu-v1-20261107/`; log riêng từng bước, báo cáo, bảng CV,
RF/SVM/selected artifact, hash model và hình confusion matrix. Run đã chốt giữ
nguyên; lệnh `select`/`evaluate` không ghi đè kết quả. Đọc coverage và phần giới
hạn cùng accuracy; không suy ra cải thiện so với 64,96% UTA trên dataset khác.

#### Kết quả NTHU v1 — đã chạy xong trên dữ liệu thật ngày 07/11/2026

- Đủ **355 video** sau cách ly: 279 development và 76 video của 4 người test mới.
  Tất cả khớp số frame giải mã/nhãn và có PTS tăng; cảnh báo codec giữ trong log,
  các kiểm tra này không chứng nhận mọi pixel sạch lỗi. 21 video ban đầu vẫn cách ly.
- Development có **4.327 cửa sổ**. Thử 24 cấu hình, 4 folds (**96 lượt fit CV**),
  **252 tổ hợp ngưỡng**. Chọn RF 300 cây, depth 10, leaf 5, balanced, ngưỡng 0,55;
  cửa sổ 20 giây, 13 đặc trưng eyes. Refit bằng **591 cửa sổ không chồng lấn**.
- Development CV mean-person recall **73,97%**, FPR **32,33%**: **chưa đạt** đồng
  thời mục tiêu thử nghiệm 75%/30%. Model được chốt trước dự đoán test.
- Test có **1.321 cửa sổ**, gồm 226 không-buồn-ngủ và 1.095 DROWSY:

| Model trên cùng NTHU held-out | Accuracy | Macro F1 | Recall DROWSY | FPR |
|---|---:|---:|---:|---:|
| **RF NTHU được chọn bằng CV** | **71,54%** | **0,6081** | **74,70%** | **43,81%** |
| SVM NTHU | 62,23% | 0,5444 | 62,47% | 38,94% |
| UTA v2 giữ nguyên làm tham chiếu | 78,80% | 0,4577 | 94,61% | 97,79% |

RF mới giảm báo nhầm và tăng Macro F1 trên cùng tập NTHU, đồng thời giảm recall
và accuracy. Không gọi đây là tăng từ 64,96% UTA lên 71,54% NTHU. Test lệch lớp:
luôn đoán DROWSY đã được accuracy **82,89%** nhưng FPR 100%; chỉ nhìn accuracy sẽ
gây hiểu nhầm. Người `nthu-033` không còn cửa sổ lớp âm sau lọc: FPR mean-person
tính trên 3 người có lớp âm, khác FPR gộp trong bảng.

Chỉ **57,21%** cửa sổ ứng viên test được chấm điểm: 745 bị loại vì chất lượng,
243 vì nhãn pha trộn. Chưa nghiệm thu camera thật, điều kiện RGB trong tối hay
độ trễ cảnh báo vật lý. Kết quả hiện vẫn là thử nghiệm, chưa thay model mặc định.

Phiên bản **`rf-nthu-v1-20261107-bc471a9e`** tại
`ml-runs/nthu-v1-20261107/selected.joblib`. `comparison.md` có diễn giải tiếng Việt;
`report.json`, `test_predictions.csv`, `confusion_matrices.png`, `verification.json`,
`code-audit.json`, `selection-frozen.json` và `tests-final.log` lưu minh chứng.
**60/60 test code đạt**; nạp lại artifact khớp đủ 1.321 dự đoán, hash model/mã
nguồn được kiểm tra và artifact UTA cũ không thay đổi. Bốn người test này nay đã
được xem kết quả; lần tối ưu sau báo điểm trên họ là hồi quy và cần người mới cho
nghiệm thu độc lập tiếp theo.

### So sánh eyes/full và chẩn đoán dữ liệu — 07/11/2026

Đã chạy trên **cùng 4.327 cửa sổ của 14 người phát triển**, cùng 4 fold tách
theo người và cùng 24 cấu hình RF/SVM cho mỗi bộ đặc trưng: **192 lần fit CV**,
504 lần đối chiếu ngưỡng. Tập test không được đọc lại trong lượt này.

| Cấu hình | Macro F1 theo người | Recall DROWSY theo người | FPR theo người |
|---|---:|---:|---:|
| RF, 13 đặc trưng mắt | 0,6061 | 73,97% | 32,33% |
| RF, 19 đặc trưng mắt và hướng đầu | **0,8094** | **97,85%** | **26,42%** |
| SVM, 19 đặc trưng | 0,7684 | 93,17% | 26,09% |

RF/full được chọn bằng quy tắc CV: 300 cây, depth 10, leaf 5, class weight
hai lớp bằng nhau, ngưỡng 0,45; refit 591 cửa sổ không chồng lấn. Phiên bản
`rf-nthu-full-20261107-79ad08b4` tại
`ml-runs/nthu-ablation-20261107/full/selected.joblib`.

**Các số trên là kết quả dùng để chọn mô hình, chưa phải nghiệm thu người mới.**
Khi gộp cửa sổ thay vì lấy trung bình theo người, RF/full có accuracy 91,19%,
Macro F1 0,8438, recall 98,27%, **FPR 37,11%**. FPR gộp vẫn lớn hơn 30%.
Không so các số CV này trực tiếp với điểm held-out của NTHU v1 hoặc UTA.
Tỷ lệ dự đoán của RF vẫn chưa được hiệu chuẩn thành confidence.

Chẩn đoán toàn bộ tập phát triển: 8.547 cửa sổ ứng viên, 3.222 loại chất lượng,
998 nhãn trộn, giữ lại 4.327 (865 không buồn ngủ, 3.462 buồn ngủ).
`ml.nthu_diagnostics` chạy lại 6 video: 5 video có tỷ lệ loại cao nhất mỗi điều
kiện và một đối chứng. Cả **192 cửa sổ của 5 video cực trị** bị chặn ở bước
chưa đủ 20 giây lịch sử liên tục sau reset; tất cả 192 mang nhãn không buồn ngủ.
Video đối chứng có 34 cửa sổ qua chất lượng. Mẫu này được chọn để tìm lỗi,
không dùng để suy ra tỷ lệ lỗi toàn dataset. Bộ lọc đang làm thiếu dữ liệu âm ở
một số người; riêng nthu-035 không còn cửa sổ âm trong tập train đã lọc.

Hướng tiếp theo: kiểm tra riêng bộ đệm cửa sổ và bộ đếm nhắm mắt liên tục,
đánh giá cách giữ lịch sử hợp lệ quanh khoảng mất mặt mà không nối khoảng
nhắm mắt xuyên gián đoạn; thử trên tập phát triển với phiên bản đặc trưng mới.
Đồng thời bổ sung cảnh nhìn quanh nhưng tỉnh táo để kiểm tra mô hình có học
nhầm đặc điểm diễn xuất của NTHU hay không. Chưa thay model mặc định của camera.

Chạy từ `edge-ai` (các file dữ liệu/kết quả là dữ liệu cục bộ được gitignore):

```powershell
./.venv/Scripts/python.exe -X utf8 -m ml.nthu_ablation --features ml-data/nthu-v1/development/features.csv --plan ml-runs/ai-next-20261107/plan.json --output-dir ml-runs/nthu-ablation-20261107
./.venv/Scripts/python.exe -X utf8 -m ml.nthu_diagnostics --features ml-data/nthu-v1/development/features.csv --manifest ml-runs/ai-next-20261107/development.csv --output-dir ml-runs/nthu-ablation-20261107/diagnostics --workers 2
```

Minh chứng: `comparison.md`, `report.json`, `development_oof_predictions.csv`,
`eyes/`, `full/` và `diagnostics/diagnosis.md` trong thư mục run này.
Các bảng kiểm thử với dữ liệu tổng hợp chỉ xác nhận logic code, không chứng minh
chất lượng mô hình trên video thật.

### V3 — giữ lịch sử hợp lệ quanh khoảng mất mặt

`ml/features.py` dùng phiên bản **`ear-pose-pixel-blink-v3-gap-history`**:

- Giữ các quan sát hợp lệ và thiếu dữ liệu trong cửa sổ thời gian đang xét;
  không xóa toàn bộ lịch sử chỉ vì mất quan sát từ 1 giây.
- Chỉ cộng thời gian giữa hai quan sát hợp lệ cách nhau không quá 0,5 giây.
  Khoảng mất mặt không được tính là mở mắt hoặc nhắm mắt.
- Bất kỳ quan sát lỗi hay khoảng gián đoạn dài nào cũng ngắt thời gian nhắm
  mắt liên tục. Ví dụ nhắm mắt 9 giây, thiếu dữ liệu 1 giây, nhắm tiếp 10 giây
  không được gộp thành nhắm mắt liên tục 20 giây.
- Vẫn yêu cầu quan sát hiện tại hợp lệ và độ phủ ít nhất 80%. Runtime trả
  `UNKNOWN` khi mất mặt, dữ liệu cũ hoặc không đủ độ phủ; không giữ dự đoán cũ
  qua các frame mất mặt.

`face_loss_reset_seconds` còn dùng cho baseline replay và thuật toán v2.
`DrowsinessModel` chọn đúng `LegacyFeatureWindow` cho artifact
`ear-pose-pixel-blink-v2`; model v3 dùng `FeatureWindow` mới. Không đổi cách
tính đầu vào của model cũ khi nạp lại. Khi train, dữ liệu phải đúng phiên bản;
không dùng CSV v2 để gắn nhãn model v3. Lệnh thí nghiệm cũ ở các mục trên là
lịch sử, cần mã nguồn cùng phiên bản để chạy lại; không chạy đè vào kết quả cũ.

Lượt v3 dùng đúng 279 video / 14 người phát triển, cửa sổ 20 giây và 4 fold như
lượt eyes/full. Nhãn frame, ngưỡng độ phủ và danh sách video cách ly giữ nguyên.
RF/SVM đều dùng 19 đặc trưng. Các người test đã xem trước đó không được đọc lại
trong lượt này; cần người mới để nghiệm thu độc lập.

Chạy từ `edge-ai`, với plan và dataset cục bộ đã chuẩn bị:

```powershell
./.venv/Scripts/python.exe -X utf8 -m ml.nthu --manifest ml-runs/ai-next-20261107/development.csv --output-dir ml-data/nthu-gap-history/development --workers 4
./.venv/Scripts/python.exe -X utf8 -m ml.nthu_train select --features ml-data/nthu-gap-history/development/features.csv --plan ml-runs/nthu-gap-history-20261107/plan.json --run-dir ml-runs/nthu-gap-history-20261107/full --feature-group full
./.venv/Scripts/python.exe -X utf8 -m ml.nthu_recovery --old-features ml-data/nthu-v1/development/features.csv --new-features ml-data/nthu-gap-history/development/features.csv --old-run ml-runs/nthu-ablation-20261107 --new-run ml-runs/nthu-gap-history-20261107/full --plan ml-runs/nthu-gap-history-20261107/plan.json --output-dir ml-runs/nthu-gap-history-20261107
```

Chỉ chạy bước `select` vào thư mục run mới. Một lần chọn đã đóng băng sẽ không
bị ghi đè. Báo cáo so sánh cũng từ chối ghi đè kết quả đã có.

Cache `observations-*.npz` chỉ lưu thời gian, EAR và hai chỉ số hướng đầu,
không chứa ảnh hoặc landmark; mỗi file có checksum trong audit. Dữ liệu,
cache, model và kết quả nằm trong `ml-data/` và `ml-runs/` đã được gitignore.
`report.json` tách chỉ số trên tập cửa sổ chung, toàn bộ cửa sổ mới và phần được
phục hồi; không coi số liệu trên hai tập cửa sổ khác nhau là cải thiện trực tiếp.

#### Kết quả v3 — hoàn tất ngày 07/11/2026

- Đã trích xuất đủ **279/279 video**, không thêm video cách ly. Giữ lại
  **5.551/8.547** cửa sổ (64,95%), so với **4.327/8.547** trước đó (50,63%).
- Phục hồi **1.224 cửa sổ**: 422 không buồn ngủ và 802 buồn ngủ. Không mất cửa
  sổ cũ; toàn bộ 19 giá trị đặc trưng và nhãn trên 4.327 cửa sổ chung giữ nguyên.
- Còn 1.903 cửa sổ không đạt chất lượng và 1.093 cửa sổ nhãn trộn bị loại.
  Không hạ ngưỡng độ phủ hay sửa nhãn để tăng số liệu.
- Thử 24 cấu hình, **96 lần fit CV**, 252 đối chiếu ngưỡng. RF được chọn:
  300 cây, depth 10, leaf 5, trọng số lớp 0/1 là 1/0,75, ngưỡng 0,40;
  refit **732 cửa sổ không chồng lấn**.

**So trên cùng 4.327 cửa sổ phát triển ngoài fold:**

| Chỉ số gộp cửa sổ | RF v2/full | RF v3/full |
|---|---:|---:|
| Accuracy | 91,19% | **91,77%** |
| Macro F1 | 0,8438 | **0,8538** |
| Recall DROWSY | 98,27% | **98,67%** |
| FPR | 37,11% | **35,84%** |

Trên toàn bộ 5.551 cửa sổ mới, RF có accuracy **92,51%**, Macro F1 **0,8850**,
recall **98,62%**, FPR **27,74%**. Đây là tập có thêm cửa sổ được phục hồi;
không gọi chênh lệch 91,19% → 92,51% là cải thiện trên cùng benchmark.

Trung bình theo người trên tập mới: Macro F1 **0,8805**, recall **98,43%**,
FPR **23,22%**; cả 14 người nay đều có cửa sổ nhãn âm, thay vì chỉ 13 người.
Riêng điều kiện `nightglasses`, FPR gộp vẫn **49,61%** (256 cửa sổ nhãn âm).
Đây là kết quả chọn model bằng CV, chưa phải chất lượng đã nghiệm thu trên
người mới hay camera RGB thực tế trong tối.

Artifact **`rf-nthu-full-20261107-8d459c63`**:
`ml-runs/nthu-gap-history-20261107/full/selected.joblib`.
Minh chứng trong cùng thư mục run: `comparison.md`, `report.json`,
`development_oof_predictions.csv`, `common_windows_confusion.png`,
`verification.json`, `code-audit.json`, `tests.log` và các log từng bước.

**72/72 test code đạt**. Kiểm tra thêm: 279 cache quan sát đúng checksum,
nạp lại được RF/SVM mới và các artifact v2 cũ; replay số liệu của 3 video thật
khớp 97 cửa sổ đặc trưng qua runtime, 190 quan sát thiếu dữ liệu đều trả
`UNKNOWN`; 47 file kết quả/model cũ giữ nguyên checksum. Chưa chạy webcam hay
tải vật lý thật, chưa đọc lại tập test và chưa thay model camera đang cấu hình.

### Kết quả v1 ngày 04/11/2026 — lưu để đối chiếu

Đã train RF/SVM từ đúng ba ZIP trong `D:/dataset`: `Fold1_part2.zip`,
`Fold2_part1.zip`, `Fold2_part2.zip`. Có 18 người / 36 video nhãn 0 và 10;
10.683 cửa sổ đạt chất lượng, 71 cửa sổ bị loại. Bỏ thêm 5 điểm baseline chưa
warmup cho cả ba phương pháp, còn 10.678 cửa sổ dùng so sánh. Một frame trùng
chính xác PTS ở video `11/0` được bỏ; toàn bộ thời gian còn lại dùng PTS gốc.

Split theo người: **10 train / 4 validation / 4 test**, seed 42. Model/ngưỡng được
chọn bằng validation; test gồm 2.272 cửa sổ từ 4 người chưa dùng để fit hoặc chọn
tham số. Các số sau là kết quả trên test:

| Phương pháp | Accuracy | Macro F1 | Recall DROWSY |
|---|---:|---:|---:|
| Quy tắc hiện tại | 53,65% | 0,5364 | 56,10% |
| Random Forest | 60,61% | 0,6026 | 52,24% |
| SVM | 59,38% | 0,5911 | 52,33% |

RF được chọn bằng validation macro F1 = 0,7739. Cấu hình: 150 cây,
`max_depth=None`, `min_samples_leaf=3`, ngưỡng điểm RF 0,65. Phiên bản artifact:
`rf-uta-20261104-961ba0b2`. **Recall DROWSY của RF còn thấp**, và điểm validation
cao hơn đáng kể so với test. Cần cải thiện khả năng tổng quát và kiểm tra camera;
chưa coi đây là model đã nghiệm thu cảnh báo thực tế. Nhãn gốc là nhãn cả video,
các cửa sổ chồng lấn không phải những mẫu quan sát độc lập.

Kết quả được lưu cục bộ tại `edge-ai/ml-runs/uta-three-zips-20261104/`:

- `selected.joblib`, `rf.joblib`, `svm.joblib`: artifact đã train thật.
- `comparison.md`, `report.json`: chỉ số, confusion matrix, kết quả từng người test.
- `confusion_matrices.png`, `test_metrics.png`: hình tổng hợp, không chứa ảnh mặt.
- `input-audit.json`, `run-plan.json`, `split.json`, `extraction.json`: nguồn ZIP,
  kiểm tra CRC, split đã chốt và xử lý timestamp.
- `test_predictions.csv`, `requirements-lock.txt`: dự đoán test và môi trường.

Đã nạp lại artifact và đối chiếu đủ 2.272 dự đoán test, kết quả khớp bản đã lưu.
Artifact v1 dùng tọa độ chuẩn hóa cũ. Runtime v2 **từ chối nạp model v1** vì
khác cách tính đặc trưng; cần train lại trước khi thử camera. Giữ các số và file
v1 làm mốc, không sửa hoặc ghi đè kết quả lịch sử.

### Tối ưu v2: hình học pixel, đặc trưng thời gian và GroupKFold

`eye.py` và `head_pose.py` quy đổi landmark theo **chiều rộng/cao của đúng ảnh
đưa vào MediaPipe** trước khi tính khoảng cách. `main.py` và `ml/extract.py`
dùng chung phép tính; baseline đổi phiên bản thành `drowsiness-v3.1-pixel`.
Các ngưỡng quy tắc vẫn là giá trị demo, cần thử lại trên camera sau sửa hình học.

`ml/features.py` có 19 đặc trưng nhân quả, phiên bản `ear-pose-pixel-blink-v2`:
11 thống kê ban đầu, thêm EAR p90, mean/std tương đối theo p90 trong chính cửa sổ,
số lần khép mắt hoàn chỉnh mỗi phút, mean/std thời lượng khép mắt, phân vị tốc độ
đóng/mở mắt. P90 là mức tham chiếu cục bộ, không khẳng định mắt đang mở hoàn toàn.
Chỉ tính lần khép mắt đã quan sát cả bắt đầu và kết thúc; mất dữ liệu ngắt lần đó.
Lấy mẫu tối đa 10 Hz có thể bỏ qua những lần chớp mắt ngắn.

Quy trình tối ưu giữ nguyên nhãn video gốc 0/10, không yêu cầu gán nhãn tay:

1. Trích xuất một lần và lưu chuỗi `timestamp, EAR, yaw, pitch` trong cache riêng tư.
2. Tạo cửa sổ 5/10/20 giây từ chuỗi đó; so sánh trên cùng các điểm kết thúc đạt
   chất lượng cho cả ba cửa sổ. Đây là phạm vi dữ liệu hợp lệ theo gate 20 giây.
3. Giữ riêng bốn người `07, 08, 12, 15` của test cũ. Gộp 14 người train/validation
   cũ làm development, dùng 4-fold **GroupKFold** với seed 42. Mỗi lượt giữ toàn
   bộ video của người validation ngoài train.
4. So sánh ba bộ đặc trưng `core` (11 số), `eyes` (13 số), `full` (19 số).
   RF thử depth/leaf/max_features; SVM thử C/gamma. Scaler chỉ fit trên train mỗi fold.
   Các cửa sổ train được chọn không chồng lấn trong từng video; validation giữ
   mọi điểm hợp lệ. Chỉ số chọn model cho mỗi người trọng số bằng nhau.
5. Ngưỡng thử nghiệm hướng tới mean-person recall DROWSY >= 0,75 và FPR <= 0,30.
   Trong các cấu hình đạt, ưu tiên macro F1; nếu không đạt, giảm tổng mức vi phạm
   hai mục tiêu trước. Đây là giá trị thử nghiệm, chưa phải chính sách nhóm chốt.
6. Ghi `selection-frozen.json` trước khi dự đoán test. Test cũ đã được xem kết quả,
   nên điểm mới trên đó chỉ là **kiểm tra hồi quy**, không phải benchmark độc lập.
   Điểm CV là điểm dùng tinh chỉnh, không được gọi là nested-CV chưa thiên lệch.

Chạy từ thư mục **edge-ai**; không ghi đè thư mục output đã hoàn tất:

```powershell
./.venv/Scripts/python.exe -X utf8 -m ml.extract --manifest ml-data/uta-optimized-v2/manifest.csv --output-dir ml-data/uta-optimized-v2/features-10s --workers 3 --allow-duplicate-pts
./.venv/Scripts/python.exe -X utf8 -m ml.rewindow --source-dir ml-data/uta-optimized-v2/features-10s --output-dir ml-data/uta-optimized-v2/windows
./.venv/Scripts/python.exe -X utf8 -m ml.optimize --features ml-data/uta-optimized-v2/windows/window-5/features.csv ml-data/uta-optimized-v2/windows/window-10/features.csv ml-data/uta-optimized-v2/windows/window-20/features.csv --split-plan ml-data/uta-optimized-v2/run-plan.json --output-dir ml-runs/uta-optimized-v2
./.venv/Scripts/python.exe -X utf8 -m ml.plot_report --run-dir ml-runs/uta-optimized-v2
```

`ml.optimize` lưu kế hoạch, score CV có thể tiếp tục khi gián đoạn trước khi chốt,
bảng ablation/ngưỡng, lựa chọn đã chốt, artifact RF/SVM/selected và báo cáo thật.
Khi trích xuất song song, mỗi video chạy trong worker mới để giải phóng trạng thái
native của decoder/MediaPipe (Python >= 3.11). Lỗi đọc frame hoặc lỗi native làm
lượt trích xuất báo lỗi; cache video đã hoàn tất vẫn giữ nguyên. Chạy lại cùng
lệnh để tiếp tục sau khi kiểm tra nguồn, không mặc định bỏ video bị lỗi.
Mặc định camera vẫn baseline; không đổi `.env`, không tự mở camera, không tự push
dataset/model lên GitHub. Sau khi train xong, thử từ **thư mục gốc project**:

```powershell
$env:AI_MODEL_MODE = 'ml'
$env:AI_MODEL_PATH = (Resolve-Path 'edge-ai/ml-runs/uta-optimized-v2/selected.joblib').Path
./edge-ai/.venv/Scripts/python.exe -X utf8 edge-ai/main.py
```

```text
Video có nhãn                         Camera khi chạy thật
  ↓ thời gian nguồn video               ↓ đồng hồ monotonic
MediaPipe → EAR, yaw/pitch             MediaPipe → EAR, yaw/pitch
  ↓                                     ↓
ml/features.py: cùng cách tính cửa sổ thời gian và kiểm tra chất lượng
  ↓                                     ↓
Train RF / StandardScaler + SVM        Model đã chọn → DROWSY / không buồn ngủ
  ↓                                     ↓
Chọn bằng validation                  Ghép quy tắc hướng đầu → 4 trạng thái
  ↓                                     ↓
Đánh giá test + xuất artifact          Xác nhận → event → SQLite / MQTT / BE
```

Chỉ học hai lớp **ALERT=0** và **DROWSY=1**. Nhãn low-vigilance=5 được loại khỏi
thử nghiệm đầu, không đổi tên thành DISTRACTED. `DISTRACTED` vẫn do quy tắc hướng
đầu đã hiệu chuẩn quyết định. Nhãn ALERT của dataset là nhãn cho bài toán nhị phân;
không tự động có nghĩa `ATTENTIVE` trong hệ thống bốn trạng thái.

### 1. Tải một phần dữ liệu vào ổ D

Nguồn: [UTA-RLDD chính thức](https://sites.google.com/view/utarldd/home), có đường
dẫn Google Drive tại mục **RLDD Dataset Videos**. Chọn trước 3–5 người để thử trích
xuất; sau đó hướng tới ít nhất 20 người có đủ hai video 0 và 10. Không cần tải toàn
bộ 111,3 GB. Bộ train/validation/test yêu cầu tối thiểu 5 người có dữ liệu hợp lệ;
ít người chỉ dùng kiểm tra công cụ, chưa đủ kết luận về khả năng tổng quát.

Nguồn Drive hiện đóng dữ liệu thành 10 ZIP (`Fold1_part1.zip` …
`Fold5_part2.zip`), mỗi file khoảng 7,5–13,4 GiB. Dùng công cụ dưới đây để đọc
mục lục ZIP bằng HTTP Range rồi chỉ lấy video 0/10 của những người đã chọn,
không tải cả archive hay toàn bộ dataset. Từ thư mục **edge-ai**:

```powershell
# Chỉ đọc mục lục và báo dung lượng; chưa tải video.
./.venv/Scripts/python.exe -X utf8 -m ml.fetch_uta --catalog-only --count 5
# Lấy 5 người đầu theo mã số, giới hạn tổng video ở 8 GiB.
./.venv/Scripts/python.exe -X utf8 -m ml.fetch_uta --count 5 --max-gib 8
```

`--subjects 01 02 03 04 05` cho phép chọn mã người rõ ràng. Catalog nằm trong
`ml-data/uta-catalog.json`; dùng `--refresh-catalog` nếu nguồn thay đổi. File tải
xong được kiểm tra dung lượng và CRC32 trong ZIP; chạy lại sẽ bỏ qua video đã
kiểm tra đúng. File đang tải có đuôi `.part`; nếu ngắt giữa chừng, lần sau tải lại
video đó, còn video đã xong được giữ. Công cụ chừa ít nhất 10 GiB trống trên ổ đích.
Mã nguồn chỉ đọc dữ liệu công khai từ Drive, không dùng tài khoản Google cá nhân.
Nếu Drive chặn/quota hoặc không trả HTTP 206, chương trình dừng và không tự tải
toàn ZIP; có thể tải thủ công từ link chính thức rồi chỉ giải nén video cần dùng.

Nếu đã có bản ZIP chính thức trên máy, công cụ có thể lấy riêng các video từ ZIP
mà không kết nối mạng và không giải nén toàn bộ:

```powershell
./.venv/Scripts/python.exe -X utf8 -m ml.fetch_uta --local-zip 'D:/datasets/Fold1_part1.zip' --count 5 --max-gib 8
```

Đường dẫn trên là ví dụ; thay bằng ZIP thật. Có thể lặp lại `--local-zip` nếu video
cần dùng nằm ở nhiều ZIP. Catalog local được lưu riêng để không thay catalog Drive.

Năm người đầu chỉ là **pilot kiểm tra luồng và chất lượng trích xuất**. Khi mở
rộng, cần lấy người từ nhiều fold/điều kiện; không dùng lựa chọn file nhỏ hoặc kết
quả pilot tốt để kết luận model tổng quát cho tài xế ngoài thực tế.

Thư mục gợi ý (đã được `.gitignore` bỏ qua):

```text
edge-ai/datasets/UTA-RLDD/
  01/0.mp4       # ALERT, kiểm tra nhãn từ bản tải gốc
  01/10.mp4      # DROWSY
  02/0.mp4
  02/10.mp4
  ...
```

Tên thư mục người phải giữ nguyên từ bộ gốc, kể cả số 0 ở đầu. Công cụ hỗ trợ
`<mã người dạng số>/<0|5|10>.<mp4|mov|avi|mkv>`; nếu cấu trúc tải về khác, kiểm tra
mapping nhãn và tạo CSV rõ ràng, không tự đổi tên để đoán nhãn. Không dùng tên clip
`DROWSY_...` do chương trình cũ tự dự đoán làm nhãn đúng để huấn luyện.

Dataset gán nhãn **trạng thái chủ yếu của cả video**, không đánh dấu chính xác
từng thời điểm nhắm mắt. Chỉ một phần người tham gia cho phép công bố ảnh khuôn
mặt; giữ video/đặc trưng riêng, không đưa vào Git hoặc báo cáo hình ảnh tùy tiện.
Khi báo cáo kết quả có sử dụng UTA-RLDD, trích dẫn công trình của Ghoddoosian,
Galib và Athitsos (2019) theo hướng dẫn trên trang dataset.

### 2. Tạo manifest và trích xuất

Từ **thư mục gốc project**, mở PowerShell rồi chạy:

```powershell
./edge-ai/.venv/Scripts/python.exe -m pip install -r edge-ai/requirements.txt
Set-Location edge-ai
./.venv/Scripts/python.exe -X utf8 -m ml.dataset --root datasets/UTA-RLDD --output ml-data/manifest.csv
./.venv/Scripts/python.exe -X utf8 -m ml.extract --manifest ml-data/manifest.csv --output-dir ml-data/features
```

Với nhiều video, có thể thêm `--workers 2` hoặc `--workers 3` để chạy song song.
Mỗi video có detector riêng; thứ tự CSV vẫn theo manifest và cache dùng chung
cho lần chạy lại. Công cụ in tiến độ mỗi 30 giây cho video đang xử lý. Decoder
chỉ chuyển sang ảnh BGR ở frame cần lấy mẫu; timestamp vẫn đọc từ video gốc.

Hai lệnh `-m ml...` chạy từ thư mục `edge-ai`. Có thể chọn người bằng
`--subjects 01 02 03 04 05` sau khi kiểm tra tên thư mục thực tế. Manifest đã có
không bị ghi đè; tạo tên mới khi thay đổi tập người. CSV hỗ trợ chỉnh tay gồm:

```csv
subject_id,video_id,path,label,label_source
01,uta-01-alert,../datasets/UTA-RLDD/01/0.mp4,ALERT,UTA-RLDD original video label 0
01,uta-01-drowsy,../datasets/UTA-RLDD/01/10.mp4,DROWSY,UTA-RLDD original video label 10
```

Đường dẫn tương đối trong CSV tính từ **thư mục chứa CSV**. Ví dụ CSV đặt trong
`ml-data/` thì path phải là `../datasets/...`; công cụ tạo manifest tự ghi đường
dẫn tuyệt đối để tránh nhầm. Mỗi video cần ID riêng, không trùng nội dung nguồn.

Để thử nhanh khâu trích xuất với 60 giây đầu mỗi video, dùng một thư mục riêng:

```powershell
./.venv/Scripts/python.exe -X utf8 -m ml.extract --manifest ml-data/manifest.csv --output-dir ml-data/pilot-60s --max-seconds 60
```

Mặc định: cửa sổ 10 giây, bước 2 giây, lấy mẫu tối đa 10 Hz, khoảng quan sát
hợp lệ tối đa 0,5 giây, yêu cầu ít nhất 80% thời gian có dữ liệu mắt/hướng đầu.
Đây là cấu hình thử nghiệm, chưa phải thông số đã tối ưu bằng dữ liệu.
EAR mean/std/p10, PERCLOS, lần nhắm liên tục dài nhất và thống kê yaw/pitch là
đầu vào model; mã người/video, nhãn, timestamp và coverage không được đưa vào model.
Yaw/pitch hiện là **tỷ lệ landmark**, không phải độ quay đầu.

- PERCLOS dùng thời gian được quan sát, không lấy số frame nhắm chia tổng frame.
- Khoảng thiếu mặt/landmark không được điền 0 rồi coi là mắt mở.
- Mất dữ liệu đủ 1 giây xóa cửa sổ ML, cần quan sát lại đủ chiều dài cửa sổ.
- Video dùng PTS (`CAP_PROP_POS_MSEC`), không dùng tốc độ máy đang trích xuất.
  Nếu decoder không trả PTS tăng, công cụ dừng. Chỉ khi đã xác nhận video có FPS
  cố định mới dùng `--timestamp-source frame-index`; lựa chọn được lưu trong audit.
  Nếu nguồn có vài frame trùng **chính xác** PTS, có thể dùng
  `--allow-duplicate-pts`: bỏ frame không có thời gian tiến thêm, tối đa 30 frame
  và 0,1% số frame đọc. Không thay timestamp; PTS đi lùi vẫn bị từ chối.
  Số frame bị bỏ được ghi trong audit và report. Cache strict đã hợp lệ có thể
  dùng lại vì đã chứng minh không có timestamp trùng.
- `features.csv` chứa bảng đặc trưng; `extraction.json` ghi hash video/model landmark,
  phiên bản thư viện, số cửa sổ nhận/loại và cấu hình. Cache từng video giúp tiếp tục
  sau lỗi bằng cách chạy lại cùng lệnh. Đổi video/cấu hình sẽ dùng cache mới.
- Video không đọc được/đọc dở bị báo lỗi; toàn bộ cửa sổ không đạt chất lượng sẽ
  không sinh dữ liệu train. Không tự xem việc tạo CSV rỗng là thành công.
- Dữ liệu đầu ra gồm chỉ số và metadata, không xuất ảnh mặt hoặc từng landmark.

### 3. Train và so sánh

Vẫn trong thư mục `edge-ai`:

```powershell
./.venv/Scripts/python.exe -X utf8 -m ml.train --features ml-data/features/features.csv --output-dir ml-runs/experiment-01 --seed 42
```

Để tạo biểu đồ PNG từ kết quả thật đã train, cài thêm thư viện vẽ và chạy:

```powershell
./.venv/Scripts/python.exe -m pip install -r ml/requirements.txt
./.venv/Scripts/python.exe -X utf8 -m ml.plot_report --run-dir ml-runs/experiment-01
```

Biểu đồ chỉ chứa thống kê tổng hợp, không xuất ảnh khuôn mặt. Report có thêm số
cửa sổ hợp lệ/bị loại cho từng lớp và số video không có cửa sổ dùng được; cần đọc
các số này cùng accuracy/F1 để tránh chỉ đánh giá trên những đoạn dễ quan sát.

Chia khoảng 60/20/20 theo **người**, không chia ngẫu nhiên các cửa sổ chồng lấn.
Với 20 người có đủ dữ liệu sẽ là 12/4/4. Nếu sau lọc chất lượng thiếu một lớp trong
split, chỉ tìm split có đủ lớp, không chọn split dựa trên kết quả model. Mã người
phải thống nhất cả khi quay nhiều phiên. Dùng cùng split cho RF và SVM; scaler
của SVM chỉ được fit trên train.

RF thử hai độ sâu; SVM thử ba giá trị C. Tham số/ngưỡng và model thắng được chọn
bằng macro F1 trên validation, hòa thì xét recall rồi precision DROWSY. Test chỉ
được đánh giá sau khi chọn xong; không chỉnh tiếp model theo test rồi gọi đó là
test độc lập. Tạo run mới để giữ kết quả cũ; tránh lặp lại thử seed để săn điểm test.

Baseline dùng lại `PerclosCalculator` và quy tắc hồi phục mắt mở 1 giây của code
hiện tại, được replay bằng thời gian video. So sánh **ứng viên buồn ngủ nhị phân
trước khi ghép hướng đầu**, cùng các điểm kết thúc cửa sổ với RF/SVM; điểm baseline
chưa warmup được loại cho cả ba và ghi số lượng. Chưa dùng phép so sánh này để
kết luận toàn bộ chuỗi event/cảnh báo ngoài xe hoạt động chính xác.

Đầu ra trong `ml-runs/experiment-01/`:

| File | Mục đích |
|---|---|
| `comparison.md` | Bảng baseline/RF/SVM: macro F1, recall/precision DROWSY |
| `report.json` | Accuracy, chỉ số từng lớp, thử nghiệm validation, latency và giới hạn |
| `confusion_*.json` | Confusion matrix; hàng là nhãn thật, cột là dự đoán |
| `split.json` | Danh sách người/video và số cửa sổ từng tập |
| `test_predictions.csv` | Truy vết từng dự đoán test; lưu riêng vì có mã người/video |
| `rf.joblib`, `svm.joblib`, `selected.joblib` | Model, ngưỡng, cấu hình đặc trưng, phiên bản |
| `extraction.json`, `requirements-lock.txt` | Nguồn dữ liệu và môi trường để tái lập |

Điểm RF là tỷ lệ phiếu chưa hiệu chuẩn; SVM dùng decision margin. **Chưa gọi các
điểm này là confidence đáng tin cậy hoặc gửi thành phần trăm chắc chắn lên BE.**
Latency trong report chỉ đo bước dự đoán model trên máy này, không bao gồm camera,
MediaPipe, thời gian gom cửa sổ, MQTT/HTTP hay ACK.

Đây là thử nghiệm hai lớp bằng subject holdout trên tập con; **khác** quy trình
5-fold/ba lớp của tác giả UTA-RLDD, nên không so điểm trực tiếp như cùng một bài toán.
Nhãn cả video chưa đủ tính độ trễ phát hiện hoặc số cảnh báo sai/phút: cần thêm
video có nhãn thời gian. Nếu validation chưa hơn baseline, report khuyến nghị
giữ baseline; không tự bật model chỉ vì train đã chạy xong.

### 4. Thử model với camera

Chỉ nạp artifact do nhóm tự train và tin cậy: `joblib.load` có thể thực thi mã trong
file, không nạp model tải từ nguồn lạ. Dùng môi trường cùng phiên bản thư viện;
code kiểm tra schema đặc trưng, sklearn/numpy/MediaPipe và hash landmark model.

Từ thư mục **gốc project**, thử bằng biến môi trường trong terminal hiện tại:

```powershell
$env:AI_MODEL_MODE = 'ml'
$env:AI_MODEL_PATH = (Resolve-Path 'edge-ai/ml-runs/experiment-01/selected.joblib').Path
./edge-ai/.venv/Scripts/python.exe -X utf8 edge-ai/main.py
```

Log phải có `Loaded ML model ...`; overlay, telemetry và MQTT status dùng phiên bản
model thực đã nạp. Trước khi đủ cửa sổ hợp lệ: `UNKNOWN`. Không buồn ngủ vẫn phải
qua quy tắc hướng đầu: lệch đủ lâu → `DISTRACTED`; hướng đầu hợp lệ/hiệu chuẩn
xong → `ATTENTIVE`. Sau đó giữ cơ chế xác nhận và THRESHOLD_REACHED, cảnh báo local,
queue SQLite, video và MQTT đang có.

Không có/hỏng artifact: log lỗi và fallback baseline rõ ràng. Lỗi khi model đang
chạy: báo `UNKNOWN` đến khi khởi động lại, không giữ kết quả cũ làm trạng thái mới.
Muốn quay lại baseline trong terminal:

```powershell
$env:AI_MODEL_MODE = 'baseline'
./edge-ai/.venv/Scripts/python.exe -X utf8 edge-ai/main.py
```

### 5. Nghiệm thu sau khi train trên dữ liệu thật

1. Lưu bảng so sánh và confusion matrix thật, ghi số người/video/cửa sổ từng tập.
2. Chạy camera ở các điều kiện ánh sáng, có/không kính, quay đầu và mất mặt.
   Ngồi thử tại chỗ; không thử gây buồn ngủ khi lái xe.
3. Kiểm tra model không biến mọi `ALERT` thành `ATTENTIVE`, và mất mặt không tạo
   cảnh báo từ thời gian cũ. Ghi model version cùng video/nhãn kiểm tra thủ công.
4. Test broker/BE ngắt và phục hồi, queue gửi bù, âm thanh local, rồi luồng tới
   ESP32 và tải thật. Báo riêng lỗi phân loại và lỗi truyền/điều khiển.
5. Đo tốc độ toàn pipeline và RAM trên máy chạy thật, tách khỏi latency estimator.

Các thư mục `datasets/`, `ml-data/`, `ml-runs/`, `models/` dưới `edge-ai` đều được
Git bỏ qua. Hash/đặc trưng vẫn là dữ liệu cần quản lý; chỉ xuất bảng tổng hợp đã
kiểm tra để làm báo cáo chung, không commit tự động video hoặc clip cá nhân.

Các file thực hiện: `ml/fetch_uta.py`, `ml/dataset.py`, `ml/extract.py`, `ml/features.py`,
`ml/baseline.py`, `ml/train.py`, `ml/runtime.py`. Kiểm thử bằng lệnh ở mục dưới.

## Chạy và kiểm tra các worker camera/video/âm thanh

Từ thư mục gốc project, dùng môi trường Python riêng của AI:

```powershell
./edge-ai/.venv/Scripts/python.exe -m pip install -r edge-ai/requirements.txt
./edge-ai/.venv/Scripts/python.exe -X utf8 edge-ai/main.py
```

`requirements.txt` không khai báo `sqlite3` vì Python đã có sẵn; `requests` dùng
để upload video. Không dùng môi trường AI để chạy Backend nếu chưa cài thư viện BE.

### Upload video không chặn vòng lặp camera

- `main.py` đóng MP4 rồi ghi đường dẫn tuyệt đối, device code, state và message ID
  vào bảng SQLite `video_upload_queue`. Worker nền phụ trách HTTP, không gọi upload
  trong vòng lặp camera hoặc chờ upload hết các clip khi thoát chương trình.
- Worker dùng HTTP Basic với `AI_MQTT_USERNAME` và `AI_MQTT_PASSWORD` từ `.env`.
  Đây phải là credential của Vision Node đã đăng ký và kích hoạt, không dùng tài
  khoản MQTT quản trị. `BACKEND_HOST` trỏ tới máy chạy Backend.
- Chỉ nhận thành công khi HTTP 200/201 và JSON có `status=SAVED`, đúng `message_id`
  và `video_id` hợp lệ. MQTT `storage_ack` không xác nhận lưu video.
- Sau xác nhận, worker lưu trạng thái `UPLOADED` trước khi xóa clip. Nếu lỗi dọn
  file, lần sau chỉ dọn lại, không upload lại. Nếu mất phản hồi sau khi server đã
  lưu, gửi lại cùng ID để Backend xử lý idempotent.
- Lỗi mạng/xác thực/phản hồi chưa hợp lệ: giữ file và queue, tăng thời gian chờ
  thử lại từ 5 giây, tối đa 300 giây theo mặc định. Một clip lỗi không chặn toàn
  bộ các clip tiếp theo. File không còn tồn tại được ghi `MISSING` để kiểm tra.
- Khi chạy lại chương trình, worker tiếp tục các clip đã có trong queue, kể cả
  khi MQTT không kết nối. Database cũ được thêm cột lịch thử lại, giữ dữ liệu cũ.
- Chạy một tiến trình AI cho mỗi thư mục queue/recordings. Clip cũ chỉ có trong
  `recordings/` nhưng chưa từng được ghi queue không được tự gán event ID để gửi;
  cần xác định đúng sự kiện trước. Clip đang ghi khi bị tắt cưỡng bức có thể chưa
  hoàn tất MP4 và chưa được đưa vào queue.

### Cảnh báo tại máy AI

- Khi tạo `DROWSY_THRESHOLD_REACHED` hoặc `DISTRACTED_THRESHOLD_REACHED`, worker
  âm thanh nhận sự kiện trực tiếp, không chờ broker, Backend hay upload video.
- Windows dùng `winsound.Beep` trên luồng nền. Event có policy v1 dùng lịch
  tăng mức/nhắc ở đầu README; cooldown cũ chỉ còn cho lời gọi legacy.
- Nền tảng khác dùng terminal bell làm fallback; phải thử loa thực tế. Lỗi âm
  thanh được ghi log, không dừng camera. UNKNOWN kéo dài có âm báo lỗi riêng.

### Mất mặt và thời gian

- MediaPipe nhận số mili giây thực trôi qua từ `time.monotonic()`, luôn tăng,
  thay cho giả định mỗi frame dài 33 ms.
- Mất mặt/read camera lỗi: ngắt bộ đếm nhắm mắt, lệch hướng đầu, xác nhận trạng
  thái và sự kiện liên tục. Trạng thái ứng viên chuyển `UNKNOWN`; trạng thái xác
  nhận của policy chuyển UNKNOWN ngay. Khoảng không quan sát được không tính là
  bằng chứng buồn ngủ/mất tập trung.
- Mất mặt đủ 1 giây theo mặc định: xóa cửa sổ PERCLOS và warmup lại. Một khoảng
  dừng giữa hai lần thấy mặt quá 0,5 giây cũng được xem là gián đoạn quan sát.
- Giữ baseline hướng đầu đã hiệu chuẩn. Nếu đang hiệu chuẩn dở thì bắt đầu lại
  với một khoảng quan sát liên tục. Khi thấy mặt lại, bộ đếm lệch hướng bắt đầu
  từ 0, không tự lấy tư thế đang quay lệch làm baseline mới.
- Các mốc 1 giây/0,5 giây là mặc định kỹ thuật để thử nghiệm, chưa phải ngưỡng
  đã được đánh giá trên dataset. Có thể điều chỉnh trong `.env`:

```dotenv
AI_FACE_LOSS_RESET_SECONDS=1.0
AI_MAX_OBSERVATION_GAP_SECONDS=0.5
AI_LOCAL_ALERT_ENABLED=true
AI_LOCAL_ALERT_COOLDOWN_SECONDS=10
AI_VIDEO_UPLOAD_INTERVAL_SECONDS=5
AI_VIDEO_UPLOAD_MAX_RETRY_SECONDS=300
```

### Kiểm tra tự động và thử nghiệm thực tế

```powershell
./edge-ai/.venv/Scripts/python.exe -X utf8 -m unittest discover -s edge-ai/tests -v
```

Các test dùng SQLite tạm, ảnh tổng hợp, loa giả và HTTP server thử trên loopback;
không mở camera, không gửi clip cá nhân và không ghi vào database Backend thật.
Kiểm tra thêm sau khi khởi động Backend và broker:

1. Chạy AI, đổi trạng thái để đóng clip: hình camera phải tiếp tục cập nhật khi
   worker upload. Xem log `Video uploaded successfully` sau xác nhận HTTP.
2. Tạm dừng Backend: clip đã đóng còn trên đĩa và trong queue. Bật Backend lại,
   chờ lịch retry; kiểm tra clip được lưu và không nhân đôi theo cùng message ID.
3. Chạy lại AI khi còn clip pending: worker phải tiếp tục gửi, không đổi ID clip.
4. Trong điều kiện ngồi tại chỗ, tạo sự kiện vượt ngưỡng; kiểm tra loa vẫn phát
   khi broker/Backend tạm ngừng. Sau khởi động, dành khoảng 5 giây nhìn thẳng để
   hiệu chuẩn hướng đầu và 10 giây dữ liệu mắt hợp lệ để warmup PERCLOS.
5. Quay lệch đầu chưa đủ thời gian, che camera trên 1 giây rồi xuất hiện lại:
   không được cộng thời gian bị che; PERCLOS warmup lại, baseline đầu đã chốt còn.

`recordings/` và database runtime được Git bỏ qua. File video upload thành công
được lưu ở kho riêng của Backend và chỉ được xóa bản local sau xác nhận.

## 1. TELEMETRY

**TOPIC:** `TELEMETRY_TOPIC`

**PAYLOAD:**
```json
{
  "message_id": "uuid-telemetry-001",
  "device_code": "EDGE_AI_001",
  "model_version": "1.0.0",
  "timestamp": "2026-10-19T15:00:00+00:00",
  "driver_state": "ATTENTIVE",
  "candidate_state": "ATTENTIVE",
  "face_detected": true,
  "ear": 0.285,
  "perclos": 0.05,
  "eyes_closed": false,
  "head_pose": {
    "yaw": 0.02,
    "pitch": -0.01,
    "roll": 1.5
  }
}
```

Gửi định kỳ mỗi giây, chứa trạng thái người lái đã xác nhận, trạng thái ứng viên và các thông số nhận diện khuôn mặt, mắt, hướng đầu.

- `driver_state`: Trạng thái đã xác nhận, thuộc `ATTENTIVE`, `DISTRACTED`, `DROWSY` hoặc `UNKNOWN`.
- `candidate_state`: Trạng thái ứng viên đang được theo dõi để xác nhận.
- `face_detected`: Có phát hiện khuôn mặt hay không.
- `ear`: Giá trị Eye Aspect Ratio trung bình của hai mắt.
- `perclos`: Tỷ lệ thời gian mắt nhắm trong cửa sổ tính toán.
- `eyes_closed`: Trạng thái mắt nhắm tại frame hiện tại.
- `head_pose`: Góc hoặc tỷ lệ ước lượng hướng đầu, gồm `yaw`, `pitch` và `roll`.

Các thông số không thể tính toán có thể nhận giá trị `null`, tùy cách triển khai hàm `publish_telemetry()`.

## 2. STATE_CHANGED

**TOPIC:** `EVENT_TOPIC`

**PAYLOAD:**
```json
{
  "message_id": "uuid-event-001",
  "sequence_number": 1,
  "device_code": "EDGE_AI_001",
  "timestamp": "2026-10-19T15:00:05+00:00",
  "event_type": "STATE_CHANGED",
  "previous_state": "ATTENTIVE",
  "state": "DISTRACTED"
}
```

Gửi khi trạng thái ứng viên đã duy trì đủ thời gian xác nhận và khác trạng thái đã xác nhận trước đó.

Các trường:
- `message_id`: UUID định danh duy nhất của event.
- `sequence_number`: Số thứ tự event trong phiên chạy Edge AI.
- `previous_state`: Trạng thái đã xác nhận trước đó; có thể là `null` khi xác nhận trạng thái lần đầu.
- `state`: Trạng thái mới được xác nhận.

**Lưu ý:** Code hiện tại không gửi trường `previous_state_duration_ms`. Backend nên tự xác định khoảng thời gian của từng trạng thái dựa trên các mốc thời gian của event, nếu cần.

## 3. DROWSY_THRESHOLD_REACHED

**TOPIC:** `EVENT_TOPIC`

**PAYLOAD:**
```json
{
  "message_id": "uuid-event-002",
  "sequence_number": 2,
  "device_code": "EDGE_AI_001",
  "timestamp": "2026-10-19T15:00:10+00:00",
  "event_type": "DROWSY_THRESHOLD_REACHED",
  "state": "DROWSY",
  "state_duration_ms": 3000
}
```

Gửi một lần khi trạng thái `DROWSY` được duy trì liên tục đủ thời gian quy định.

- `state`: Trạng thái đạt ngưỡng.
- `state_duration_ms`: Thời gian duy trì trạng thái được tính bởi Edge AI, tính bằng mili giây.

Giá trị cấu hình hiện tại: `THRESHOLD_SECONDS["DROWSY"] = 3.0`.

Thời gian chỉ được tính khi `candidate_state` và `confirmed_state` cùng là `DROWSY`. Bộ đếm được đặt lại nếu trạng thái ứng viên hoặc trạng thái xác nhận thay đổi.

## 4. DISTRACTED_THRESHOLD_REACHED

**TOPIC:** `EVENT_TOPIC`

**PAYLOAD:**
```json
{
  "message_id": "uuid-event-003",
  "sequence_number": 3,
  "device_code": "EDGE_AI_001",
  "timestamp": "2026-10-19T15:00:15+00:00",
  "event_type": "DISTRACTED_THRESHOLD_REACHED",
  "state": "DISTRACTED",
  "state_duration_ms": 3000
}
```

Gửi một lần khi trạng thái `DISTRACTED` được duy trì liên tục đủ thời gian quy định.

Giá trị cấu hình hiện tại: `THRESHOLD_SECONDS["DISTRACTED"] = 3.0`.

Điều kiện phát event và cách tính thời gian tương tự `DROWSY_THRESHOLD_REACHED`.

## 5. SESSION_ENDED

**TOPIC:** `EVENT_TOPIC`

**PAYLOAD:**
```json
{
  "message_id": "uuid-event-004",
  "sequence_number": 4,
  "device_code": "EDGE_AI_001",
  "timestamp": "2026-10-19T15:05:00+00:00",
  "event_type": "SESSION_ENDED",
  "final_state": "ATTENTIVE"
}
```

Gửi trong khối `finally` khi phiên Edge AI đã khởi tạo MQTT client thành công và chương trình bắt đầu kết thúc.

- `final_state`: Trạng thái đã xác nhận tại thời điểm kết thúc; có thể là `null` nếu chưa xác nhận được trạng thái nào.
- `sequence_number`: Số thứ tự tiếp theo trong chuỗi event của phiên chạy.

Backend có thể sử dụng event này để đóng bản ghi trạng thái người lái đang mở hoặc đánh dấu phiên giám sát đã kết thúc.

**Lưu ý:** Event này thể hiện quá trình Edge AI kết thúc, không đồng nghĩa chương trình luôn đóng bình thường. Code hiện tại chưa phân biệt nguyên nhân kết thúc như người dùng thoát, lỗi camera hay lỗi xử lý. Ngoài ra, việc gọi `publish_event()` trước `mqtt_client.close()` chưa tự đảm bảo Backend đã nhận được event; cần kiểm tra cơ chế gửi, hàng đợi offline và xác nhận publish trong implementation MQTT.

## 6. DEVICE_STATUS – ONLINE

**TOPIC:** `STATUS_TOPIC`

**PAYLOAD:**
```json
{
  "device_code": "EDGE_AI_001",
  "model_version": "1.0.0",
  "status": "ONLINE",
  "timestamp": "2026-10-19T15:00:00+00:00"
}
```

Thông báo thiết bị đang trực tuyến. Theo tài liệu cấu hình MQTT, trạng thái này được gửi khi kết nối Broker thành công, với QoS 1 và `retain=true`.

Việc gửi thực tế phụ thuộc vào implementation của `MQTTClient`.

## 7. DEVICE_STATUS – OFFLINE

**TOPIC:** `STATUS_TOPIC`

**PAYLOAD:**
```json
{
  "device_code": "EDGE_AI_001",
  "model_version": "1.0.0",
  "status": "OFFLINE",
  "timestamp": "2026-10-19T15:05:00+00:00"
}
```

Thông báo thiết bị ngoại tuyến khi chương trình đóng kết nối bình thường hoặc khi Broker phát Last Will do mất kết nối bất thường, tùy cấu hình MQTT.

**Lưu ý:** `main.py` hiện tại không trực tiếp gọi `publish_status("OFFLINE")` trong `finally`. Việc gửi trạng thái `OFFLINE` chủ động hoặc qua Last Will phụ thuộc vào `MQTTClient`.

## 8. DEVICE_STATUS – CAMERA_ERROR

**TOPIC:** `STATUS_TOPIC`

**PAYLOAD:**
```json
{
  "device_code": "EDGE_AI_001",
  "model_version": "1.0.0",
  "status": "CAMERA_ERROR",
  "timestamp": "2026-10-19T15:10:00+00:00"
}
```

Được yêu cầu gửi khi camera không đọc được frame liên tiếp đủ số lần giới hạn.

Cấu hình hiện tại:
- `MAX_CAMERA_FAILURES = 5`.
- Mỗi lần đọc frame thất bại, bộ đếm tăng lên.
- Khi bộ đếm đạt giới hạn, chương trình gọi `mqtt_client.publish_status("CAMERA_ERROR")` rồi thoát vòng lặp.

Khả năng gửi thành công phụ thuộc vào trạng thái kết nối và implementation của MQTT client.

## 9. BACKEND ACK – SAVED

**TOPIC:** `ACK_TOPIC`

**PAYLOAD:**
```json
{
  "message_id": "uuid-telemetry-001",
  "status": "SAVED"
}
```

Backend gửi ACK sau khi lưu message thành công.

Edge AI có thể dùng `message_id` để tìm message tương ứng trong hàng đợi SQLite và xóa message đã được xác nhận.

ACK này là xác nhận ở tầng ứng dụng, không phải MQTT PUBACK.

## 10. BACKEND ACK – FAILED

**TOPIC:** `ACK_TOPIC`

**PAYLOAD:**
```json
{
  "message_id": "uuid-event-001",
  "status": "FAILED"
}
```

Minh họa trường hợp Backend không lưu được message.

Cách xử lý khi nhận `FAILED`, bao gồm giữ message trong SQLite, ghi log và retry, phụ thuộc vào implementation của bộ xử lý ACK. Không nên mặc định rằng mọi lỗi đều được xử lý giống nhau nếu chưa kiểm tra code.

---

## Tổng hợp payload

| Payload | Topic | Thời điểm gửi |
|---|---|---|
| `TELEMETRY` | `TELEMETRY_TOPIC` | Định kỳ mỗi giây |
| `STATE_CHANGED` | `EVENT_TOPIC` | Khi trạng thái xác nhận thay đổi |
| `DROWSY_THRESHOLD_REACHED` | `EVENT_TOPIC` | Duy trì `DROWSY` đủ 3 giây |
| `DISTRACTED_THRESHOLD_REACHED` | `EVENT_TOPIC` | Duy trì `DISTRACTED` đủ 3 giây |
| `SESSION_ENDED` | `EVENT_TOPIC` | Khi phiên Edge AI kết thúc sau khi MQTT client được khởi tạo |
| `ONLINE` | `STATUS_TOPIC` | Khi MQTT kết nối thành công, tùy implementation |
| `OFFLINE` | `STATUS_TOPIC` | Khi đóng kết nối hoặc Broker phát Last Will |
| `CAMERA_ERROR` | `STATUS_TOPIC` | Camera lỗi liên tiếp đủ giới hạn |
| ACK – `SAVED` | `ACK_TOPIC` | Backend xác nhận lưu thành công |
| ACK – `FAILED` | `ACK_TOPIC` | Backend báo lưu thất bại |

## Lưu ý triển khai

1. `device_code`, `model_version`, UUID và timestamp trong tài liệu chỉ là giá trị minh họa; dữ liệu thực tế được lấy từ cấu hình hoặc sinh khi chạy.
2. Tên topic thực tế phụ thuộc vào các biến cấu hình như `TELEMETRY_TOPIC`, `EVENT_TOPIC`, `STATUS_TOPIC` và `ACK_TOPIC`.
3. `sequence_number` được tăng khi tạo event và có phạm vi theo phiên chạy hiện tại; code hiện tại khởi tạo lại từ `0` mỗi lần chạy.
4. `STATE_CHANGED` không chứa `previous_state_duration_ms`; Backend cần tự tính thời lượng nếu nghiệp vụ yêu cầu.
5. `SESSION_ENDED` là event ở tầng ứng dụng, khác với trạng thái MQTT `OFFLINE`. Một event báo kết thúc phiên không thay thế Last Will.
6. MQTT PUBACK xác nhận Broker nhận publish ở tầng MQTT; ACK `SAVED` xác nhận Backend xử lý và lưu message ở tầng ứng dụng.
7. Các payload ACK và DEVICE_STATUS ở trên là mẫu hợp đồng dữ liệu. Cần đối chiếu `MQTTClient`, `publish_event()`, `publish_telemetry()` và bộ xử lý ACK để xác nhận mọi trường và hành vi đều khớp với implementation thực tế.
