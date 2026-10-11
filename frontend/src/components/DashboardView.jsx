import AppShell, { Icon } from "./AppShell.jsx";
import DeviceStatusCard from "./DeviceStatusCard.jsx";
import DriverStatusCard from "./DriverStatusCard.jsx";
import MetricCard from "./MetricCard.jsx";

function DashboardView({ user, onLogout, onOpenDevices, onOpenCommands, onOpenAlerts, wsConnected, devices, devicesLoading, devicesError, selectedDeviceId, onSelectDevice, telemetry, telemetrySource, telemetryStale, telemetryError, earText, perclosText, hasEar, hasPerclos }) {
  const onlineCount = devices.filter(device => !device.isStale && device.status === "ONLINE").length;
  const offlineCount = devices.filter(device => !device.isStale && device.status === "OFFLINE").length;
  const updatedAt = telemetry?.recorded_at || telemetry?.received_at;
  const updatedText = updatedAt ? new Date(updatedAt).toLocaleString("vi-VN") : "Chưa ghi nhận";
  const confidence = Number.isFinite(telemetry?.confidence) ?
    `${(telemetry.confidence * 100).toFixed(0)}%` : "—";
  const angle = value => Number.isFinite(value) ? `${value.toFixed(1)}°` : "—";

  return <AppShell user={user} activePage="dashboard" serverConnected={wsConnected} onDashboard={() => {}} onDevices={onOpenDevices} onCommands={onOpenCommands} onAlerts={onOpenAlerts} onLogout={onLogout}>
    <div className="page-title"><h1>Tổng quan</h1><p>Theo dõi kết nối thiết bị và trạng thái tài xế</p></div>
    <div className="telemetry-toolbar">
      <label>Thiết bị đo
        <select value={selectedDeviceId ?? ""} onChange={event => onSelectDevice(event.target.value ? Number(event.target.value) : null)}>
          <option value="">Chọn thiết bị</option>
          {devices.map(device => <option key={device.id} value={device.id}>{device.name || device.device_code} · {device.device_code}</option>)}
        </select>
      </label>
      <span className="telemetry-freshness" role="status">
        {selectedDeviceId == null ? "Chọn thiết bị để xem số đo" :
          !telemetry ? "Chưa có dữ liệu tài xế" :
          telemetryStale ? `Dữ liệu cũ — cập nhật lần cuối: ${updatedText}` :
          telemetrySource === "snapshot" ? `Dữ liệu lưu gần nhất · ${updatedText}` :
          `Cập nhật lúc ${updatedText}`}
      </span>
    </div>
    {telemetryError && <p className="notice-error" role="alert">{telemetryError}</p>}

    <section className="stats-grid" aria-label="Thống kê thiết bị">
      <div className="stat-card"><span className="stat-icon stat-icon--blue"><Icon name="device" size={27} /></span><div><span>Thiết bị</span><strong>{devices.length}</strong></div></div>
      <div className="stat-card"><span className="stat-icon stat-icon--green"><Icon name="wifi" size={29} /></span><div><span>Trực tuyến</span><strong className="text-green">{onlineCount}</strong></div></div>
      <div className="stat-card"><span className="stat-icon stat-icon--red"><Icon name="wifiOff" size={29} /></span><div><span>Ngoại tuyến</span><strong className="text-red">{offlineCount}</strong></div></div>
    </section>
    {devices.some(device => device.isStale) && <p className="muted-note">Một số trạng thái thiết bị là dữ liệu cũ; số đếm chỉ tính trạng thái đã được cập nhật.</p>}

    <section className="telemetry-grid" aria-label="Số đo và trạng thái tài xế">
      <DriverStatusCard state={telemetry?.driver_state} faceDetected={telemetry?.face_detected} />
      <div className="metric-stack">
        <MetricCard title="EAR" value={earText} description={hasEar ? "Chỉ số độ mở mắt" : "Chưa có dữ liệu"} />
        <MetricCard title="PERCLOS" value={perclosText} unit={hasPerclos ? "%" : ""} description={hasPerclos ? "Tỷ lệ nhắm mắt" : "Chưa đủ dữ liệu"} />
      </div>
    </section>
    <section className="ai-detail-grid" aria-label="Dữ liệu AI bổ sung">
      <MetricCard title="Khuôn mặt" value={telemetry?.face_detected === true ? "Có mặt" : telemetry?.face_detected === false ? "Không thấy mặt" : "—"} />
      <MetricCard title="Góc đầu X / Y / Z" value={`${angle(telemetry?.angle_x)} / ${angle(telemetry?.angle_y)} / ${angle(telemetry?.angle_z)}`} />
      <MetricCard title="Độ tin cậy" value={confidence} />
    </section>

    <section className="surface-card device-preview" aria-labelledby="devices-heading">
      <div className="section-heading"><h2 id="devices-heading">Thiết bị trong hệ thống</h2><button className="text-link" onClick={onOpenDevices}>Xem tất cả <Icon name="arrow" size={17} /></button></div>
      {devicesLoading && <p role="status">Đang tải trạng thái thiết bị…</p>}
      {devicesError && <p className="notice-error" role="alert">{devicesError}</p>}
      {!devicesLoading && !devicesError && devices.length === 0 && <p>Chưa có thiết bị được gán cho tài khoản này.</p>}
      <div className="preview-grid">{devices.map(device => <DeviceStatusCard key={device.id} deviceCode={device.device_code} name={device.name || device.model || "Thiết bị"} status={device.status} lastSeen={device.last_seen} isStale={device.isStale} />)}</div>
    </section>
  </AppShell>;
}

export default DashboardView;
