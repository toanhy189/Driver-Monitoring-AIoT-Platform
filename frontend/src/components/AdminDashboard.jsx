import { useEffect, useState } from "react";
import AppShell, { ConnectionBadge, Icon } from "./AppShell.jsx";
import { getDevices } from "../services/devices.js";
import { getUserDevices, getUsers } from "../services/users.js";
import { displayValue, formatLastSeen } from "../services/deviceDisplay.js";
import "../styles/admin.css";

function AdminDashboard({ user, realtime, onLogout, onUnauthorized, onOpenDevices, onOpenDevice }) {
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
  }, [selectedUser, onUnauthorized]);

  const onlineCount = devices.filter(device => device.status === "ONLINE").length;
  const offlineCount = devices.filter(device => device.status === "OFFLINE").length;
  const otherCount = devices.length - onlineCount - offlineCount;

  return <AppShell
    user={user}
    activePage="dashboard"
    serverConnected={realtime?.connected}
    onDashboard={() => {}}
    onDevices={onOpenDevices}
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
      <div className="section-heading"><div><h2 id="admin-users-heading">Người dùng</h2><p>Tra cứu tài khoản và các thiết bị đang được gán.</p></div></div>
      {users.length === 0 ? <p>Chưa có người dùng.</p> : <div className="device-table-wrap"><table className="device-table">
        <thead><tr><th>Người dùng</th><th>Tên đăng nhập</th><th>Email</th><th>Điện thoại</th><th>Vai trò</th><th /></tr></thead>
        <tbody>{users.map(item => <tr key={item.id}>
          <td>{displayValue(item.fullname)}</td><td>{item.username}</td><td>{displayValue(item.email)}</td><td>{displayValue(item.phone)}</td><td>{item.role}</td>
          <td><button className="outline-button" type="button" onClick={() => setSelectedUser(item)}>Thiết bị được gán</button></td>
        </tr>)}</tbody>
      </table></div>}
      {selectedUser && <section className="admin-user-devices" aria-live="polite">
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
            <td>{displayValue(device.model)}</td><td className="muted-cell">{displayValue(device.lifecycle_state)}</td><td><ConnectionBadge status={device.status} /></td><td>{formatLastSeen(device.last_seen)}</td>
          </tr>)}</tbody>
        </table></div>}
      </section>}
    </section>}
  </AppShell>;
}

export default AdminDashboard;
