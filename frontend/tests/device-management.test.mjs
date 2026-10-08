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
    jsx: "automatic",
    external: jsx ? ["react", "react/jsx-runtime"] : [],
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
    text: async () => data == null ? "" : JSON.stringify(data) };
}

test("API chi tiết và đăng ký dùng ID DB, Bearer token và JSON", async () => {
  const calls = [];
  const service = await loadModule("../src/services/devices.js", {
    localStorage: { getItem: () => "token" },
    fetch: async (url, options) => {
      calls.push({ url, options });
      return url.endsWith("/devices/2")
        ? response(200, { id: 2, device_code: "alert-01", status: "OFFLINE" })
        : response(201, { id: 3, device_code: "vision-01" });
    },
  });

  const device = await service.getDeviceDetail(2);
  assert.equal(device.device_code, "alert-01");
  assert.equal(calls[0].url, "http://localhost:8000/api/devices/2");
  assert.equal(calls[0].options.headers.Authorization, "Bearer token");

  await service.registerDevice({ device_code: " vision-01 ", name: "Camera", model: "Vision" });
  assert.equal(calls[1].url, "http://localhost:8000/api/devices");
  assert.equal(calls[1].options.method, "POST");
  assert.equal(JSON.parse(calls[1].options.body).device_code, "vision-01");
});

test("bốn thao tác vòng đời gọi đúng URL; lỗi không tạo trạng thái thành công", async () => {
  const calls = [];
  const service = await loadModule("../src/services/devices.js", {
    localStorage: { getItem: () => "token" },
    fetch: async (url, options) => {
      calls.push({ url, options });
      return response(404, { detail: "Not Found" });
    },
  });

  for (const action of ["provision", "activate", "maintenance", "decommission"]) {
    await assert.rejects(service.runDeviceAction(2, action), error => error.status === 404);
  }
  assert.deepEqual(calls.map(call => call.url), [
    "http://localhost:8000/api/devices/2/provision",
    "http://localhost:8000/api/devices/2/activate",
    "http://localhost:8000/api/devices/2/maintenance",
    "http://localhost:8000/api/devices/2/decommission",
  ]);
  assert.ok(calls.every(call => call.options.method === "POST"));
  assert.throws(() => service.runDeviceAction(0, "activate"), /ID thiết bị/);
  assert.throws(() => service.runDeviceAction(2, "delete"), /Thao tác thiết bị/);
  assert.equal(calls.length, 4);
});

test("tin cập nhật thay record cùng ID, không thêm dòng mới", async () => {
  const { applyDeviceUpdate } = await loadModule("../src/services/devices.js", {
    localStorage: { getItem: () => "token" },
  });
  const original = [{ id: 2, device_code: "alert-01", status: "OFFLINE", lifecycle_state: "ACTIVE" }];
  const updated = applyDeviceUpdate(original, { id: 2, lifecycle_state: "MAINTENANCE" });
  assert.equal(updated.length, 1);
  assert.equal(updated[0].lifecycle_state, "MAINTENANCE");
  assert.equal(updated[0].status, "OFFLINE");
  assert.equal(applyDeviceUpdate(updated, { id: 3, status: "ONLINE" }).length, 1);
});

test("trang chi tiết dùng dữ liệu có thật và ẩn thao tác với Customer", async () => {
  const { default: Detail } = await loadModule("../src/pages/DeviceDetailPage.jsx", {}, true);
  const summary = { id: 2, device_code: "alert-01", model: "Alert Node", status: "OFFLINE" };
  const customer = renderToStaticMarkup(React.createElement(Detail, {
    user: { role: "Customer" }, deviceId: 2, summary,
  }));
  assert.match(customer, /alert-01/);
  assert.match(customer, /OFFLINE/);
  assert.match(customer, /Chưa cung cấp/);
  assert.match(customer, /Thông tin bên dưới lấy từ danh sách/);
  assert.doesNotMatch(customer, /Chuyển sang bảo trì/);

  const admin = renderToStaticMarkup(React.createElement(Detail, {
    user: { role: "Admin" }, deviceId: 2, summary,
  }));
  assert.match(admin, /Chuyển sang bảo trì/);
  assert.match(admin, /Ngừng sử dụng/);
});
