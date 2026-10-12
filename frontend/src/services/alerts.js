import { authenticatedRequest } from "./api.js";
import { mergeAlerts, normalizeAlert } from "./alertModel.js";
export { alertId, normalizeAlert, mergeAlerts, isAlertAcknowledged, canAcknowledgeAlert } from "./alertModel.js";

export async function getAlerts({ signal } = {}) {
  const result = await authenticatedRequest("/alerts", { missingMessage: "Bạn cần đăng nhập để xem cảnh báo.", signal });
  if (!Array.isArray(result)) throw new Error("BE trả lịch sử cảnh báo không đúng định dạng.");
  return mergeAlerts([], result);
}

export async function acknowledgeAlert(id, { signal } = {}) {
  const value = typeof id === "number" ? String(id) : id;
  if (typeof value !== "string" || !value.trim()) throw new Error("Mã cảnh báo không hợp lệ.");
  const result = await authenticatedRequest(`/alerts/${encodeURIComponent(value.trim())}/acknowledge`, {
    method: "POST", missingMessage: "Bạn cần đăng nhập để xem cảnh báo.", signal,
  });
  if (result == null || typeof result !== "object" || !Object.hasOwn(result, "alert_id")) {
    return null;
  }
  const alert = normalizeAlert(result);
  if (alert.alert_id !== value.trim()) throw new Error("BE trả kết quả của cảnh báo khác.");
  return alert;
}
