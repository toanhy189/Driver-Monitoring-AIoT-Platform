import { apiRequest } from "./api.js";

function requireToken() {
  const token = localStorage.getItem("access_token");
  if (!token) {
    throw Object.assign(new Error("Bạn cần đăng nhập để xem thiết bị."), { status: 401 });
  }
  return token;
}

function devicePath(id) {
  if (!Number.isSafeInteger(id) || id <= 0) {
    throw new Error("ID thiết bị không hợp lệ.");
  }
  return `/devices/${id}`;
}

export async function getDevices({ signal } = {}) {
  const devices = await apiRequest("/devices", { token: requireToken(), signal });
  if (!Array.isArray(devices) || devices.some(device =>
    !device || !Number.isSafeInteger(device.id) || device.id <= 0 ||
    typeof device.device_code !== "string" || device.device_code.trim() === ""
  )) {
    throw new Error("Danh sách thiết bị từ máy chủ không đúng định dạng.");
  }

  return devices.map(device => ({ ...device, isStale: false }));
}

// Các URL sau là hợp đồng tạm của FE; TV2 hiện chưa triển khai chúng.
export async function getDeviceDetail(id, { signal } = {}) {
  const device = await apiRequest(devicePath(id), { token: requireToken(), signal });
  if (!device || device.id !== id || typeof device.device_code !== "string" ||
      !device.device_code.trim()) {
    throw new Error("Chi tiết thiết bị từ máy chủ không đúng định dạng.");
  }
  return device;
}

export function registerDevice({ device_code, name, model }, { signal } = {}) {
  return apiRequest("/devices", {
    method: "POST",
    token: requireToken(),
    body: { device_code: device_code.trim(), name: name.trim(), model: model.trim() },
    signal,
  });
}

const LIFECYCLE_ACTIONS = ["provision", "activate", "maintenance", "decommission"];

export function runDeviceAction(id, action, { signal } = {}) {
  if (!LIFECYCLE_ACTIONS.includes(action)) {
    throw new Error("Thao tác thiết bị không hợp lệ.");
  }
  return apiRequest(`${devicePath(id)}/${action}`, {
    method: "POST",
    token: requireToken(),
    signal,
  });
}

// Chỉ sửa record đã có cùng ID/mã; tin WebSocket không tự thêm thiết bị mới.
export function applyDeviceUpdate(devices, update) {
  const fields = ["status", "last_seen", "lifecycle_state", "name", "model", "firmware_version"];
  if (!update || typeof update !== "object" ||
      !fields.some(field => Object.hasOwn(update, field))) {
    return devices;
  }
  const id = update.id ?? update.device_id;
  const code = update.device_code;
  if (id == null && code == null) return devices;
  if (id != null && (!Number.isSafeInteger(id) || id <= 0)) return devices;
  if (code != null && (typeof code !== "string" || code.trim() === "")) return devices;
  if (update.id != null && update.device_id != null && update.id !== update.device_id) {
    return devices;
  }

  return devices.map(device => {
    const matchesId = id == null || device.id === id;
    const matchesCode = code == null || device.device_code === code;
    if (!matchesId || !matchesCode) return device;

    const changes = Object.fromEntries(fields.filter(field => Object.hasOwn(update, field))
      .map(field => [field, update[field]]));
    return { ...device, ...changes, isStale: false };
  });
}

export function markDevicesStale(devices) {
  return devices.map(device => ({ ...device, isStale: true }));
}
