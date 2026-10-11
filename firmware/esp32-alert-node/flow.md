# Luồng hoạt động tổng quát
```mermaid
flowchart TD
    A[mqtt/es32_test.py] --> B[firmware/esp32-alert-node/src/app/main.cpp]
    B --> C[mqtt/consumer.py]
```

# Mẫu Topic và Payload
## Nhận ACK COMPLETED (gửi 1 trong 2)
```text
TOPIC: 'driver/alert-01/command'
PAYLOAD:
    {
        "request_id": "cmd-001",
        "device_code": "alert-01",
        "command": "LED_ON",
        "duration": 5000,
        "intensity": "STRONG"
    }
```

```text
TOPIC: 'driver/alert-01/command'
PAYLOAD:
    {
        "request_id": "cmd-001",
        "device_code": "alert-01",
        "command": "LED_OFF"
    }
```
## Nhận ACK FAILED: INVALID_COMMAND
```text
TOPIC: 'driver/alert-01/command'
PAYLOAD:
    {
        "request_id": "cmd-001",
        "device_code": "alert-01",
        "command": null,
    }
```

## Nhận ACK FAILED: UNKNOWN_COMMAND
```text
TOPIC: 'driver/alert-01/command'
PAYLOAD:
    {
        "request_id": "cmd-001",
        "device_code": "alert-01",
        "command": "DO_SOMETHING"
    }
```

## Nhận ACK FAILED: INVALID_PAYLOAD
```text
TOPIC: 'driver/alert-01/command'
PAYLOAD:
    {
        "request_id": "cmd-001",
        "device_code": "alert-01",
        "command": "LED_ON"
    }
```

## Nhận ACK FAILED: INTENSITY_TOO_LOW (gửi 2 cái liên tiếp)
```text
TOPIC: 'driver/alert-01/command'
PAYLOAD:
    {
        "request_id": "cmd-001",
        "device_code": "alert-01",
        "command": "LED_ON",
        "duration": 5000,
        "intensity": "STRONG"
    }
```

```text
TOPIC: 'driver/alert-01/command'
PAYLOAD:
    {
        "request_id": "cmd-001",
        "device_code": "alert-01",
        "command": "LED_ON",
        "duration": 5000,
        "intensity": "WEAK"
    }
```
Theo trình tự ưu tiên: OFF, CONSTANT, STRONG, MEDIUM, WEAK

## ACK mẫu
```text
TOPIC: 'driver/alert-01/ack'
PAYLOAD:
    {
        "request_id": "cmd-001",
        "device_code": "alert-01",
        "status": "FAILED",
        "elapsed_ms": 5000,
        "error": "UNKNOWN_COMMAND"
    }
```
command: LED_ON, LED_OFF, BUZZER_ON,.., MOTOR_ON,..
status: ACKNOWLEDGED, STARTED, COMPLETED, INTERRUPTED, FAILED
error: INVALID_PAYLOAD, INTENSITY_TOO_LOW, INVALID_COMMAND, UNKNOWN_COMMAND

# Luồng hoạt động chi tiết
```mermaid
flowchart TD
    A["setup()"] --> B["loop()"]

    B --> D["runMqtt()"]
    B --> E["deviceLoop()"]

    D --> C["onMessage()"]
    C --> F["Parse JSON"]
    F --> G["Gửi ACKNOWLEDGED"]
    G --> H["runCommand()"]

    H --> I{"Có command?"}
    I -->|Không| J["Gửi FAILED<br>INVALID_COMMAND"]
    I -->|Có| K{"Loại command"}

    K -->|LED_ON| L["handleDeviceOn(LED)"]
    K -->|BUZZER_ON| M["handleDeviceOn(BUZZER)"]
    K -->|MOTOR_ON| N["handleDeviceOn(MOTOR)"]

    K -->|LED_OFF| O["handleDeviceOff(LED)"]
    K -->|BUZZER_OFF| P["handleDeviceOff(BUZZER)"]
    K -->|MOTOR_OFF| Q["handleDeviceOff(MOTOR)"]

    K -->|Khác| R["Gửi FAILED<br>UNKNOWN_COMMAND"]

    L --> S{"duration và intensity có đủ?"}
    M --> S
    N --> S

    S -->|Không| T["Gửi FAILED<br>INVALID_PAYLOAD"]
    S -->|Có| U["switchDevice()"]

    U --> V{"Device đang active?"}
    V -->|Không| W["Bắt đầu command mới"]
    V -->|Có| AA{"Intensity mới >= intensity hiện tại?"}

    AA -->|Không| AB["Gửi FAILED<br>INTENSITY_TOO_LOW"]
    AA -->|Có| AC["Gửi INTERRUPTED<br>command cũ"]
    AC --> W

    W --> AD["Lưu requestId, duration, intensity"]
    AD --> AE["Bật output HIGH"]
    AE --> AF["Gửi STARTED"]

    O --> AG{"Device đang active?"}
    P --> AG
    Q --> AG

    AG -->|Có| AH["Gửi INTERRUPTED<br>command đang chạy"]
    AG -->|Không| AI["Tắt output LOW"]
    AH --> AI
    AI --> AJ["active = false"]
    AJ --> AK["Gửi COMPLETED"]

    E --> AL{"Device active?"}
    AL -->|Không| E
    AL -->|Có| AM{"Đã hết duration?"}

    AM -->|Có| AN["Tắt output LOW"]
    AN --> AO["active = false"]
    AO --> AP["Gửi COMPLETED"]

    AM -->|Chưa| AQ{"Đang HIGH?"}
    AQ -->|Có| AR{"Đủ startMs?"}
    AR -->|Có| AS["LOW + chuyển phase"]
    AR -->|Không| E

    AQ -->|Không| AT{"Đủ endMs?"}
    AT -->|Có| AU["HIGH + chuyển phase"]
    AT -->|Không| E

    AS --> E
    AU --> E
```