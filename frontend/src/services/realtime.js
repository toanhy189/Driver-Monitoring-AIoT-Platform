export const REALTIME_TYPES = new Set([
  "telemetry.updated", "device.updated", "command.updated", "alert.created", "config.updated",
]);

export function retryDelay(attempt) {
  return Math.min(1000 * 2 ** Math.min(attempt, 5), 30000);
}

export function parseRealtimeMessage(message) {
  if (!message || typeof message !== "object" || Array.isArray(message)) return null;
  if (message.type == null) return { type: "telemetry.updated", data: message };
  if (!REALTIME_TYPES.has(message.type) || !message.data ||
      typeof message.data !== "object" || Array.isArray(message.data)) return null;
  return { type: message.type, data: message.data };
}

export function matchesDevice(data, deviceId, deviceCode) {
  if (!data || (data.device_id == null && data.id == null && data.device_code == null)) return false;
  const id = data.device_id ?? data.id;
  if (id != null && id !== deviceId) return false;
  if (data.device_code != null && data.device_code !== deviceCode) return false;
  return true;
}
