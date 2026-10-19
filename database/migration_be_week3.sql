-- Additive migration. Safe to rerun; never drop application data.
BEGIN;
ALTER TABLE telemetry ADD COLUMN IF NOT EXISTS received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE configs ADD COLUMN IF NOT EXISTS revision INT NOT NULL DEFAULT 0;

ALTER TABLE commands
    ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(128),
    ADD COLUMN IF NOT EXISTS request_hash VARCHAR(64),
    ADD COLUMN IF NOT EXISTS http_received_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS http_completed_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS http_duration_ms DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS mqtt_published_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS first_ack_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS completed_ack_at TIMESTAMP;

CREATE UNIQUE INDEX IF NOT EXISTS commands_idempotency_key
    ON commands(created_by_user_id, device_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS commands_alert_idx ON commands(alert_id);

CREATE TABLE IF NOT EXISTS ai_events (
    id SERIAL PRIMARY KEY,
    event_id VARCHAR(80) NOT NULL UNIQUE,
    device_id INT NOT NULL REFERENCES devices(id),
    event_type VARCHAR(80) NOT NULL,
    occurred_at TIMESTAMP NOT NULL,
    received_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    model_version VARCHAR(80),
    state VARCHAR(30),
    state_duration_ms BIGINT,
    payload_hash VARCHAR(64) NOT NULL,
    payload JSONB NOT NULL,
    outcome VARCHAR(40) NOT NULL DEFAULT 'RECORDED'
);
CREATE INDEX IF NOT EXISTS ai_events_device_time_idx ON ai_events(device_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS telemetry_model_time_idx ON telemetry(device_id, model_version, recorded_at DESC);

-- Storage acknowledgements share the transaction of the telemetry/event they confirm.
CREATE TABLE IF NOT EXISTS ai_message_receipts (
    id SERIAL PRIMARY KEY,
    device_id INT NOT NULL REFERENCES devices(id),
    message_id VARCHAR(80) NOT NULL,
    topic VARCHAR(200) NOT NULL,
    payload_hash VARCHAR(64) NOT NULL,
    saved_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (device_id, message_id)
);

CREATE TABLE IF NOT EXISTS rule_bindings (
    source_device_id INT PRIMARY KEY REFERENCES devices(id),
    target_device_id INT NOT NULL REFERENCES devices(id),
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    policy JSONB NOT NULL,
    last_triggered_at TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (source_device_id <> target_device_id)
);

INSERT INTO command_types(code, name, description)
VALUES ('AUTO_ALERT', 'Cảnh báo tự động', 'Lệnh được tạo từ sự kiện AI theo Rule Engine')
ON CONFLICT (code) DO NOTHING;

COMMIT;
