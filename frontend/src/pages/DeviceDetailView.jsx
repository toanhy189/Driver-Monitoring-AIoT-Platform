import AppShell, { ConnectionBadge, Icon } from "../components/AppShell.jsx";
import { hasPermission } from "../services/permissions.js";
import { displayValue, formatLastSeen, deviceTypeLabel } from "../services/deviceDisplay.js";
import { deviceActionBlockReason } from "../services/deviceModel.js";
import TestAlertSection from "../components/TestAlertSection.jsx";
import DeviceHistoryPanel from "../components/DeviceHistoryPanel.jsx";
import HardwareVersionForm from "../components/HardwareVersionForm.jsx";
import RuleBindingPanel from "../components/RuleBindingPanel.jsx";

const ACTIONS = [
  { key: "provision", label: "Cấp thông tin kết nối", hint: "Thiết lập thông tin kết nối thiết bị", icon: "wifi" },
  { key: "activate", label: "Kích hoạt", hint: "Đưa thiết bị vào hoạt động", icon: "play" },
  { key: "maintenance", label: "Chuyển sang bảo trì", hint: "Tạm dừng để bảo trì thiết bị", icon: "wrench" },
  { key: "decommission", label: "Ngừng sử dụng", hint: "Ngừng sử dụng thiết bị", icon: "stop" },
];

function DeviceDetailView({ user, realtime, deviceId, device, detailSource, loading, detailError, actionError, actionNotice, busyAction, retry, performAction, onBack, onDashboard, onOpenHistory, onOpenConfig, onOpenCommands, onOpenAlerts, onOpenTarget, onUnauthorized, onLogout }) {
  const canManage = hasPermission(user?.role, "device:manage");
  const canDecommission = hasPermission(user?.role, "device:decommission");
  const canSendCommand = hasPermission(user?.role, "command:send");
  const type = device?.type ?? device?.device_type;
  const isAlertNode = type === "ALERT_NODE";
  return <AppShell user={user} activePage="devices" serverConnected={realtime?.connected} onDashboard={onDashboard} onDevices={onBack} onCommands={onOpenCommands} onAlerts={onOpenAlerts} onLogout={onLogout}>
    <div className="breadcrumbs">Thiết bị <span>/</span> {device?.device_code || `#${deviceId}`}</div>
    <button className="text-link back-link" onClick={onBack}><Icon name="back" size={18} /> Danh sách thiết bị</button>
    <div className="detail-title"><div><h1>{displayValue(device?.name)}</h1><p>{device?.device_code || `#${deviceId}`} <span>·</span> {displayValue(device?.model)}</p></div><ConnectionBadge status={device?.status} isStale={device?.isStale} /></div>

    {loading && <p role="status">Đang tải chi tiết thiết bị…</p>}
    {detailError && <div className="warning-banner" role="alert"><Icon name="alert" size={26} /><div><strong>Chưa tải được thông tin chi tiết</strong><span>{detailError}</span></div><button className="outline-button" onClick={retry}><Icon name="refresh" size={17} /> Thử lại</button></div>}
    {detailSource === "list" && <p className="device-note">Thông tin bên dưới lấy từ danh sách. Đang chờ thông tin chi tiết mới.</p>}
    {detailSource === "detail" && detailError && <p className="device-note">Thông tin đang hiển thị là lần tải thành công trước đó.</p>}

    {isAlertNode && <div className="detail-quick-actions">
      {hasPermission(user?.role, "config:view") && <button className="outline-button" type="button" onClick={() => onOpenConfig?.(device)}><Icon name="settings" size={18} /> Cấu hình cảnh báo</button>}
      {canSendCommand && <TestAlertSection user={user} realtime={realtime} device={device} deviceId={deviceId} onUnauthorized={onUnauthorized} onOpenHistory={() => onOpenHistory?.(device)} />}
    </div>}

    <section className="surface-card detail-panel" aria-label="Thông tin thiết bị"><div className="panel-heading"><Icon name="device" /><h2>Thông tin thiết bị</h2></div><dl className="device-details">
      <div><dt>Mã thiết bị</dt><dd>{displayValue(device?.device_code)}</dd></div>
      <div><dt>Tên thiết bị</dt><dd>{displayValue(device?.name)}</dd></div>
      <div><dt>Loại thiết bị</dt><dd>{deviceTypeLabel(type)}</dd></div>
      <div><dt>Model phần cứng</dt><dd>{displayValue(device?.model)}</dd></div>
      <div><dt>Trạng thái quản lý</dt><dd>{displayValue(device?.lifecycle_state)}</dd></div>
      <div><dt>Kết nối</dt><dd><ConnectionBadge status={device?.status} isStale={device?.isStale} /></dd></div>
      <div><dt>Hoạt động cuối</dt><dd>{formatLastSeen(device?.last_seen)}</dd></div>
      <div><dt>Phiên bản firmware</dt><dd>{displayValue(device?.firmware_version)}</dd></div>
      <div><dt>Phiên bản phần cứng</dt><dd>{displayValue(device?.hardware_version)}</dd></div>
    </dl></section>
    {canManage && detailSource === "detail" && !["VISION_NODE", "ALERT_NODE"].includes(type) && <p role="status" className="warning-banner">Hồ sơ cũ chưa xác định loại thiết bị. Hãy ngừng sử dụng hồ sơ này rồi đăng ký lại, chọn rõ Camera AI hoặc Bộ cảnh báo ESP32 và dùng mã mới.</p>}

    {canManage && <section className="surface-card lifecycle-panel" aria-labelledby="lifecycle-heading"><div className="panel-heading"><Icon name="settings" /><h2 id="lifecycle-heading">Quản lý thiết bị</h2></div><p>Các thao tác gửi yêu cầu tới BE. Trạng thái chỉ đổi sau khi BE trả dữ liệu mới.</p><div className="action-grid">{ACTIONS.filter(item => item.key !== "decommission" || canDecommission).map(item => {
      const reason = deviceActionBlockReason(device, item.key);
      return <button key={item.key} className={`action-tile action-tile--${item.key}`} disabled={busyAction !== null || Boolean(reason)} title={reason || undefined} onClick={() => performAction(item.key)}><Icon name={item.icon} size={28} /><span><strong>{busyAction === item.key ? "Đang gửi…" : item.label}</strong><small>{reason || item.hint}</small></span></button>;
    })}</div>{detailSource === "detail" && <div className="device-removal"><button className="outline-button" type="button" disabled={busyAction !== null || !device?.can_delete_registration} onClick={() => performAction("delete-registration")}>Xóa đăng ký </button><p className="muted-note">{device?.delete_block_reason || "Chỉ xóa hồ sơ mới chưa cấp kết nối, chưa phân công và chưa có dữ liệu."}</p></div>}{actionError && <p className="notice-error" role="alert">{actionError}</p>}{actionNotice && <p className="notice-success" role="status">{actionNotice}</p>}</section>}
    {type === "VISION_NODE" && detailSource === "detail" && !detailError && hasPermission(user?.role, "rule:manage") &&
      <RuleBindingPanel key={`rule-${deviceId}`} deviceId={deviceId} device={device} onUnauthorized={onUnauthorized} onOpenTarget={onOpenTarget} onOpenAlerts={onOpenAlerts} />}
    {canManage && detailSource === "detail" && <details className="surface-card detail-panel"><summary>Thông tin kỹ thuật</summary><p className="muted-note">Thiết bị có thể tự cập nhật phiên bản phần cứng khi gửi heartbeat. Chỉ chỉnh thủ công khi cần bổ sung thông tin bảo trì.</p><HardwareVersionForm key={`hardware-${deviceId}`} deviceId={deviceId} initialValue={device?.hardware_version} onSaved={retry} onUnauthorized={onUnauthorized} /></details>}
    {detailSource === "detail" && !detailError && <DeviceHistoryPanel
      deviceId={deviceId}
      deviceType={type}
      canDeleteVideo={canSendCommand}
      onUnauthorized={onUnauthorized}
    />}
  </AppShell>;
}

export default DeviceDetailView;
