import { authenticatedRequest } from "./api.js";
export { applyDeviceUpdate, markDevicesStale } from "./deviceModel.js";

function devicePath(id) {
  if (!Number.isSafeInteger(id) || id <= 0) {
    throw new Error("ID thiết bị không hợp lệ.");
  }
  return `/devices/${id}`;
}

export async function getDevices({ signal } = {}) {
  const devices = await authenticatedRequest("/devices", { missingMessage: "Bạn cần đăng nhập để xem thiết bị.", signal });
  if (!Array.isArray(devices) || devices.some(device =>
    !device || !Number.isSafeInteger(device.id) || device.id <= 0 ||
    typeof device.device_code !== "string" || device.device_code.trim() === ""
  )) {
    throw new Error("Danh sách thiết bị từ máy chủ không đúng định dạng.");
  }

  return devices.map(device => ({ ...device, isStale: false }));
}

// API chi tiết thiết bị dùng cùng ID số như danh sách.
export async function getDeviceDetail(id, { signal } = {}) {
  const device = await authenticatedRequest(devicePath(id), { missingMessage: "Bạn cần đăng nhập để xem thiết bị.", signal });
  if (!device || device.id !== id || typeof device.device_code !== "string" ||
      !device.device_code.trim()) {
    throw new Error("Chi tiết thiết bị từ máy chủ không đúng định dạng.");
  }
  return device;
}

export async function registerDevice({ device_code, name, model }, { signal } = {}) {
  const normalizedCode = device_code.trim();
  const result = await authenticatedRequest("/devices", {
    method: "POST",
    missingMessage: "Bạn cần đăng nhập để xem thiết bị.",
    body: { device_code: normalizedCode, name: name.trim(), model: model.trim() },
    signal,
  });
  if (!result?.device || !Number.isSafeInteger(result.device.id) ||
      result.device.id <= 0 || result.device.device_code !== normalizedCode) {
    throw new Error("BE chưa trả đúng thiết bị vừa đăng ký.");
  }
  return result;
}

const LIFECYCLE_ACTIONS = ["provision", "activate", "maintenance", "decommission"];

export async function runDeviceAction(id, action, { signal } = {}) {
  if (!LIFECYCLE_ACTIONS.includes(action)) {
    throw new Error("Thao tác thiết bị không hợp lệ.");
  }
  const result = await authenticatedRequest(`${devicePath(id)}/${action}`, {
    method: "POST",
    missingMessage: "Bạn cần đăng nhập để xem thiết bị.",
    signal,
  });
  if (!result || result.id !== id || typeof result.device_code !== "string" ||
      typeof result.lifecycle_state !== "string") {
    throw new Error("BE chưa trả trạng thái hợp lệ của thiết bị vừa thao tác.");
  }
  return result;
}
