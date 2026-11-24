// Admin quản trị; Employee vận hành thiết bị được gán; Customer theo dõi và xác nhận đã xem.
const ROLE_PERMISSIONS = Object.freeze({
  Admin: Object.freeze([
    "dashboard:view", "command:view", "command:send", "config:view", "config:edit",
    "device:manage", "device:decommission", "user:view", "alert:view", "alert:acknowledge", "rule:manage", "firmware:manage",
  ]),
  Employee: Object.freeze([
    "dashboard:view", "command:view", "command:send", "config:view", "config:edit",
    "alert:view", "alert:acknowledge",
  ]),
  Customer: Object.freeze(["dashboard:view", "command:view", "config:view", "alert:view", "alert:acknowledge"]),
});

const ROLE_ALIASES = Object.freeze({ ADMIN: "Admin", OPERATOR: "Employee", VIEWER: "Customer" });

export const isAdmin = role => ["Admin", "ADMIN"].includes(role);
export const roleLabel = role => ({ Admin: "Quản trị viên", Employee: "Nhân viên điều hành", Customer: "Người dùng cá nhân / tài xế" }[ROLE_ALIASES[role] || role] || "Chưa xác định");

export function hasPermission(role, permission) {
  const normalized = ROLE_ALIASES[role] || role;
  return typeof normalized === "string" && Object.hasOwn(ROLE_PERMISSIONS, normalized) &&
    ROLE_PERMISSIONS[normalized].includes(permission);
}
