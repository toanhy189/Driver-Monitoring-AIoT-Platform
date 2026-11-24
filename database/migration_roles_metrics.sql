-- Additive and repeatable. Existing alerts, commands and assignments remain intact.
BEGIN;
CREATE UNIQUE INDEX IF NOT EXISTS users_single_admin_idx
    ON users ((1)) WHERE role IN ('Admin', 'ADMIN');
CREATE TABLE IF NOT EXISTS alert_reads (
    alert_id INTEGER NOT NULL REFERENCES alerts(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    acknowledged_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (alert_id, user_id)
);
CREATE INDEX IF NOT EXISTS alert_reads_user_idx ON alert_reads(user_id, alert_id);
-- Preserve old acknowledgements when the audit trail identifies the reader.
INSERT INTO alert_reads (alert_id, user_id, acknowledged_at)
SELECT a.id, u.id, COALESCE(MIN(log.created_at), CURRENT_TIMESTAMP)
FROM audit_logs log
JOIN alerts a ON CAST(a.id AS TEXT) = log.entity_id
JOIN users u ON u.id = log.user_id
WHERE log.action = 'ACKNOWLEDGE_ALERT' AND log.entity_type = 'Alert'
GROUP BY a.id, u.id
ON CONFLICT (alert_id, user_id) DO NOTHING;
COMMIT;
