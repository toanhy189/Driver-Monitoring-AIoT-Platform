// Test dùng cùng kiểu loadModule với alerts.test.mjs (esbuild + vm).
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import { build } from "esbuild";

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
    module, exports: module.exports, console, ...globals,
  });
  return module.exports;
}


test("alertVideoState phân biệt ready/pending/none", async () => {
  const model = await loadModule("../src/services/alertModel.js");
  assert.equal(model.alertVideoState({ video: { video_id: 3 } }), "ready");
  assert.equal(model.alertVideoState({ video: null, video_status: "PENDING" }), "pending");
  assert.equal(model.alertVideoState({ video: null, video_status: "UNAVAILABLE" }), "none");
});