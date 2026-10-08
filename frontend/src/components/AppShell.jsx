import { hasPermission } from "../services/permissions.js";

const paths = {
  wheel: <><circle cx="12" cy="12" r="10" /><circle cx="12" cy="11" r="3" /><path d="M3 9h6m6 0h6M12 14v8M3.5 10.5C6 11 8 12 9 14m11.5-3.5C18 11 16 12 15 14" /></>,
  home: <><path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z" /></>,
  device: <><rect x="6" y="2.5" width="12" height="19" rx="2" /><path d="M10 18h4" /></>,
  alert: <><path d="m12 3 10 18H2L12 3Z" /><path d="M12 9v5m0 3h.01" /></>,
  commands: <><rect x="4" y="3" width="16" height="18" rx="2" /><path d="M8 8h8M8 12h8M8 16h5" /></>,
  logout: <><path d="M10 17l5-5-5-5m5 5H3" /><path d="M12 3h7a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-7" /></>,
  user: <><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></>,
  wifi: <><path d="M2 8a16 16 0 0 1 20 0M5 12a11 11 0 0 1 14 0m-11 4a6 6 0 0 1 8 0" /><circle cx="12" cy="20" r="1" fill="currentColor" stroke="none" /></>,
  wifiOff: <><path d="M2 8a16 16 0 0 1 20 0M5 12a11 11 0 0 1 14 0m-11 4a6 6 0 0 1 8 0M3 3l18 18" /></>,
  search: <><circle cx="11" cy="11" r="7" /><path d="m16 16 5 5" /></>,
  refresh: <><path d="M20 11a8 8 0 1 0-2 6M20 4v7h-7" /></>,
  plus: <><path d="M12 4v16M4 12h16" /></>,
  arrow: <><path d="M4 12h16m-6-6 6 6-6 6" /></>,
  back: <><path d="M20 12H4m6-6-6 6 6 6" /></>,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v6m0-10h.01" /></>,
  settings: <><circle cx="12" cy="12" r="3" /><path d="M12 2v3m0 14v3M2 12h3m14 0h3M5 5l2 2m10 10 2 2M19 5l-2 2M7 17l-2 2" /></>,
  play: <><path d="m8 4 12 8-12 8V4Z" /></>,
  wrench: <><path d="M20 6a6 6 0 0 1-8 7l-7 7a2 2 0 0 1-3-3l7-7a6 6 0 0 1 7-8l-3 3 3 3 4-2Z" /></>,
  stop: <><rect x="5" y="5" width="14" height="14" rx="2" /></>,
};

export function Icon({ name, size = 20, className = "" }) {
  return <svg className={className} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

export function ConnectionBadge({ status, isStale = false }) {
  const state = status === "ONLINE" ? "online" : status === "OFFLINE" ? "offline" : "unknown";
  const text = state === "unknown" ? "CHƯA XÁC ĐỊNH" : status;
  return <span className={`status-badge status-badge--${isStale ? "unknown" : state}`}>
    <span className="badge-dot" />{text}{isStale && state !== "unknown" ? " (gần nhất)" : ""}
  </span>;
}

function AppShell({ user, activePage, serverConnected, onDashboard, onDevices, onCommands, onAlerts, onLogout, children }) {
  const connectionClass = serverConnected === true ? "online" : serverConnected === false ? "offline" : "unknown";
  const connectionLabel = serverConnected === true ? "Máy chủ đã kết nối" : serverConnected === false ? "Mất kết nối máy chủ" : "Chưa xác định kết nối máy chủ";
  return <div className="app-shell">
    <aside className="app-sidebar">
      <div className="brand"><span className="brand-mark"><Icon name="wheel" size={30} /></span><div><strong>DRIVER MONITOR</strong><small>Giám sát tài xế AIoT</small></div></div>
      <nav className="side-nav" aria-label="Điều hướng chính">
        <button className={activePage === "dashboard" ? "active" : ""} onClick={onDashboard} aria-current={activePage === "dashboard" ? "page" : undefined}><Icon name="home" />Tổng quan</button>
        <button className={activePage === "devices" ? "active" : ""} onClick={onDevices} aria-current={activePage === "devices" ? "page" : undefined}><Icon name="device" />Thiết bị</button>
        {hasPermission(user?.role, "command:view") && <button className={activePage === "commands" ? "active" : ""} onClick={onCommands} aria-current={activePage === "commands" ? "page" : undefined}><Icon name="commands" />Lịch sử lệnh</button>}
        {hasPermission(user?.role, "alert:view") && <button className={activePage === "alerts" ? "active" : ""} onClick={onAlerts} aria-current={activePage === "alerts" ? "page" : undefined} disabled={!onAlerts}><Icon name="alert" />Cảnh báo</button>}
      </nav>
      <div className="sidebar-user"><span className="avatar"><Icon name="user" /></span><div><strong>{user?.fullname || user?.username || "Người dùng"}</strong><small>{user?.role}{!hasPermission(user?.role, "command:send") && " · Chỉ xem"}</small></div></div>
    </aside>
    <div className="app-workspace">
      <header className="app-topbar"><span className={`connection-status connection-status--${connectionClass}`}><span className="badge-dot" />{connectionLabel}</span><span className="topbar-user"><span className="avatar"><Icon name="user" /></span>{user?.fullname || user?.username || "Người dùng"}</span><button className="topbar-logout" onClick={onLogout} aria-label="Đăng xuất" title="Đăng xuất"><Icon name="logout" /></button></header>
      <main className="app-content">{children}</main>
    </div>
  </div>;
}

export default AppShell;
