DROP SCHEMA public CASCADE;
CREATE SCHEMA public;

-- TODO: thêm confidence

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
	fullname VARCHAR(255) NOT NULL,
    username VARCHAR(255) NOT NULL,
    hash_password VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    phone VARCHAR(20) UNIQUE NOT NULL,
	role VARCHAR(20) NOT NULL DEFAULT 'Customer'
        CHECK (role IN ('ADMIN', 'OPERATOR', 'VIEWER'))
);

CREATE TABLE devices (
    id SERIAL PRIMARY KEY,
    device_code VARCHAR(100) UNIQUE NOT NULL,
    model VARCHAR(100) NOT NULL,
    name VARCHAR(255),
    status VARCHAR(30) DEFAULT 'OFFLINE',
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

CREATE TABLE event_types (
    id SERIAL PRIMARY KEY,
    code VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    description VARCHAR(255)
);

CREATE TABLE events (
    id SERIAL PRIMARY KEY,
    device_id INT NOT NULL REFERENCES devices(id),
    event_type_id INT NOT NULL REFERENCES event_types(id),

    started_at TIMESTAMP NOT NULL,
    ended_at TIMESTAMP,
    duration_seconds FLOAT,

    angle_x FLOAT,
    angle_y FLOAT,
    angle_z FLOAT,

    warning_triggered BOOLEAN DEFAULT FALSE,
    warning_at TIMESTAMP
);

CREATE TABLE alerts (
    id SERIAL PRIMARY KEY,
    event_id INT REFERENCES events(id),
    device_id INT NOT NULL REFERENCES devices(id),
    alert_type VARCHAR(50) NOT NULL,
    description VARCHAR(255),
    severity VARCHAR(20),
    status VARCHAR(30) DEFAULT 'NEW',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP
);

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

    status VARCHAR(30),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    executed_at TIMESTAMP
);

CREATE TABLE command_acks (
    id SERIAL PRIMARY KEY,
    command_id INT NOT NULL REFERENCES commands(id),

    status VARCHAR(30),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    executed_at TIMESTAMP
);


CREATE TABLE captures(
	id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id),
	device_id INT NOT NULL REFERENCES devices(id),
    video_path VARCHAR(255)
);

CREATE TABLE configs (
    id SERIAL PRIMARY KEY,
    device_id INT UNIQUE NOT NULL REFERENCES devices(id),
    desired_config JSON,
    applied_config JSON,
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