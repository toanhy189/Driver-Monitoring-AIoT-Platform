import { apiRequest } from "./api.js";
import { hasPermission } from "./permissions.js";

// Hợp đồng tạm theo hướng dẫn FE tuần 2; TV2 cần chốt body và response thực tế.
export const TEST_ALERT_BODY = Object.freeze({
  action: "TEST_ALERT",
  buzzer_ms: 1000,
  vibration_ms: 1000,
  led_mode: "FLASH",
});

const MAX_DURATION_MS = 10000;

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
    buzzer_ms: integerInRange(value.buzzer_ms, "Thời lượng còi (ms)", 0, MAX_DURATION_MS),
    vibration_ms: integerInRange(value.vibration_ms, "Thời lượng rung (ms)", 0, MAX_DURATION_MS),
    led_mode: value.led_mode,
  };
}

const FINAL_STATUSES = new Set(["FAILED", "TIMEOUT"]);

function token() {
  const value = localStorage.getItem("access_token");
  if (!value) throw Object.assign(new Error("Bạn cần đăng nhập để xem lệnh."), { status: 401 });
  return value;
}

function validDeviceId(id) {
  if (!Number.isSafeInteger(id) || id <= 0) throw new Error("ID thiết bị không hợp lệ.");
  return id;
}

function validRequestId(id) {
  if (typeof id !== "string" || !id.trim()) throw new Error("Mã lệnh không hợp lệ.");
  return id;
}

export function normalizeCommand(value) {
  if (!value || typeof value !== "object" || Array.isArray(value) ||
      typeof value.request_id !== "string" || !value.request_id.trim()) {
    throw new Error("BE trả lệnh thiếu request_id hợp lệ.");
  }
  return { ...value, request_id: value.request_id.trim() };
}

export async function sendTestAlert(deviceId, { parameters = TEST_ALERT_BODY, signal } = {}) {
  const response = await apiRequest(`/devices/${validDeviceId(deviceId)}/commands`, {
    method: "POST", body: validateTestAlertParameters(parameters), token: token(), signal,
  });
  return normalizeCommand(response);
}

export async function getCommands({ deviceId, signal } = {}) {
  const query = deviceId == null ? "" : `?device_id=${validDeviceId(deviceId)}`;
  const response = await apiRequest(`/commands${query}`, { token: token(), signal });
  if (!Array.isArray(response)) throw new Error("BE trả lịch sử lệnh không đúng định dạng.");
  return response.map(normalizeCommand);
}

export async function getCommand(requestId, { signal } = {}) {
  const id = validRequestId(requestId);
  const response = await apiRequest(`/commands/${encodeURIComponent(id)}`, { token: token(), signal });
  const command = normalizeCommand(response);
  if (command.request_id !== id) throw new Error("BE trả kết quả của lệnh khác.");
  return command;
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
  if (commandFinished(command)) return 3;
  if (command?.status === "ACKNOWLEDGED") return 2;
  if (command?.status === "SENT") return 1;
  if (command?.status === "PENDING") return 0;
  return -1;
}

// ACK cuối có thể về trước HTTP response SENT: không ghi lùi kết quả đã hoàn tất.
export function keepNewerCommand(current, incoming) {
  if (!current) return incoming;
  if (!incoming || current.request_id !== incoming.request_id) return current;
  if (current.device_id != null && incoming.device_id != null &&
      current.device_id !== incoming.device_id) return current;
  if (current.device_code != null && incoming.device_code != null &&
      current.device_code !== incoming.device_code) return current;
  if (progressRank(current) > progressRank(incoming)) return current;
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
  if (!device.last_seen || Number.isNaN(new Date(device.last_seen).getTime()) || device.isStale) {
    return "Chưa xác nhận được hoạt động gần đây của thiết bị.";
  }
  if (isSubmitting) return "Đang gửi yêu cầu, vui lòng chờ.";
  return "";
}
