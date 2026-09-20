/* ../component/ = một mảnh giao diện có thể tái sử dụng.
nhận: { deviceId, connected}
Ví dụ Dashboard truyền: 
    <DeviceStatusCard
    deviceId="vision-01"
    connected={true}
    />
thì giao diện sẽ hiển thị:
    Vision Node                 ONLINE
    Device ID                   vision-01
Nếu: connected={false}
thì:
    Vision Node                 OFFLINE
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
          {connected ? "ONLINE" : "OFFLINE"}
        </span>
      </div>

      <div className="device-info">
        <span>Device ID</span>
        <strong>{deviceId || "Unknown"}</strong>
      </div>
    </section>
  );
}

export default DeviceStatusCard;