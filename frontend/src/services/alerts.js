import { apiRequest } from "./api.js";

function token() {
  const value = localStorage.getItem("access_token");
  if (!value) throw Object.assign(new Error("Bạn cần đăng nhập để xem cảnh báo."), { status: 401 });
  return value;
}

export function alertId(value) {
  const id = value?.alert_id;
  if (typeof id === "number" && Number.isSafeInteger(id) && id > 0) return String(id);
  if (typeof id === "string" && id.trim()) return id.trim();
  throw new Error("BE trả cảnh báo thiếu alert_id hợp lệ.");
}

export function normalizeAlert(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("BE trả cảnh báo không đúng định dạng.");
  }
  return { ...value, alert_id: alertId(value) };
}

export function mergeAlerts(current, incoming) {
  const byId = new Map(current.map(alert => [alertId(alert), alert]));
  for (const alert of incoming) {
    const normalized = normalizeAlert(alert);
    byId.set(normalized.alert_id, { ...byId.get(normalized.alert_id), ...normalized });
  }
  return [...byId.values()];
}

export async function getAlerts({ signal } = {}) {
  const result = await apiRequest("/alerts", { token: token(), signal });
  if (!Array.isArray(result)) throw new Error("BE trả lịch sử cảnh báo không đúng định dạng.");
  return mergeAlerts([], result);
}

export async function acknowledgeAlert(id, { signal } = {}) {
  const value = typeof id === "number" ? String(id) : id;
  if (typeof value !== "string" || !value.trim()) throw new Error("Mã cảnh báo không hợp lệ.");
  const result = await apiRequest(`/alerts/${encodeURIComponent(value.trim())}/acknowledge`, {
    method: "POST", token: token(), signal,
  });
  if (result == null || typeof result !== "object" || !Object.hasOwn(result, "alert_id")) {
    return null;
  }
  const alert = normalizeAlert(result);
  if (alert.alert_id !== value.trim()) throw new Error("BE trả kết quả của cảnh báo khác.");
  return alert;
}

export function isAlertAcknowledged(alert) {
  return Boolean(alert?.acknowledged_at) || alert?.acknowledged === true ||
    alert?.status === "ACKNOWLEDGED";
}

export function canAcknowledgeAlert(alert) {
  if (isAlertAcknowledged(alert)) return false;
  return alert.acknowledged === false || ["NEW", "OPEN", "UNACKNOWLEDGED"].includes(alert.status);
}
