const STATE_KEY = "driverMonitorView";

export const DASHBOARD_VIEW = Object.freeze({ page: "dashboard" });

export function viewHash(view) {
  if (view.page === "alerts") return "#/alerts";
  if (view.page === "devices") return "#/devices";
  if (view.page === "device-detail") return `#/devices/${view.deviceId}`;
  if (view.page === "config") return `#/devices/${view.deviceId}/config`;
  if (view.page === "commands" && view.deviceId != null) return `#/devices/${view.deviceId}/commands`;
  if (view.page === "commands") return "#/commands";
  return "#/dashboard";
}

export function viewFromHash(hash) {
  const detail = /^#\/devices\/([1-9]\d*)$/.exec(hash);
  if (detail && Number.isSafeInteger(Number(detail[1]))) {
    return { page: "device-detail", deviceId: Number(detail[1]) };
  }
  const history = /^#\/devices\/([1-9]\d*)\/commands$/.exec(hash);
  if (history && Number.isSafeInteger(Number(history[1]))) {
    return { page: "commands", deviceId: Number(history[1]) };
  }
  const config = /^#\/devices\/([1-9]\d*)\/config$/.exec(hash);
  if (config && Number.isSafeInteger(Number(config[1]))) {
    return { page: "config", deviceId: Number(config[1]) };
  }
  if (hash === "#/devices") return { page: "devices" };
  if (hash === "#/commands") return { page: "commands" };
  if (hash === "#/alerts") return { page: "alerts" };
  return DASHBOARD_VIEW;
}

function currentEntry() {
  return window.history.state?.[STATE_KEY];
}

export function currentView() {
  return viewFromHash(window.location.hash);
}

export function replaceView(view, ownerId, depth = 0) {
  const hash = viewHash(view);
  window.history.replaceState({
    ...window.history.state,
    [STATE_KEY]: { view, ownerId, depth, hash },
  }, "", hash);
}

export function ensureView(ownerId) {
  const entry = currentEntry();
  if (entry?.hash === window.location.hash && entry.ownerId === ownerId) return entry.view;

  // A previous account may have left device details in this tab's history.
  const view = entry && entry.ownerId !== ownerId ? DASHBOARD_VIEW : currentView();
  replaceView(view, ownerId);
  return view;
}

export function pushView(view, ownerId) {
  const entry = currentEntry();
  const depth = entry?.ownerId === ownerId ? entry.depth : 0;
  const hash = viewHash(view);
  if (window.location.hash === hash) {
    replaceView(view, ownerId, depth);
    return;
  }
  window.history.pushState({
    ...window.history.state,
    [STATE_KEY]: { view, ownerId, depth: depth + 1, hash },
  }, "", hash);
}

export function hasPreviousView(ownerId) {
  const entry = currentEntry();
  return entry?.ownerId === ownerId && entry.hash === window.location.hash && entry.depth > 0;
}
