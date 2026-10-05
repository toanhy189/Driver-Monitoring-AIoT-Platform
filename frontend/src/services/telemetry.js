const DRIVER_STATES = ["ATTENTIVE", "DISTRACTED", "DROWSY"];

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

  return {
    device_id: data.device_id ?? null,
    device_code: data.device_code ?? null,
    ear: Number.isFinite(data.ear) ? data.ear : null,
    perclos: Number.isFinite(data.perclos) ? data.perclos : null,
    // Không tính trạng thái tài xế từ số đo hoặc giữ kết luận của tin trước.
    driver_state: DRIVER_STATES.includes(data.driver_state) ? data.driver_state : "UNKNOWN",
  };
}
