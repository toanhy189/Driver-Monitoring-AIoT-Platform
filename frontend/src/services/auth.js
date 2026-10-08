import { apiRequest } from "./api.js";

export async function getCurrentUser({ token, signal } = {}) {
  if (!token) {
    throw Object.assign(new Error("Chưa có phiên đăng nhập."), { status: 401 });
  }

  const user = await apiRequest("/me", { token, signal });
  if (!user || !Number.isSafeInteger(user.id) || user.id <= 0 ||
      typeof user.username !== "string" || !user.username.trim() ||
      typeof user.role !== "string" || !user.role.trim()) {
    throw new Error("Thông tin tài khoản từ máy chủ không đúng định dạng.");
  }
  return user;
}
