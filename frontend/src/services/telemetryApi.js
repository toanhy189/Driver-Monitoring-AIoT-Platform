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

export async function getTelemetryHistory(deviceId, { fromTime, toTime, limit = 100, signal } = {}) {
  if (!Number.isSafeInteger(deviceId) || deviceId <= 0) throw new Error("ID thiết bị không hợp lệ.");
  const params = new URLSearchParams();
  if (fromTime) params.append("from_time", fromTime);
  if (toTime) params.append("to_time", toTime);
  if (limit) params.append("limit", String(limit));
  const queryString = params.toString() ? `?${params.toString()}` : "";
  const response = await authenticatedRequest(`/${deviceId}/telemetry/history${queryString}`, {
    missingMessage: "Bạn cần đăng nhập để xem lịch sử số đo.",
    signal,
  });
  return response;
}
