import { authenticatedRequest } from "./api.js";
import { normalizeTelemetry } from "./telemetry.js";

export async function getLatestTelemetry(deviceId, { signal } = {}) {
  if (!Number.isSafeInteger(deviceId) || deviceId <= 0) throw new Error("ID thiết bị không hợp lệ.");
  const response = await authenticatedRequest(`/${deviceId}/telemetry`, { missingMessage: "Bạn cần đăng nhập để xem số đo.", signal });
  if (response === null) return null;
  const telemetry = normalizeTelemetry(response);
  if (telemetry.device_id !== deviceId) throw new Error("BE trả số đo của thiết bị khác.");
  return telemetry;
}
