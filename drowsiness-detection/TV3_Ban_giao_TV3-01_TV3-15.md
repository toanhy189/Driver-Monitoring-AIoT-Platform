# TV3 — Bàn giao Edge AI Driver Monitoring (TV3-01 đến TV3-15)

## 1. Mục đích

TV3 phụ trách xử lý Edge AI trên máy tính: lấy hình ảnh từ camera, phát hiện các điểm mốc khuôn mặt, tính đặc trưng mắt và hướng đầu, xác định trạng thái tài xế, sau đó gửi dữ liệu telemetry và sự kiện qua MQTT cho backend.

**Phạm vi hien tai:** các công việc TV3-01 đến TV3-15 đã triển khai và kiểm thử trong quá trình phát triển. Trạng thái bên dưới dựa trên các lần chạy và kiểm tra đã thực hiện; cần chạy lại trên môi trường tiếp nhận nếu muốn xác nhận lại.

## 2. Kiến trúc tổng quan

```text
Webcam
  -> MediaPipe Face Landmarker
  -> EAR / thời lượng nhắm mắt
  -> PERCLOS
  -> Head pose (yaw/pitch/roll và độ lệch so với baseline)
  -> Trạng thái tài xế
  -> MQTT telemetry: driver/telemetry
  -> MQTT events: driver/events
  -> MQTT status / Last Will: driver/status
```

TV3 phát hiện và gửi dữ liệu trạng thái/sự kiện. Backend/TV2 tiếp nhận, lưu trữ và xử lý tiếp theo theo thiết kế của nhóm.

## 3. Cấu trúc thư mục

```text
drowsiness-detection/
├── main.py                 # Vòng lặp camera và pipeline xử lý
├── camera.py               # Mô-đun camera
├── face_detection.py       # Face Landmarker / điểm mốc khuôn mặt
├── drowsiness.py           # EAR, theo dõi nhắm mắt, PERCLOS
├── head_pose.py            # Ước lượng hướng đầu và theo dõi độ lệch baseline
├── mqtt_client.py          # MQTT client, telemetry, event, status, reconnect
├── config.py               # Cấu hình thiết bị, broker, topic, ngưỡng
├── face_landmarker.task    # Mô hình MediaPipe Face Landmarker
├── requirements.txt        # Các thư viện phụ thuộc
├── TV3_Ban_giao_TV3-01_TV3-15.md 
└── .venv/                  # Môi trường ảo cục bộ; không commit
```


## 4. Kết quả TV3-01 đến TV3-15
(xem tai https://docs.google.com/spreadsheets/d/1atfGxnBC1xKhD-5NIKjYCNmTLSyKeWAm/edit?gid=250140631#gid=250140631)

## 5. Đặc trưng và quy tắc xử lý

### 5.1. EAR — Eye Aspect Ratio

EAR được tính từ các điểm mốc quanh mắt để ước lượng mức độ mở của mắt. Trong quá trình kiểm tra, EAR khi mắt mở thường khoảng `0.390–0.480`, còn khi nhắm thường thấp hơn, nhưng hai khoảng có thể chồng lấn tùy khuôn mặt, góc camera và điều kiện ánh sáng.

Ngưỡng hiện tại là `EAR_THRESHOLD = 0.20`, chỉ nên xem là ngưỡng thử nghiệm ban đầu. Cần kiểm tra trên nhiều người và điều kiện quay khác nhau trước khi kết luận đây là ngưỡng phù hợp cho sản phẩm.

### 5.2. PERCLOS

PERCLOS biểu diễn tỷ lệ thời gian mắt nhắm trong một cửa sổ thời gian. Cấu hình thử nghiệm đã dùng cửa sổ 10 giây và có thời gian warm-up. Cần chú ý các khoảng mất mẫu hoặc không phát hiện được khuôn mặt khi đánh giá kết quả.

### 5.3. Head pose

Hệ thống theo dõi các giá trị `yaw`, `pitch`, `roll` và độ lệch `yaw_diff`, `pitch_diff` so với baseline. Các giá trị yaw/pitch hiện tại là chỉ số tương đối dựa trên landmark, không nên mặc định xem chúng là góc đo chính xác theo độ. `roll` dùng để quan sát độ nghiêng đầu.

Bộ ước lượng và bộ theo dõi head pose cần được khởi tạo bên ngoài vòng lặp xử lý frame để không bị đặt lại trạng thái ở mỗi frame. Quá trình hiệu chuẩn baseline kéo dài khoảng 5 giây; ngưỡng thử nghiệm đã dùng độ lệch yaw `0.20`, pitch `0.05` và thời lượng phân tâm `2.0` giây.

### 5.4. Trạng thái tài xế và sự kiện

Các trạng thái chính gồm `ATTENTIVE`, `DISTRACTED`, `DROWSY` và `UNKNOWN`. `EYES_CLOSED` là đặc trưng/trạng thái trung gian dùng trong xử lý mắt, không nhất thiết là trạng thái tài xế cuối cùng.

- Sự kiện đổi trạng thái: `STATE_CHANGED`, có thông tin trạng thái trước/sau và thời lượng trạng thái trước.
- Sự kiện đạt ngưỡng buồn ngủ: `DROWSY_THRESHOLD_REACHED`, được giới hạn để tránh phát lặp liên tục trong cùng một đợt.
- Ngưỡng buồn ngủ đang được triển khai ở mức thử nghiệm: 3000 ms; thời gian phục hồi khi mắt mở là 1 giây. Cần thống nhất lại với TV2/nhóm trước khi chốt.

## 6. MQTT: topic và dữ liệu

| Topic | Mục đích |
|---|---|
| `driver/telemetry` | Dữ liệu đo liên tục từ thiết bị. |
| `driver/events` | Sự kiện đổi trạng thái hoặc cảnh báo. |
| `driver/status` | Trạng thái kết nối `ONLINE`/`OFFLINE`; có Last Will. |

Telemetry hiện có các trường chính như `device_id`, `timestamp`, `ear`, `perclos`, `eye_closed`, `closed_duration_ms`, `driver_state` và `head_pose` (gồm `yaw`, `pitch`, `roll`, `yaw_diff`, `pitch_diff`). Cấu trúc JSON thực tế trong mã nguồn là căn cứ cuối cùng khi tích hợp.

Event có các trường như `event_id`, `timestamp`, `model_version`, loại/trạng thái sự kiện và thời lượng trạng thái khi phù hợp. Hãy kiểm tra payload thực tế trong `main.py` và `mqtt_client.py` trước khi xây dựng schema lưu trữ phía backend.

## 7. Cách chạy và kiểm tra

1. Mở terminal tại thư mục `drowsiness-detection`.
2. Kích hoạt môi trường ảo `.venv`.
3. Cài các thư viện trong `requirements.txt` nếu môi trường chưa có đủ.
4. Kiểm tra cấu hình trong `config.py`, gồm broker, cổng, thiết bị và topic MQTT.
5. Khởi động Mosquitto broker.
6. Chạy chương trình bằng `python main.py`.
7. Dùng `mosquitto_sub` để theo dõi các topic, ví dụ:

```bat
D:\mosquitto\mosquitto_sub.exe -h localhost -t driver/status -v
D:\mosquitto\mosquitto_sub.exe -h localhost -t driver/telemetry -v
D:\mosquitto\mosquitto_sub.exe -h localhost -t driver/events -v
```

Đường dẫn `D:\mosquitto\...` là ví dụ theo môi trường phát triển hiện tại; máy khác có thể cài Mosquitto ở vị trí khác.

### Các kiểm tra MQTT đã thực hiện

- Khi chương trình kết nối broker, subscriber nhận được trạng thái `ONLINE`.
- Khi client bị dừng bất thường, broker gửi trạng thái Last Will `OFFLINE`.
- Khi broker bị tắt trong lúc camera đang chạy, pipeline camera vẫn tiếp tục.
- Khi broker được khởi động lại, MQTT client tự kết nối lại và gửi trạng thái `ONLINE`.

## 8. Giới hạn hiện tại và việc cần làm tiếp

- Các ngưỡng EAR, PERCLOS và head pose mới là ngưỡng thử nghiệm; cần đánh giá trên dữ liệu đa dạng trước khi sử dụng thực tế.
- Xác nhận với TV2 schema telemetry/event, quy tắc kích hoạt cảnh báo, tên trường và ngưỡng cuối cùng.
- Kiểm tra xử lý khi mất khuôn mặt kéo dài, dữ liệu bị gián đoạn và khôi phục trạng thái sau khi phát hiện lại khuôn mặt.
- Kiểm thử toàn luồng Edge AI → MQTT → backend → cơ sở dữ liệu/dashboard.
- Không xem kết quả thử nghiệm trên một máy/một người là bằng chứng về độ chính xác tổng quát.
