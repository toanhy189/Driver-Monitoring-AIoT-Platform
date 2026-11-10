const MOUTH = ["NORMAL", "YAWN", "TALKING_LAUGHING", "UNKNOWN"];
const EYES = ["NORMAL", "SLEEPY", "UNKNOWN"];
const CROP_REASONS = ["VALID", "NO_FACE", "INVALID_GEOMETRY", "SMALL_REGION", "OUTSIDE_FRAME", "EMPTY_REGION", "BLANK"];
const score = value => Number.isFinite(value) && value >= 0 && value <= 1 ? value : null;

export function normalizeAiSignals(data) {
  if (!data || typeof data !== "object" || Array.isArray(data) || !["eye-mouth-v1", "eye-mouth-v2"].includes(data.schema_version)) return null;
  const v2 = data.schema_version === "eye-mouth-v2";
  const eyes = data.eyes_available === true && (!v2 || data.eye_quality === "VALID");
  const mouth = data.mouth_available === true && (!v2 || data.mouth_quality === "VALID");
  const result = {
    schema_version: data.schema_version,
    mar: (mouth || v2 && data.mouth_quality === "VALID") && Number.isFinite(data.mar) && data.mar >= 0 && data.mar <= 2 ? data.mar : null,
    eye_sleepy_probability: eyes ? score(data.eye_sleepy_probability) : null,
    yawn_probability: mouth ? score(data.yawn_probability) : null,
    fusion_score: score(data.fusion_score),
    mouth_state: mouth && MOUTH.includes(data.mouth_state) ? data.mouth_state : "UNKNOWN",
    eye_state: eyes && EYES.includes(data.eye_state) ? data.eye_state : "UNKNOWN",
    eyes_available: eyes,
    mouth_available: mouth,
    experimental: data.experimental !== false,
  };
  if (v2) Object.assign(result, {
    ear_available: data.ear_available === true && data.eye_quality === "VALID",
    eye_confidence: score(data.eye_confidence), mouth_confidence: score(data.mouth_confidence),
    eye_quality: Object.hasOwn(QUALITY_LABELS, data.eye_quality) ? data.eye_quality : "NO_CROP",
    mouth_quality: Object.hasOwn(QUALITY_LABELS, data.mouth_quality) ? data.mouth_quality : "NO_CROP",
    eye_crop_reason: CROP_REASONS.includes(data.eye_crop_reason) ? data.eye_crop_reason : null,
    mouth_crop_reason: CROP_REASONS.includes(data.mouth_crop_reason) ? data.mouth_crop_reason : null,
    decision_reason: Object.hasOwn(DECISION_LABELS, data.decision_reason) ? data.decision_reason : "INSUFFICIENT_SUPPORT",
    eye_closure_state: Object.hasOwn(CLOSURE_LABELS, data.eye_closure_state) ? data.eye_closure_state : "UNAVAILABLE",
    calibration_id: typeof data.calibration_id === "string" && /^[0-9a-f]{64}$/.test(data.calibration_id) ? data.calibration_id : null,
    sample_age_ms: Number.isFinite(data.sample_age_ms) && data.sample_age_ms >= 0 && data.sample_age_ms <= 200.001 ? data.sample_age_ms : null,
    head_motion: normalizeHeadMotion(data.head_motion),
    head_eye_fusion: normalizeHeadEyeFusion(data.head_eye_fusion),
    head_down_policy: normalizeHeadDownPolicy(data.head_down_policy),
  });
  if (result.head_motion?.eye_closure_supported && result.eye_closure_state !== "CLOSED_RISK") result.head_motion = null;
  if (result.head_eye_fusion?.state !== "UNAVAILABLE" && result.head_eye_fusion && (!result.ear_available
    || !result.calibration_id || !result.head_motion?.calibrated || !result.head_motion?.available
    || ["UNAVAILABLE", "CALIBRATING", "REACQUIRING", "OUT_OF_RANGE"].includes(result.head_motion.state))) result.head_eye_fusion = null;
  if (result.head_down_policy && !["UNAVAILABLE","CALIBRATING"].includes(result.head_down_policy.state)
    && (!result.head_motion?.available || !result.head_motion?.calibrated || result.head_motion.state === "OUT_OF_RANGE")) result.head_down_policy=null;
  return result;
}

const QUALITY_LABELS = { VALID: "Qua kiểm tra ảnh kỹ thuật", NO_CROP: "Không lấy được vùng ảnh", NO_FACE: "Không thấy khuôn mặt",
  BLANK: "Vùng ảnh thiếu chi tiết", LOW_CONTRAST: "Độ tương phản thấp", SATURATED: "Ảnh quá tối hoặc bão hòa" };
export const qualityLabel = reason => QUALITY_LABELS[reason] || "Chưa xác định";

const DECISION_LABELS = { WARMUP: "Đang tích lũy dữ liệu", INSUFFICIENT_COVERAGE: "Chưa đủ thời gian quan sát hợp lệ",
    NO_FACE: "Không thấy khuôn mặt", FRAME_GAP: "Quan sát bị gián đoạn", INFERENCE_FAILED: "Lỗi suy luận AI",
    EYE_CLOSURE_RISK: "Nhắm mắt kéo dài theo hiệu chuẩn", RF_POSITIVE: "Model kết hợp phát hiện nguy cơ",
    RF_NEGATIVE: "Model kết hợp chưa phát hiện nguy cơ", HEAD_DEVIATION: "Đầu lệch hướng kéo dài",
    HEAD_CALIBRATING: "Đang hiệu chuẩn hướng đầu", HEAD_UNAVAILABLE: "Chưa đo được hướng đầu",
    INSUFFICIENT_SUPPORT: "Chưa đủ tín hiệu để kết luận" };
DECISION_LABELS.HEAD_EYE_CLOSURE_RISK = "Nhắm mắt kéo dài kèm cúi hoặc gật đầu theo hiệu chuẩn";
DECISION_LABELS.HEAD_DOWN_RISK = "Cúi đầu kéo dài theo quy tắc cảnh báo";
export const decisionReasonLabel = reason => DECISION_LABELS[reason] || "Chưa xác định";

const CLOSURE_LABELS = { DISABLED: "Chưa bật profile hiệu chuẩn", UNAVAILABLE: "Chưa đo được mắt ở tư thế phù hợp",
    OPEN: "Đang mở mắt", CLOSING: "Đang đếm thời gian nhắm", CLOSED_RISK: "Nhắm mắt kéo dài",
    RECOVERING: "Đang xác nhận mở mắt lại" };
export const closureLabel = state => CLOSURE_LABELS[state] || "Chưa xác định";

export function mouthStateLabel(state) {
  return { NORMAL: "Bình thường", YAWN: "Ngáp", TALKING_LAUGHING: "Nói / cười" }[state] || "Chưa xác định";
}

export function eyeStateLabel(state) {
  return { NORMAL: "Bình thường", SLEEPY: "Biểu hiện mắt buồn ngủ" }[state] || "Chưa xác định";
}

const HEAD_STATES = { UNAVAILABLE: "Chưa đo được chuyển động đầu", CALIBRATING: "Đang lấy mốc nhìn thẳng",
  REACQUIRING: "Đang xác nhận nhìn thẳng sau gián đoạn",
  OUT_OF_RANGE: "Tư thế vượt phạm vi theo dõi gật đầu", NEUTRAL: "Đầu ở gần mốc nhìn thẳng",
  MOVING: "Đầu đang di chuyển", LOWERED: "Đầu đang hạ thấp", NOD_DETECTED: "Ghi nhận một chu kỳ gật đầu",
  REPEATED_NODS: "Ghi nhận gật đầu lặp lại" };
export const headMotionLabel = state => HEAD_STATES[state] || "Chưa xác định";

export function normalizeHeadMotion(data) {
  if (!data || data.version !== "head-motion-v1" || data.mode !== "OBSERVE_ONLY" || !Object.hasOwn(HEAD_STATES, data.state)
    || typeof data.available !== "boolean" || typeof data.calibrated !== "boolean"
    || !Number.isInteger(data.nod_count) || data.nod_count < 0 || data.nod_count > 100
    || typeof data.repeated_nods !== "boolean" || typeof data.eye_closure_supported !== "boolean"
    || data.available !== (data.state !== "UNAVAILABLE") || data.repeated_nods !== (data.nod_count >= 2)) return null;
  const angles = [data.pitch_deg, data.yaw_deg, data.roll_deg];
  if (["UNAVAILABLE", "CALIBRATING"].includes(data.state)) {
    if (angles.some(v => v != null) || data.nod_count || data.state === "CALIBRATING" && data.calibrated) return null;
  } else if (!data.calibrated || angles.some(v => !Number.isFinite(v) || Math.abs(v) > 180)) return null;
  if (["OUT_OF_RANGE", "REACQUIRING"].includes(data.state) && data.nod_count || data.state === "REPEATED_NODS" && !data.repeated_nods
    || data.eye_closure_supported && !data.repeated_nods) return null;
  return { version: data.version, mode: data.mode, available: data.available, calibrated: data.calibrated, state: data.state,
    pitch_deg: data.pitch_deg ?? null, yaw_deg: data.yaw_deg ?? null, roll_deg: data.roll_deg ?? null,
    nod_count: data.nod_count, repeated_nods: data.repeated_nods, eye_closure_supported: data.eye_closure_supported };
}

export function normalizeHeadEyeFusion(data) {
  if (!data || data.version !== "pose-calibrated-head-eye-v1" || !["PRIVATE_PREVIEW", "ENABLED"].includes(data.mode)
    || !["UNAVAILABLE", "OPEN", "CLOSING", "CLOSED_RISK", "RECOVERING"].includes(data.state)
    || typeof data.risk_candidate !== "boolean" || !/^[0-9a-f]{64}$/.test(data.profile_sha256 || "")) return null;
  if (data.state === "UNAVAILABLE" ? data.ear_threshold !== null : !Number.isFinite(data.ear_threshold)
      || data.ear_threshold <= 0 || data.ear_threshold >= .8) return null;
  if (data.risk_candidate && !["CLOSED_RISK", "RECOVERING"].includes(data.state)) return null;
  return { version: data.version, mode: data.mode, state: data.state, ear_threshold: data.ear_threshold,
    risk_candidate: data.risk_candidate, profile_sha256: data.profile_sha256 };
}

const POSTURE_STATES={UNAVAILABLE:"Chưa đo được tư thế",CALIBRATING:"Nhìn thẳng để lấy mốc",NORMAL:"Đầu ở gần vị trí nhìn thẳng",
  LOWERED:"Đang đếm thời gian cúi đầu",DOWN_RISK:"Cúi đầu kéo dài",RECOVERING:"Đang xác nhận ngẩng đầu lại"};
export const headDownLabel=state=>POSTURE_STATES[state] || "Chưa xác định";
export function normalizeHeadDownPolicy(data) {
  if (!data || data.version!=="sustained-head-down-v1" || !Object.hasOwn(POSTURE_STATES,data.state)
    || typeof data.risk_candidate!=="boolean" || !Number.isFinite(data.observed_down_seconds) || data.observed_down_seconds<0
    || data.enter_pitch_deg!==12 || data.min_seconds!==3
    || data.risk_candidate!==["DOWN_RISK","RECOVERING"].includes(data.state)
    || data.risk_candidate && data.observed_down_seconds<3
    || ["UNAVAILABLE","CALIBRATING","NORMAL"].includes(data.state) && data.observed_down_seconds!==0) return null;
  return {version:data.version,state:data.state,risk_candidate:data.risk_candidate,observed_down_seconds:data.observed_down_seconds,
    enter_pitch_deg:data.enter_pitch_deg,min_seconds:data.min_seconds};
}
