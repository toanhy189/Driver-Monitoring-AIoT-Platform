const MOUTH = ["NORMAL", "YAWN", "TALKING_LAUGHING", "UNKNOWN"];
const EYES = ["NORMAL", "SLEEPY", "UNKNOWN"];
const score = value => Number.isFinite(value) && value >= 0 && value <= 1 ? value : null;

export function normalizeAiSignals(data) {
  if (!data || typeof data !== "object" || Array.isArray(data) || data.schema_version !== "eye-mouth-v1") return null;
  const eyes = data.eyes_available === true;
  const mouth = data.mouth_available === true;
  return {
    schema_version: "eye-mouth-v1",
    mar: mouth && Number.isFinite(data.mar) && data.mar >= 0 && data.mar <= 2 ? data.mar : null,
    eye_sleepy_probability: eyes ? score(data.eye_sleepy_probability) : null,
    yawn_probability: mouth ? score(data.yawn_probability) : null,
    fusion_score: score(data.fusion_score),
    mouth_state: mouth && MOUTH.includes(data.mouth_state) ? data.mouth_state : "UNKNOWN",
    eye_state: eyes && EYES.includes(data.eye_state) ? data.eye_state : "UNKNOWN",
    eyes_available: eyes,
    mouth_available: mouth,
    experimental: data.experimental !== false,
  };
}

export function mouthStateLabel(state) {
  return { NORMAL: "Bình thường", YAWN: "Ngáp", TALKING_LAUGHING: "Nói / cười" }[state] || "Chưa xác định";
}

export function eyeStateLabel(state) {
  return { NORMAL: "Bình thường", SLEEPY: "Biểu hiện mắt buồn ngủ" }[state] || "Chưa xác định";
}
