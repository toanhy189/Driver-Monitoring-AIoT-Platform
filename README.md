# Driver Monitoring AIoT Platform

## Hệ thống cảnh báo ngủ gật và mất tập trung sử dụng Edge AI, ESP32 và MQTT

---

# 1. Giới thiệu

Đề tài xây dựng một **hệ thống AIoT giám sát trạng thái tài xế theo thời gian thực**, nhằm phát hiện các dấu hiệu như:

- Buồn ngủ.
- Ngủ gật.
- Mất tập trung.
- Nhắm mắt quá lâu.
- Quay đầu khỏi hướng lái.
- Không phát hiện khuôn mặt.

Hệ thống sử dụng **webcam** làm cảm biến hình ảnh chính. Dữ liệu được xử lý tại **Laptop Edge AI Node** bằng Computer Vision và Machine Learning.

Các đặc trưng dự kiến:

- EAR (Eye Aspect Ratio).
- PERCLOS.
- Blink Duration.
- Blink Frequency.
- Head Pose.
- Yawn Score.
- Face Detection Status.

Hệ thống phân loại trạng thái tài xế:

```text
ATTENTIVE
DISTRACTED
DROWSY
```

Khi phát hiện trạng thái nguy hiểm, kết quả AI được gửi qua **MQTT** tới backend. Backend xử lý Rule Engine và gửi lệnh tới **ESP32 Alert Node**.

ESP32 tạo cảnh báo vật lý bằng:

- LED.
- Buzzer.
- Motor rung.

Sau khi thực hiện lệnh, ESP32 gửi **ACK** về backend.

Ngoài cảnh báo, hệ thống còn hướng tới:

- Quản lý người dùng.
- RBAC.
- Quản lý thiết bị.
- Theo dõi online/offline.
- Telemetry realtime.
- Alert Management.
- Remote Configuration.
- Command + ACK.
- Audit Log.
- Hoạt động trong Wi-Fi cục bộ khi không có Internet.
- Offline Store & Forward.
- Docker Compose.
- Monitoring.
- CI/CD.

Mục tiêu không phải chỉ là một chương trình nhận diện ngủ gật, mà là tích hợp **AI + IoT + Backend + Device Management + Realtime Monitoring + Physical Alert** thành một nguyên mẫu hoàn chỉnh.

---

# 2. Kiến trúc hệ thống

## 2.1. Kiến trúc tổng thể

```text
Webcam
   ↓
Laptop Edge AI Node
   ↓
EAR / PERCLOS / Head Pose / Driver State
   ↓
MQTT Telemetry / Event
   ↓
Mosquitto MQTT Broker
   ↓
Backend
├── Authentication / RBAC
├── User Management
├── Device Management
├── Telemetry Processing
├── Alert Management
├── Rule Engine
├── Command Management
└── Audit Log
   ├──→ PostgreSQL
   ├──→ WebSocket / REST → React Dashboard
   └──→ MQTT Command
              ↓
        ESP32 Alert Node
        ├── LED
        ├── Buzzer
        └── Motor rung
              ↓
             ACK
              ↓
           Backend
```

## 2.2. Vision Edge Node

Vision Edge Node gồm:

```text
Laptop + Webcam
```

Nhiệm vụ:

- Thu dữ liệu hình ảnh.
- Xử lý ảnh tại Edge.
- Face Detection.
- Face Landmarks.
- EAR.
- PERCLOS.
- Head Pose.
- Phân loại trạng thái tài xế.
- Publish telemetry/event qua MQTT.
- Gửi heartbeat/status.
- Có `device_id` riêng.

Ví dụ:

```text
device_id = vision-01
device_type = EDGE_VISION
```

## 2.3. ESP32 Alert Node

ESP32 là node IoT vật lý dùng để nhận lệnh và tạo cảnh báo.

Nhiệm vụ:

- Kết nối Wi-Fi.
- Kết nối MQTT.
- Nhận command.
- Nhận remote config.
- Điều khiển LED.
- Điều khiển buzzer.
- Điều khiển motor rung.
- Gửi ACK.
- Gửi heartbeat.
- Phát hiện mất kết nối.
- Tự động reconnect.
- Có `device_id` riêng.

Ví dụ:

```text
device_id = alert-01
device_type = ALERT_NODE
```

## 2.4. Luồng phát hiện và cảnh báo

```text
Webcam
→ Laptop Edge AI
→ Driver State
→ MQTT Event
→ Backend
→ Rule Engine
→ MQTT Command
→ ESP32
→ LED + Buzzer + Motor rung
→ ACK
→ Backend
→ Dashboard
```

## 2.5. Luồng telemetry

```text
Vision Edge Node
→ MQTT
→ Backend
→ Validate
→ PostgreSQL
→ WebSocket
→ Dashboard
```

## 2.6. Luồng điều khiển

```text
Operator
→ Dashboard
→ Backend
→ Authentication / RBAC
→ MQTT Command
→ ESP32
→ Actuator
→ ACK
→ Backend
→ Command History
```

## 2.7. Kiến trúc khi không có Internet

Laptop có thể tạo hotspot Wi-Fi cục bộ và chạy:

- Mosquitto MQTT Broker.
- Backend.
- PostgreSQL.
- Edge AI.
- Frontend.

ESP32 kết nối vào hotspot của laptop.

```text
Internet: OFF

Webcam
→ Edge AI
→ MQTT Local
→ Backend Local
→ ESP32
→ Buzzer / Motor / LED
```

Do đó hệ thống vẫn có thể cảnh báo khi không có Internet.

Nếu broker/backend tạm thời lỗi:

```text
AI Event
→ Local Alert
→ Store Event Locally
→ synced = false

Connection Restored
→ Re-publish
→ Backend ACK
→ synced = true
```

## 2.8. Layer Architecture

```text
Application Layer
├── React Dashboard
├── REST API
└── WebSocket

Backend / Service Layer
├── Authentication
├── User Management
├── Device Management
├── Telemetry Service
├── Alert Service
├── Rule Engine
├── Command Service
└── Audit Service

Data Layer
├── PostgreSQL
└── Local Offline Store

Messaging Layer
└── MQTT / Mosquitto

Edge Layer
└── Laptop Edge AI Node

Device Layer
└── ESP32 Alert Node

Physical Layer
├── Webcam
├── LED
├── Buzzer
└── Motor rung
```

## 2.9. Công nghệ dự kiến

### Edge AI
- Python
- OpenCV
- MediaPipe
- NumPy
- pandas
- scikit-learn

### Backend
- FastAPI
- SQLAlchemy
- PostgreSQL
- JWT
- WebSocket

### IoT
- ESP32
- MQTT
- Mosquitto

### Frontend
- React
- Vite

### Deployment
- Docker Compose

### Monitoring
- Prometheus
- Grafana

### CI/CD
- GitHub Actions

---

> **Trạng thái README hiện tại:** mới hoàn thiện phần **Giới thiệu** và **Kiến trúc hệ thống**. Các phần hướng dẫn cài đặt, chạy hệ thống, API, MQTT payload, database, security, testing và deployment sẽ bổ sung sau.
