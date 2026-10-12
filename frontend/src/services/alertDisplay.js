import { isAlertAcknowledged } from "./alertModel.js";

const ALERT_TYPES = {
  DISTRACTION: "Mất tập trung",
  FACE_LOST: "Không thấy khuôn mặt",
  DROWSINESS: "Buồn ngủ",
  DROWSINESS_WARNING: "Cảnh báo buồn ngủ",
  DROWSY_THRESHOLD_REACHED: "Buồn ngủ vượt ngưỡng",
  HEAD_POSE: "Tư thế đầu bất thường",
  EYE_CLOSED: "Nhắm mắt",
  FATIGUE: "Mệt mỏi",
  SLEEP_DETECTED: "Phát hiện ngủ gật",
};

const ALERT_STATUSES = {
  NEW: "Chưa xem",
  OPEN: "Đang mở",
  UNACKNOWLEDGED: "Chưa xem",
  ACKNOWLEDGED: "Đã xem",
  RESOLVED: "Đã xử lý",
  CLOSED: "Đã đóng",
};

export function alertTypeLabel(value) {
  if (typeof value !== "string" || !value.trim()) return "Chưa xác định";
  return ALERT_TYPES[value.trim().toUpperCase()] ?? "Cảnh báo khác";
}

export function alertStatusLabel(alert) {
  const status = typeof alert?.status === "string" ? alert.status.trim().toUpperCase() : null;
  if (status === "RESOLVED" || status === "CLOSED") return ALERT_STATUSES[status];
  if (isAlertAcknowledged(alert)) return "Đã xem";
  if (!status) return "Chưa xác định";
  return ALERT_STATUSES[status] ?? "Chưa xác định";
}
