import { authenticatedRequest } from "./api.js";
import { TEST_ALERT_BODY, normalizeCommand, validateTestAlertParameters } from "./commandModel.js";

export {
  TEST_ALERT_BODY, validateTestAlertParameters, normalizeCommand,
  commandBelongsToDevice, commandFinished, keepNewerCommand,
  collapseCommands, testAlertBlockReason,
} from "./commandModel.js";

function validDeviceId(id) {
  if (!Number.isSafeInteger(id) || id <= 0) throw new Error("ID thiết bị không hợp lệ.");
  return id;
}

function validRequestId(id) {
  if (typeof id !== "string" || !id.trim()) throw new Error("Mã lệnh không hợp lệ.");
  return id;
}

export async function sendTestAlert(deviceId, { parameters = TEST_ALERT_BODY, signal } = {}) {
  const id = validDeviceId(deviceId);
  const response = await authenticatedRequest(`/devices/${id}/commands`, {
    method: "POST", body: validateTestAlertParameters(parameters),
    missingMessage: "Bạn cần đăng nhập để xem lệnh.", signal,
  });
  const command = normalizeCommand(response);
  if (command.device_id !== id || command.action !== "TEST_ALERT" ||
      !["PENDING", "SENT", "ACKNOWLEDGED", "FAILED", "TIMEOUT"].includes(command.status)) {
    throw new Error("BE chưa trả trạng thái hợp lệ của lệnh kiểm tra.");
  }
  return command;
}

export async function getCommands({ deviceId, signal } = {}) {
  const query = deviceId == null ? "" : `?device_id=${validDeviceId(deviceId)}`;
  const response = await authenticatedRequest(`/commands${query}`, {
    missingMessage: "Bạn cần đăng nhập để xem lệnh.", signal,
  });
  if (!Array.isArray(response)) throw new Error("BE trả lịch sử lệnh không đúng định dạng.");
  return response.map(normalizeCommand);
}

export async function getCommand(requestId, { signal } = {}) {
  const id = validRequestId(requestId);
  const response = await authenticatedRequest(`/commands/${encodeURIComponent(id)}`, {
    missingMessage: "Bạn cần đăng nhập để xem lệnh.", signal,
  });
  const command = normalizeCommand(response);
  if (command.request_id !== id) throw new Error("BE trả kết quả của lệnh khác.");
  return command;
}
