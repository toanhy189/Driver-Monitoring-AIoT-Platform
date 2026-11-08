-- Additive upgrade. Never run create.sql against an existing application DB.
BEGIN;
ALTER TABLE users ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE';
ALTER TABLE users ADD COLUMN IF NOT EXISTS session_version INTEGER NOT NULL DEFAULT 0;
ALTER TABLE devices ADD COLUMN IF NOT EXISTS hardware_version VARCHAR(80);
ALTER TABLE ai_videos ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;
-- Fail on duplicate identities instead of guessing which user's data to delete.
CREATE UNIQUE INDEX IF NOT EXISTS users_username_unique_idx ON users(username);
CREATE UNIQUE INDEX IF NOT EXISTS user_devices_active_unique_idx
    ON user_devices(user_id, device_id) WHERE unassigned_at IS NULL;
COMMIT;
