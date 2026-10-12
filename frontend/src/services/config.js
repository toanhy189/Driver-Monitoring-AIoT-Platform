import { authenticatedRequest } from "./api.js";
import { normalizeConfig, validateTimings } from "./configModel.js";

export {
  CONFIG_OUTPUTS, CONFIG_LEVELS, MAX_TIMING_MS, validateTimings,
  emptyDraft, draftFromTimings, timingsFromDraft, normalizeConfig, configStatus,
} from "./configModel.js";

function validDeviceId(value) {
  if (!Number.isSafeInteger(value) || value <= 0) throw new Error("ID thiết bị không hợp lệ.");
  return value;
}

export async function getDeviceConfig(deviceId, { signal } = {}) {
  const response = await authenticatedRequest(`/devices/${validDeviceId(deviceId)}/config`, {
    missingMessage: "Bạn cần đăng nhập để xem cấu hình.", signal,
  });
  return normalizeConfig(response);
}

export async function updateDeviceConfig(deviceId, timings, { signal } = {}) {
  const response = await authenticatedRequest(`/devices/${validDeviceId(deviceId)}/config`, {
    method: "PUT", body: { timings: validateTimings(timings) },
    missingMessage: "Bạn cần đăng nhập để xem cấu hình.", signal,
  });
  const configId = typeof response?.config_id === "string" ? response.config_id.trim() : "";
  if (!configId) throw new Error("BE chưa trả config_id; chưa thể theo dõi thiết bị đã áp dụng hay chưa.");
  return configId;
}
