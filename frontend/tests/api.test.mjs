import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import { build } from "esbuild";

async function loadService(entry, globals) {
  const result = await build({
    entryPoints: [fileURLToPath(new URL(entry, import.meta.url))],
    bundle: true, write: false, platform: "node", format: "cjs",
    define: { "import.meta.env": "{}" },
  });
  const module = { exports: {} };
  vm.runInNewContext(result.outputFiles[0].text, {
    module, exports: module.exports, ...globals,
  });
  return module.exports;
}

function jsonResponse(status, data) {
  return {
    status, ok: status >= 200 && status < 300,
    text: async () => data == null ? "" : JSON.stringify(data),
  };
}

test("GET ghép URL một lần, gắn token, chuyển AbortSignal", async () => {
  const calls = [];
  const { apiRequest } = await loadService("../src/services/api.js", {
    fetch: async (...args) => { calls.push(args); return jsonResponse(200, [{ id: 1 }]); },
  });
  const signal = new AbortController().signal;
  const data = await apiRequest("/devices", { token: "abc", signal });
  assert.equal(calls[0][0], "http://localhost:8000/api/devices");
  assert.equal(calls[0][1].method, "GET");
  assert.equal(calls[0][1].headers.Authorization, "Bearer abc");
  assert.equal(calls[0][1].signal, signal);
  assert.equal(data[0].id, 1);
  assert.equal(calls[0][1].headers["Content-Type"], undefined);
});

test("POST login gửi JSON và không gắn token cũ", async () => {
  let request;
  const { apiRequest } = await loadService("../src/services/api.js", {
    fetch: async (url, options) => {
      request = { url, options };
      return jsonResponse(200, { access_token: "new-token" });
    },
  });
  const response = await apiRequest("/login", {
    method: "POST", body: { username: "a", password: "b" },
  });
  assert.equal(request.url, "http://localhost:8000/api/login");
  assert.equal(request.options.headers.Authorization, undefined);
  assert.equal(request.options.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(request.options.body), { username: "a", password: "b" });
  assert.equal(response.access_token, "new-token");
});

test("401, 403 và 422 giữ HTTP status cùng thông báo từ BE", async () => {
  for (const [status, data, expected] of [
    [401, { detail: "Incorrect username or password" }, "Incorrect username or password"],
    [403, { detail: "Forbidden" }, "Forbidden"],
    [422, { detail: [{ msg: "Field required" }] }, "Field required"],
  ]) {
    const { apiRequest } = await loadService("../src/services/api.js", {
      fetch: async () => jsonResponse(status, data),
    });
    await assert.rejects(apiRequest("/devices"), error =>
      error.status === status && error.message === expected);
  }
});

test("204 không có body trả null; JSON hỏng báo lỗi kèm status", async () => {
  const { apiRequest: noContent } = await loadService("../src/services/api.js", {
    fetch: async () => jsonResponse(204, null),
  });
  assert.equal(await noContent("/commands/1", { method: "DELETE" }), null);

  const { apiRequest: invalidJson } = await loadService("../src/services/api.js", {
    fetch: async () => ({ status: 500, ok: false, text: async () => "<html>error</html>" }),
  });
  await assert.rejects(invalidJson("/devices"), error =>
    error.status === 500 && error.message.includes("không đúng JSON"));
});

test("lỗi mạng có thông báo dễ đọc, hủy request giữ AbortError", async () => {
  const { apiRequest: networkError } = await loadService("../src/services/api.js", {
    fetch: async () => { throw new TypeError("Failed to fetch"); },
  });
  await assert.rejects(networkError("/devices"), error =>
    error.message.includes("Không kết nối được máy chủ") && error.status === undefined);

  const { apiRequest: aborted } = await loadService("../src/services/api.js", {
    fetch: async () => { throw new DOMException("Aborted", "AbortError"); },
  });
  await assert.rejects(aborted("/devices"), error => error.name === "AbortError");
});

test("chặn đường dẫn thiếu / hoặc lặp lại /api", async () => {
  const { apiRequest } = await loadService("../src/services/api.js", {
    fetch: async () => { throw new Error("Không được gọi fetch"); },
  });
  await assert.rejects(apiRequest("devices"), /Đường dẫn API/);
  await assert.rejects(apiRequest("/api/devices"), /Đường dẫn API/);
});

test("getDevices giữ kiểm tra dữ liệu và gửi Bearer token qua apiRequest", async () => {
  let request;
  const { getDevices } = await loadService("../src/services/devices.js", {
    localStorage: { getItem: () => "token-1" },
    fetch: async (url, options) => {
      request = { url, options };
      return jsonResponse(200, [{ id: 2, device_code: "alert-01", status: "OFFLINE" }]);
    },
  });
  const devices = await getDevices();
  assert.equal(request.url, "http://localhost:8000/api/devices");
  assert.equal(request.options.headers.Authorization, "Bearer token-1");
  assert.equal(devices[0].device_code, "alert-01");
  assert.equal(devices[0].isStale, false);
});

test("getDevices thiếu token báo 401, còn thiếu quyền giữ 403", async () => {
  const { getDevices: withoutToken } = await loadService("../src/services/devices.js", {
    localStorage: { getItem: () => null },
    fetch: async () => { throw new Error("Không được gọi fetch"); },
  });
  await assert.rejects(withoutToken(), error => error.status === 401);

  const { getDevices: forbidden } = await loadService("../src/services/devices.js", {
    localStorage: { getItem: () => "token-1" },
    fetch: async () => jsonResponse(403, { detail: "Bạn không có quyền" }),
  });
  await assert.rejects(forbidden(), error => error.status === 403);
});
