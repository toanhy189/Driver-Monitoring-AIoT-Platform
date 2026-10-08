import { useEffect, useRef, useState } from "react";
import AppShell, { ConnectionBadge, Icon } from "../components/AppShell.jsx";
import { hasPermission } from "../services/permissions.js";
import { displayValue, formatLastSeen } from "../services/deviceDisplay.js";

function DeviceListView({ user, onBack, onOpenDevice, onOpenCommands, onOpenAlerts, onLogout, serverConnected, devices, loading, error, retry, fields, setFields, registerBusy, registerError, registerNotice, submitRegistration, resetRegistration }) {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [registerOpen, setRegisterOpen] = useState(false);
  const registerPanelRef = useRef(null);
  useEffect(() => {
    if (registerOpen) registerPanelRef.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  }, [registerOpen]);
  const canManage = hasPermission(user?.role, "device:manage");
  const onlineCount = devices.filter(device => !device.isStale && device.status === "ONLINE").length;
  const visibleDevices = devices.filter(device => {
    const query = search.trim().toLocaleLowerCase("vi-VN");
    const matchesSearch = !query || [device.device_code, device.name, device.model].some(value => String(value || "").toLocaleLowerCase("vi-VN").includes(query));
    const matchesStatus = statusFilter === "all" || (statusFilter === "unknown" ? !["ONLINE", "OFFLINE"].includes(device.status) : device.status === statusFilter);
    return matchesSearch && matchesStatus;
  });

  return <AppShell user={user} activePage="devices" serverConnected={serverConnected} onDashboard={onBack} onDevices={() => {}} onCommands={onOpenCommands} onAlerts={onOpenAlerts} onLogout={onLogout}>
    <div className="page-title page-title--actions"><div><h1>Thiết bị</h1><p>Quản lý thiết bị cảnh báo và camera trong hệ thống</p></div>{canManage && <button className="primary-button" type="button" disabled={registerBusy} aria-expanded={registerOpen} aria-controls="register-panel" onClick={() => setRegisterOpen(open => !open)}><Icon name="plus" />{registerOpen ? "Đóng form" : "Đăng ký thiết bị"}</button>}</div>
    <section className="stats-grid stats-grid--two" aria-label="Thống kê thiết bị">
      <div className="stat-card"><span className="stat-icon stat-icon--blue"><Icon name="device" size={27} /></span><div><span>Tổng thiết bị</span><strong>{devices.length}</strong></div></div>
      <div className="stat-card"><span className="stat-icon stat-icon--green"><Icon name="wifi" size={29} /></span><div><span>Đang kết nối</span><strong className="text-green">{onlineCount}</strong></div></div>
    </section>
    {devices.some(device => device.isStale) && <p className="muted-note">Trạng thái dữ liệu cũ không được tính vào số đang kết nối.</p>}

    <section className="surface-card device-list-panel" aria-label="Danh sách thiết bị">
      <div className="device-toolbar">
        <label className="search-field"><Icon name="search" /><span className="sr-only">Tìm thiết bị</span><input value={search} onChange={event => setSearch(event.target.value)} placeholder="Tìm theo mã hoặc tên thiết bị" /></label>
        <label className="filter-field"><span className="sr-only">Lọc kết nối</span><select value={statusFilter} onChange={event => setStatusFilter(event.target.value)}><option value="all">Kết nối: Tất cả</option><option value="ONLINE">Online</option><option value="OFFLINE">Offline</option><option value="unknown">Chưa xác định</option></select></label>
        <button className="icon-button" onClick={retry} aria-label="Tải lại danh sách" title="Tải lại danh sách"><Icon name="refresh" /></button>
      </div>
      {loading && <p role="status">Đang tải thiết bị…</p>}
      {error && <div className="notice-error" role="alert"><span>{error}</span><button className="outline-button" onClick={retry}>Thử lại</button></div>}
      {!loading && !error && devices.length === 0 && <p>Chưa có thiết bị được gán cho bạn.</p>}
      {devices.length > 0 && <div className="device-table-wrap"><table className="device-table"><thead><tr><th>Thiết bị</th><th>Loại / Model</th><th>Quản lý</th><th>Kết nối</th><th>Hoạt động cuối</th><th><span className="sr-only">Thao tác</span></th></tr></thead><tbody>{visibleDevices.map(device => <tr key={device.id}>
        <td><div className="device-name-cell"><span className="device-icon"><Icon name="device" /></span><div><strong>{displayValue(device.name)}</strong><small>{device.device_code}</small></div></div></td>
        <td>{displayValue(device.model)}</td><td className="muted-cell">{displayValue(device.lifecycle_state)}</td>
        <td><ConnectionBadge status={device.status} isStale={device.isStale} /></td><td>{formatLastSeen(device.last_seen)}</td>
        <td><button className="outline-button" onClick={() => onOpenDevice(device)}>Xem chi tiết <Icon name="arrow" size={17} /></button></td>
      </tr>)}</tbody></table>{visibleDevices.length === 0 && <p className="empty-result">Không tìm thấy thiết bị phù hợp.</p>}</div>}

      {canManage && registerOpen && <section id="register-panel" ref={registerPanelRef} className="register-panel" aria-labelledby="register-heading"><div className="section-heading"><div><h2 id="register-heading">Đăng ký thiết bị</h2><p>Thêm thiết bị mới vào hệ thống</p></div></div><form className="device-form" onSubmit={submitRegistration}>
        <label>Mã thiết bị<input required value={fields.device_code} placeholder="Nhập mã thiết bị" onChange={event => setFields(current => ({ ...current, device_code: event.target.value }))} /></label>
        <label>Tên thiết bị<input required value={fields.name} placeholder="Nhập tên thiết bị" onChange={event => setFields(current => ({ ...current, name: event.target.value }))} /></label>
        <label>Loại / Model<input required value={fields.model} placeholder="Nhập loại hoặc model" onChange={event => setFields(current => ({ ...current, model: event.target.value }))} /></label>
        <div className="form-actions"><button className="outline-button" type="button" disabled={registerBusy} onClick={() => { resetRegistration(); setRegisterOpen(false); }}>Hủy</button><button className="primary-button" disabled={registerBusy} type="submit">{registerBusy ? "Đang gửi…" : "Đăng ký"}</button></div>
      </form>{registerError && <p className="notice-error" role="alert">{registerError}</p>}{registerNotice && <p className="notice-success" role="status">{registerNotice}</p>}</section>}
    </section>
  </AppShell>;
}

export default DeviceListView;
