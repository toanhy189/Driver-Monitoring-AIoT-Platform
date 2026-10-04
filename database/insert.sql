INSERT INTO users (fullname, username, hash_password, email, phone)
VALUES ('Nguyễn Văn An', 'nguyenan', '$argon2id$v=19$m=65536,t=3,p=4$DdvWdfr4/V2LHpZkN9zhGg$fdDtduGG/5ATl28e6nqTXN1RKAhgOrMQVI0TFlweTyk', 'an@example.com', '0901234567');

INSERT INTO devices (device_code, model, name, status, ip_address)
VALUES ('alert-01', 'Thiết bị cảnh báo V1', 'V1-A01 của An', 'ONLINE', '192.168.1.10'),
       ('DM-000002', 'External-Cam-V1', 'Camera phụ', 'OFFLINE', '192.168.1.11');

INSERT INTO user_devices (user_id, device_id, assigned_at, unassigned_at)
VALUES (1, 1, CURRENT_TIMESTAMP, NULL),
       (1, 2, CURRENT_TIMESTAMP, NULL);

INSERT INTO telemetry (device_id, recorded_at, ear, perclos, angle_x, angle_y, angle_z, confidence)
VALUES
    -- Bình thường
    (1, '2026-09-21 08:10:00', 0.31, 0.02,  2.1,   1.2,  0.5, 0.96),
    (1, '2026-09-21 08:10:05', 0.30, 0.02,  2.4,   1.5,  0.6, 0.97),
    
    -- YAWN: EAR giảm, PERCLOS tăng
    (1, '2026-09-21 08:10:10', 0.24, 0.05,  2.2,   1.1,  0.4, 0.94),
    (1, '2026-09-21 08:10:15', 0.18, 0.08,  2.0,   1.0,  0.3, 0.93),
    (1, '2026-09-21 08:10:20', 0.29, 0.08,  2.3,   1.4,  0.5, 0.95),

    -- Bình thường
    (1, '2026-09-21 08:15:00', 0.32, 0.04,  3.0,   1.2,  0.4, 0.97),
    
    -- HEAD_DOWN: angle_x tăng
    (1, '2026-09-21 08:15:05', 0.31, 0.04,  8.5,   1.5,  0.5, 0.96),
    (1, '2026-09-21 08:15:10', 0.30, 0.05, 15.2,   1.3,  0.4, 0.95),
    (1, '2026-09-21 08:15:15', 0.29, 0.05, 18.5,   1.2,  0.5, 0.94),
    (1, '2026-09-21 08:15:20', 0.28, 0.06, 19.2,   1.4,  0.6, 0.93),
    (1, '2026-09-21 08:15:25', 0.30, 0.06,  8.1,   1.1,  0.4, 0.95),

    -- HEAD_TILT_LEFT
    (1, '2026-09-21 08:20:00', 0.30, 0.05,  2.0,   1.2,  0.5, 0.97),
    (1, '2026-09-21 08:20:05', 0.30, 0.05,  2.1,  -4.2, -10.5, 0.95),
    (1, '2026-09-21 08:20:10', 0.31, 0.05,  2.2,  -4.5,  -3.0, 0.96),

    -- HEAD_TILT_RIGHT
    (1, '2026-09-21 08:25:25', 0.30, 0.06,  2.0,   4.0,   8.2, 0.95),
    (1, '2026-09-21 08:25:30', 0.29, 0.06,  1.8,   4.2,  16.2, 0.94),
    (1, '2026-09-21 08:25:35', 0.30, 0.07,  1.9,   3.8,   6.5, 0.96),

    -- EYE_CLOSED
    (1, '2026-09-21 08:30:05', 0.30, 0.08,  2.1,   1.2,  0.5, 0.97),
    (1, '2026-09-21 08:30:10', 0.14, 0.12,  2.0,   1.1,  0.4, 0.94),
    (1, '2026-09-21 08:30:15', 0.12, 0.16,  2.2,   1.0,  0.3, 0.93),
    (1, '2026-09-21 08:30:20', 0.30, 0.16,  2.1,   1.2,  0.5, 0.96),

    -- FACE_LOST
    (1, '2026-09-21 08:35:00', NULL, NULL, NULL, NULL, NULL, 0.21),
    (1, '2026-09-21 08:35:05', NULL, NULL, NULL, NULL, NULL, 0.18),
    (1, '2026-09-21 08:35:10', 0.30, 0.10,  2.0,   1.0,  0.4, 0.95),

    -- HEAD_DOWN / drowsiness
    (1, '2026-09-21 08:40:00', 0.27, 0.12,  8.5,   1.0,  0.4, 0.94),
    (1, '2026-09-21 08:40:05', 0.20, 0.17, 16.8,   1.2,  0.5, 0.92),
    (1, '2026-09-21 08:40:10', 0.16, 0.21, 18.2,   1.0,  0.3, 0.91),

    -- LOOK_LEFT
    (1, '2026-09-21 08:45:05', 0.30, 0.08,  2.0, -20.5,  0.5, 0.95),
    (1, '2026-09-21 08:45:10', 0.29, 0.08,  1.8, -28.5,  0.4, 0.94),
    (1, '2026-09-21 08:45:15', 0.30, 0.08,  2.1,  -8.5,  0.5, 0.96),

    -- LOOK_RIGHT
    (1, '2026-09-21 08:50:15', 0.30, 0.09,  2.0,  20.2,  0.5, 0.95),
    (1, '2026-09-21 08:50:20', 0.29, 0.10,  1.9,  31.2,  0.4, 0.94),
    (1, '2026-09-21 08:50:25', 0.28, 0.10,  2.1,  25.5,  0.5, 0.95),
    (1, '2026-09-21 08:50:30', 0.30, 0.10,  2.0,   5.2,  0.4, 0.97);

INSERT INTO event_types (code, name, description)
VALUES
    ('YAWN', 'Ngáp', 'Phát hiện người lái đang ngáp'),
    ('HEAD_DOWN', 'Đầu cúi', 'Phát hiện đầu cúi về phía trước'),
    ('HEAD_TILT_LEFT', 'Đầu nghiêng trái', 'Phát hiện đầu nghiêng sang trái'),
    ('HEAD_TILT_RIGHT', 'Đầu nghiêng phải', 'Phát hiện đầu nghiêng sang phải'),
    ('EYE_CLOSED', 'Mắt nhắm', 'Phát hiện mắt đang nhắm'),
    ('EYE_OPEN', 'Mắt mở', 'Phát hiện mắt đang mở'),
    ('FACE_LOST', 'Mặt biến mất', 'Không phát hiện được khuôn mặt trong vùng camera'),
    ('LOOK_LEFT', 'Nhìn sang trái', 'Phát hiện người lái nhìn sang trái'),
    ('LOOK_RIGHT', 'Nhìn sang phải', 'Phát hiện người lái nhìn sang phải');

INSERT INTO events (device_id,event_type_id,started_at,ended_at, duration_seconds, warning_triggered, warning_at, confidence)
VALUES
    (1, 1, '2026-09-21 08:10:12', '2026-09-21 08:10:15', 3.0, FALSE, NULL, 0.91),
    (1, 2, '2026-09-21 08:15:20', '2026-09-21 08:15:24', 4.0, TRUE,  '2026-09-21 08:15:23', 0.94),
    (1, 3, '2026-09-21 08:20:05', '2026-09-21 08:20:08', 3.0, FALSE, NULL, 0.89),
    (1, 4, '2026-09-21 08:25:30', '2026-09-21 08:25:34', 4.0, TRUE,  '2026-09-21 08:25:33', 0.96),
    (1, 5, '2026-09-21 08:30:10', '2026-09-21 08:30:14', 4.0, TRUE,  '2026-09-21 08:30:12', 0.98),
    (1, 6, '2026-09-21 08:30:14', '2026-09-21 08:30:20', 6.0, FALSE, NULL, 0.95),
    (1, 7, '2026-09-21 08:40:02', '2026-09-21 08:40:07', 5.0, TRUE,  '2026-09-21 08:40:05', 0.93),
    (1, 8, '2026-09-21 08:45:10', '2026-09-21 08:45:13', 3.0, FALSE, NULL, 0.90),
    (1, 9, '2026-09-21 08:50:22', '2026-09-21 08:50:26', 4.0, TRUE,  '2026-09-21 08:50:25', 0.97);
	
INSERT INTO alerts (event_id, type, severity, created_at, resolved_at)
VALUES (5, 'DROWSINESS', 'WARNING', '2026-09-21 08:30:12', '2026-09-21 08:30:20'),
       (2, 'HEAD_POSE', 'WARNING', '2026-09-21 08:15:23', NULL),
       (4, 'HEAD_POSE', 'WARNING', '2026-09-21 08:25:33', NULL),
       (7, 'FACE_LOST', 'WARNING', '2026-09-21 08:40:05', '2026-09-21 08:40:07'),
       (9, 'DISTRACTION', 'WARNING', '2026-09-21 08:50:25', NULL);

INSERT INTO command_types (code, name, description)
VALUES
    ('BUZZER_ON', 'Bật còi', 'Bật còi cảnh báo'),
    ('VIBRATION_ON', 'Bật rung', 'Bật motor rung cảnh báo'),
    ('LED_ON', 'Bật đèn', 'Bật đèn cảnh báo'),
    ('CAMERA_CHECK', 'Kiểm tra camera', 'Yêu cầu thiết bị kiểm tra trạng thái camera')
    ('BUZZER_OFF', 'Tắt còi', 'Tắt còi cảnh báo'),
    ('VIBRATION_OFF', 'Tắt rung', 'Tắt motor rung cảnh báo'),
    ('LED_OFF', 'Tắt đèn', 'Tắt đèn cảnh báo');

INSERT INTO commands (alert_id, device_id, command_type_id, status, created_at, executed_at)
VALUES (1, 1, 1, 'EXECUTED', '2026-09-21 08:30:12', '2026-09-21 08:30:12'),
       (2, 1, 2, 'EXECUTED', '2026-09-21 08:15:23', '2026-09-21 08:15:23'),
       (3, 1, 1, 'EXECUTED', '2026-09-21 08:25:33', '2026-09-21 08:25:34'),
       (4, 1, 4, 'EXECUTED', '2026-09-21 08:40:05', '2026-09-21 08:40:06');
	   
INSERT INTO command_acks (command_id, status, created_at, executed_at)
VALUES (1, 'EXECUTED', '2026-09-21 08:30:12', '2026-09-21 08:30:12'),
       (2, 'EXECUTED', '2026-09-21 08:15:23', '2026-09-21 08:15:23'),
       (3, 'EXECUTED', '2026-09-21 08:25:33', '2026-09-21 08:25:34'),
       (4, 'EXECUTED', '2026-09-21 08:40:05', '2026-09-21 08:40:06');
	   
INSERT INTO captures (user_id, device_id, video_path)
VALUES (1, 1, 'captures/2026-09-21/session_001.mp4'),
       (1, 1, 'captures/2026-09-21/session_002.mp4'),
       (1, 2, 'captures/2026-09-21/session_003.mp4');
