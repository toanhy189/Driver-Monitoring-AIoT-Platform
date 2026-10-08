const host = (import.meta.env.VITE_BACKEND_HOST || "http://localhost:8000").replace(/\/+$/, "");
const prefix = `/${(import.meta.env.VITE_API_STR || "/api").replace(/^\/+|\/+$/g, "")}`;

// Các service truyền đường dẫn sau /api, ví dụ "/devices".
export async function apiRequest(path, { method = "GET", body, token, signal } = {}) {
  if (typeof path !== "string" || !path.startsWith("/") ||
      path === prefix || path.startsWith(`${prefix}/`)) {
    throw new Error(`Đường dẫn API phải bắt đầu bằng / và không lặp lại ${prefix}.`);
  }

  const headers = { Accept: "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let response;
  try {
    response = await fetch(`${host}${prefix}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error("Không kết nối được máy chủ. Hãy kiểm tra địa chỉ BE.", { cause: error });
  }

  const text = await response.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    throw Object.assign(new Error("Máy chủ trả dữ liệu không đúng JSON."), {
      status: response.status,
    });
  }

  if (!response.ok) {
    const detail = data?.detail;
    const message = typeof detail === "string" ? detail :
      Array.isArray(detail) ? detail.map(item => item.msg).filter(Boolean).join("; ") :
      null;
    throw Object.assign(new Error(message || `Yêu cầu thất bại (HTTP ${response.status}).`), {
      status: response.status,
    });
  }

  return data;
}
