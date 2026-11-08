BEGIN;

ALTER TABLE ai_events
  ADD COLUMN IF NOT EXISTS segment_message_id VARCHAR(80),
  ADD COLUMN IF NOT EXISTS segment_event_id INT REFERENCES ai_events(id) ON DELETE SET NULL;

ALTER TABLE ai_videos
  ADD COLUMN IF NOT EXISTS event_id INT REFERENCES ai_events(id) ON DELETE SET NULL;

-- Backfill 1: video -> STATE_CHANGED event
UPDATE ai_videos v SET event_id = e.id
FROM ai_events e
WHERE v.event_id IS NULL AND e.event_id = v.message_id AND e.device_id = v.device_id;

-- Backfill 2: alerts.event_id từ source_event_id
UPDATE alerts a SET event_id = e.id
FROM ai_events e
WHERE a.event_id IS NULL AND a.source_event_id = e.event_id;

-- Backfill 3 (dữ liệu cũ, suy luận): threshold -> STATE_CHANGED gần nhất cùng state, trước đó
UPDATE ai_events t SET segment_event_id = (
    SELECT s.id FROM ai_events s
    WHERE s.device_id = t.device_id AND s.event_type = 'STATE_CHANGED'
      AND s.state = t.state AND s.occurred_at <= t.occurred_at
    ORDER BY s.occurred_at DESC, s.id DESC LIMIT 1)
WHERE t.event_type IN ('DROWSY_THRESHOLD_REACHED','DISTRACTED_THRESHOLD_REACHED')
  AND t.segment_event_id IS NULL;

UPDATE ai_events t SET segment_message_id = s.event_id
FROM ai_events s
WHERE t.segment_event_id = s.id AND t.segment_message_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ai_videos_event_id_key ON ai_videos(event_id) WHERE event_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ai_events_segment_event_idx ON ai_events(segment_event_id);
CREATE INDEX IF NOT EXISTS ai_events_segment_msg_idx ON ai_events(device_id, segment_message_id)
  WHERE segment_message_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS alerts_event_id_idx ON alerts(event_id);

-- View để kiểm tra nhanh bằng psql
CREATE OR REPLACE VIEW alert_video_v AS
SELECT a.id AS alert_id, a.alert_type, a.severity, a.created_at AS alert_at,
       v.id AS video_id, v.state, v.size_bytes
FROM alerts a
JOIN ai_events t ON t.id = a.event_id
JOIN ai_videos v ON v.event_id = t.segment_event_id;

-- Dữ liệu tham chiếu mà ứng dụng bắt buộc có (idempotent, trùng với insert.sql)
INSERT INTO command_types (code, name, description) VALUES
    ('BUZZER_ON', 'Bật còi', 'Kích hoạt còi cảnh báo trên node ESP32'),
    ('LED_ON', 'Bật đèn', 'Bật đèn cảnh báo và báo hiệu'),
    ('VIBRATION_ON', 'Bật rung', 'Kích hoạt motor rung cảnh báo'),
    ('CAMERA_CHECK', 'Kiểm tra camera', 'Yêu cầu AI Vision kiểm tra lại camera'),
    ('TEST_ALERT', 'Kiểm tra cảnh báo', 'Chạy test toàn bộ actuator'),
    ('AUTO_ALERT', 'Cảnh báo tự động', 'Kích hoạt cảnh báo từ Rule Engine')
ON CONFLICT (code) DO NOTHING;

COMMIT;