import test from "node:test";
import assert from "node:assert/strict";
import { matchesDevice, parseRealtimeMessage, retryDelay } from "../src/services/realtime.js";

test("WebSocket nhận telemetry cũ và phân loại gói tuần 2", () => {
  const raw = { device_code: "vision-01", ear: 0.21 };
  assert.deepEqual(parseRealtimeMessage(raw), { type: "telemetry.updated", data: raw });
  const command = { type: "command.updated", data: { request_id: "cmd-1", device_id: 2 } };
  assert.deepEqual(parseRealtimeMessage(command), command);
  assert.equal(parseRealtimeMessage({ type: "command.updated", data: null }), null);
  assert.equal(parseRealtimeMessage({ type: "unknown", data: raw }), null);
  assert.equal(parseRealtimeMessage([]), null);
});

test("sự kiện phải khớp thiết bị đang xem", () => {
  assert.equal(matchesDevice({ device_id: 1, device_code: "vision-01" }, 1, "vision-01"), true);
  assert.equal(matchesDevice({ device_code: "vision-01" }, 1, "vision-01"), true);
  assert.equal(matchesDevice({ device_id: 2 }, 1, "vision-01"), false);
  assert.equal(matchesDevice({ device_id: 1, device_code: "other" }, 1, "vision-01"), false);
  assert.equal(matchesDevice({ ear: 0.21 }, 1, "vision-01"), false);
});

test("reconnect chờ tăng dần và dừng ở 30 giây", () => {
  assert.deepEqual([0, 1, 2, 3, 4, 5, 6].map(retryDelay),
    [1000, 2000, 4000, 8000, 16000, 30000, 30000]);
});
