BEGIN;
ALTER TABLE devices ADD COLUMN IF NOT EXISTS ota_capabilities JSONB;
CREATE TABLE IF NOT EXISTS firmware_artifacts (
 id SERIAL PRIMARY KEY, version VARCHAR(80) NOT NULL, hardware_version VARCHAR(80) NOT NULL,
 sha256 VARCHAR(64) NOT NULL, app_sha256 VARCHAR(64) NOT NULL, size_bytes INTEGER NOT NULL,
 storage_key VARCHAR(100) NOT NULL, manifest JSONB NOT NULL, state VARCHAR(30) NOT NULL DEFAULT 'DRAFT',
 notes TEXT NOT NULL DEFAULT '', verification_error TEXT, created_by INTEGER NOT NULL REFERENCES users(id),
 created_at TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'utc'), UNIQUE(version,hardware_version)
);
CREATE TABLE IF NOT EXISTS ota_deployments (
 id SERIAL PRIMARY KEY, artifact_id INTEGER NOT NULL REFERENCES firmware_artifacts(id),
 created_by INTEGER NOT NULL REFERENCES users(id), created_at TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
);
CREATE TABLE IF NOT EXISTS ota_device_jobs (
 id SERIAL PRIMARY KEY, deployment_id INTEGER NOT NULL REFERENCES ota_deployments(id),
 device_id INTEGER NOT NULL REFERENCES devices(id), request_id VARCHAR(80) NOT NULL UNIQUE,
 state VARCHAR(30) NOT NULL DEFAULT 'QUEUED', previous_version VARCHAR(80), previous_sha256 VARCHAR(64),
 installed_version VARCHAR(80), installed_sha256 VARCHAR(64), bytes_received INTEGER NOT NULL DEFAULT 0,
 last_sequence INTEGER NOT NULL DEFAULT -1, error TEXT,
 created_at TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
 updated_at TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'utc'), expires_at TIMESTAMP NOT NULL,
 UNIQUE(deployment_id,device_id)
);
CREATE INDEX IF NOT EXISTS ix_ota_device_jobs_device_id ON ota_device_jobs(device_id);
CREATE INDEX IF NOT EXISTS ix_ota_device_jobs_deployment_id ON ota_device_jobs(deployment_id);
CREATE TABLE IF NOT EXISTS ota_job_events (
 id SERIAL PRIMARY KEY, job_id INTEGER NOT NULL REFERENCES ota_device_jobs(id), event_id VARCHAR(100) NOT NULL,
 state VARCHAR(30) NOT NULL, detail TEXT, bytes_received INTEGER NOT NULL DEFAULT 0,
 created_at TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'utc'), UNIQUE(job_id,event_id)
);
CREATE INDEX IF NOT EXISTS ix_ota_job_events_job_id ON ota_job_events(job_id);
COMMIT;
