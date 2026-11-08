import { useEffect, useState } from "react";
import AppShell, { ConnectionBadge, Icon } from "./AppShell.jsx";
import { getDevices } from "../services/devices.js";
import { getUserDevices, getUsers, createUser, updateUser, assignUserDevice, unassignUserDevice } from "../services/users.js";
import { displayValue, formatLastSeen } from "../services/deviceDisplay.js";
import { authenticatedRequest } from "../services/api.js";
import "../styles/admin.css";

function AdminDashboard({ user, realtime, onLogout, onUnauthorized, onOpenDevices, onOpenDevice, onOpenCommands, onOpenAlerts }) {
  const [section, setSection] = useState("devices");
  const [users, setUsers] = useState([]);
  const [devices, setDevices] = useState([]);
  const [selectedUser, setSelectedUser] = useState(null);
  const [userDevices, setUserDevices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [userDevicesLoading, setUserDevicesLoading] = useState(false);
  const [userDevicesError, setUserDevicesError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [busy, setBusy] = useState(false);
  const [assignmentReload, setAssignmentReload] = useState(0);
  const [assignId, setAssignId] = useState("");
  const [newUser, setNewUser] = useState({ fullname: "", username: "", email: "", phone: "", password: "", confirm_password: "", role: "Customer" });
  const [storage, setStorage] = useState(null);
  useEffect(() => {
    const interval = setInterval(() => {
      getDevices().then(setDevices).catch(cause => { if (cause.status === 401) onUnauthorized(); });
      authenticatedRequest("/videos/storage").then(setStorage).catch(() => {});
    }, 10000);
    return () => clearInterval(interval);
  }, [onUnauthorized]);
  useEffect(() => {
    const controller = new AbortController();
    authenticatedRequest("/videos/storage", { signal: controller.signal }).then(setStorage).catch(() => {});
    return () => controller.abort();
  }, [reloadKey]);
  async function mutate(action) {
    setBusy(true); setError("");
    try { await action(); setReloadKey(value => value + 1); setAssignmentReload(value => value + 1); }
    catch (cause) { if (cause.status === 401) onUnauthorized(); else setError(cause.message); }
    finally { setBusy(false); }
  }

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    Promise.all([
      getUsers({ signal: controller.signal }),
      getDevices({ signal: controller.signal }),
    ]).then(([userRows, deviceRows]) => {
      if (controller.signal.aborted) return;
      setUsers(userRows);
      setDevices(deviceRows);
    }).catch(cause => {
      if (cause.name === "AbortError") return;
      if (cause.status === 401) onUnauthorized();
      else setError(cause.message);
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [reloadKey, onUnauthorized]);

  useEffect(() => {
    if (!selectedUser) {
      setUserDevices([]);
      setUserDevicesError("");
      return undefined;
    }
    const controller = new AbortController();
    setUserDevicesLoading(true);
    setUserDevicesError("");
    getUserDevices(selectedUser.id, { signal: controller.signal })
      .then(items => { if (!controller.signal.aborted) setUserDevices(items); })
      .catch(cause => {
        if (cause.name === "AbortError") return;
        if (cause.status === 401) onUnauthorized();
        else setUserDevicesError(cause.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setUserDevicesLoading(false);
      });
    return () => controller.abort();
  }, [selectedUser, onUnauthorized, assignmentReload]);

  const onlineCount = devices.filter(device => device.status === "ONLINE").length;
  const offlineCount = devices.filter(device => device.status === "OFFLINE").length;
  const otherCount = devices.length - onlineCount - offlineCount;

  return <AppShell
    user={user}
    activePage="dashboard"
    serverConnected={realtime?.connected}
    onDashboard={() => {}}
    onDevices={onOpenDevices}
    onCommands={onOpenCommands}
    onAlerts={onOpenAlerts}
    onLogout={onLogout}
  >
    <div className="page-title page-title--actions">
      <div><h1>Quản trị hệ thống</h1><p>Quản lý người dùng, thiết bị và trạng thái kết nối</p></div>
      <button className="outline-button" type="button" onClick={() => setReloadKey(value => value + 1)}>
        <Icon name="refresh" /> Làm mới
      </button>
    </div>

    <section className="admin-stats" aria-label="Tổng quan hệ thống">
      <div className="stat-card"><span className="stat-icon stat-icon--blue"><Icon name="user" size={27} /></span><div><span>Người dùng</span><strong>{loading ? "—" : users.length}</strong></div></div>
      <div className="stat-card"><span className="stat-icon stat-icon--blue"><Icon name="device" size={27} /></span><div><span>Tổng thiết bị</span><strong>{loading ? "—" : devices.length}</strong></div></div>
      <div className="stat-card"><span className="stat-icon stat-icon--green"><Icon name="wifi" size={29} /></span><div><span>Đang trực tuyến</span><strong className="text-green">{loading ? "—" : onlineCount}</strong></div></div>
      <div className="stat-card"><span className="stat-icon stat-icon--red"><Icon name="wifiOff" size={29} /></span><div><span>Ngoại tuyến / khác</span><strong className="text-red">{loading ? "—" : offlineCount + otherCount}</strong></div></div>
    </section>

    <div className="admin-tabs" role="tablist" aria-label="Khu vực quản trị">
      <button type="button" role="tab" aria-selected={section === "devices"} className={section === "devices" ? "active" : ""} onClick={() => setSection("devices")}>
        <Icon name="device" /> Thiết bị
      </button>
      <button type="button" role="tab" aria-selected={section === "users"} className={section === "users" ? "active" : ""} onClick={() => setSection("users")}>
        <Icon name="user" /> Người dùng
      </button>
    </div>

    {error && <div className="notice-error" role="alert"><span>{error}</span><button className="outline-button" onClick={() => setReloadKey(value => value + 1)}>Thử lại</button></div>}
    {storage && <p className={storage.warning ? "notice-error" : "device-note"} role="status">Video: {(storage.used_bytes / 1048576).toFixed(1)} / {(storage.max_bytes / 1048576).toFixed(0)} MB. Chỉ xóa thủ công.{storage.warning && " Bộ nhớ gần đầy; cần xóa các clip đã xem hoặc tăng dung lượng."}</p>}
    {loading && <p role="status">Đang tải dữ liệu quản trị…</p>}

    {!loading && !error && section === "devices" && <section className="surface-card admin-panel" aria-labelledby="admin-devices-heading">
      <div className="section-heading">
        <div><h2 id="admin-devices-heading">Toàn bộ thiết bị</h2><p>Xem trạng thái và mở trang thao tác thiết bị.</p></div>
        <button className="primary-button" type="button" onClick={onOpenDevices}><Icon name="settings" /> Quản lý thiết bị</button>
      </div>
      {devices.length === 0 ? <p>Chưa có thiết bị trong hệ thống.</p> : <div className="device-table-wrap"><table className="device-table">
        <thead><tr><th>Thiết bị</th><th>Loại / Model</th><th>Trạng thái quản lý</th><th>Kết nối</th><th>Hoạt động cuối</th><th /></tr></thead>
        <tbody>{devices.map(device => <tr key={device.id}>
          <td><div className="device-name-cell"><span className="device-icon"><Icon name="device" /></span><div><strong>{displayValue(device.name)}</strong><small>{device.device_code}</small></div></div></td>
          <td>{displayValue(device.model)}</td><td className="muted-cell">{displayValue(device.lifecycle_state)}</td>
          <td><ConnectionBadge status={device.status} /></td><td>{formatLastSeen(device.last_seen)}</td>
          <td><button className="outline-button" type="button" onClick={() => onOpenDevice(device)}>Chi tiết <Icon name="arrow" size={17} /></button></td>
        </tr>)}</tbody>
      </table></div>}
    </section>}

    {!loading && !error && section === "users" && <section className="surface-card admin-panel" aria-labelledby="admin-users-heading">
      <div className="section-heading"><div><h2 id="admin-users-heading">Người dùng</h2><p>Quản lý tài khoản và các thiết bị được gán.</p></div></div>
      <details><summary>Tạo tài khoản</summary><form className="config-actions" onSubmit={event => { event.preventDefault(); mutate(async () => { await createUser(newUser); setNewUser({ ...newUser, username: "", password: "", confirm_password: "" }); }); }}>
        {[["fullname", "Họ tên", "text"], ["username", "Tên đăng nhập", "text"], ["email", "Email", "email"], ["phone", "Điện thoại", "tel"], ["password", "Mật khẩu", "password"], ["confirm_password", "Nhập lại mật khẩu", "password"]].map(([key, label, type]) => <label key={key}>{label}<input required type={type} minLength={type === "password" ? 8 : undefined} value={newUser[key]} onChange={event => setNewUser({ ...newUser, [key]: event.target.value })} /></label>)}
        <label>Vai trò<select value={newUser.role} onChange={event => setNewUser({ ...newUser, role: event.target.value })}>{["Admin", "Employee", "Customer"].map(role => <option key={role}>{role}</option>)}</select></label><button className="primary-button" disabled={busy}>Tạo tài khoản</button>
      </form></details>
      {users.length === 0 ? <p>Chưa có người dùng.</p> : <div className="device-table-wrap"><table className="device-table">
        <thead><tr><th>Người dùng</th><th>Tên đăng nhập</th><th>Email</th><th>Điện thoại</th><th>Vai trò</th><th /></tr></thead>
        <tbody>{users.map(item => <tr key={item.id}>
          <td>{displayValue(item.fullname)}</td><td>{item.username}</td><td>{displayValue(item.email)}</td><td>{displayValue(item.phone)}</td><td>{item.role}</td>
          <td><div className="config-actions"><select aria-label={`Vai trò ${item.username}`} value={item.role} disabled={busy || item.id === user.id} onChange={event => { const role = event.target.value; if (window.confirm(`Đổi vai trò ${item.username} thành ${role}? Các phiên của tài khoản này sẽ kết thúc.`)) mutate(() => updateUser(item.id, { role })); }}>{["Admin", "Employee", "Customer"].map(role => <option key={role}>{role}</option>)}</select>
            <button className="outline-button" disabled={busy || item.id === user.id} onClick={() => { if (window.confirm(`${item.status === "DISABLED" ? "Mở khóa" : "Khóa"} tài khoản ${item.username}?`)) mutate(() => updateUser(item.id, { status: item.status === "DISABLED" ? "ACTIVE" : "DISABLED" })); }}>{item.status === "DISABLED" ? "Mở khóa" : "Khóa"}</button>
            <button className="outline-button" type="button" onClick={() => setSelectedUser(item)}>Thiết bị được gán</button></div></td>
        </tr>)}</tbody>
      </table></div>}
      {selectedUser && <section className="admin-user-devices" aria-live="polite">
        <form className="config-actions" onSubmit={event => { event.preventDefault(); mutate(() => assignUserDevice(selectedUser.id, Number(assignId))); }}><label>Gán thiết bị<select required value={assignId} onChange={event => setAssignId(event.target.value)}><option value="">Chọn thiết bị</option>{devices.filter(device => device.lifecycle_state !== "DECOMMISSIONED" && !userDevices.some(item => item.id === device.id)).map(device => <option value={device.id} key={device.id}>{device.device_code} — {device.name || device.model}</option>)}</select></label><button className="primary-button" disabled={busy || !assignId}>Gán</button></form>
        <div className="section-heading"><div><h3>Thiết bị của {selectedUser.fullname || selectedUser.username}</h3><p>Chỉ hiển thị assignment đang còn hiệu lực.</p></div>
          <button className="icon-button" type="button" aria-label="Đóng danh sách thiết bị người dùng" onClick={() => setSelectedUser(null)}>×</button>
        </div>
        {userDevicesLoading && <p role="status">Đang tải thiết bị…</p>}
        {userDevicesError && <p className="notice-error" role="alert">{userDevicesError}</p>}
        {!userDevicesLoading && !userDevicesError && userDevices.length === 0 && <p>Người dùng chưa được gán thiết bị nào.</p>}
        {!userDevicesLoading && !userDevicesError && userDevices.length > 0 && <div className="device-table-wrap"><table className="device-table">
          <thead><tr><th>Thiết bị</th><th>Loại / Model</th><th>Trạng thái quản lý</th><th>Kết nối</th><th>Hoạt động cuối</th></tr></thead>
          <tbody>{userDevices.map(device => <tr key={device.id}>
            <td><strong>{displayValue(device.name)}</strong><small className="admin-device-code">{device.device_code}</small></td>
            <td>{displayValue(device.model)}</td><td className="muted-cell">{displayValue(device.lifecycle_state)}</td><td><ConnectionBadge status={device.status} /></td><td>{formatLastSeen(device.last_seen)} <button className="outline-button" disabled={busy} onClick={() => { if (window.confirm(`Thu hồi quyền của ${selectedUser.username} với ${device.device_code}?`)) mutate(() => unassignUserDevice(selectedUser.id, device.id)); }}>Thu hồi</button></td>
          </tr>)}</tbody>
        </table></div>}
      </section>}
    </section>}
  </AppShell>;
}

export default AdminDashboard;
