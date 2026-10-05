const BACKEND_HOST = import.meta.env.VITE_BACKEND_HOST || "http://localhost:8000";
const API_STR = import.meta.env.VITE_API_STR || "/api";

export async function getDevices({ signal } = {}) {
  const token = localStorage.getItem("access_token");
  if (!token) throw new Error("Bạn cần đăng nhập để xem trạng thái thiết bị.");

  const response = await fetch(`${BACKEND_HOST}${API_STR}/devices`, {
    headers: { Authorization: `Bearer ${token}` },
    signal,
  });

  if (!response.ok) {
    if (response.status === 401) {
      throw new Error("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.");
    }
    throw new Error(`Không tải được trạng thái thiết bị (HTTP ${response.status}).`);
  }

  const devices = await response.json();
  if (!Array.isArray(devices) || devices.some(device =>
    !device || !Number.isSafeInteger(device.id) || device.id <= 0 ||
    typeof device.device_code !== "string" || device.device_code.trim() === ""
  )) {
    throw new Error("Danh sách thiết bị từ máy chủ không đúng định dạng.");
  }

  return devices.map(device => ({ ...device, isStale: false }));
}

// Chỉ cập nhật thiết bị đã được API trả về, không lấy online từ WebSocket.
export function applyDeviceUpdate(devices, update) {
  if (!update || typeof update !== "object" || !Object.hasOwn(update, "status")) {
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

    return {
      ...device,
      status: update.status,
      last_seen: Object.hasOwn(update, "last_seen") ? update.last_seen : device.last_seen,
      isStale: false,
    };
  });
}

export function markDevicesStale(devices) {
  return devices.map(device => ({ ...device, isStale: true }));
}
