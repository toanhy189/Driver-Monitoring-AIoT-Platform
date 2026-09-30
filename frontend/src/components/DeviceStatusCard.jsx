/*
  DeviceStatusCard là một mảnh giao diện có thể tái sử dụng.

  Nhận:
    { deviceId, connected }

  Ví dụ Dashboard truyền:
    <DeviceStatusCard
      deviceId="vision-01"
      connected={true}
    />

  Giao diện hiển thị:
    Vision Node                ĐANG HOẠT ĐỘNG
    Mã thiết bị                vision-01

  Nếu connected={false}:
    Vision Node                NGOẠI TUYẾN
*/

function DeviceStatusCard({
  deviceId,
  connected
}) {
  return (
    <section className="status-card">
      <div className="card-header">
        <h2>Vision Node</h2>

        <span
          className={
            connected
              ? "status-badge status-badge--online"
              : "status-badge status-badge--offline"
          }
        >
          {connected
            ? "ĐANG HOẠT ĐỘNG"
            : "NGOẠI TUYẾN"}
        </span>
      </div>

      <div className="device-info">
        <span>Mã thiết bị</span>

        <strong>
          {deviceId || "Không xác định"}
        </strong>
      </div>
    </section>
  );
}

export default DeviceStatusCard;