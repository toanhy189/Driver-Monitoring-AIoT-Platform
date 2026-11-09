import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { hasPermission } from "../src/services/permissions.js";
import { ruleRequest, ruleBlockerLabel } from "../src/services/ruleModel.js";

const require = createRequire(import.meta.url);
async function bundle(entry, globals = {}, jsx = false) {
  const result = await build({ entryPoints: [fileURLToPath(new URL(entry, import.meta.url))],
    bundle: true, write: false, outdir: "out", platform: "node", format: "cjs", jsx: "automatic",
    external: jsx ? ["react", "react/jsx-runtime"] : [], define: { "import.meta.env": "{}" } });
  const module = { exports: {} };
  vm.runInNewContext(result.outputFiles.find(item => item.path.endsWith(".js")).text,
    { module, exports: module.exports, require, console, ...globals });
  return module.exports;
}

const snapshot = { source_device_id: 5, target_device_id: 1, enabled: false, effective_enabled: false,
  engine_enabled: false, updated_at: "2026-11-09T00:00:00.000000", targets: [],
  readiness: { blockers: ["ENGINE_DISABLED"], ready: false, target: null, inflight: false } };

test("new/changed target saves disarmed; same target can enable with the exact loaded revision", () => {
  assert.equal(ruleRequest({ ...snapshot, target_device_id: null, updated_at: null }, { target: "1", enabled: true }).enabled, false);
  assert.equal(ruleRequest(snapshot, { target: "2", enabled: true }).enabled, false);
  const body = ruleRequest(snapshot, { target: "1", enabled: true });
  assert.equal(body.enabled, true);
  assert.equal(body.expected_updated_at, snapshot.updated_at);
  assert.deepEqual(body.policy, { policy_version: "driver-bench-20261107-v1" });
  assert.throws(() => ruleRequest(snapshot, { target: "", enabled: false }), /chọn thiết bị/);
});

test("reading the editor never issues a command; saving uses only the rule API and JWT", async () => {
  const calls = [];
  const api = await bundle("../src/services/rules.js", {
    localStorage: { getItem: () => "test-jwt" },
    fetch: async (url, options) => {
      calls.push({ url, options });
      return { ok: true, status: 200, text: async () => JSON.stringify(snapshot) };
    },
  });
  await api.getRule(5);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].options.method, "GET");
  await api.saveRule(5, snapshot, { target: "1", enabled: false });
  assert.equal(calls[1].url, "/api/devices/5/rule");
  assert.equal(calls[1].options.headers.Authorization, "Bearer test-jwt");
  assert.equal(calls[1].options.method, "PUT");
  assert.equal(JSON.parse(calls[1].options.body).expected_updated_at, snapshot.updated_at);
  assert.equal(calls.some(call => call.url.includes("/commands")), false);
  await assert.rejects(api.getRule("vision-01"), /ID camera/);
});

test("missing readiness from an older Backend is reported instead of claiming ready", async () => {
  const api = await bundle("../src/services/rules.js", {
    localStorage: { getItem: () => "jwt" },
    fetch: async () => ({ ok: true, status: 200, text: async () => JSON.stringify({ source_device_id: 5, enabled: true }) }),
  });
  await assert.rejects(api.getRule(5), /cập nhật Backend/);
  assert.match(ruleBlockerLabel("TARGET_OFFLINE"), /offline/);
  assert.match(ruleBlockerLabel("ENGINE_DISABLED"), /toàn hệ thống/);
});

test("only Admin sees the editor, and only on a loaded Vision Node", async () => {
  const { default: View } = await bundle("../src/pages/DeviceDetailView.jsx", {}, true);
  const props = { realtime: { events: [], connected: true }, deviceId: 5, detailSource: "detail", busyAction: null,
    device: { id: 5, device_code: "vision-01", type: "VISION_NODE", lifecycle_state: "ACTIVE" } };
  for (const role of ["Admin", "Employee", "Customer"]) {
    const html = renderToStaticMarkup(React.createElement(View, { ...props, user: { role } }));
    assert.equal(html.includes('id="rule-binding-heading"'), role === "Admin");
    assert.equal(hasPermission(role, "rule:manage"), role === "Admin");
  }
  const html = renderToStaticMarkup(React.createElement(View, {
    ...props, user: { role: "Admin" }, device: { ...props.device, type: "ALERT_NODE" },
  }));
  assert.equal(html.includes('id="rule-binding-heading"'), false);
  assert.match(html, /Kiểm tra cảnh báo/);
});
