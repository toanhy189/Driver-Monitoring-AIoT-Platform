import test from "node:test";
import assert from "node:assert/strict";
import { normalizeTelemetry } from "../src/services/telemetry.js";

test("giữ ID số và mã thực tế BE cung cấp, không gán mã theo ID", () => {
  const result = normalizeTelemetry({
    device_id: 42,
    device_code: "DM-000001",
    ear: 0.21,
    perclos: 0.35,
    driver_state: "DROWSY",
  });
  assert.deepEqual(result, {
    device_id: 42,
    device_code: "DM-000001",
    ear: 0.21,
    perclos: 0.35,
    driver_state: "DROWSY",
  });
});

test("không dùng mã thiết bị hoặc chuỗi số thay ID DB", () => {
  for (const device_id of ["vision-01", "1", null, undefined, 0, -1, 1.5, NaN, Infinity]) {
    assert.throws(() => normalizeTelemetry({ device_id }));
  }
});

test("nhận payload chỉ có device_code theo tài liệu bàn giao trên main", () => {
  for (const device_id of [undefined, null]) {
    const result = normalizeTelemetry({
      device_id, device_code: "DM-000001", ear: 0.21, perclos: 0.35, driver_state: "DROWSY",
    });
    assert.deepEqual(result, {
      device_id: null, device_code: "DM-000001", ear: 0.21, perclos: 0.35, driver_state: "DROWSY",
    });
  }
});

test("có mã hợp lệ vẫn không chấp nhận ID sai kiểu; thiếu cả ID và mã thì từ chối", () => {
  for (const device_id of ["42", "vision-01", 0, -1, 1.5, NaN, Infinity]) {
    assert.throws(() => normalizeTelemetry({ device_id, device_code: "DM-000001" }));
  }
  assert.throws(() => normalizeTelemetry({ ear: 0.21 }));
  assert.throws(() => normalizeTelemetry({ device_id: null, device_code: null }));
});

test("không suy ra driver_state từ EAR/PERCLOS khi BE chưa cung cấp", () => {
  const result = normalizeTelemetry({ device_id: 1, ear: 0.01, perclos: 0.99 });
  assert.equal(result.driver_state, "UNKNOWN");
  assert.equal(result.device_code, null);
});

test("thiếu số đo, null hoặc sai kiểu không bị đổi thành số 0", () => {
  for (const value of [null, undefined, "0.35", false, NaN, Infinity, {}]) {
    const result = normalizeTelemetry({ device_id: 1, ear: value, perclos: value });
    assert.equal(result.ear, null);
    assert.equal(result.perclos, null);
  }
  const zero = normalizeTelemetry({ device_id: 1, ear: 0, perclos: 0 });
  assert.equal(zero.ear, 0);
  assert.equal(zero.perclos, 0);
});

test("chỉ nhận ba trạng thái đã chốt; trạng thái lạ không làm lỗi UI", () => {
  for (const state of ["ATTENTIVE", "DISTRACTED", "DROWSY"]) {
    assert.equal(normalizeTelemetry({ device_id: 1, driver_state: state }).driver_state, state);
  }
  for (const state of [undefined, null, "ONLINE", "drowsy", 1, {}, []]) {
    assert.equal(normalizeTelemetry({ device_id: 1, driver_state: state }).driver_state, "UNKNOWN");
  }
});

test("không giữ dữ liệu tin cũ khi tin mới thiếu trường", () => {
  normalizeTelemetry({ device_id: 1, device_code: "vision-01", perclos: 0.35, driver_state: "ATTENTIVE" });
  const next = normalizeTelemetry({ device_id: 2, device_code: "DM-000002", ear: 0.22 });
  assert.equal(next.driver_state, "UNKNOWN");
  assert.equal(next.perclos, null);
  assert.equal(next.device_code, "DM-000002");
});

test("từ chối payload hoặc mã thiết bị sai định dạng", () => {
  for (const value of [null, [], 1, "telemetry"]) {
    assert.throws(() => normalizeTelemetry(value));
  }
  for (const device_code of [1, {}, [], "", "   "]) {
    assert.throws(() => normalizeTelemetry({ device_id: 1, device_code }));
  }
});
