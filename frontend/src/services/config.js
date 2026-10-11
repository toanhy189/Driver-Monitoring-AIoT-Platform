import { apiRequest } from "./api.js";

export const CONFIG_OUTPUTS = Object.freeze([
  { key: "led", label: "Đèn LED" },
  { key: "buzzer", label: "Còi" },
  { key: "motor", label: "Motor rung" },
]);
export const CONFIG_LEVELS = Object.freeze([1, 2, 3]);
// Giới hạn tạm theo hướng dẫn tuần 2; TV1/TV2 cần xác nhận trong hợp đồng API.
export const MAX_TIMING_MS = 10000;

function accessToken() {
  const token = localStorage.getItem("access_token");
  if (!token) throw Object.assign(new Error("Bạn cần đăng nhập để xem cấu hình."), { status: 401 });
  return token;
}

function validDeviceId(value) {
  if (!Number.isSafeInteger(value) || value <= 0) throw new Error("ID thiết bị không hợp lệ.");
  return value;
}

function validConfigId(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function timing(value, label) {
  if (typeof value !== "number" || !Number.isSafeInteger(value) ||
      value < 0 || value > MAX_TIMING_MS) {
    throw new Error(`${label} phải là số nguyên từ 0 đến ${MAX_TIMING_MS} ms.`);
  }
  return value;
}

export function validateTimings(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Cấu hình thời gian không đúng định dạng.");
  }
  const result = {};
  for (const output of CONFIG_OUTPUTS) {
    result[output.key] = {};
    for (const level of CONFIG_LEVELS) {
      const profile = value[output.key]?.[level];
      if (!profile || typeof profile !== "object" || Array.isArray(profile)) {
        throw new Error(`Thiếu thời gian ${output.label}, mức ${level}.`);
      }
      result[output.key][level] = {
        on_ms: timing(profile.on_ms, `${output.label}, mức ${level}, thời gian bật`),
        off_ms: timing(profile.off_ms, `${output.label}, mức ${level}, thời gian tắt`),
      };
    }
  }
  return result;
}

export function emptyDraft() {
  return Object.fromEntries(CONFIG_OUTPUTS.map(output => [output.key,
    Object.fromEntries(CONFIG_LEVELS.map(level => [level, { on_ms: "", off_ms: "" }]))]));
}

export function draftFromTimings(timings) {
  const draft = emptyDraft();
  if (!timings) return draft;
  const normalized = validateTimings(timings);
  for (const output of CONFIG_OUTPUTS) {
    for (const level of CONFIG_LEVELS) {
      draft[output.key][level] = {
        on_ms: String(normalized[output.key][level].on_ms),
        off_ms: String(normalized[output.key][level].off_ms),
      };
    }
  }
  return draft;
}

export function timingsFromDraft(draft) {
  const numeric = {};
  for (const output of CONFIG_OUTPUTS) {
    numeric[output.key] = {};
    for (const level of CONFIG_LEVELS) {
      const profile = draft?.[output.key]?.[level];
      numeric[output.key][level] = {};
      for (const field of ["on_ms", "off_ms"]) {
        const raw = profile?.[field];
        if (typeof raw !== "string" || !/^\d+$/.test(raw.trim())) {
          throw new Error(`${output.label}, mức ${level}: nhập ${field === "on_ms" ? "thời gian bật" : "thời gian tắt"} bằng số nguyên ms.`);
        }
        numeric[output.key][level][field] = Number(raw.trim());
      }
    }
  }
  return validateTimings(numeric);
}

export function normalizeConfig(response) {
  if (!response || typeof response !== "object" || Array.isArray(response)) {
    throw new Error("BE trả cấu hình không đúng định dạng.");
  }
  if (!Object.hasOwn(response, "desired")) {
    throw new Error("BE chưa trả trường desired theo hợp đồng cấu hình tạm.");
  }
  const desiredPart = response.desired ?? null;
  const appliedPart = response.applied ?? null;
  if (desiredPart !== null && (typeof desiredPart !== "object" || !desiredPart.timings)) {
    throw new Error("BE chưa trả cấu hình theo từng mức cảnh báo; cần thống nhất lại JSON với TV2.");
  }
  if (appliedPart !== null && (typeof appliedPart !== "object" || !appliedPart.timings)) {
    throw new Error("BE trả cấu hình đã áp dụng không đúng định dạng.");
  }
  return {
    desiredId: validConfigId(response.config_id ?? desiredPart?.config_id),
    appliedId: validConfigId(response.applied_config_id ?? appliedPart?.config_id),
    desired: desiredPart ? validateTimings(desiredPart.timings) : null,
    applied: appliedPart ? validateTimings(appliedPart.timings) : null,
  };
}

export function configStatus(snapshot) {
  if (!snapshot) return { kind: "unavailable", label: "Chưa tải được cấu hình" };
  if (!snapshot.desired) return { kind: "empty", label: "Chưa có cấu hình mong muốn" };
  if (!snapshot.desiredId) return { kind: "unknown", label: "Chưa xác định trạng thái áp dụng" };
  if (snapshot.appliedId !== snapshot.desiredId) {
    return { kind: "pending", label: "Chờ thiết bị áp dụng" };
  }
  return { kind: "applied", label: "Thiết bị đã áp dụng" };
}

export async function getDeviceConfig(deviceId, { signal } = {}) {
  const response = await apiRequest(`/devices/${validDeviceId(deviceId)}/config`, {
    token: accessToken(), signal,
  });
  return normalizeConfig(response);
}

export async function updateDeviceConfig(deviceId, timings, { signal } = {}) {
  const response = await apiRequest(`/devices/${validDeviceId(deviceId)}/config`, {
    method: "PUT", body: { timings: validateTimings(timings) }, token: accessToken(), signal,
  });
  const configId = validConfigId(response?.config_id);
  if (!configId) throw new Error("BE chưa trả config_id; chưa thể theo dõi thiết bị đã áp dụng hay chưa.");
  return configId;
}
