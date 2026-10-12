// A realtime event updates only a device already present in the authorized list.
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

export function deviceActionBlockReason(device, action) {
  const state = device?.lifecycle_state;
  if (!state) return "Chưa có trạng thái quản lý của thiết bị.";
  if (state === "DECOMMISSIONED") return "Thiết bị đã ngừng sử dụng.";
  if (action === "provision" && state !== "REGISTERED") {
    return "Chỉ cấp thông tin kết nối cho thiết bị đã đăng ký.";
  }
  if (action === "activate" && !["PROVISIONED", "MAINTENANCE"].includes(state)) {
    return "Chỉ kích hoạt thiết bị đã cấp kết nối hoặc đang bảo trì.";
  }
  if (action === "maintenance" && state !== "ACTIVE") {
    return "Chỉ chuyển thiết bị đang hoạt động sang bảo trì.";
  }
  return "";
}
