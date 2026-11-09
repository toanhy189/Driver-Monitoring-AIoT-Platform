import { authenticatedRequest } from "./api.js";
import { ruleRequest } from "./ruleModel.js";
export { ruleRequest, RULE_POLICY_VERSION, ruleBlockerLabel } from "./ruleModel.js";

function path(id) {
  if (!Number.isSafeInteger(id) || id <= 0) throw new Error("ID camera không hợp lệ.");
  return `/devices/${id}/rule`;
}

function validateRule(result, id) {
  if (!result || result.source_device_id !== id || typeof result.enabled !== "boolean" ||
      typeof result.engine_enabled !== "boolean" || !Array.isArray(result.targets) ||
      !Array.isArray(result.readiness?.blockers) ||
      (result.updated_at !== null && typeof result.updated_at !== "string") ||
      (result.target_device_id !== null && (!Number.isSafeInteger(result.target_device_id) || result.target_device_id <= 0))) {
    throw new Error("Máy chủ chưa trả thông tin liên kết hợp lệ. Hãy cập nhật Backend và tải lại.");
  }
  return result;
}

export async function getRule(id, { signal } = {}) {
  return validateRule(await authenticatedRequest(path(id), { signal }), id);
}

export async function saveRule(id, snapshot, draft, { signal } = {}) {
  return validateRule(await authenticatedRequest(path(id), {
    method: "PUT", body: ruleRequest(snapshot, draft), signal,
  }), id);
}
