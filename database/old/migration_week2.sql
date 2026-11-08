-- ============================================================
-- Migration Database cho Dữ liệu Tuần 2
-- Purpose:
--   - Chuẩn hóa role user (TV2-02, TV2-05)
--   - Bổ sung MQTT credential cho device (TV2-07, TV2-08)
--   - Chuẩn bị dữ liệu cho Command lifecycle (TV2-10)
--   - Sửa cấu trúc alerts, thêm configs, audit_logs (TV2-17, TV2-18, TV2-19)
--
-- IMPORTANT:
--   Migration này KHÔNG xóa dữ liệu hiện tại.
-- ============================================================

-- ============================================================
-- 1. USER ROLE (Phần bạn đã làm)
-- ============================================================
-- ALTER TABLE users
-- DROP CONSTRAINT IF EXISTS users_role_check;

-- UPDATE users
-- SET role = CASE role
--     WHEN 'Admin' THEN 'ADMIN'
--     WHEN 'Employee' THEN 'OPERATOR'
--     WHEN 'Customer' THEN 'VIEWER'
--     ELSE role
-- END;

-- ALTER TABLE users
-- ADD CONSTRAINT users_role_check
-- CHECK (role IN ('ADMIN', 'OPERATOR', 'VIEWER'));

-- -- ============================================================
-- -- 2. DEVICE MQTT CREDENTIAL (Phần bạn đã làm)
-- -- ============================================================
-- ALTER TABLE devices
-- ADD COLUMN IF NOT EXISTS mqtt_username VARCHAR(255);

-- ALTER TABLE devices
-- ADD COLUMN IF NOT EXISTS mqtt_password VARCHAR(255);

-- -- ============================================================
-- -- 3. COMMAND STATUS (Phần bạn đã làm)
-- -- ============================================================
-- UPDATE commands
-- SET status = 'PENDING'
-- WHERE status IS NULL;

-- ============================================================
-- 4. ALERTS TABLE UPDATE (Phần làm thêm cho TV2-18)
-- ============================================================
ALTER TABLE alerts
RENAME COLUMN type TO alert_type;

ALTER TABLE alerts
ALTER COLUMN event_id DROP NOT NULL;

ALTER TABLE alerts
ADD COLUMN IF NOT EXISTS device_id INT REFERENCES devices(id),
ADD COLUMN IF NOT EXISTS description VARCHAR(255),
ADD COLUMN IF NOT EXISTS status VARCHAR(30) DEFAULT 'NEW';

-- Tự động map device_id cho alert cũ
UPDATE alerts
SET device_id = events.device_id
FROM events
WHERE alerts.event_id = events.id;

-- ============================================================
-- 5. NEW TABLES (Phần làm thêm cho TV2-17, TV2-19)
-- ============================================================
CREATE TABLE IF NOT EXISTS configs (
    id SERIAL PRIMARY KEY,
    device_id INT UNIQUE NOT NULL REFERENCES devices(id),
    desired_config JSON,
    applied_config JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id),
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(100),
    entity_id VARCHAR(100),
    details JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 6. INDEXES (Phần bạn đã làm)
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_devices_device_code
ON devices(device_code);

CREATE INDEX IF NOT EXISTS idx_devices_status
ON devices(status);

CREATE INDEX IF NOT EXISTS idx_commands_device_id
ON commands(device_id);

CREATE INDEX IF NOT EXISTS idx_commands_status
ON commands(status);

CREATE INDEX IF NOT EXISTS idx_commands_created_at
ON commands(created_at);

-- ============================================================
-- 7. VERIFY
-- ============================================================
SELECT
    id,
    device_code,
    mqtt_username,
    status
FROM devices
ORDER BY id;

SELECT
    id,
    device_id,
    command_type_id,
    status,
    created_at
FROM commands
ORDER BY id;
