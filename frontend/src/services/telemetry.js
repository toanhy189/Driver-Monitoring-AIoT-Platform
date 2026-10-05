const DRIVER_STATES = ["ATTENTIVE", "DISTRACTED", "DROWSY"];

// Hợp đồng FE: device_id là ID số trong DB; device_code là mã BE cung cấp.
export function normalizeTelemetry(data) {
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    throw new Error("Telemetry phải là một object JSON.");
  }
  if (!Number.isSafeInteger(data.device_id) || data.device_id <= 0) {
    throw new Error("Telemetry device_id phải là ID số nguyên dương, không phải mã thiết bị.");
  }
  if (data.device_code != null && (
    typeof data.device_code !== "string" || data.device_code.trim() === ""
  )) {
    throw new Error("Telemetry device_code phải là mã thiết bị dạng chuỗi.");
  }

  return {
    device_id: data.device_id,
    device_code: data.device_code ?? null,
    ear: Number.isFinite(data.ear) ? data.ear : null,
    perclos: Number.isFinite(data.perclos) ? data.perclos : null,
    // Không tính trạng thái tài xế từ số đo hoặc giữ kết luận của tin trước.
    driver_state: DRIVER_STATES.includes(data.driver_state) ? data.driver_state : "UNKNOWN",
  };
}
