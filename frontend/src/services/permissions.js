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

const ROLE_ALIASES = Object.freeze({ ADMIN: "Admin", OPERATOR: "Employee", VIEWER: "Customer" });

export function hasPermission(role, permission) {
  const normalized = ROLE_ALIASES[role] || role;
  return typeof normalized === "string" && Object.hasOwn(ROLE_PERMISSIONS, normalized) &&
    ROLE_PERMISSIONS[normalized].includes(permission);
}
