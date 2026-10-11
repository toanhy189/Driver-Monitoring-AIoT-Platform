import { apiRequest } from "./api.js";
import { normalizeTelemetry } from "./telemetry.js";

export async function getLatestTelemetry(deviceId, { signal } = {}) {
  if (!Number.isSafeInteger(deviceId) || deviceId <= 0) throw new Error("ID thiết bị không hợp lệ.");
  const token = localStorage.getItem("access_token");
  if (!token) throw Object.assign(new Error("Bạn cần đăng nhập để xem số đo."), { status: 401 });
  const response = await apiRequest(`/${deviceId}/telemetry`, { token, signal });
  if (response === null) return null;
  const telemetry = normalizeTelemetry(response);
  if (telemetry.device_id !== deviceId) throw new Error("BE trả số đo của thiết bị khác.");
  return telemetry;
}
