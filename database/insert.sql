BEGIN;

-- =========================================
-- 1. USERS: ADMIN -> EMPLOYEE -> CUSTOMER
-- =========================================

INSERT INTO users (fullname, username, hash_password, email, phone, role)
VALUES
    ('Lê Cao', 'lec', '$argon2id$v=19$m=65536,t=3,p=4$DdvWdfr4/V2LHpZkN9zhGg$fdDtduGG/5ATl28e6nqTXN1RKAhgOrMQVI0TFlweTyk', 'c@example.com', '0901234569', 'Admin'),
    ('Trần Thị Bình', 'tranb', '$argon2id$v=19$m=65536,t=3,p=4$DdvWdfr4/V2LHpZkN9zhGg$fdDtduGG/5ATl28e6nqTXN1RKAhgOrMQVI0TFlweTyk', 'b@example.com', '0901234568', 'Employee'),
    ('Lê Thị Hoa', 'lehoa', '$argon2id$v=19$m=65536,t=3,p=4$DdvWdfr4/V2LHpZkN9zhGg$fdDtduGG/5ATl28e6nqTXN1RKAhgOrMQVI0TFlweTyk', 'hoa@example.com', '0901234573', 'Employee'),
    ('Nguyễn Văn An', 'nguyenan', '$argon2id$v=19$m=65536,t=3,p=4$DdvWdfr4/V2LHpZkN9zhGg$fdDtduGG/5ATl28e6nqTXN1RKAhgOrMQVI0TFlweTyk', 'an@example.com', '0901234567', 'Customer'),
    ('Phạm Dinh', 'phamd', '$argon2id$v=19$m=65536,t=3,p=4$DdvWdfr4/V2LHpZkN9zhGg$fdDtduGG/5ATl28e6nqTXN1RKAhgOrMQVI0TFlweTyk', 'd@example.com', '0901234570', 'Customer'),
    ('Trần Văn Dũng', 'trand', '$argon2id$v=19$m=65536,t=3,p=4$DdvWdfr4/V2LHpZkN9zhGg$fdDtduGG/5ATl28e6nqTXN1RKAhgOrMQVI0TFlweTyk', 'dung@example.com', '0901234572', 'Customer');


-- =========================================
-- 2. DEVICES
-- =========================================

INSERT INTO devices (device_code, model, name, status, device_type, lifecycle_state, ip_address, last_seen, mqtt_username, mqtt_password)
VALUES
    ('vision-01', 'AI Vision Node', 'Camera AI - Nguyễn Văn An', 'ONLINE', 'VISION_NODE', 'ACTIVE', '192.168.1.10', '2026-09-21 08:12:00', 'vision-01-user', 'vision-01-pass'),
    ('alert-01', 'ESP32 Alert Node', 'Thiết bị cảnh báo - Nguyễn Văn An', 'ONLINE', 'ALERT_NODE', 'ACTIVE', '192.168.1.11', '2026-09-21 08:12:05', 'alert-01-user', 'alert-01-pass'),
    ('vision-02', 'AI Vision Node', 'Camera AI - Phạm Dinh', 'ONLINE', 'VISION_NODE', 'ACTIVE', '192.168.1.12', '2026-09-21 08:11:50', 'vision-02-user', 'vision-02-pass'),
    ('alert-02', 'ESP32 Alert Node', 'Thiết bị cảnh báo - Phạm Dinh', 'OFFLINE', 'ALERT_NODE', 'REGISTERED', '192.168.1.13', '2026-09-21 08:00:00', 'alert-02-user', 'alert-02-pass'),
    ('vision-03', 'AI Vision Node', 'Camera AI - Lê Thị Hoa', 'ONLINE', 'VISION_NODE', 'ACTIVE', '192.168.1.14', '2026-09-21 08:11:20', 'vision-03-user', 'vision-03-pass'),
    ('alert-03', 'ESP32 Alert Node', 'Thiết bị cảnh báo - Lê Thị Hoa', 'OFFLINE', 'ALERT_NODE', 'REGISTERED', '192.168.1.15', '2026-09-21 08:00:00', 'alert-03-user', 'alert-03-pass'),
    ('vision-04', 'AI Vision Node', 'Camera AI - Trần Văn Dũng', 'OFFLINE', 'VISION_NODE', 'REGISTERED', '192.168.1.16', '2026-09-21 08:00:00', 'vision-04-user', 'vision-04-pass'),
    ('alert-04', 'ESP32 Alert Node', 'Thiết bị cảnh báo - Trần Văn Dũng', 'OFFLINE', 'ALERT_NODE', 'REGISTERED', '192.168.1.17', '2026-09-21 08:00:00', 'alert-04-user', 'alert-04-pass');

-- =========================================
-- 3. USER_DEVICES
-- =========================================

INSERT INTO user_devices (user_id, device_id)
SELECT u.id, d.id
FROM (
    VALUES
        ('nguyenan', 'vision-01'),
        ('nguyenan', 'alert-01'),
        ('phamd', 'vision-02'),
        ('phamd', 'alert-02'),
        ('tranb', 'vision-01'),
        ('tranb', 'alert-01'),
        ('tranb', 'vision-02'),
        ('tranb', 'alert-02'),
        ('lehoa', 'vision-03'),
        ('lehoa', 'alert-03'),
        ('trand', 'vision-04'),
        ('trand', 'alert-04')
) AS v(username, device_code)
JOIN users u ON u.username = v.username
JOIN devices d ON d.device_code = v.device_code;

-- ============================================================
-- 2. TELEMETRY
-- ============================================================

INSERT INTO telemetry (device_id, recorded_at, received_at, ear, perclos, confidence, driver_state, face_detected, head_pose, model_version)
VALUES
    (1, '2026-09-21 08:10:00', '2026-09-21 08:10:00', 0.31, 0.02, 0.96, 'ATTENTIVE', TRUE, '{"yaw": 0.02, "pitch": -0.01, "roll": 1.5}'::jsonb, 'edge-ai-v2.3'),
    (1, '2026-09-21 08:10:15', '2026-09-21 08:10:15', 0.23, 0.08, 0.91, 'DROWSY', TRUE, '{"yaw": 0.7, "pitch": -4.6, "roll": 2.3}'::jsonb, 'edge-ai-v2.3'),
    (1, '2026-09-21 08:10:30', '2026-09-21 08:10:30', 0.18, 0.12, 0.88, 'DROWSY', FALSE, '{"yaw": -12.5, "pitch": 2.2, "roll": 3.4}'::jsonb, 'edge-ai-v2.3');

-- ============================================================
-- 3. AI EVENTS, MESSAGE RECEIPTS, AND ALERTS
-- ============================================================

INSERT INTO ai_events (event_id, device_id, event_type, occurred_at, received_at, model_version, state, state_duration_ms, payload_hash, payload, outcome)
VALUES
    ('evt-yawn-001', 1, 'YAWN', '2026-09-21 08:10:12', '2026-09-21 08:10:13', 'edge-ai-v2.3', 'DROWSY', 4200, 'd8fb9e6f3d4dbbd498b6f8ea8d0f3f4d7fd620ff4ed9b28590ae78feaf6d6f2', '{"score": 0.91, "reason": "EAR_low", "yawn_detected": true}'::jsonb, 'RECORDED'),
    ('evt-head-down-001', 1, 'HEAD_DOWN', '2026-09-21 08:10:26', '2026-09-21 08:10:26', 'edge-ai-v2.3', 'DISTRACTED', 3200, '1f1c4a9d973068d7e1b7874f477a390a77024d87fc29e94857ec9b97259c6f1', '{"score": 0.87, "reason": "pitch_high", "pitch_deg": 14.2}'::jsonb, 'RECORDED'),
    ('evt-face-lost-001', 1, 'FACE_LOST', '2026-09-21 08:10:31', '2026-09-21 08:10:32', 'edge-ai-v2.3', 'ATTENTION_LOST', 1800, '8c49ec7d8d4fb25b84ba7d9adf6f2cf4fe705dab3dfd79cddb9d7c94251a5a2', '{"score": 0.62, "reason": "face_absent", "frames_missing": 7}'::jsonb, 'RECORDED');

INSERT INTO ai_message_receipts (device_id, message_id, topic, payload_hash, saved_at)
VALUES
    (1, 'msg-vision-001', 'driver/vision-01/telemetry', 'd8fb9e6f3d4dbbd498b6f8ea8d0f3f4d7fd620ff4ed9b28590ae78feaf6d6f2', '2026-09-21 08:10:00'),
    (2, 'msg-alert-001', 'driver/alert-01/ack', 'e6586c0d824e01a3389e4e245f43ebf4f4703db1e32b84578d44d6c77ce9e97a', '2026-09-21 08:10:40');

INSERT INTO alerts (event_id, device_id, alert_type, description, severity, status, created_at, resolved_at, source_event_id)
SELECT ae.id, ae.device_id, 'DROWSINESS', 'Người lái có dấu hiệu buồn ngủ và nhắm mắt', 'WARNING', 'NEW', '2026-09-21 08:10:14', NULL, ae.event_id
FROM ai_events ae
WHERE ae.event_id = 'evt-yawn-001';

INSERT INTO alerts (event_id, device_id, alert_type, description, severity, status, created_at, resolved_at, source_event_id)
SELECT ae.id, ae.device_id, 'HEAD_POSE', 'Đầu cúi quá mức, cần cảnh báo', 'WARNING', 'NEW', '2026-09-21 08:10:28', NULL, ae.event_id
FROM ai_events ae
WHERE ae.event_id = 'evt-head-down-001';

INSERT INTO alerts (event_id, device_id, alert_type, description, severity, status, created_at, resolved_at, source_event_id)
SELECT ae.id, ae.device_id, 'FACE_LOST', 'Mất khuôn mặt trong vùng quan sát', 'CRITICAL', 'NEW', '2026-09-21 08:10:34', NULL, ae.event_id
FROM ai_events ae
WHERE ae.event_id = 'evt-face-lost-001';

-- ============================================================
-- 4. COMMANDS AND ACKS
-- ============================================================

INSERT INTO command_types (code, name, description)
VALUES
    ('BUZZER_ON', 'Bật còi', 'Kích hoạt còi cảnh báo trên node ESP32'),
    ('LED_ON', 'Bật đèn', 'Bật đèn cảnh báo và báo hiệu'),
    ('VIBRATION_ON', 'Bật rung', 'Kích hoạt motor rung cảnh báo'),
    ('CAMERA_CHECK', 'Kiểm tra camera', 'Yêu cầu AI Vision kiểm tra lại camera'),
    ('TEST_ALERT', 'Kiểm tra cảnh báo', 'Chạy test toàn bộ actuator'),
    ('AUTO_ALERT', 'Cảnh báo tự động', 'Kích hoạt cảnh báo từ Rule Engine')
ON CONFLICT (code) DO NOTHING;

-- ============================================================
-- 5. VIDEO CAPTURES AND RULES / CONFIG / AUDIT
-- ============================================================

INSERT INTO rule_bindings (source_device_id, target_device_id, enabled, policy, last_triggered_at, updated_at)
VALUES
    (1, 2, TRUE, '{"mode": "AUTO_ALERT", "alert_type": "DROWSINESS", "threshold": 0.8}'::jsonb, '2026-09-21 08:10:14', '2026-09-21 08:10:40');

INSERT INTO configs (device_id, desired_config, applied_config, revision, updated_at)
VALUES
    (2, '{"led": "ON", "buzzer": "ON", "motor": "MEDIUM"}'::json, '{"led": "ON", "buzzer": "ON", "motor": "MEDIUM"}'::json, 1, '2026-09-21 08:10:20');

COMMIT;

