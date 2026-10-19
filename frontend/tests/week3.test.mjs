import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import { build } from "esbuild";

const require = createRequire(import.meta.url);
async function moduleFor(entry, globals = {}) {
  const result = await build({ entryPoints: [fileURLToPath(new URL(entry, import.meta.url))],
    bundle: true, write: false, platform: "node", format: "cjs", define: { "import.meta.env": "{}" } });
  const module = { exports: {} };
  vm.runInNewContext(result.outputFiles[0].text, { module, exports: module.exports, require,
    console, URLSearchParams, localStorage: { getItem: () => "test-token" }, ...globals });
  return module.exports;
}
const response = body => ({ status: 200, ok: true, text: async () => JSON.stringify(body) });

test("tuần 3: gửi cùng khóa idempotency và không tự retry POST khi mất kết nối", async () => {
  const calls = [];
  const commands = await moduleFor("../src/services/commands.js", { fetch: async (url, options) => {
    calls.push(options); return response({ request_id: "cmd-1", device_id: 2, action: "TEST_ALERT", status: "SENT" });
  } });
  await commands.sendTestAlert(2, { idempotencyKey: "same-test-key" });
  await commands.sendTestAlert(2, { idempotencyKey: "same-test-key" });
  assert.equal(calls[0].headers["Idempotency-Key"], "same-test-key");
  assert.equal(calls[1].headers["Idempotency-Key"], "same-test-key");
  let attempts = 0;
  const offline = await moduleFor("../src/services/commands.js", { fetch: async () => { attempts++; throw new Error("offline"); } });
  await assert.rejects(offline.sendTestAlert(2));
  assert.equal(attempts, 1);
});

test("tuần 3: API lịch sử dùng ID, UTC, phiên bản AI và giới hạn", async () => {
  const calls = [];
  const history = await moduleFor("../src/services/history.js", { fetch: async (url, options) => {
    calls.push({ url, options }); return response({ items: [], limit: 50, offset: 0, has_more: false });
  } });
  for (const kind of ["telemetry", "commands", "timeline", "metrics"]) {
    await history.getDeviceHistory(2, kind, { from: "2026-10-18T10:00:00+07:00", modelVersion: "model-v1", limit: 50 });
  }
  assert.match(calls[0].url, /devices\/2\/telemetry\/history/);
  const query = new URL(calls[0].url).searchParams;
  assert.equal(query.get("from"), "2026-10-18T03:00:00.000Z");
  assert.equal(query.get("model_version"), "model-v1");
  assert.equal(query.get("limit"), "50");
  assert.match(calls[1].url, /devices\/2\/history/);
  assert.match(calls[2].url, /devices\/2\/timeline/);
  assert.match(calls[3].url, /devices\/2\/metrics/);
  assert.equal(calls[0].options.headers.Authorization, "Bearer test-token");
});
