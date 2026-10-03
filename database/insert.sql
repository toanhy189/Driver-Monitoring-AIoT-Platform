INSERT INTO users (fullname, username, hash_password, email, phone)
VALUES ('Nguyễn Văn An', 'nguyenan', '$argon2id$v=19$m=65536,t=3,p=4$DdvWdfr4/V2LHpZkN9zhGg$fdDtduGG/5ATl28e6nqTXN1RKAhgOrMQVI0TFlweTyk', 'an@example.com', '0901234567');

INSERT INTO devices (device_code, model, name, status, ip_address)
VALUES ('DM-000001', 'Laptop-Cam-V1', 'Laptop của An', 'ONLINE', '192.168.1.10'),
       ('DM-000002', 'External-Cam-V1', 'Camera phụ', 'OFFLINE', '192.168.1.11');

INSERT INTO user_devices (user_id, device_id, assigned_at, unassigned_at)
VALUES (1, 1, CURRENT_TIMESTAMP, NULL),
       (1, 2, CURRENT_TIMESTAMP, NULL);

INSERT INTO event_types (code, name, description)
VALUES ('YAWN', 'Ngáp', 'Phát hiện người lái đang ngáp'),
       ('HEAD_DOWN', 'Đầu cúi', 'Phát hiện đầu cúi về phía trước'),
       ('HEAD_TILT_LEFT', 'Đầu nghiêng trái', 'Phát hiện đầu nghiêng sang trái'),
       ('HEAD_TILT_RIGHT', 'Đầu nghiêng phải', 'Phát hiện đầu nghiêng sang phải'),
       ('EYE_CLOSED', 'Mắt nhắm', 'Phát hiện mắt đang nhắm'),
       ('EYE_OPEN', 'Mắt mở', 'Phát hiện mắt đang mở'),
       ('FACE_LOST', 'Mặt biến mất', 'Không phát hiện được khuôn mặt trong vùng camera'),
       ('LOOK_LEFT', 'Nhìn sang trái', 'Phát hiện người lái nhìn sang trái'),
       ('LOOK_RIGHT', 'Nhìn sang phải', 'Phát hiện người lái nhìn sang phải');

INSERT INTO events (device_id, event_type_id, started_at, ended_at, duration_seconds, angle_x, angle_y, angle_z, warning_triggered, warning_at)
VALUES (1, 1, '2026-09-21 08:10:12', '2026-09-21 08:10:15', 3.0, NULL, NULL, NULL, FALSE, NULL),
       (1, 2, '2026-09-21 08:15:20', '2026-09-21 08:15:24', 4.0, 18.5, 1.2, -0.5, TRUE, '2026-09-21 08:15:23'),
       (1, 3, '2026-09-21 08:20:05', '2026-09-21 08:20:08', 3.0, 2.0, -15.4, 4.1, FALSE, NULL),
       (1, 4, '2026-09-21 08:25:30', '2026-09-21 08:25:34', 4.0, 1.8, 16.2, -3.2, TRUE, '2026-09-21 08:25:33'),
       (1, 5, '2026-09-21 08:30:10', '2026-09-21 08:30:14', 4.0, NULL, NULL, NULL, TRUE, '2026-09-21 08:30:12'),
       (1, 6, '2026-09-21 08:30:14', '2026-09-21 08:30:20', 6.0, NULL, NULL, NULL, FALSE, NULL),
       (1, 7, '2026-09-21 08:40:02', '2026-09-21 08:40:07', 5.0, NULL, NULL, NULL, TRUE, '2026-09-21 08:40:05'),
       (1, 8, '2026-09-21 08:45:10', '2026-09-21 08:45:13', 3.0, NULL, -28.5, NULL, FALSE, NULL),
       (1, 9, '2026-09-21 08:50:22', '2026-09-21 08:50:26', 4.0, NULL, 31.2, NULL, TRUE, '2026-09-21 08:50:25');

INSERT INTO alerts (event_id, type, severity, created_at, resolved_at)
VALUES (5, 'DROWSINESS', 'WARNING', '2026-09-21 08:30:12', '2026-09-21 08:30:20'),
       (2, 'HEAD_POSE', 'WARNING', '2026-09-21 08:15:23', NULL),
       (4, 'HEAD_POSE', 'WARNING', '2026-09-21 08:25:33', NULL),
       (7, 'FACE_LOST', 'WARNING', '2026-09-21 08:40:05', '2026-09-21 08:40:07'),
       (9, 'DISTRACTION', 'WARNING', '2026-09-21 08:50:25', NULL);

INSERT INTO command_types (code, name, description)
VALUES ('BUZZER_ON', 'Bật còi', 'Bật còi cảnh báo'),
	   ('VIBRATION_ON', 'Bật rung', 'Bật motor rung cảnh báo'),
	   ('LED_ON', 'Bật đèn', 'Bật đèn cảnh báo'),
	   ('CAMERA_CHECK', 'Kiểm tra camera', 'Yêu cầu thiết bị kiểm tra trạng thái camera');

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
