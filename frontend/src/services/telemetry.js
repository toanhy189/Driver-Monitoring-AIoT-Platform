const DRIVER_STATES = ["ATTENTIVE", "DISTRACTED", "DROWSY"];

function validTimestamp(value) {
  return typeof value === "string" && Number.isFinite(Date.parse(value)) ? value : null;
}

// API dùng ID số; telemetry có thể chỉ có mã thiết bị theo tài liệu bàn giao.
export function normalizeTelemetry(data) {
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    throw new Error("Telemetry phải là một object JSON.");
  }
  if (data.device_id != null && (!Number.isSafeInteger(data.device_id) || data.device_id <= 0)) {
    throw new Error("Telemetry device_id phải là ID số nguyên dương, không phải mã thiết bị.");
  }
  if (data.device_code != null && (
    typeof data.device_code !== "string" || data.device_code.trim() === ""
  )) {
    throw new Error("Telemetry device_code phải là mã thiết bị dạng chuỗi.");
  }
  if (data.device_id == null && data.device_code == null) {
    throw new Error("Telemetry cần device_id số hoặc device_code để xác định nguồn số đo.");
  }

  const faceDetected = typeof data.face_detected === "boolean" ? data.face_detected : null;
  const result = {
    device_id: data.device_id ?? null,
    device_code: data.device_code ?? null,
    ear: Number.isFinite(data.ear) ? data.ear : null,
    perclos: Number.isFinite(data.perclos) ? data.perclos : null,
    // Không tính trạng thái tài xế từ số đo hoặc giữ kết luận của tin trước.
    driver_state: faceDetected === false ? "UNKNOWN" :
      DRIVER_STATES.includes(data.driver_state) ? data.driver_state : "UNKNOWN",
  };
  if (Object.hasOwn(data, "face_detected")) result.face_detected = faceDetected;
  for (const field of ["angle_x", "angle_y", "angle_z"]) {
    if (Object.hasOwn(data, field)) result[field] = Number.isFinite(data[field]) ? data[field] : null;
  }
  if (Object.hasOwn(data, "confidence")) {
    result.confidence = Number.isFinite(data.confidence) && data.confidence >= 0 &&
      data.confidence <= 1 ? data.confidence : null;
  }
  if (Object.hasOwn(data, "recorded_at") || Object.hasOwn(data, "timestamp")) {
    result.recorded_at = validTimestamp(data.recorded_at ?? data.timestamp);
  }
  return result;
}
