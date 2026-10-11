import test from "node:test";
import assert from "node:assert/strict";
import { DASHBOARD_VIEW, ensureView, hasPreviousView, pushView, replaceView, viewFromHash, viewHash } from "../src/services/navigation.js";

test("trang cảnh báo có URL riêng", () => {
  assert.equal(viewHash({ page: "alerts" }), "#/alerts");
  assert.deepEqual(viewFromHash("#/alerts"), { page: "alerts" });
});

function fakeWindow(initialHash = "") {
  const entries = [{ hash: initialHash, state: null }];
  let index = 0;
  return {
    location: { hash: initialHash },
    history: {
      get state() { return entries[index].state; },
      replaceState(state, _title, hash) {
        entries[index] = { state, hash };
        window.location.hash = hash;
      },
      pushState(state, _title, hash) {
        entries.splice(index + 1);
        entries.push({ state, hash });
        index += 1;
        window.location.hash = hash;
      },
      back() {
        if (index === 0) return;
        index -= 1;
        window.location.hash = entries[index].hash;
      },
      forward() {
        if (index === entries.length - 1) return;
        index += 1;
        window.location.hash = entries[index].hash;
      },
      get length() { return entries.length; },
    },
  };
}

test("Back/Forward quay giữa tổng quan, danh sách và đúng thiết bị", () => {
  const previousWindow = globalThis.window;
  globalThis.window = fakeWindow();
  try {
    assert.deepEqual(ensureView(1), DASHBOARD_VIEW);
    pushView({ page: "devices" }, 1);
    const device = { page: "device-detail", deviceId: 2, summary: { id: 2, name: "Thiết bị 2" } };
    pushView(device, 1);
    assert.equal(window.location.hash, "#/devices/2");
    assert.equal(hasPreviousView(1), true);
    window.history.back();
    assert.deepEqual(ensureView(1), { page: "devices" });
    window.history.back();
    assert.deepEqual(ensureView(1), DASHBOARD_VIEW);
    window.history.forward();
    window.history.forward();
    assert.deepEqual(ensureView(1), device);
  } finally {
    globalThis.window = previousWindow;
  }
});

test("URL chi tiết mở trực tiếp không tự quay khỏi web; đổi tài khoản không giữ thông tin cũ", () => {
  const previousWindow = globalThis.window;
  globalThis.window = fakeWindow("#/devices/2");
  try {
    assert.deepEqual(ensureView(1), { page: "device-detail", deviceId: 2 });
    assert.equal(hasPreviousView(1), false);
    pushView({ page: "commands", deviceId: 2, deviceCode: "alert-02" }, 1);
    assert.equal(window.location.hash, "#/devices/2/commands");
    assert.deepEqual(ensureView(1), { page: "commands", deviceId: 2, deviceCode: "alert-02" });
    pushView({ page: "config", deviceId: 2, deviceCode: "alert-02" }, 1);
    assert.equal(window.location.hash, "#/devices/2/config");
    assert.deepEqual(ensureView(1), { page: "config", deviceId: 2, deviceCode: "alert-02" });
    replaceView({ page: "device-detail", deviceId: 2, summary: { name: "Riêng tư" } }, 1);
    assert.deepEqual(ensureView(5), DASHBOARD_VIEW);
    assert.equal(window.location.hash, "#/dashboard");
  } finally {
    globalThis.window = previousWindow;
  }
});
