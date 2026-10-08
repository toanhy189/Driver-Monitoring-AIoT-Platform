// Quyền tạm thời theo đúng tên role mà GET /api/me hiện trả về.
// Khi TV2 chốt bảng quyền, sửa tập trung tại đây.
const ROLE_PERMISSIONS = Object.freeze({
  Admin: Object.freeze([
    "dashboard:view", "command:view", "command:send", "config:view", "config:edit",
    "device:manage", "device:decommission", "alert:view", "alert:acknowledge",
  ]),
  Employee: Object.freeze([
    "dashboard:view", "command:view", "command:send", "config:view", "config:edit",
    "alert:view", "alert:acknowledge",
  ]),
  Customer: Object.freeze(["dashboard:view", "command:view", "config:view", "alert:view"]),
});

export function hasPermission(role, permission) {
  return typeof role === "string" && Object.hasOwn(ROLE_PERMISSIONS, role) &&
    ROLE_PERMISSIONS[role].includes(permission);
}
