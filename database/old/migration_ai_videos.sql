-- File bytes stay in private storage; this table holds metadata only.
BEGIN;
CREATE TABLE IF NOT EXISTS ai_videos (
    id SERIAL PRIMARY KEY,
    device_id INT NOT NULL REFERENCES devices(id),
    message_id VARCHAR(80) NOT NULL,
    state VARCHAR(30) NOT NULL,
    storage_key VARCHAR(80) NOT NULL,
    sha256 VARCHAR(64) NOT NULL,
    size_bytes BIGINT NOT NULL CHECK (size_bytes > 0),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (device_id, message_id)
);
CREATE INDEX IF NOT EXISTS ai_videos_device_time_idx ON ai_videos(device_id, created_at DESC);
COMMIT;
