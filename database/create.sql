BEGIN;

DROP SCHEMA public CASCADE;
CREATE SCHEMA public;

-- ============================================================
-- 1. USERS AND DEVICES
-- ============================================================

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    fullname VARCHAR(255) NOT NULL,
    username VARCHAR(255) NOT NULL,
    hash_password VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    phone VARCHAR(20) UNIQUE NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'Customer'
        CHECK (role IN ('Admin', 'Employee', 'Customer'))
);

CREATE TABLE devices (
    id SERIAL PRIMARY KEY,
    device_code VARCHAR(100) UNIQUE NOT NULL,
    model VARCHAR(100) NOT NULL,
    name VARCHAR(255),
    status VARCHAR(30) DEFAULT 'OFFLINE',
    device_type VARCHAR(30),
    lifecycle_state VARCHAR(30) NOT NULL DEFAULT 'REGISTERED',
    firmware_version VARCHAR(80),
    ip_address INET,
    mac_address MACADDR,
    last_seen TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    mqtt_username VARCHAR(255),
    mqtt_password VARCHAR(255)
);

CREATE TABLE user_devices (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id),
    device_id INT NOT NULL REFERENCES devices(id),
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    unassigned_at TIMESTAMP
);

-- ============================================================
-- 2. TELEMETRY
-- ============================================================

CREATE TABLE telemetry (
    id SERIAL PRIMARY KEY,
    device_id INT NOT NULL REFERENCES devices(id),
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ear DOUBLE PRECISION,
    perclos DOUBLE PRECISION,
    confidence DOUBLE PRECISION,
    driver_state VARCHAR(30),
    face_detected BOOLEAN,
    head_pose JSONB,
    model_version VARCHAR(80)
);

-- ============================================================
-- 3. AI EVENTS, MESSAGE RECEIPTS, AND ALERTS
-- ============================================================

CREATE TABLE ai_events (
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

CREATE TABLE ai_message_receipts (
    id SERIAL PRIMARY KEY,
    device_id INT NOT NULL REFERENCES devices(id),
    message_id VARCHAR(80) NOT NULL,
    topic VARCHAR(200) NOT NULL,
    payload_hash VARCHAR(64) NOT NULL,
    saved_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (device_id, message_id)
);

CREATE TABLE alerts (
    id SERIAL PRIMARY KEY,
    event_id INT REFERENCES ai_events(id),
    device_id INT NOT NULL REFERENCES devices(id),
    alert_type VARCHAR(50) NOT NULL,
    description VARCHAR(255),
    severity VARCHAR(20),
    status VARCHAR(30) DEFAULT 'NEW',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    source_event_id VARCHAR(80)
);

-- ============================================================
-- 4. COMMANDS AND ACKNOWLEDGEMENTS
-- ============================================================

CREATE TABLE command_types (
    id SERIAL PRIMARY KEY,
    code VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    description VARCHAR(255)
);

CREATE TABLE commands (
    id SERIAL PRIMARY KEY,
    alert_id INT REFERENCES alerts(id),
    device_id INT NOT NULL REFERENCES devices(id),
    command_type_id INT NOT NULL REFERENCES command_types(id),
    status VARCHAR(30) DEFAULT 'PENDING',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    executed_at TIMESTAMP,
    request_id VARCHAR(80),
    action VARCHAR(40),
    created_by_user_id INT REFERENCES users(id),
    ack_status VARCHAR(30),
    error_message TEXT,
    dispatches JSONB,
    idempotency_key VARCHAR(128),
    request_hash VARCHAR(64),
    http_received_at TIMESTAMP,
    http_completed_at TIMESTAMP,
    http_duration_ms DOUBLE PRECISION,
    mqtt_published_at TIMESTAMP,
    first_ack_at TIMESTAMP,
    completed_ack_at TIMESTAMP
);

CREATE TABLE command_acks (
    id SERIAL PRIMARY KEY,
    command_id INT NOT NULL REFERENCES commands(id),
    status VARCHAR(30),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    executed_at TIMESTAMP
);

-- ============================================================
-- 5. VIDEO CAPTURES AND AI VIDEO METADATA
-- ============================================================

-- Actual video bytes are stored outside PostgreSQL in private storage.
-- This table stores metadata and the storage key only.
CREATE TABLE ai_videos (
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

-- ============================================================
-- 6. RULES, CONFIGURATION AND AUDIT
-- ============================================================

CREATE TABLE rule_bindings (
    source_device_id INT PRIMARY KEY REFERENCES devices(id),
    target_device_id INT NOT NULL REFERENCES devices(id),
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    policy JSONB NOT NULL,
    last_triggered_at TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (source_device_id <> target_device_id)
);

CREATE TABLE configs (
    id SERIAL PRIMARY KEY,
    device_id INT UNIQUE NOT NULL REFERENCES devices(id),
    desired_config JSON,
    applied_config JSON,
    revision INT NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE audit_logs (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id),
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(100),
    entity_id VARCHAR(100),
    details JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 8. INDEXES
-- ============================================================

CREATE INDEX user_devices_active_user_device_idx
    ON user_devices(user_id, device_id)
    WHERE unassigned_at IS NULL;

CREATE INDEX telemetry_device_recorded_idx
    ON telemetry(device_id, recorded_at DESC);

CREATE INDEX telemetry_model_time_idx
    ON telemetry(device_id, model_version, recorded_at DESC);

CREATE INDEX ai_events_device_time_idx
    ON ai_events(device_id, occurred_at DESC);

CREATE INDEX ai_videos_device_time_idx
    ON ai_videos(device_id, created_at DESC);

CREATE INDEX commands_alert_idx
    ON commands(alert_id);

CREATE INDEX commands_device_created_idx
    ON commands(device_id, created_at DESC);

CREATE INDEX commands_device_id_idx
    ON commands(device_id);

CREATE INDEX commands_status_idx
    ON commands(status);

CREATE INDEX commands_created_at_idx
    ON commands(created_at);

CREATE UNIQUE INDEX commands_request_id_key
    ON commands(request_id)
    WHERE request_id IS NOT NULL;

CREATE UNIQUE INDEX commands_idempotency_key
    ON commands(created_by_user_id, device_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE UNIQUE INDEX alerts_source_event_id_key
    ON alerts(source_event_id)
    WHERE source_event_id IS NOT NULL;

CREATE INDEX devices_status_idx
    ON devices(status);

COMMIT;
