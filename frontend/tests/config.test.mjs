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

function timings() {
  return Object.fromEntries(["led", "buzzer", "motor"].map(output => [output,
    Object.fromEntries([1, 2, 3].map(level => [level, { on_ms: level * 100, off_ms: level * 200 }]))]));
}

function response(status, data) {
  return { status, ok: status >= 200 && status < 300,
    text: async () => data == null ? "" : JSON.stringify(data) };
}

test("GET/PUT cấu hình dùng ID DB, token và ba mức bật/tắt cho từng tải", async () => {
  const calls = [];
  const config = await loadModule("../src/services/config.js", {
    localStorage: { getItem: () => "token" },
    fetch: async (url, options) => {
      calls.push({ url, options });
      return options.method === "PUT" ? response(200, { config_id: "cfg-002" }) :
        response(200, { config_id: "cfg-001", applied_config_id: "cfg-000",
          desired: { timings: timings() }, applied: null });
    },
  });
  const current = await config.getDeviceConfig(2);
  assert.equal(current.desired.buzzer[3].on_ms, 300);
  assert.equal(config.configStatus(current).kind, "pending");
  assert.equal(await config.updateDeviceConfig(2, timings()), "cfg-002");
  assert.equal(calls[0].url, "http://localhost:8000/api/devices/2/config");
  assert.equal(calls[0].options.method, "GET");
  assert.equal(calls[1].options.method, "PUT");
  assert.equal(calls[1].options.headers.Authorization, "Bearer token");
  assert.equal(JSON.parse(calls[1].options.body).timings.motor[2].off_ms, 400);
});

test("không báo đã áp dụng trước khi config_id khớp; sai schema hoặc thời gian bị từ chối", async () => {
  const config = await loadModule("../src/services/config.js");
  const current = config.normalizeConfig({ config_id: "cfg-002", applied_config_id: "cfg-001",
    desired: { timings: timings() }, applied: null });
  assert.equal(config.configStatus(current).kind, "pending");
  assert.equal(config.configStatus({ ...current, appliedId: "cfg-002" }).kind, "applied");
  assert.equal(config.configStatus({ ...current, desiredId: null }).kind, "unknown");
  assert.throws(() => config.normalizeConfig({ severity: 2, buzzer_ms: 1000 }), /desired/);
  const draft = config.draftFromTimings(timings());
  assert.equal(config.timingsFromDraft(draft).led[1].on_ms, 100);
  draft.led[1].on_ms = "100.5";
  assert.throws(() => config.timingsFromDraft(draft), /số nguyên/);
  draft.led[1].on_ms = "10001";
  assert.throws(() => config.timingsFromDraft(draft), /10000/);
  draft.led[1].on_ms = "-1";
  assert.throws(() => config.timingsFromDraft(draft), /số nguyên/);
});

test("Customer xem form nhưng không có nút lưu; Admin chỉ được lưu sau khi tải cấu hình", async () => {
  const { default: Page } = await loadModule("../src/pages/RemoteConfigPage.jsx", {}, true);
  const props = { deviceId: 2, deviceCode: "alert-01" };
  const customer = renderToStaticMarkup(React.createElement(Page, { ...props, user: { role: "Customer" } }));
  assert.match(customer, /chỉ được xem cấu hình/);
  assert.doesNotMatch(customer, /<button[^>]*>Lưu cấu hình<\/button>/);
  const customerInput = customer.match(/<input[^>]*aria-label="Đèn LED mức 1, thời gian bật \(ms\)"[^>]*>/)?.[0];
  assert.match(customerInput, /readOnly/);
  const admin = renderToStaticMarkup(React.createElement(Page, { ...props, user: { role: "Admin" } }));
  assert.match(admin, /Cấu hình đã lưu/);
  assert.match(admin, /Cấu hình thiết bị/);
  assert.equal((admin.match(/aria-label="Chưa có dữ liệu"/g) || []).length, 2);
  assert.match(admin, /<button[^>]*>Lưu cấu hình<\/button>/);
  const adminInput = admin.match(/<input[^>]*aria-label="Đèn LED mức 1, thời gian bật \(ms\)"[^>]*>/)?.[0];
  assert.doesNotMatch(adminInput, /readOnly/);
  assert.match(admin, /type="submit" disabled=""/);
  assert.match(admin, /Bạn có thể nhập thử/);
  assert.match(admin, /1000 ms = 1 giây/);
});
