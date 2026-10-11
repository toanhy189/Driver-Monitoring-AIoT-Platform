export function displayValue(value) {
  return typeof value === "string" && value.trim() ? value : "Chưa cung cấp";
}

export function formatLastSeen(value) {
  if (!value) return "Chưa ghi nhận";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Chưa ghi nhận" : date.toLocaleString("vi-VN");
}

export function connectionText(status) {
  if (status === "ONLINE") return "ONLINE";
  if (status === "OFFLINE") return "OFFLINE";
  return "Chưa xác định";
}

export function deviceApiError(error) {
  if (error.status === 404) return "API này chưa có trên BE hoặc thiết bị không tồn tại (HTTP 404).";
  if (error.status === 405) return "BE chưa hỗ trợ thao tác này (HTTP 405).";
  if (error.status === 403) return "Tài khoản không có quyền thực hiện thao tác này (HTTP 403).";
  return error.message || "Không thể hoàn thành yêu cầu. Vui lòng thử lại.";
}
