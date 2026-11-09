-- Add optional measurements. Existing telemetry, rules, assignments and commands stay intact.
BEGIN;
ALTER TABLE telemetry ADD COLUMN IF NOT EXISTS ai_signals JSONB;
COMMIT;
