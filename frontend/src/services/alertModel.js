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

export function isAlertAcknowledged(alert) {
  return Boolean(alert?.acknowledged_at) || alert?.acknowledged === true ||
    alert?.status === "ACKNOWLEDGED";
}

export function canAcknowledgeAlert(alert) {
  if (isAlertAcknowledged(alert)) return false;
  return alert?.status === "NEW";
}

// Adapted from feature/alert-video-link; include current deletion/file states.
export function alertVideoState(alert) {
  if (alert?.video_status === "DELETED" || alert?.video?.deleted_at) return "deleted";
  if (alert?.video_status === "MISSING") return "missing";
  if (Number.isSafeInteger(alert?.video?.video_id) && alert.video.video_id > 0) return "ready";
  if (["PENDING", "PENDING_OR_UNAVAILABLE"].includes(alert?.video_status)) return "pending";
  return "none";
}
