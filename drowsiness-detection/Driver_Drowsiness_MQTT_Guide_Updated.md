# Driver Drowsiness Detection – MQTT Guide

## 1. Mục đích

Prototype hệ thống phát hiện buồn ngủ của tài xế bằng webcam.

Luồng chính:

```text
Webcam
→ Face Landmarks
→ EAR
→ PERCLOS
→ Driver State
→ JSON Telemetry
→ MQTT
```

Hệ thống hiện có 3 trạng thái:

- `ATTENTIVE`
- `EYES_CLOSED`
- `DROWSY`

> Lưu ý: EAR/PERCLOS hiện dùng ngưỡng prototype để kiểm thử, chưa phải ngưỡng được hiệu chuẩn cho triển khai thực tế hoặc mục đích y tế.

---

## 2. Cấu trúc project

```text
drowsiness-detection/
├── .venv/
├── main.py
├── camera.py
├── face_detection.py
├── drowsiness.py
├── mqtt_client.py
├── config.py
├── requirements.txt
└── face_landmarker.task
```

| File | Nhiệm vụ |
|---|---|
| `main.py` | Điều phối toàn bộ hệ thống |
| `camera.py` | Mở webcam, đọc frame, giải phóng webcam |
| `face_detection.py` | Phát hiện khuôn mặt và facial landmarks |
| `drowsiness.py` | Tính EAR và PERCLOS |
| `mqtt_client.py` | Kết nối MQTT và publish telemetry |
| `config.py` | Cấu hình thiết bị, MQTT và ngưỡng |
| `requirements.txt` | Danh sách thư viện |
| `face_landmarker.task` | Model MediaPipe Face Landmarker |

---

## 3. Luồng hoạt động

```text
Webcam
   ↓
camera.py
   ↓
main.py
   ↓
face_detection.py
   ↓
Face Landmarks
   ↓
drowsiness.py
   ├── EAR
   └── PERCLOS
   ↓
Driver State
   ├── ATTENTIVE
   ├── EYES_CLOSED
   └── DROWSY
   ↓
mqtt_client.py
   ↓
Mosquitto
   ↓
driver/telemetry
```

---

## 4. Môi trường Python

Project sử dụng Python 3.13 và virtual environment `.venv`.

```powershell
cd D:\drowsiness-detection
.\.venv\Scripts\Activate.ps1
```

Kiểm tra:

```powershell
python --version
```

---

## 5. Thư viện

Các thư viện chính:

- OpenCV
- MediaPipe
- NumPy
- pandas
- scikit-learn
- paho-mqtt

Cài theo requirements:

```powershell
pip install -r requirements.txt
```

---

## 6. Camera – `camera.py`

`camera.py` chịu trách nhiệm mở webcam, đọc frame và giải phóng webcam.

```python
import cv2

class Camera:
    def __init__(self, camera_id=0):
        self.cap = cv2.VideoCapture(camera_id)

        if not self.cap.isOpened():
            raise RuntimeError("Không thể mở webcam.")

    def read(self):
        ret, frame = self.cap.read()

        if not ret:
            return None

        return frame

    def release(self):
        self.cap.release()
```

Trong `main.py`:

```python
camera = Camera()
frame = camera.read()
camera.release()
```

**Không chạy riêng `camera.py`.** Chỉ chạy:

```powershell
python main.py
```

---

## 7. Face Landmarks – `face_detection.py`

Project sử dụng MediaPipe Tasks API và model:

```text
face_landmarker.task
```

File model phải nằm tại:

```text
D:\drowsiness-detection\face_landmarker.task
```

Model được dùng để lấy facial landmarks từ frame webcam.

Project xử lý tối đa:

```text
num_faces = 1
```

---

## 8. EAR – Eye Aspect Ratio

EAR dùng để đánh giá mức độ mở/nhắm của mắt.

Công thức:

```text
EAR = (||p2-p6|| + ||p3-p5||)
      --------------------------------
             2 × ||p1-p4||
```

Landmark hai mắt:

```python
LEFT_EYE = [362, 385, 387, 263, 373, 380]
RIGHT_EYE = [33, 160, 158, 133, 153, 144]
```

EAR trung bình:

```text
average EAR = (left EAR + right EAR) / 2
```

Ngưỡng prototype:

```python
EAR_THRESHOLD = 0.20
```

Nếu:

```text
EAR < 0.20
```

thì trạng thái hiện tại được xác định là:

```text
EYES_CLOSED
```

---

## 9. PERCLOS

PERCLOS theo dõi tỷ lệ frame mà mắt được xem là đang đóng trong một cửa sổ thời gian.

Hiện tại:

```python
WINDOW_SIZE = 300
```

Nếu chạy khoảng 30 FPS:

```text
300 / 30 ≈ 10 giây
```

Mỗi frame:

```text
EAR < EAR_THRESHOLD → 1
EAR >= EAR_THRESHOLD → 0
```

PERCLOS:

```text
số frame mắt đóng
------------------
tổng số frame trong cửa sổ
```

Ngưỡng prototype:

```python
PERCLOS_THRESHOLD = 0.20
```

> Đây là cách tính prototype hiện tại. Khi triển khai thực tế có thể chuyển sang tính theo timestamp/thời gian thực.

---

## 10. Driver State

Logic trong `main.py`:

```python
if ear < EAR_THRESHOLD:
    driver_state = "EYES_CLOSED"
elif perclos > PERCLOS_THRESHOLD:
    driver_state = "DROWSY"
else:
    driver_state = "ATTENTIVE"
```

### `ATTENTIVE`

EAR và PERCLOS chưa vượt các ngưỡng prototype.

### `EYES_CLOSED`

EAR hiện tại nhỏ hơn:

```text
0.20
```

### `DROWSY`

EAR hiện tại không thấp hơn ngưỡng đóng mắt nhưng:

```text
PERCLOS > 0.20
```

---

## 11. MQTT

Broker sử dụng:

```text
Mosquitto
```

Cấu hình:

```text
Broker: localhost
Port: 1883
Topic: driver/telemetry
```

Trong `config.py`:

```python
DEVICE_ID = "vision-01"

MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC = "driver/telemetry"

EAR_THRESHOLD = 0.20
PERCLOS_THRESHOLD = 0.20
```

---

## 12. Mosquitto

Mosquitto được cài tại:

```text
D:\Mosquitto
```

Chạy broker:

```powershell
& "D:\Mosquitto\mosquitto.exe" -v
```

Kiểm tra broker:

```powershell
Get-Process mosquitto
```

Nếu process `mosquitto` đã tồn tại thì **không chạy thêm một Mosquitto khác**, vì port `1883` đã được sử dụng.

---

## 13. MQTT Client – `mqtt_client.py`

`mqtt_client.py` chịu trách nhiệm:

1. Tạo MQTT client.
2. Kết nối broker.
3. Bắt đầu MQTT loop.
4. Chuyển telemetry thành JSON.
5. Publish lên `driver/telemetry`.
6. Đóng kết nối khi chương trình kết thúc.

Tần suất publish được điều khiển ở `main.py`:

```python
MQTT_INTERVAL = 1.0
```

Tức là hệ thống publish khoảng 1 lần/giây.

---

## 14. Telemetry JSON

Dữ liệu gửi qua MQTT có dạng:

```json
{
    "device_id": "vision-01",
    "timestamp": "2026-09-23T01:26:53.424533+00:00",
    "ear": 0.302,
    "perclos": 0.177,
    "driver_state": "ATTENTIVE"
}
```

Ý nghĩa:

| Thuộc tính | Ý nghĩa |
|---|---|
| `device_id` | ID thiết bị |
| `timestamp` | Thời điểm gửi |
| `ear` | EAR hiện tại |
| `perclos` | PERCLOS hiện tại |
| `driver_state` | Trạng thái tài xế |

Ví dụ:

```json
{
    "device_id": "vision-01",
    "timestamp": "2026-09-23T01:26:56.041650+00:00",
    "ear": 0.154,
    "perclos": 0.18,
    "driver_state": "EYES_CLOSED"
}
```

---

## 15. Chạy toàn bộ hệ thống

### Bước 1: Mở PowerShell

```powershell
cd D:\drowsiness-detection
```

### Bước 2: Kích hoạt môi trường

```powershell
.\.venv\Scripts\Activate.ps1
```

### Bước 3: Kiểm tra Mosquitto

```powershell
Get-Process mosquitto
```

Nếu đã chạy → sang bước 4.

Nếu chưa chạy:

```powershell
& "D:\Mosquitto\mosquitto.exe" -v
```

Giữ terminal này chạy.

### Bước 4: Chạy chương trình

Mở PowerShell khác:

```powershell
cd D:\drowsiness-detection
.\.venv\Scripts\Activate.ps1
python main.py
```

Webcam sẽ mở và hiển thị:

```text
EAR: ...
PERCLOS: ...
STATE: ...
```

Terminal sẽ hiển thị MQTT telemetry.

### Bước 5: Dừng

Nhấn:

```text
Q
```

trên cửa sổ webcam.

Hoặc:

```text
Ctrl + C
```

---

## 16. Kiểm tra MQTT bằng Subscriber

Mở PowerShell khác:

```powershell
& "D:\Mosquitto\mosquitto_sub.exe" -h localhost -p 1883 -t driver/telemetry
```

Sau đó chạy:

```powershell
python main.py
```

Subscriber sẽ nhận JSON như:

```json
{"device_id":"vision-01","timestamp":"...","ear":0.302,"perclos":0.177,"driver_state":"ATTENTIVE"}
```

Luồng kiểm tra:

```text
Webcam
→ main.py
→ MQTT Client
→ Mosquitto
→ mosquitto_sub
```

---

## 17. Các lỗi thường gặp

### Không kết nối MQTT

```text
[WinError 10061]
```

Kiểm tra:

```powershell
Get-Process mosquitto
```

Nếu chưa chạy:

```powershell
& "D:\Mosquitto\mosquitto.exe" -v
```

### Port 1883 đã được sử dụng

Nếu Mosquitto báo:

```text
Only one usage of each socket address...
```

thì thường là Mosquitto đã chạy sẵn.

Kiểm tra:

```powershell
Get-Process mosquitto
```

Không chạy thêm instance nếu đã có process.

### Không mở được webcam

Nếu thấy:

```text
Không thể mở webcam.
```

Kiểm tra:

- Webcam có đang bị ứng dụng khác sử dụng không.
- Windows đã cấp quyền Camera chưa.
- Camera ID có đúng không.

Mặc định:

```python
Camera(0)
```

### Không tìm thấy model

Kiểm tra:

```text
D:\drowsiness-detection\face_landmarker.task
```

### Không tìm thấy thư viện

Kích hoạt `.venv`:

```powershell
.\.venv\Scripts\Activate.ps1
```

Sau đó:

```powershell
pip install -r requirements.txt
```

### `mp.solutions` không tồn tại

Project hiện tại dùng MediaPipe Tasks API / Face Landmarker.

Không sử dụng code cũ:

```python
mp.solutions.face_mesh
```

---

## 18. Không chạy riêng các module

Các file này là module được `main.py` import:

```text
camera.py
face_detection.py
drowsiness.py
mqtt_client.py
config.py
```

Không cần chạy:

```powershell
python camera.py
python face_detection.py
python drowsiness.py
python mqtt_client.py
```

Chỉ chạy:

```powershell
python main.py
```

---

## 19. Checklist

### Environment

- [x] Python
- [x] `.venv`
- [x] OpenCV
- [x] MediaPipe
- [x] NumPy
- [x] pandas
- [x] scikit-learn
- [x] paho-mqtt

### Camera

- [x] Mở webcam
- [x] Đọc realtime frame
- [x] Release webcam
- [x] Tách camera thành `camera.py`

### Face Detection

- [x] MediaPipe Face Landmarker
- [x] Load `face_landmarker.task`
- [x] Facial landmarks

### Drowsiness Detection

- [x] EAR
- [x] PERCLOS prototype
- [x] `ATTENTIVE`
- [x] `EYES_CLOSED`
- [x] `DROWSY`

### MQTT

- [x] Mosquitto
- [x] MQTT connection
- [x] Topic `driver/telemetry`
- [x] JSON telemetry
- [x] Publish khoảng 1 lần/giây
- [x] Subscriber test

### Integration

- [x] `main.py` + camera
- [x] `main.py` + face landmarks
- [x] `main.py` + EAR/PERCLOS
- [x] `main.py` + MQTT
- [x] Realtime display

---

## 20. Lệnh chạy nhanh

Nếu Mosquitto đã chạy:

```powershell
cd D:\drowsiness-detection
.\.venv\Scripts\Activate.ps1
python main.py
```

Nếu Mosquitto chưa chạy:

**Terminal 1:**

```powershell
& "D:\Mosquitto\mosquitto.exe" -v
```

**Terminal 2:**

```powershell
cd D:\drowsiness-detection
.\.venv\Scripts\Activate.ps1
python main.py
```

---

## 21. Kết quả mong muốn

Webcam:

```text
EAR: 0.302
PERCLOS: 0.177
STATE: ATTENTIVE
```

Khi mắt đóng:

```text
EAR: 0.154
PERCLOS: 0.180
STATE: EYES_CLOSED
```

MQTT:

```json
{
    "device_id": "vision-01",
    "timestamp": "...",
    "ear": 0.154,
    "perclos": 0.18,
    "driver_state": "EYES_CLOSED"
}
```

Kết quả cuối cùng:

```text
Camera
→ Face Landmarks
→ EAR
→ PERCLOS
→ Driver State
→ JSON Telemetry
→ MQTT
```
