import test from "node:test";
import assert from "node:assert/strict";

import { hasPermission } from "../src/services/permissions.js";

test("Customer chỉ xem; Employee gửi lệnh và sửa cấu hình; Admin quản lý thiết bị", () => {
  assert.equal(hasPermission("Customer", "dashboard:view"), true);
  assert.equal(hasPermission("Customer", "config:view"), true);
  assert.equal(hasPermission("Customer", "command:send"), false);
  assert.equal(hasPermission("Customer", "config:edit"), false);
  assert.equal(hasPermission("Customer", "alert:view"), true);
  assert.equal(hasPermission("Customer", "alert:acknowledge"), false);

  assert.equal(hasPermission("Employee", "command:send"), true);
  assert.equal(hasPermission("Employee", "config:edit"), true);
  assert.equal(hasPermission("Employee", "device:manage"), false);
  assert.equal(hasPermission("Employee", "device:decommission"), false);
  assert.equal(hasPermission("Employee", "alert:acknowledge"), true);

  assert.equal(hasPermission("Admin", "device:manage"), true);
  assert.equal(hasPermission("Admin", "device:decommission"), true);
  assert.equal(hasPermission("Admin", "alert:acknowledge"), true);
});

test("role lạ hoặc thiếu role không được cấp quyền", () => {
  for (const role of [undefined, "", "OPERATOR", "Viewer", "__proto__"]) {
    assert.equal(hasPermission(role, "dashboard:view"), false);
    assert.equal(hasPermission(role, "command:send"), false);
  }
});
