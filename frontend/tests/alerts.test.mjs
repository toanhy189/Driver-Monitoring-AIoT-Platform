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
  vm.runInNewContext(script.text, {
    module, exports: module.exports, require, console, ...globals,
  });
  return module.exports;
}

function response(status, data) {
  return { status, ok: status >= 200 && status < 300,
    text: async () => JSON.stringify(data) };
}

test("lịch sử cảnh báo GET và xác nhận đã xem POST đúng API, token, ID", async () => {
  const calls = [];
  const alerts = await loadModule("../src/services/alerts.js", {
    localStorage: { getItem: () => "token" },
    fetch: async (url, options) => {
      calls.push({ url, options });
      return options.method === "POST" ?
        response(200, { alert_id: 2, status: "ACKNOWLEDGED" }) :
        response(200, [{ alert_id: 2, status: "OPEN" }]);
    },
  });
  const list = await alerts.getAlerts();
  assert.equal(list[0].alert_id, "2");
  assert.equal(alerts.canAcknowledgeAlert(list[0]), true);
  const updated = await alerts.acknowledgeAlert("2");
  assert.equal(alerts.canAcknowledgeAlert(updated), false);
  assert.equal(calls[0].url, "http://localhost:8000/api/alerts");
  assert.equal(calls[1].url, "http://localhost:8000/api/alerts/2/acknowledge");
  assert.equal(calls[1].options.method, "POST");
  assert.ok(calls.every(call => call.options.headers.Authorization === "Bearer token"));
});

test("cảnh báo cùng alert_id được gộp, không tạo dòng trùng", async () => {
  const alerts = await loadModule("../src/services/alerts.js");
  const merged = alerts.mergeAlerts(
    [{ alert_id: "a-1", status: "OPEN", severity: 2 }],
    [{ alert_id: "a-1", status: "ACKNOWLEDGED" }],
  );
  assert.equal(merged.length, 1);
  assert.equal(merged[0].severity, 2);
  assert.equal(merged[0].status, "ACKNOWLEDGED");
  assert.throws(() => alerts.normalizeAlert({ status: "OPEN" }), /alert_id/);
});

test("trang cảnh báo có trạng thái tải và Customer không có nút xác nhận", async () => {
  const { default: Page } = await loadModule("../src/pages/AlertHistoryPage.jsx", {}, true);
  const html = renderToStaticMarkup(React.createElement(Page, { user: { role: "Customer" } }));
  assert.match(html, /Đang tải cảnh báo/);
  assert.match(html, /Cảnh báo/);
  assert.doesNotMatch(html, /<button[^>]*>Đã xem<\/button>/);
});
