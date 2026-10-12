-- Apply once to an existing PostgreSQL volume. Additive and safe to rerun.
-- Do not run create.sql on an existing database: it drops the public schema.

BEGIN;

ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
ALTER TABLE users ADD CONSTRAINT users_role_check
    CHECK (role IN ('Admin', 'Employee', 'Customer', 'ADMIN', 'OPERATOR', 'VIEWER'));

ALTER TABLE devices
    ADD COLUMN IF NOT EXISTS device_type VARCHAR(30),
    ADD COLUMN IF NOT EXISTS lifecycle_state VARCHAR(30) NOT NULL DEFAULT 'REGISTERED',
    ADD COLUMN IF NOT EXISTS firmware_version VARCHAR(80),
    ADD COLUMN IF NOT EXISTS mqtt_username VARCHAR(255),
    ADD COLUMN IF NOT EXISTS mqtt_password VARCHAR(255);

UPDATE devices
SET device_type = CASE
    WHEN device_code ILIKE 'alert-%' OR model ILIKE '%alert%' OR model ILIKE '%cảnh báo%'
        THEN 'ALERT_NODE'
    WHEN device_code ILIKE 'vision-%' OR model ILIKE '%cam%'
        THEN 'VISION_NODE'
    ELSE NULL
END
WHERE device_type IS NULL;

ALTER TABLE telemetry
    ADD COLUMN IF NOT EXISTS driver_state VARCHAR(30),
    ADD COLUMN IF NOT EXISTS face_detected BOOLEAN,
    ADD COLUMN IF NOT EXISTS head_pose JSONB,
    ADD COLUMN IF NOT EXISTS model_version VARCHAR(80);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'alerts' AND column_name = 'type')
       AND NOT EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name = 'alerts' AND column_name = 'alert_type') THEN
        ALTER TABLE alerts RENAME COLUMN type TO alert_type;
    END IF;
END $$;

ALTER TABLE alerts
    ADD COLUMN IF NOT EXISTS device_id INT REFERENCES devices(id),
    ADD COLUMN IF NOT EXISTS alert_type VARCHAR(50),
    ADD COLUMN IF NOT EXISTS description VARCHAR(255),
    ADD COLUMN IF NOT EXISTS status VARCHAR(30) DEFAULT 'NEW',
    ADD COLUMN IF NOT EXISTS source_event_id VARCHAR(80);

ALTER TABLE alerts ALTER COLUMN event_id DROP NOT NULL;

UPDATE alerts AS a SET device_id = e.device_id
FROM events AS e WHERE a.event_id = e.id AND a.device_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS alerts_source_event_id_key
    ON alerts(source_event_id) WHERE source_event_id IS NOT NULL;

ALTER TABLE commands
    ADD COLUMN IF NOT EXISTS request_id VARCHAR(80),
    ADD COLUMN IF NOT EXISTS action VARCHAR(40),
    ADD COLUMN IF NOT EXISTS created_by_user_id INT REFERENCES users(id),
    ADD COLUMN IF NOT EXISTS ack_status VARCHAR(30),
    ADD COLUMN IF NOT EXISTS error_message TEXT,
    ADD COLUMN IF NOT EXISTS dispatches JSONB;

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

CREATE UNIQUE INDEX IF NOT EXISTS commands_request_id_key
    ON commands(request_id) WHERE request_id IS NOT NULL;

INSERT INTO command_types(code, name, description)
VALUES ('TEST_ALERT', 'Kiểm tra cảnh báo', 'Kiểm tra LED, còi và motor')
ON CONFLICT (code) DO NOTHING;

CREATE INDEX IF NOT EXISTS user_devices_active_user_device_idx
    ON user_devices(user_id, device_id) WHERE unassigned_at IS NULL;
CREATE INDEX IF NOT EXISTS telemetry_device_recorded_idx
    ON telemetry(device_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS commands_device_created_idx
    ON commands(device_id, created_at DESC);

COMMIT;
