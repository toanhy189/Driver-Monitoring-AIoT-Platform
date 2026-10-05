1. Architecture Draft
1.1. Kiến trúc tổng thể

Luồng hệ thống tuần 1 nên thể hiện:
                         ┌──────────────────────┐
                         │       TV3 / AI       │
                         │ Driver Monitoring    │
                         │                     │
                         │ device_id            │
                         │ EAR                  │
                         │ PERCLOS              │
                         │ driver_state         │
                         └──────────┬───────────┘
                                    │
                                    │ MQTT
                                    ▼
                         ┌──────────────────────┐
                         │    Mosquitto MQTT    │
                         │      Broker          │
                         │                      │
                         │ driver/+/telemetry  │
                         └──────────┬───────────┘
                                    │
                                    │ Subscribe
                                    ▼
┌───────────────────────────────────────────────────────────────────┐
│                         TV2 / BACKEND                             │
│                                                                   │
│    ┌─────────────────┐      ┌──────────────────┐                  │
│    │ MQTT Consumer   │─────►│ Telemetry Schema │                  │
│    └─────────────────┘      └────────┬─────────┘                  │
│                                      │                            │
│                                      ▼                            │
│                         ┌──────────────────┐                      │
│                         │ PostgreSQL       │                      │
│                         │ Telemetry DB     │                      │
│                         └──────────────────┘                      │
│                                                                   │
│                    ┌──────────────────────┐                       │
│                    │ FastAPI              │                       │
│                    │ REST API             │                       │
│                    │ /login               │                       │
│                    │ /users               │                       │
│                    │ /devices             │                       │
│                    │ /telemetry/...       │                       │
│                    └──────────┬───────────┘                       │
│                               │                                   │
│                    ┌──────────▼───────────┐                       │
│                    │ WebSocket             │                      │
│                    │ /ws/telemetry         │                      │
│                    └──────────┬────────────┘                      │
└───────────────────────────────┼───────────────────────────────────┘
                                │
                                │ WebSocket
                                ▼
                    ┌─────────────────────────┐
                    │        TV4 / Frontend   │
                    │       React + Vite      │
                    │                         │
                    │ ┌─────────────────────┐ │
                    │ │ Login               │ │
                    │ └──────────┬──────────┘ │
                    │            ▼            │
                    │ ┌─────────────────────┐ │
                    │ │ Dashboard           │ │
                    │ │                     │ │
                    │ │ Device Status       │ │
                    │ │ Driver Status       │ │
                    │ │ EAR                 │ │
                    │ │ PERCLOS             │ │
                    │ └─────────────────────┘ │
                    └─────────────────────────┘
2. Architecture theo các tầng
# Tầng 1 — Data source
TV3 / AI Driver Monitoring
Sinh dữ liệu giám sát tài xế:
{
  "device_id": "vision-01",
  "ear": 0.28,
  "perclos": 0.12,
  "driver_state": "ATTENTIVE"
}
# Tầng 2 — Communication
MQTT Mosquitto

Topic dự kiến:
driver/+/telemetry

Ví dụ:
driver/vision-01/telemetry

TV2 subscribe topic này để nhận telemetry.

# Tầng 3 — Backend
Sử dụng:
FastAPI
SQLModel/SQLAlchemy
PostgreSQL
JWT authentication
MQTT consumer
WebSocket

Backend hiện đã có cấu trúc authentication và REST API.

Ví dụ:
POST /api/login
GET  /api/me
GET  /api/devices
GET  /api/{device_id}/telemetry

WebSocket dự kiến:
/ws/telemetry

# Tầng 4 — Frontend

Công nghệ:
React
Vite
JavaScript

Các thành phần hiện có:
Login
   ↓
Dashboard
   ├── DeviceStatusCard
   ├── DriverStatusCard
   ├── MetricCard — EAR
   └── MetricCard — PERCLOS

websocket.js chịu trách nhiệm kết nối tới backend.

Dashboard nhận:
device_id
ear
perclos
driver_state

và cập nhật UI bằng React state.