import test from "node:test";
import assert from "node:assert/strict";
import { normalizeAiSignals, mouthStateLabel, eyeStateLabel, normalizeHeadMotion, headMotionLabel, normalizeHeadEyeFusion, normalizeHeadDownPolicy, decisionReasonLabel } from "../src/services/aiSignals.js";
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

test("head motion preserves observations, rejects contradictions, and clears stale angles", () => {
  const head = { version: "head-motion-v1", mode: "OBSERVE_ONLY", available: true, calibrated: true,
    state: "REPEATED_NODS", pitch_deg: 1, yaw_deg: 2, roll_deg: 0, nod_count: 2,
    repeated_nods: true, eye_closure_supported: false };
  assert.deepEqual(normalizeHeadMotion(head), head);
  assert.deepEqual(normalizeHeadMotion(normalizeHeadMotion(head)), head);
  assert.equal(headMotionLabel(head.state), "Ghi nhận gật đầu lặp lại");
  for (const change of [{ mode: "ACTIVE" }, { pitch_deg: Infinity }, { nod_count: true },
    { nod_count: 1 }, { available: false }, { calibrated: false }, { state: "UNAVAILABLE" }, { state: "REACQUIRING" }]) {
    assert.equal(normalizeHeadMotion({ ...head, ...change }), null);
  }
  const unavailable = normalizeHeadMotion({ ...head, available: false, state: "UNAVAILABLE", pitch_deg: null,
    yaw_deg: null, roll_deg: null, nod_count: 0, repeated_nods: false });
  assert.equal(unavailable.pitch_deg, null);
  assert.equal(normalizeHeadMotion({ ...head, state: "REACQUIRING", nod_count: 0, repeated_nods: false }).state, "REACQUIRING");
  const raw = { ...signal, schema_version: "eye-mouth-v2", eye_quality: "NO_FACE", mouth_quality: "VALID", head_motion: head };
  const once = normalizeAiSignals(raw);
  assert.deepEqual(normalizeAiSignals(once), once);
  assert.equal(once.head_motion.nod_count, 2);
  assert.equal(normalizeTelemetry({ device_id: 5, driver_state: "ATTENTIVE", ai_signals: raw }).driver_state, "ATTENTIVE");
});

test("pose-bound eyes preserve risk metadata and reject missing geometry or invalid values", () => {
  const fusion={ version:"pose-calibrated-head-eye-v1",mode:"ENABLED",state:"CLOSED_RISK",
    ear_threshold:.28,risk_candidate:true,profile_sha256:"b".repeat(64) };
  assert.deepEqual(normalizeHeadEyeFusion(fusion),fusion);
  for (const change of [{mode:"unknown"},{ear_threshold:NaN},{state:"OPEN"},{profile_sha256:"wrong"}]) {
    assert.equal(normalizeHeadEyeFusion({...fusion,...change}),null);
  }
  const raw={...signal,schema_version:"eye-mouth-v2",eye_quality:"VALID",mouth_quality:"VALID",ear_available:true,
    calibration_id:"a".repeat(64),head_eye_fusion:fusion,decision_reason:"HEAD_EYE_CLOSURE_RISK",
    head_motion:{version:"head-motion-v1",mode:"OBSERVE_ONLY",state:"LOWERED",available:true,calibrated:true,
      pitch_deg:14,yaw_deg:0,roll_deg:0,nod_count:0,repeated_nods:false,eye_closure_supported:false}};
  assert.deepEqual(normalizeAiSignals(raw).head_eye_fusion,fusion);
  assert.deepEqual(normalizeAiSignals(normalizeAiSignals(raw)),normalizeAiSignals(raw));
  assert.equal(normalizeAiSignals({...raw,ear_available:false}).head_eye_fusion,null);
  assert.equal(normalizeAiSignals({...raw,head_motion:null}).head_eye_fusion,null);
});

test("head-down posture is labelled as a rule and requires matching current head geometry", () => {
  const posture={version:"sustained-head-down-v1",state:"DOWN_RISK",risk_candidate:true,
    observed_down_seconds:3.5,enter_pitch_deg:12,min_seconds:3};
  assert.deepEqual(normalizeHeadDownPolicy(posture),posture);
  assert.equal(decisionReasonLabel("HEAD_DOWN_RISK"),"Cúi đầu kéo dài theo quy tắc cảnh báo");
  for (const change of [{observed_down_seconds:1},{state:"NORMAL"},{observed_down_seconds:NaN}]) {
    assert.equal(normalizeHeadDownPolicy({...posture,...change}),null);
  }
  const raw={...signal,schema_version:"eye-mouth-v2",head_down_policy:posture,
    eye_quality:"NO_FACE",mouth_quality:"VALID",decision_reason:"HEAD_DOWN_RISK",
    head_motion:{version:"head-motion-v1",mode:"OBSERVE_ONLY",available:true,calibrated:true,state:"LOWERED",
      pitch_deg:15,yaw_deg:0,roll_deg:0,nod_count:0,repeated_nods:false,eye_closure_supported:false}};
  assert.deepEqual(normalizeAiSignals(raw).head_down_policy,posture);
  assert.deepEqual(normalizeAiSignals(normalizeAiSignals(raw)),normalizeAiSignals(raw));
  assert.equal(normalizeAiSignals({...raw,head_motion:null}).head_down_policy,null);
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

test("v2 keeps uncertain eye probabilities, independent geometry and reason codes across repeated normalization", () => {
  const raw = { ...signal, schema_version: "eye-mouth-v2", eyes_available: true, eye_state: "UNKNOWN",
    eye_sleepy_probability: .51, eye_confidence: .51, mouth_confidence: .8, ear_available: true,
    eye_quality: "VALID", mouth_quality: "VALID", decision_reason: "RF_NEGATIVE",
    eye_closure_state: "DISABLED", sample_age_ms: 25 };
  const once = normalizeAiSignals(raw);
  assert.deepEqual(normalizeAiSignals(once), once);
  assert.equal(once.eye_sleepy_probability, .51);
  assert.equal(once.eye_state, "UNKNOWN");
  assert.equal(once.ear_available, true);
  assert.equal(once.decision_reason, "RF_NEGATIVE");
  const current = normalizeTelemetry({ device_id: 5, ear: .31, face_detected: true, driver_state: "ATTENTIVE", ai_signals: raw });
  assert.equal(current.ear, .31);
  assert.equal(current.driver_state, "ATTENTIVE");
  const missing = normalizeAiSignals({ ...raw, eye_quality: "NO_FACE" });
  assert.equal(missing.eyes_available, false);
  assert.equal(missing.eye_sleepy_probability, null);
  assert.equal(missing.ear_available, false);
  const outside = normalizeAiSignals({ ...raw, mouth_available: false, mouth_quality: "NO_CROP",
    mouth_crop_reason: "OUTSIDE_FRAME", mar: .8, yawn_probability: .9 });
  assert.deepEqual(normalizeAiSignals(outside), outside);
  assert.equal(outside.mouth_crop_reason, "OUTSIDE_FRAME");
  assert.equal(outside.yawn_probability, null);
  assert.equal(outside.mar, null);
});
