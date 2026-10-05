// status và lastSeen lấy từ backend, độc lập với kết nối của Dashboard.
function DeviceStatusCard({
  deviceCode,
  name = "Thiết bị",
  status,
  lastSeen,
  isStale = false,
}) {
  const state = status === "ONLINE" ? "online" :
    status === "OFFLINE" ? "offline" : "unknown";
  const statusText = {
    online: "ONLINE",
    offline: "OFFLINE",
    unknown: "CHƯA XÁC ĐỊNH",
  }[state];
  const date = lastSeen ? new Date(lastSeen) : null;
  const lastSeenText = date && !Number.isNaN(date.getTime())
    ? date.toLocaleString("vi-VN")
    : "Chưa ghi nhận";

  return (
    <section className="status-card">
      <div className="card-header">
        <h2>{name}</h2>

        <span
          className={`status-badge status-badge--${isStale ? "unknown" : state}`}
        >
          {statusText}{isStale && state !== "unknown" ? " (gần nhất)" : ""}
        </span>
      </div>

      <div className="device-info">
        <span>Lần hoạt động cuối</span>
        <strong>{lastSeenText}</strong>
      </div>

      {isStale && (
        <p className="device-status-note" role="status">
          Dữ liệu cũ — chưa cập nhật. Chưa xác nhận được trạng thái hiện tại.
        </p>
      )}

      <div className="device-info">
        <span>Mã thiết bị</span>

        <strong>
          {deviceCode || "Không xác định"}
        </strong>
      </div>
    </section>
  );
}

export default DeviceStatusCard;
