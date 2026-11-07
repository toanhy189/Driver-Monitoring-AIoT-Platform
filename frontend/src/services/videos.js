import { authenticatedBlobRequest, authenticatedRequest } from "./api.js";
export function getVideoForMessage(deviceId, messageId, { signal } = {}) {
  if (!Number.isSafeInteger(deviceId) || deviceId <= 0) throw new Error("ID thiết bị không hợp lệ.");
  if (typeof messageId !== "string" || messageId.trim() === "" || messageId.length > 80) {
    throw new Error("Message ID không hợp lệ.");
  }
  const query = new URLSearchParams({ message_id: messageId, limit: "1" });
  return authenticatedRequest(`/devices/${deviceId}/videos?${query}`, { signal });
}

export function getVideoContent(videoId, { signal } = {}) {
  if (!Number.isSafeInteger(videoId) || videoId <= 0) throw new Error("ID video không hợp lệ.");
  return authenticatedBlobRequest(`/videos/${videoId}/content`, { signal });
}
