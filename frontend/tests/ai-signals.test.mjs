import test from "node:test";
import assert from "node:assert/strict";
import { normalizeAiSignals, mouthStateLabel, eyeStateLabel } from "../src/services/aiSignals.js";
import { normalizeTelemetry } from "../src/services/telemetry.js";

const signal = { schema_version: "eye-mouth-v1", mar: .4, mouth_state: "YAWN", mouth_available: true,
  yawn_probability: .8, eyes_available: false, eye_state: "UNKNOWN", experimental: true };

test("MAR and yawn remain different, unavailable eyes never become normal", () => {
  const result = normalizeAiSignals({ ...signal, eye_state: "NORMAL", eye_sleepy_probability: .9 });
  assert.equal(result.mar, .4);
  assert.equal(result.mouth_state, "YAWN");
  assert.equal(result.eye_state, "UNKNOWN");
  assert.equal(result.eye_sleepy_probability, null);
  assert.equal(mouthStateLabel("TALKING_LAUGHING"), "Nói / cười");
  assert.equal(eyeStateLabel("SLEEPY"), "Biểu hiện mắt buồn ngủ");
});

test("new telemetry preserves signals without inferring driver_state; face loss clears them", () => {
  const result = normalizeTelemetry({ device_id: 5, driver_state: "UNKNOWN", face_detected: true, ai_signals: signal });
  assert.equal(result.ai_signals.mouth_state, "YAWN");
  assert.equal(result.driver_state, "UNKNOWN");
  assert.equal(normalizeTelemetry({ device_id: 5, face_detected: false, ai_signals: signal }).ai_signals, null);
  assert.equal(normalizeAiSignals({ ...signal, schema_version: "unknown" }), null);
  assert.equal(normalizeAiSignals({ ...signal, yawn_probability: Infinity }).yawn_probability, null);
  assert.equal(Object.hasOwn(normalizeTelemetry({ device_id: 5 }), "ai_signals"), false);
});
