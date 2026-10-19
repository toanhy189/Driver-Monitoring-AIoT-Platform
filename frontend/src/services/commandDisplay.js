export function commandStatus(command) {
  if (!command) return { label: "Chưa có lệnh", tone: "unknown" };
  if (command.status === "PENDING") return { label: "Đang chờ gửi", tone: "pending" };
  if (command.status === "SENT") return { label: "Đã gửi, chờ thiết bị phản hồi", tone: "pending" };
  if (command.status === "ACKNOWLEDGED") {
    if (command.ack_status === "COMPLETED") return { label: "Thiết bị đã hoàn tất", tone: "success" };
    if (command.ack_status === "FAILED") return { label: "Thiết bị báo thực hiện thất bại", tone: "error" };
    if (command.ack_status === "ACCEPTED") return { label: "Thiết bị đã nhận, đang thực hiện", tone: "pending" };
    return { label: "Đã nhận ACK, chờ kết quả cuối", tone: "pending" };
  }
  if (command.status === "FAILED") return { label: "Lệnh thất bại", tone: "error" };
  if (command.status === "TIMEOUT") return { label: "Hết thời gian chờ kết quả", tone: "error" };
  return { label: "Trạng thái chưa xác định", tone: "unknown" };
}

export function commandTime(value) {
  if (!value) return "Chưa cung cấp";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Chưa cung cấp" : date.toLocaleString("vi-VN");
}

export function commandValue(value) {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return "Chưa cung cấp";
}

const ACTION_LABELS = {
  AUTO_ALERT: "Cảnh báo tự động",
  TEST_ALERT: "Kiểm tra cảnh báo",
  CAMERA_CHECK: "Kiểm tra camera",
  BUZZER_ON: "Bật còi",
  BUZZER_OFF: "Tắt còi",
  VIBRATION_ON: "Bật motor rung",
  VIBRATION_OFF: "Tắt motor rung",
  LED_ON: "Bật đèn LED",
  LED_OFF: "Tắt đèn LED",
};

export function commandActionLabel(value) {
  if (typeof value !== "string" || !value.trim()) return "Chưa cung cấp";
  return ACTION_LABELS[value.trim().toUpperCase()] ?? value;
}

export function commandAckLabel(value) {
  if (typeof value !== "string" || !value.trim()) return "Chưa có phản hồi";
  return {
    ACCEPTED: "Thiết bị đã nhận",
    ACKNOWLEDGED: "Thiết bị đã nhận",
    STARTED: "Đang thực hiện",
    COMPLETED: "Đã hoàn tất",
    FAILED: "Thiết bị báo lỗi",
    INTERRUPTED: "Đã bị gián đoạn",
  }[value.trim().toUpperCase()] ?? "Chưa xác định";
}
