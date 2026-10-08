import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import { build } from "esbuild";

async function loadAuth(fetch) {
  const result = await build({
    entryPoints: [fileURLToPath(new URL("../src/services/auth.js", import.meta.url))],
    bundle: true, write: false, platform: "node", format: "cjs",
    define: { "import.meta.env": "{}" },
  });
  const module = { exports: {} };
  vm.runInNewContext(result.outputFiles[0].text, {
    module, exports: module.exports, fetch,
  });
  return module.exports;
}

function response(status, data) {
  return {
    status,
    ok: status >= 200 && status < 300,
    text: async () => JSON.stringify(data),
  };
}

test("/me xác nhận token và trả đúng role từ backend", async () => {
  let request;
  const { getCurrentUser } = await loadAuth(async (url, options) => {
    request = { url, options };
    return response(200, { id: 1, username: "an", role: "Customer" });
  });
  const user = await getCurrentUser({ token: "abc" });
  assert.equal(request.url, "http://localhost:8000/api/me");
  assert.equal(request.options.headers.Authorization, "Bearer abc");
  assert.equal(user.role, "Customer");
});

test("/me từ chối token hết hạn hoặc response thiếu role", async () => {
  const { getCurrentUser: expired } = await loadAuth(async () =>
    response(401, { detail: "Could not validate credentials" }));
  await assert.rejects(expired({ token: "expired" }), error => error.status === 401);

  const { getCurrentUser: invalidProfile } = await loadAuth(async () =>
    response(200, { id: 1, username: "an" }));
  await assert.rejects(invalidProfile({ token: "abc" }), /Thông tin tài khoản/);
});
