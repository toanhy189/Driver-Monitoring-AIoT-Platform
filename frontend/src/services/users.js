import { authenticatedRequest } from "./api.js";

export async function getUsers({ signal } = {}) {
  const users = await authenticatedRequest("/users", { signal });
  if (!Array.isArray(users) || users.some(user =>
    !user || !Number.isSafeInteger(user.id) || user.id <= 0 ||
    typeof user.username !== "string" || typeof user.role !== "string"
  )) {
    throw new Error("Danh sách người dùng từ máy chủ không đúng định dạng.");
  }
  return users;
}

export async function getUserDevices(userId, { signal } = {}) {
  if (!Number.isSafeInteger(userId) || userId <= 0) {
    throw new Error("ID người dùng không hợp lệ.");
  }
  const devices = await authenticatedRequest(`/users/${userId}/devices`, { signal });
  if (!Array.isArray(devices) || devices.some(device =>
    !device || !Number.isSafeInteger(device.id) || device.id <= 0 ||
    typeof device.device_code !== "string" || !device.device_code.trim()
  )) {
    throw new Error("Danh sách thiết bị của người dùng từ máy chủ không đúng định dạng.");
  }
  return devices;
}
