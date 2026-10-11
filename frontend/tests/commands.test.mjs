import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const require = createRequire(import.meta.url);

async function loadModule(entry, globals = {}, jsx = false) {
  const result = await build({
    entryPoints: [fileURLToPath(new URL(entry, import.meta.url))],
    bundle: true, write: false, outdir: "out", platform: "node", format: "cjs",
    jsx: "automatic", external: jsx ? ["react", "react/jsx-runtime"] : [],
    define: { "import.meta.env": "{}" },
  });
  const module = { exports: {} };
  const script = result.outputFiles.find(file => file.path.endsWith(".js"));
  vm.runInNewContext(script.text, { module, exports: module.exports, require, console, ...globals });
  return module.exports;
}

function response(status, data) {
  return { status, ok: status >= 200 && status < 300,
    text: async () => data == null ? "" : JSON.stringify(data) };
}

test("Test Alert chỉ POST khi gọi hàm, dùng ID DB, token và body tạm đã chốt trong FE", async () => {
  const calls = [];
  const service = await loadModule("../src/services/commands.js", {
    localStorage: { getItem: () => "token" },
    fetch: async (url, options) => {
      calls.push({ url, options });
      return response(202, { request_id: "cmd-001", status: "SENT" });
    },
  });
  assert.equal(calls.length, 0);
  const command = await service.sendTestAlert(2);
  assert.equal(calls[0].url, "http://localhost:8000/api/devices/2/commands");
  assert.equal(calls[0].options.method, "POST");
  assert.equal(calls[0].options.headers.Authorization, "Bearer token");
  assert.equal(JSON.parse(calls[0].options.body).action, "TEST_ALERT");
  assert.equal(Object.hasOwn(JSON.parse(calls[0].options.body), "severity"), false);
  assert.equal(command.request_id, "cmd-001");
  assert.equal(service.commandFinished(command), false);
  await assert.rejects(service.sendTestAlert("alert-01"), /ID thiết bị/);
  assert.equal(calls.length, 1);
});

test("form kiểm tra gửi đúng thông số đã nhập và chặn giá trị sai trước khi POST", async () => {
  const calls = [];
  const service = await loadModule("../src/services/commands.js", {
    localStorage: { getItem: () => "token" },
    fetch: async (_url, options) => {
      calls.push(JSON.parse(options.body));
      return response(202, { request_id: "cmd-002", status: "SENT" });
    },
  });
  await service.sendTestAlert(2, { parameters: {
    buzzer_ms: "2500", vibration_ms: "500", led_mode: "ON",
  } });
  assert.equal(calls[0].buzzer_ms, 2500);
  assert.equal(calls[0].led_mode, "ON");
  assert.equal(Object.hasOwn(calls[0], "severity"), false);
  await assert.rejects(service.sendTestAlert(2, { parameters: {
    buzzer_ms: "1000", vibration_ms: "1000", led_mode: "INVALID",
  } }), /Chế độ LED/);
  await assert.rejects(service.sendTestAlert(2, { parameters: {
    buzzer_ms: "10001", vibration_ms: "1000", led_mode: "FLASH",
  } }), /Thời lượng còi/);
  assert.equal(calls.length, 1);
});

test("lịch sử và chi tiết lệnh dùng GET; response thiếu hoặc sai request_id bị từ chối", async () => {
  const calls = [];
  const service = await loadModule("../src/services/commands.js", {
    localStorage: { getItem: () => "token" },
    fetch: async (url, options) => {
      calls.push({ url, options });
      return response(200, url.includes("?device_id=")
        ? [{ request_id: "cmd-001", device_id: 2, status: "SENT" }]
        : { request_id: "cmd-001", device_id: 2, status: "ACKNOWLEDGED", ack_status: "COMPLETED" });
    },
  });
  const list = await service.getCommands({ deviceId: 2 });
  const detail = await service.getCommand("cmd-001");
  assert.equal(list.length, 1);
  assert.equal(detail.ack_status, "COMPLETED");
  assert.equal(calls[0].url, "http://localhost:8000/api/commands?device_id=2");
  assert.equal(calls[1].url, "http://localhost:8000/api/commands/cmd-001");
  assert.ok(calls.every(call => call.options.method === "GET" && call.options.headers.Authorization === "Bearer token"));
  assert.throws(() => service.normalizeCommand({ status: "SENT" }), /request_id/);
});

test("chỉ ACK COMPLETED mới hiện hoàn tất; ACCEPTED và SENT vẫn đang chờ", async () => {
  const { commandStatus } = await loadModule("../src/services/commandDisplay.js");
  const service = await loadModule("../src/services/commands.js");
  const sent = { request_id: "cmd-001", status: "SENT" };
  const accepted = { request_id: "cmd-001", status: "ACKNOWLEDGED", ack_status: "ACCEPTED" };
  const completed = { request_id: "cmd-001", status: "ACKNOWLEDGED", ack_status: "COMPLETED" };
  assert.equal(commandStatus(sent).tone, "pending");
  assert.equal(commandStatus(accepted).tone, "pending");
  assert.equal(commandStatus(completed).label, "Thiết bị đã hoàn tất");
  assert.equal(service.commandFinished(accepted), false);
  assert.equal(service.commandFinished(completed), true);
  assert.equal(service.keepNewerCommand(completed, sent).ack_status, "COMPLETED");
  assert.equal(service.keepNewerCommand(accepted, sent).ack_status, "ACCEPTED");
  assert.equal(service.collapseCommands([completed, sent, accepted]).length, 1);
  assert.equal(service.collapseCommands([completed, sent, accepted])[0].ack_status, "COMPLETED");
  assert.equal(commandStatus({ status: "EXECUTED" }).tone, "unknown");
});

test("FE khóa Test Alert khi không có quyền, sai loại, bảo trì, offline hoặc thiếu trạng thái", async () => {
  const { testAlertBlockReason } = await loadModule("../src/services/commands.js");
  const device = { type: "ALERT_NODE", lifecycle_state: "ACTIVE", status: "ONLINE", last_seen: "2026-10-07T10:00:00" };
  const reason = (role, changes = {}) => testAlertBlockReason({ user: { role }, device: { ...device, ...changes } });
  assert.match(reason("Customer"), /chỉ có quyền xem/);
  assert.match(reason("Admin", { type: "VISION_NODE" }), /thiết bị cảnh báo/);
  assert.match(reason("Admin", { type: undefined }), /chưa cung cấp loại/);
  assert.match(reason("Admin", { lifecycle_state: "MAINTENANCE" }), /bảo trì/);
  assert.match(reason("Admin", { status: "OFFLINE" }), /offline/);
  assert.match(reason("Admin", { last_seen: null }), /hoạt động gần đây/);
  assert.equal(reason("Admin"), "");
  assert.equal(reason("Employee"), "");
});

test("trang chi tiết đặt nút kiểm tra trước thông số; biểu mẫu chỉ mở khi bấm", async () => {
  const { default: Detail } = await loadModule("../src/pages/DeviceDetailPage.jsx", {}, true);
  const alert = renderToStaticMarkup(React.createElement(Detail, {
    user: { role: "Admin" }, deviceId: 1,
    summary: { id: 1, device_code: "alert-01", model: "Thiết bị cảnh báo V1", status: "ONLINE" },
  }));
  assert.match(alert, /Kiểm tra cảnh báo/);
  assert.match(alert, /aria-expanded="false"/);
  assert.doesNotMatch(alert, /Gửi lệnh kiểm tra/);
  assert.ok(alert.indexOf("Kiểm tra cảnh báo") < alert.indexOf("Thông tin thiết bị"));
  const vision = renderToStaticMarkup(React.createElement(Detail, {
    user: { role: "Admin" }, deviceId: 2,
    summary: { id: 2, device_code: "vision-01", type: "VISION_NODE", model: "Camera" },
  }));
  assert.doesNotMatch(vision, /Kiểm tra cảnh báo/);
  const customer = renderToStaticMarkup(React.createElement(Detail, {
    user: { role: "Customer" }, deviceId: 1,
    summary: { id: 1, device_code: "alert-01", type: "ALERT_NODE", model: "Thiết bị cảnh báo V1" },
  }));
  assert.doesNotMatch(customer, /Kiểm tra cảnh báo/);
  assert.match(customer, /Cấu hình cảnh báo/);
  assert.match(customer, /Lịch sử lệnh/);
});
