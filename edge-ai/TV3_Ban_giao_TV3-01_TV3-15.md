# TV3 — Bàn giao Edge AI Driver Monitoring (TV3-01 đến TV3-22)

## 1. Mục đích

TV3 phụ trách xử lý Edge AI trên máy tính: lấy hình ảnh từ camera, phát hiện các điểm mốc khuôn mặt, tính đặc trưng mắt và hướng đầu, xác định trạng thái tài xế, sau đó gửi dữ liệu telemetry và sự kiện qua MQTT cho backend.

Trong quá trình phát triển, hệ thống được mở rộng thêm cơ chế lưu trữ dữ liệu cục bộ bằng SQLite để hạn chế mất dữ liệu khi MQTT broker không khả dụng, đồng thời bổ sung các thử nghiệm model nhận diện khuôn mặt và landmark.

**Phạm vi bàn giao:** TV3-01 đến TV3-15 là các công việc đã triển khai và kiểm thử trong quá trình phát triển. TV3-16 đến TV3-22 bao gồm các phần mở rộng về MQTT, lưu trữ ngoại tuyến, kiểm thử payload và thử nghiệm AI. Trạng thái cụ thể cần được đối chiếu với mã nguồn và chạy lại trên môi trường tiếp nhận trước khi xác nhận hoàn tất toàn bộ.

## 2. Kiến trúc tổng quan

```text
Webcam
  -> MediaPipe Face Landmarker
  -> EAR / thời lượng nhắm mắt
  -> PERCLOS
  -> Head pose (yaw/pitch/roll và độ lệch so với baseline)
  -> Xác định trạng thái tài xế
  -> Tạo telemetry / event
  -> Lưu message vào SQLite
  -> MQTT queue worker
  -> MQTT broker
  -> Backend tiếp nhận và lưu dữ liệu
  -> Backend gửi application-level ACK
  -> Edge nhận ACK và xóa message tương ứng khỏi SQLite
```

Các topic MQTT được chuẩn hóa theo namespace `driver/vision-01/`.

TV3 phụ trách thu thập dữ liệu, xử lý AI, quản lý hàng đợi và truyền dữ liệu. Backend/TV2 tiếp nhận, lưu trữ và xử lý dữ liệu tiếp theo theo thiết kế chung của nhóm.

## 3. Cấu trúc thư mục

```text
drowsiness-detection/
├── main.py                       # Vòng lặp camera và pipeline xử lý
├── camera.py                     # Mô-đun camera
├── face_detection.py             # Face Landmarker / điểm mốc khuôn mặt
├── drowsiness.py                 # EAR, theo dõi nhắm mắt, PERCLOS
├── head_pose.py                  # Ước lượng hướng đầu và baseline
├── mqtt_client.py                # MQTT client, reconnect, queue worker, ACK
├── edge_queue.py                 # SQLite offline queue
├── config.py                     # Cấu hình thiết bị, broker, topic, ngưỡng
├── face_landmarker.task           # Model MediaPipe Face Landmarker
├── requirements.txt              # Các thư viện phụ thuộc
├── README.md                      # Hướng dẫn chạy và payload mẫu
├── edge_ai_test.py                # Kiểm thử Edge AI / payload
├── train_detection_ai.ipynb       # Notebook thử nghiệm AI
├── data/
│   └── queue.db                   # SQLite offline queue, tạo khi chạy
└── .venv/                         # Môi trường ảo cục bộ; không commit
```

Cấu trúc trên là cấu trúc tham chiếu. Cần đối chiếu tên file và vị trí thực tế trong repository trước khi bàn giao; không commit môi trường ảo hoặc dữ liệu SQLite phát sinh khi chạy.

## 4. Danh sách công việc TV3-01 đến TV3-22

TV3-01 đến TV3-15: xem danh sách công việc và kết quả kiểm thử trong bảng theo dõi của nhóm:

https://docs.google.com/spreadsheets/d/1atfGxnBC1xKhD-5NIKjYCNmTLSyKeWAm/edit?gid=250140631#gid=250140631

Các công việc mở rộng TV3-16 đến TV3-22:

| Mã | Công việc | Kết quả / trạng thái |
|---|---|---|
| TV3-16 | Chuẩn hóa namespace MQTT | Đã chỉnh các topic sang namespace `driver/vision-01/`. |
| TV3-17 | Xây dựng SQLite offline queue | Đã bổ sung cơ chế lưu message cục bộ khi chờ gửi qua MQTT. |
| TV3-18 | Gửi lại dữ liệu khi kết nối MQTT | Đã bổ sung queue worker chạy bằng thread để xử lý message tồn đọng khi kết nối. |
| TV3-19 | Xác nhận lưu trữ bằng application-level ACK | Đã bổ sung topic `storage_ack` và luồng xử lý ACK; cần kiểm thử đầu cuối với backend. |
| TV3-20 | Chuẩn hóa payload kiểm thử và tích hợp | Đã bổ sung payload mẫu trong README và `edge_ai_test.py`. |
| TV3-21 | Thử nghiệm AI nhận diện landmark | Đã bổ sung notebook `train_detection_ai.ipynb` và xác định dataset Facial Keypoints Detection trên Kaggle. |
| TV3-22 | Hoàn thiện tài liệu và kiểm thử bàn giao | Đang tổng hợp kiến trúc, cấu hình, payload và các trường hợp kiểm thử; cần chạy xác nhận toàn luồng trên môi trường tiếp nhận. |

Trạng thái TV3-16 đến TV3-22 mô tả các phần đã được bổ sung hoặc đang hoàn thiện theo tiến trình phát triển. Không xem đây là bằng chứng rằng mọi trường hợp lỗi hoặc kiểm thử tích hợp đều đã đạt.

## 5. Đặc trưng và quy tắc xử lý AI

### 5.1. EAR — Eye Aspect Ratio

EAR được tính từ các điểm mốc quanh mắt để ước lượng mức độ mở của mắt.

Trong quá trình kiểm tra, EAR khi mắt mở thường khoảng `0.390–0.480`, còn khi nhắm thường thấp hơn. Hai khoảng có thể chồng lấn tùy khuôn mặt, góc camera và điều kiện ánh sáng.

Ngưỡng hiện tại là `EAR_THRESHOLD = 0.20`, được sử dụng như ngưỡng thử nghiệm ban đầu. Cần đánh giá trên nhiều người và điều kiện quay khác nhau trước khi kết luận đây là ngưỡng phù hợp cho sản phẩm.

### 5.2. PERCLOS

PERCLOS biểu diễn tỷ lệ thời gian mắt nhắm trong một cửa sổ thời gian.

Cấu hình thử nghiệm đã dùng cửa sổ 10 giây và có thời gian warm-up. Khi đánh giá, cần xử lý rõ các khoảng mất mẫu hoặc không phát hiện được khuôn mặt để tránh làm sai lệch kết quả.

### 5.3. Head pose

Hệ thống theo dõi các giá trị `yaw`, `pitch`, `roll` và độ lệch `yaw_diff`, `pitch_diff` so với baseline.

Các giá trị yaw/pitch hiện tại là chỉ số tương đối dựa trên landmark, không nên mặc định xem chúng là góc đo chính xác theo độ. `roll` được dùng để quan sát độ nghiêng đầu.

Bộ ước lượng và bộ theo dõi head pose phải được khởi tạo bên ngoài vòng lặp xử lý frame để tránh bị đặt lại trạng thái ở mỗi frame.

Quá trình hiệu chuẩn baseline kéo dài khoảng 5 giây. Các ngưỡng thử nghiệm đã dùng:

- Độ lệch yaw: `0.20`.
- Độ lệch pitch: `0.05`.
- Thời lượng phân tâm: `2.0` giây.

Các ngưỡng cần được đánh giá và thống nhất với nhóm trước khi chốt.

### 5.4. Trạng thái tài xế và sự kiện

Các trạng thái chính gồm:

- `ATTENTIVE`
- `DISTRACTED`
- `DROWSY`
- `UNKNOWN`

`EYES_CLOSED` là đặc trưng/trạng thái trung gian dùng trong xử lý mắt, không nhất thiết là trạng thái tài xế cuối cùng.

Các sự kiện chính:

- `STATE_CHANGED`: ghi nhận việc chuyển trạng thái, gồm trạng thái trước/sau và thời lượng trạng thái trước.
- `DROWSY_THRESHOLD_REACHED`: ghi nhận khi thời lượng buồn ngủ đạt ngưỡng, có cơ chế giới hạn phát lặp trong cùng một đợt.

Ngưỡng buồn ngủ đang được triển khai ở mức thử nghiệm là 3000 ms; thời gian phục hồi khi mắt mở là 1 giây. Cần thống nhất lại với TV2/nhóm trước khi chốt.

## 6. MQTT: topic và dữ liệu

### 6.1. Danh sách topic

| Topic | Mục đích |
|---|---|
| `driver/vision-01/telemetry` | Dữ liệu đo liên tục từ thiết bị. |
| `driver/vision-01/events` | Sự kiện đổi trạng thái hoặc cảnh báo. |
| `driver/vision-01/status` | Trạng thái kết nối `ONLINE`/`OFFLINE`; hỗ trợ Last Will. |
| `driver/vision-01/storage_ack` | Backend gửi xác nhận lưu trữ cho các message đã được lưu thành công. |

Tên topic phải được thống nhất giữa `config.py`, edge client và backend. MQTT phân biệt chính xác tên topic, vì vậy không tự ý đổi namespace hoặc tên topic khi tích hợp.

### 6.2. Payload telemetry

Telemetry chứa các trường chính như:

- `device_id`
- `timestamp`
- `ear`
- `perclos`
- `eye_closed`
- `closed_duration_ms`
- `driver_state`
- `head_pose`: gồm `yaw`, `pitch`, `roll`, `yaw_diff`, `pitch_diff`

Payload mẫu được cung cấp trong README và `edge_ai_test.py`. Cấu trúc JSON thực tế trong mã nguồn là căn cứ cuối cùng khi tích hợp.

### 6.3. Payload event

Event có các trường như `event_id`, `timestamp`, `model_version`, loại/trạng thái sự kiện và thời lượng trạng thái khi phù hợp.

Cần kiểm tra payload thực tế trong `main.py` và `mqtt_client.py` để xác nhận tên trường, ID và schema trước khi xây dựng hoặc điều chỉnh schema lưu trữ phía backend.

### 6.4. Payload ACK

ACK là xác nhận ở cấp ứng dụng, không phải chỉ là xác nhận QoS của giao thức MQTT.

Payload tham chiếu:

```json
{
  "message_id": "ID-cua-message-goc",
  "status": "SAVED"
}
```

Trong đó:

- `message_id`: ID của message telemetry/event ban đầu.
- `status`: `SAVED` khi backend đã lưu thành công và transaction đã commit.

Backend phải publish ACK vào `driver/vision-01/storage_ack`. Edge chỉ xóa message tương ứng trong SQLite khi nhận ACK hợp lệ có `message_id` khớp và `status == "SAVED"`.

Nếu backend lưu thành công nhưng ACK bị mất, edge có thể gửi lại message. Backend cần xử lý idempotent theo `message_id` để tránh ghi trùng dữ liệu và nên gửi lại ACK khi nhận một message đã lưu trước đó.

## 7. SQLite offline queue và MQTT worker

### 7.1. Mục đích

SQLite được dùng làm hàng đợi lưu trữ cục bộ trên máy chạy Edge AI. Mục tiêu là giữ dữ liệu trong thời gian broker không khả dụng, thay vì để dữ liệu bị mất chỉ vì publish thất bại.

### 7.2. Cấu trúc dữ liệu

Bảng `offline_queue` sử dụng các trường chính:

| Trường | Ý nghĩa |
|---|---|
| `id` | Khóa chính tự tăng, phục vụ sắp xếp hàng đợi. |
| `message_id` | ID duy nhất của message. |
| `topic` | Topic đích của message. |
| `payload` | Nội dung JSON đã được serialize. |
| `created_at` | Thời điểm message được lưu vào hàng đợi. |
| `status` | Trạng thái hàng đợi, mặc định `PENDING`. |
| `retry_count` | Số lần thử gửi lại, nếu được cập nhật bởi logic retry. |

`message_id` phải được tạo một lần cho mỗi message và được giữ nguyên trong mọi lần retry. Không tạo ID mới mỗi lần gửi lại.

### 7.3. Luồng gửi dữ liệu

1. Edge AI tạo telemetry hoặc event.
2. Message được lưu vào SQLite trước khi gửi.
3. MQTT worker lấy các bản ghi `PENDING` theo thứ tự tạo.
4. Worker publish message lên topic đã lưu trong DB khi MQTT đang kết nối.
5. Bản ghi tiếp tục được giữ trong SQLite sau khi publish thành công.
6. Khi nhận ACK `SAVED` với đúng `message_id`, edge xóa bản ghi tương ứng.

Worker chạy bằng thread riêng để không chặn vòng lặp camera và xử lý AI. Khi MQTT kết nối lại, worker được đánh thức để gửi dữ liệu tồn đọng.

### 7.4. Các điểm cần kiểm tra

- SQLite được khởi tạo thành công trước khi chạy pipeline.
- Khi broker mất kết nối, camera và pipeline AI vẫn tiếp tục hoạt động.
- Message mới vẫn được lưu trong SQLite khi không thể publish.
- Khi broker kết nối lại, các message tồn đọng được gửi theo thứ tự.
- Publish MQTT thành công nhưng chưa nhận application-level ACK thì message vẫn còn trong DB.
- ACK có `message_id` không khớp không được xóa message khác.
- ACK không có `message_id` hoặc có trạng thái khác `SAVED` không được xem là xác nhận lưu thành công.
- Khi ACK bị mất, message được gửi lại và backend không ghi trùng.
- Cần kiểm tra tình huống worker đang chờ ACK trong khi kết nối MQTT bị ngắt.
- Cần xem xét giới hạn dung lượng SQLite khi broker/backend mất kết nối trong thời gian dài.

## 8. Thử nghiệm AI và dataset

### 8.1. Notebook thử nghiệm

File `train_detection_ai.ipynb` được dùng để thử nghiệm các model AI liên quan đến phát hiện khuôn mặt và trích xuất landmark.

Mục tiêu là đánh giá sơ bộ khả năng xác định khuôn mặt và các điểm đặc trưng trên ảnh, đồng thời cung cấp cơ sở so sánh trước khi lựa chọn model phù hợp cho hệ thống Edge AI.

### 8.2. Dataset

Dataset được lựa chọn:

**Facial Keypoints Detection — Kaggle**

https://www.kaggle.com/competitions/facial-keypoints-detection/data

Dataset cung cấp ảnh khuôn mặt và các tọa độ keypoint có nhãn. Đây là dữ liệu phù hợp để thử nghiệm và đối chiếu tọa độ landmark.

### 8.3. Hướng đánh giá

Các nội dung có thể đánh giá trong notebook:

- Khả năng phát hiện khuôn mặt trên ảnh.
- Khả năng xác định vị trí landmark tương ứng với nhãn.
- Sai số tọa độ landmark, có thể chuẩn hóa theo kích thước khuôn mặt.
- Thời gian xử lý mỗi ảnh hoặc FPS.
- Độ ổn định trên các ảnh có góc mặt và điều kiện ánh sáng khác nhau.

Các model cần được so sánh trên cùng tập ảnh kiểm thử và theo cùng tiêu chí. Không thể so sánh trực tiếp toàn bộ mesh 468/478 điểm của MediaPipe với model chỉ trả về 5 landmark nếu không có bước ánh xạ điểm tương ứng.

Dataset Facial Keypoints Detection chủ yếu phục vụ bài toán landmark, không phải benchmark toàn diện cho mọi điều kiện phát hiện khuôn mặt. Do đó, kết quả từ notebook chỉ nên được dùng để chứng minh và so sánh trong phạm vi dữ liệu đã thử nghiệm; không suy rộng thành độ chính xác tổng quát cho mọi người dùng và mọi môi trường.

## 9. Cách chạy và kiểm tra

1. Mở terminal tại thư mục `drowsiness-detection`.
2. Kích hoạt môi trường ảo `.venv`.
3. Cài các thư viện trong `requirements.txt` nếu môi trường chưa có đủ.
4. Kiểm tra `config.py`, gồm broker, cổng, thiết bị và các topic MQTT.
5. Khởi động Mosquitto broker.
6. Chạy chương trình bằng `python main.py`.
7. Theo dõi topic bằng `mosquitto_sub`:

```bat
D:\mosquitto\mosquitto_sub.exe -h localhost -t driver/vision-01/status -v
D:\mosquitto\mosquitto_sub.exe -h localhost -t driver/vision-01/telemetry -v
D:\mosquitto\mosquitto_sub.exe -h localhost -t driver/vision-01/events -v
```

Để kiểm tra ACK, cần theo dõi thêm topic:

```bat
D:\mosquitto\mosquitto_sub.exe -h localhost -t driver/vision-01/storage_ack -v
```

Đường dẫn `D:\mosquitto\...` là ví dụ theo môi trường phát triển; máy khác có thể cài Mosquitto ở vị trí khác.

Để kiểm thử SQLite offline queue, cần chủ động tắt broker trong lúc Edge AI đang chạy, xác nhận message vẫn được ghi vào DB, sau đó khởi động lại broker và kiểm tra quá trình gửi lại.

Để kiểm thử application-level ACK, cần có backend hoặc MQTT test client mô phỏng việc lưu dữ liệu thành công và publish ACK với đúng `message_id`.

## 10. Giới hạn hiện tại và việc cần làm tiếp

- Xác nhận lại schema telemetry/event và các trường ID với TV2.
- Kiểm thử toàn luồng Edge AI → SQLite → MQTT → backend → database → ACK → xóa khỏi SQLite.
- Xác nhận worker xử lý đúng khi broker mất kết nối, kết nối lại hoặc ACK đến chậm.
- Bổ sung hoặc xác nhận chính sách retry, backoff và giới hạn dung lượng hàng đợi khi mất kết nối kéo dài.
- Kiểm tra xử lý khi mất khuôn mặt kéo dài, dữ liệu bị gián đoạn và khôi phục trạng thái sau khi phát hiện lại khuôn mặt.
- Đánh giá các ngưỡng EAR, PERCLOS và head pose trên dữ liệu đa dạng hơn.
- Hoàn thiện kết quả thực nghiệm của `benchmark/detection-ai.ipynb`, gồm cấu hình model, tập dữ liệu thực tế đã sử dụng và các chỉ số đo được.
- Kiểm tra sự nhất quán giữa payload mẫu trong README và payload thực tế do `main.py` tạo ra.
- Chạy lại các trường hợp kiểm thử trên môi trường tiếp nhận trước khi xác nhận trạng thái hoàn tất TV3-01 đến TV3-22.

Không xem kết quả thử nghiệm trên một máy hoặc một người là bằng chứng về độ chính xác tổng quát của hệ thống.
