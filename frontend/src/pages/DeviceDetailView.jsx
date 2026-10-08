import AppShell, { ConnectionBadge, Icon } from "../components/AppShell.jsx";
import { hasPermission } from "../services/permissions.js";
import { displayValue, formatLastSeen } from "../services/deviceDisplay.js";
import TestAlertSection from "../components/TestAlertSection.jsx";

const ACTIONS = [
  { key: "provision", label: "Cấp thông tin kết nối", hint: "Thiết lập thông tin kết nối thiết bị", icon: "wifi" },
  { key: "activate", label: "Kích hoạt", hint: "Đưa thiết bị vào hoạt động", icon: "play" },
  { key: "maintenance", label: "Chuyển sang bảo trì", hint: "Tạm dừng để bảo trì thiết bị", icon: "wrench" },
  { key: "decommission", label: "Ngừng sử dụng", hint: "Ngừng sử dụng thiết bị", icon: "stop" },
];

function DeviceDetailView({ user, realtime, deviceId, device, detailSource, loading, detailError, actionError, actionNotice, busyAction, retry, performAction, onBack, onDashboard, onOpenHistory, onOpenConfig, onOpenCommands, onOpenAlerts, onUnauthorized, onLogout }) {
  const canManage = hasPermission(user?.role, "device:manage");
  const canSendCommand = hasPermission(user?.role, "command:send");
  const type = device?.type ?? device?.device_type;
  const isAlertNode = type === "ALERT_NODE" || (!type && /^alert-/i.test(device?.device_code || ""));
  return <AppShell user={user} activePage="devices" serverConnected={realtime?.connected} onDashboard={onDashboard} onDevices={onBack} onCommands={onOpenCommands} onAlerts={onOpenAlerts} onLogout={onLogout}>
    <div className="breadcrumbs">Thiết bị <span>/</span> {device?.device_code || `#${deviceId}`}</div>
    <button className="text-link back-link" onClick={onBack}><Icon name="back" size={18} /> Danh sách thiết bị</button>
    <div className="detail-title"><div><h1>{displayValue(device?.name)}</h1><p>{device?.device_code || `#${deviceId}`} <span>·</span> {displayValue(device?.model)}</p></div><ConnectionBadge status={device?.status} isStale={device?.isStale} /></div>

    {loading && <p role="status">Đang tải chi tiết thiết bị…</p>}
    {detailError && <div className="warning-banner" role="alert"><Icon name="alert" size={26} /><div><strong>Chưa tải được thông tin chi tiết</strong><span>{detailError}</span></div><button className="outline-button" onClick={retry}><Icon name="refresh" size={17} /> Thử lại</button></div>}
    {detailSource === "list" && <p className="device-note">Thông tin bên dưới lấy từ danh sách. BE chưa trả dữ liệu chi tiết cho lần xem này.</p>}
    {detailSource === "detail" && detailError && <p className="device-note">Thông tin đang hiển thị là lần tải thành công trước đó.</p>}

    {isAlertNode && <div className="detail-quick-actions">
      {hasPermission(user?.role, "config:view") && <button className="outline-button" type="button" onClick={() => onOpenConfig?.(device)}><Icon name="settings" size={18} /> Cấu hình cảnh báo</button>}
      {canSendCommand && <TestAlertSection user={user} realtime={realtime} device={device} deviceId={deviceId} onUnauthorized={onUnauthorized} onOpenHistory={() => onOpenHistory?.(device)} />}
    </div>}

    <section className="surface-card detail-panel" aria-label="Thông tin thiết bị"><div className="panel-heading"><Icon name="device" /><h2>Thông tin thiết bị</h2></div><dl className="device-details">
      <div><dt>Mã thiết bị</dt><dd>{displayValue(device?.device_code)}</dd></div>
      <div><dt>Tên thiết bị</dt><dd>{displayValue(device?.name)}</dd></div>
      <div><dt>Loại / Model</dt><dd>{displayValue(device?.model)}</dd></div>
      <div><dt>Trạng thái quản lý</dt><dd>{displayValue(device?.lifecycle_state)}</dd></div>
      <div><dt>Kết nối</dt><dd><ConnectionBadge status={device?.status} isStale={device?.isStale} /></dd></div>
      <div><dt>Hoạt động cuối</dt><dd>{formatLastSeen(device?.last_seen)}</dd></div>
      <div><dt>Phiên bản firmware</dt><dd>{displayValue(device?.firmware_version)}</dd></div>
    </dl></section>

    {canManage && <section className="surface-card lifecycle-panel" aria-labelledby="lifecycle-heading"><div className="panel-heading"><Icon name="settings" /><h2 id="lifecycle-heading">Quản lý thiết bị</h2></div><p>Các thao tác gửi yêu cầu tới BE. Trạng thái chỉ đổi sau khi BE trả dữ liệu mới.</p><div className="action-grid">{ACTIONS.filter(item => item.key !== "decommission" || hasPermission(user?.role, "device:decommission")).map(item => <button key={item.key} className={`action-tile action-tile--${item.key}`} disabled={busyAction !== null || device?.lifecycle_state === "DECOMMISSIONED"} onClick={() => performAction(item.key)}><Icon name={item.icon} size={28} /><span><strong>{busyAction === item.key ? "Đang gửi…" : item.label}</strong><small>{item.hint}</small></span></button>)}</div>{actionError && <p className="notice-error" role="alert">{actionError}</p>}{actionNotice && <p className="notice-success" role="status">{actionNotice}</p>}</section>}
  </AppShell>;
}

export default DeviceDetailView;
