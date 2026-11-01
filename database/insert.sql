BEGIN;

INSERT INTO users (fullname, username, hash_password, email, phone, role)
VALUES ('Nguyễn Văn An', 'nguyenan', '$argon2id$v=19$m=65536,t=3,p=4$DdvWdfr4/V2LHpZkN9zhGg$fdDtduGG/5ATl28e6nqTXN1RKAhgOrMQVI0TFlweTyk', 'an@example.com', '0901234567', 'Customer');

INSERT INTO devices (device_code, model, name, status, device_type, ip_address)
VALUES
    ('alert-01', 'Thiết bị cảnh báo V1', 'V1-A01 của An', 'OFFLINE', 'ALERT_NODE', '192.168.1.10'),
    ('DM-000002', 'External-Cam-V1', 'Camera phụ', 'OFFLINE', 'VISION_NODE', '192.168.1.11'),
    ('vision-01', 'AI Vision Node', 'Camera AI', 'OFFLINE', 'VISION_NODE', NULL);

INSERT INTO user_devices (user_id, device_id)
SELECT u.id, d.id
FROM users u
CROSS JOIN devices d
WHERE u.username = 'nguyenan'
  AND d.device_code IN ('alert-01', 'DM-000002', 'vision-01');

-- ===================
-- 2. Telemetry
-- ===================

INSERT INTO telemetry (device_id, recorded_at, received_at, ear, perclos, confidence, driver_state, face_detected, head_pose, model_version)
VALUES
    (3, '2026-09-21 08:10:00', '2026-09-21 08:10:00', 0.31, 0.02, 0.96, 'ATTENTIVE', TRUE, '{"angle_x":2.1,"angle_y":1.2,"angle_z":0.5}'::jsonb, 'demo-v1');

COMMIT;