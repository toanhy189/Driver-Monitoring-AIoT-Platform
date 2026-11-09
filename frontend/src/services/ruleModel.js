export const RULE_POLICY_VERSION = "driver-bench-20261107-v1";

export function ruleRequest(snapshot, draft) {
  const target = Number(draft.target);
  if (!Number.isSafeInteger(target) || target <= 0) throw new Error("Hãy chọn thiết bị nhận cảnh báo.");
  if (!snapshot) throw new Error("Cần tải liên kết hiện tại trước khi lưu.");
  return {
    target_device_id: target,
    // A new or changed target is saved disarmed; enabling is a separate save.
    enabled: snapshot.target_device_id === target && draft.enabled === true,
    expected_updated_at: snapshot.updated_at,
    policy: { policy_version: RULE_POLICY_VERSION },
  };
}

const BLOCKERS = {
  UNBOUND: "Chưa chọn thiết bị nhận cảnh báo.",
  DISABLED: "Cảnh báo tự động đang tắt.",
  ENGINE_DISABLED: "Rule Engine toàn hệ thống đang tắt tại cấu hình triển khai.",
  POLICY_MISMATCH: "Liên kết đang dùng policy khác. Lưu để áp dụng policy hiển thị bên dưới.",
  SOURCE_INACTIVE: "Camera chưa ở trạng thái quản lý ACTIVE.",
  TARGET_INACTIVE: "Thiết bị nhận chưa ACTIVE hoặc đã ngừng sử dụng.",
  TARGET_OFFLINE: "Thiết bị nhận offline hoặc heartbeat đã cũ.",
  SESSION_ENDED: "Phiên AI đã kết thúc. Đang chờ phiên mới.",
  MONITORING_UNAVAILABLE: "AI chưa quan sát được tài xế; đang tạm ngừng phát lệnh tự động.",
  WAITING_FOR_AI: "Đang chờ quan sát AI mới hợp lệ từ camera.",
};

export function ruleBlockerLabel(code) {
  return BLOCKERS[code] || "Chưa đủ điều kiện phát lệnh; hãy tải lại trạng thái.";
}
