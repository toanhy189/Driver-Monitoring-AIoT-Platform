import { hasPermission } from "./permissions.js";

// Keep the existing firmware command body. The server expands one web request
// into LED, buzzer and motor dispatches and owns their ACK state.
export const TEST_ALERT_BODY = Object.freeze({
  action: "TEST_ALERT",
  buzzer_ms: 1000,
  vibration_ms: 1000,
  led_mode: "FLASH",
});

const MAX_DURATION_MS = 10000;
const FINAL_STATUSES = new Set(["FAILED", "TIMEOUT"]);

function integerInRange(value, label, minimum, maximum) {
  const text = typeof value === "number" ? String(value) : value;
  if (typeof text !== "string" || !/^\d+$/.test(text.trim())) {
    throw new Error(`${label} phải là số nguyên từ ${minimum} đến ${maximum}.`);
  }
  const number = Number(text.trim());
  if (!Number.isSafeInteger(number) || number < minimum || number > maximum) {
    throw new Error(`${label} phải là số nguyên từ ${minimum} đến ${maximum}.`);
  }
  return number;
}

export function validateTestAlertParameters(value) {
  if (!value || typeof value !== "object" || Array.isArray(value) ||
      (value.action != null && value.action !== "TEST_ALERT")) {
    throw new Error("Thông số lệnh kiểm tra không hợp lệ.");
  }
  if (!["ON", "FLASH"].includes(value.led_mode)) {
    throw new Error("Chế độ LED phải là sáng liên tục hoặc nhấp nháy.");
  }
  return {
    action: "TEST_ALERT",
    buzzer_ms: integerInRange(value.buzzer_ms, "Thời lượng còi (ms)", 1, MAX_DURATION_MS),
    vibration_ms: integerInRange(value.vibration_ms, "Thời lượng rung (ms)", 1, MAX_DURATION_MS),
    led_mode: value.led_mode,
  };
}

export function normalizeCommand(value) {
  if (!value || typeof value !== "object" || Array.isArray(value) ||
      typeof value.request_id !== "string" || !value.request_id.trim()) {
    throw new Error("BE trả lệnh thiếu request_id hợp lệ.");
  }
  return { ...value, request_id: value.request_id.trim() };
}

export function commandBelongsToDevice(command, deviceId, deviceCode, { requireIdentity = false } = {}) {
  if (requireIdentity && command.device_id == null && command.device_code == null) return false;
  if (command.device_id != null && command.device_id !== deviceId &&
      command.device_id !== deviceCode) return false;
  if (command.device_code != null && command.device_code !== deviceCode) return false;
  return true;
}

export function commandFinished(command) {
  if (!command) return false;
  if (FINAL_STATUSES.has(command.status)) return true;
  return command.status === "ACKNOWLEDGED" &&
    ["COMPLETED", "FAILED"].includes(command.ack_status);
}

function progressRank(command) {
  if (command?.status === "TIMEOUT") return 3;
  if (commandFinished(command)) return 4;
  if (command?.status === "ACKNOWLEDGED") return 2;
  if (command?.status === "SENT") return 1;
  if (command?.status === "PENDING") return 0;
  return -1;
}

// An ACK may arrive before the HTTP response or a polling snapshot. Once a
// terminal result is displayed, a late snapshot must not replace it.
export function keepNewerCommand(current, incoming) {
  if (!current) return incoming;
  if (!incoming || current.request_id !== incoming.request_id) return current;
  if (current.device_id != null && incoming.device_id != null &&
      current.device_id !== incoming.device_id) return current;
  if (current.device_code != null && incoming.device_code != null &&
      current.device_code !== incoming.device_code) return current;
  if (commandFinished(current) && commandFinished(incoming) &&
      current.status !== "TIMEOUT") return current;
  if (progressRank(current) > progressRank(incoming)) return current;
  if (current.status === "TIMEOUT" && incoming.status === "TIMEOUT") return current;
  return { ...current, ...incoming };
}

export function collapseCommands(commands) {
  const byRequestId = new Map();
  for (const command of commands) {
    const current = byRequestId.get(command.request_id);
    if (current && current.device_id != null && command.device_id != null &&
        current.device_id !== command.device_id) {
      throw new Error("BE trả cùng request_id cho hai thiết bị khác nhau.");
    }
    byRequestId.set(command.request_id, keepNewerCommand(current, command));
  }
  return [...byRequestId.values()];
}

export function testAlertBlockReason({ user, device, isSubmitting = false }) {
  if (!hasPermission(user?.role, "command:send")) return "Bạn chỉ có quyền xem, không được gửi lệnh.";
  if (!device) return "Chưa có thông tin thiết bị.";
  const type = device.type ?? device.device_type;
  if (!type) return "BE chưa cung cấp loại thiết bị; chưa thể xác nhận đây là thiết bị cảnh báo.";
  if (type !== "ALERT_NODE") return "Chỉ có thể kiểm tra cảnh báo trên thiết bị cảnh báo.";
  if (!device.lifecycle_state) return "BE chưa cung cấp trạng thái quản lý của thiết bị.";
  if (device.lifecycle_state === "MAINTENANCE") return "Thiết bị đang bảo trì.";
  if (device.lifecycle_state !== "ACTIVE") return "Thiết bị chưa ở trạng thái ACTIVE.";
  if (device.status !== "ONLINE") return device.status === "OFFLINE" ?
    "Thiết bị đang offline." : "Chưa xác định thiết bị có online hay không.";
  const lastSeen = Date.parse(device.last_seen);
  if (!Number.isFinite(lastSeen) || device.isStale ||
      Date.now() - lastSeen > 90000 || lastSeen - Date.now() > 5000) {
    return "Chưa xác nhận được hoạt động gần đây của thiết bị.";
  }
  if (isSubmitting) return "Đang gửi yêu cầu, vui lòng chờ.";
  return "";
}
