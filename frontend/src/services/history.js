import { authenticatedRequest } from "./api.js";

export function getDeviceHistory(deviceId, kind, { from, to, modelVersion, limit = 100, offset = 0, signal } = {}) {
  if (!Number.isSafeInteger(deviceId) || deviceId <= 0) throw new Error("ID thiết bị không hợp lệ.");
  const endpoints = { telemetry: "telemetry/history", commands: "history", timeline: "timeline", metrics: "metrics" };
  if (!endpoints[kind]) throw new Error("Loại lịch sử không hợp lệ.");
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (from) query.set("from", new Date(from).toISOString());
  if (to) query.set("to", new Date(to).toISOString());
  if (modelVersion?.trim()) query.set("model_version", modelVersion.trim());
  return authenticatedRequest(`/devices/${deviceId}/${endpoints[kind]}?${query}`, { signal });
}
