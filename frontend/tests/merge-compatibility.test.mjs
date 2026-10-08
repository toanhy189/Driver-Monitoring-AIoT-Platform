import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { normalizeTelemetry } from "../src/services/telemetry.js";

const require = createRequire(import.meta.url);

// Dùng bộ biên dịch của Vite để nạp JSX và import.meta.env trong Node.
async function loadModule(entry, globals = {}) {
  const result = await build({
    entryPoints: [fileURLToPath(new URL(entry, import.meta.url))],
    bundle: true,
    write: false,
    platform: "node",
    format: "cjs",
    jsx: "automatic",
    external: ["react", "react/jsx-runtime"],
    define: { "import.meta.env": "{}" },
  });
  const module = { exports: {} };
  vm.runInNewContext(result.outputFiles[0].text, {
    module, exports: module.exports, require, console, ...globals,
  });
  return module.exports;
}

test("Dashboard ban đầu không hiển thị số đo mẫu hoặc kết luận tỉnh táo", async () => {
  const { default: Dashboard } = await loadModule("../src/components/Dashboard.jsx");
  const html = renderToStaticMarkup(React.createElement(Dashboard));
  assert.match(html, /Chưa có dữ liệu/);
  assert.match(html, /CHƯA XÁC ĐỊNH/);
  assert.doesNotMatch(html, /0\.28|12%|ATTENTIVE/);
});

test("thẻ thiết bị dùng status của BE dù WebSocket đang kết nối", async () => {
  const { default: Card } = await loadModule("../src/components/DeviceStatusCard.jsx");
  const html = renderToStaticMarkup(React.createElement(Card, {
    deviceCode: "DM-000001", name: "ESP32", status: "OFFLINE", connected: true,
  }));
  assert.match(html, /OFFLINE/);
  assert.match(html, /DM-000001/);
  assert.doesNotMatch(html, /status-badge--online/);
  const unknown = renderToStaticMarkup(React.createElement(Card, { connected: true }));
  assert.match(unknown, /CHƯA XÁC ĐỊNH/);
});

test("không thấy mặt thì thẻ tài xế không hiện tỉnh táo", async () => {
  const { default: Card } = await loadModule("../src/components/DriverStatusCard.jsx");
  const html = renderToStaticMarkup(React.createElement(Card, {
    state: "ATTENTIVE", faceDetected: false,
  }));
  assert.match(html, /Không thấy mặt/);
  assert.doesNotMatch(html, /TỈNH TÁO/);
});

test("thẻ giữ trạng thái gần nhất kèm ghi chú khi dữ liệu cũ", async () => {
  const { default: Card } = await loadModule("../src/components/DeviceStatusCard.jsx");
  const html = renderToStaticMarkup(React.createElement(Card, {
    status: "ONLINE", isStale: true, lastSeen: "invalid-date",
  }));
  assert.match(html, /ONLINE \(gần nhất\)/);
  assert.match(html, /Dữ liệu cũ/);
  assert.match(html, /Chưa ghi nhận/);
  assert.match(html, /status-badge--unknown/);
});

test("WebSocket chuyển payload chỉ có mã và phát sự kiện đóng đúng tên", async () => {
  class FakeSocket {
    constructor(url) { this.url = url; }
  }
  const { createTelemetrySocket } = await loadModule("../src/services/websocket.js", {
    WebSocket: FakeSocket,
    console: { log() {}, error() {} },
  });
  const received = [];
  let opens = 0;
  let closes = 0;
  let errors = 0;
  const socket = createTelemetrySocket({
    onMessage: data => received.push(normalizeTelemetry(data)),
    onOpen: () => opens++, onClose: () => closes++, onError: () => errors++,
  });
  assert.equal(socket.url, "ws://localhost:8000/ws/telemetry");
  socket.onopen();
  socket.onmessage({ data: JSON.stringify({
    device_code: "DM-000001", ear: 0.21, perclos: 0.35, driver_state: "DROWSY",
  }) });
  socket.onmessage({ data: "invalid-json" });
  socket.onerror();
  socket.onclose();
  assert.equal(received.length, 1);
  assert.equal(received[0].device_id, null);
  assert.equal(received[0].device_code, "DM-000001");
  assert.equal(received[0].driver_state, "DROWSY");
  assert.equal(opens, 1);
  assert.equal(closes, 1);
  assert.equal(errors, 1);
});
