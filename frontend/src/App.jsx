import { useCallback, useEffect, useState } from "react";

import Login from "./components/Login.jsx";
import Dashboard from "./components/Dashboard.jsx";
import DeviceListPage from "./pages/DeviceListPage.jsx";
import DeviceDetailPage from "./pages/DeviceDetailPage.jsx";
import CommandHistoryPage from "./pages/CommandHistoryPage.jsx";
import RemoteConfigPage from "./pages/RemoteConfigPage.jsx";
import AlertHistoryPage from "./pages/AlertHistoryPage.jsx";
import { getCurrentUser } from "./services/auth.js";
import { hasPermission } from "./services/permissions.js";
import { DASHBOARD_VIEW, currentView, ensureView, hasPreviousView, pushView, replaceView } from "./services/navigation.js";
import useRealtime from "./hooks/useRealtime.js";

function App() {
  const [session, setSession] = useState(() => ({
    status: localStorage.getItem("access_token") ? "checking" : "anonymous",
    user: null,
    error: "",
  }));
  const [checkAttempt, setCheckAttempt] = useState(0);
  const [view, setView] = useState(currentView);
  const realtime = useRealtime(session.status === "authenticated" &&
    hasPermission(session.user?.role, "dashboard:view") ? session.user?.id : null);

  const handleLogout = useCallback(() => {
    localStorage.removeItem("access_token");
    replaceView(DASHBOARD_VIEW, null);
    setSession({ status: "anonymous", user: null, error: "" });
    setView(DASHBOARD_VIEW);
  }, []);

  useEffect(() => {
    if (session.status !== "checking") return;

    const token = localStorage.getItem("access_token");
    if (!token) {
      setSession({ status: "anonymous", user: null, error: "" });
      return;
    }

    let active = true;
    const controller = new AbortController();

    getCurrentUser({ token, signal: controller.signal })
      .then(user => {
        if (active) {
          setView(ensureView(user.id));
          setSession({ status: "authenticated", user, error: "" });
        }
      })
      .catch(error => {
        if (!active || error.name === "AbortError") return;
        if (error.status === 401) {
          handleLogout();
        } else {
          setSession({
            status: "checking",
            user: null,
            error: error.message || "Không thể kiểm tra phiên đăng nhập.",
          });
        }
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [session.status, checkAttempt, handleLogout]);

  const handleLogin = useCallback(({ token, user }) => {
    localStorage.setItem("access_token", token);
    replaceView(DASHBOARD_VIEW, user.id);
    setSession({ status: "authenticated", user, error: "" });
    setView(DASHBOARD_VIEW);
  }, []);

  useEffect(() => {
    if (session.status !== "authenticated") return;
    const onPopState = () => setView(ensureView(session.user.id));
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, [session.status, session.user?.id]);

  const navigateTo = useCallback(nextView => {
    pushView(nextView, session.user?.id);
    setView(nextView);
  }, [session.user?.id]);

  const navigateBack = useCallback(fallback => {
    if (hasPreviousView(session.user?.id)) {
      window.history.back();
    } else {
      replaceView(fallback, session.user?.id);
      setView(fallback);
    }
  }, [session.user?.id]);

  if (session.status === "checking") {
    return (
      <main className="login-page">
        <div className="login-card" role="status">
          <h1 className="login-title">Kiểm tra phiên đăng nhập</h1>
          {session.error ? (
            <>
              <p className="login-error" role="alert">{session.error}</p>
              <button className="login-button" onClick={() => {
                setSession(current => ({ ...current, error: "" }));
                setCheckAttempt(attempt => attempt + 1);
              }}>Thử lại</button>
              <button className="login-secondary-button" onClick={handleLogout}>
                Đăng nhập lại
              </button>
            </>
          ) : <p>Đang kiểm tra phiên…</p>}
        </div>
      </main>
    );
  }

  if (session.status === "anonymous") {
    return <Login onLogin={handleLogin} />;
  }

  if (!hasPermission(session.user?.role, "dashboard:view")) {
    return (
      <main className="login-page">
        <div className="login-card">
          <h1 className="login-title">Không có quyền truy cập Dashboard</h1>
          <p>Role của tài khoản chưa được cấp quyền xem trang này.</p>
          <button className="login-button" onClick={handleLogout}>Đăng xuất</button>
        </div>
      </main>
    );
  }

  if (view.page === "devices") {
    return (
      <DeviceListPage
        user={session.user}
        realtime={realtime}
        onBack={() => navigateBack(DASHBOARD_VIEW)}
        onOpenDevice={device => navigateTo({ page: "device-detail", deviceId: device.id, summary: device })}
        onOpenCommands={() => navigateTo({ page: "commands" })}
        onOpenAlerts={() => navigateTo({ page: "alerts" })}
        onLogout={handleLogout}
        onUnauthorized={handleLogout}
      />
    );
  }

  if (view.page === "device-detail") {
    return (
      <DeviceDetailPage
        key={view.deviceId}
        user={session.user}
        realtime={realtime}
        deviceId={view.deviceId}
        summary={view.summary}
        onBack={() => navigateBack({ page: "devices" })}
        onDashboard={() => navigateTo(DASHBOARD_VIEW)}
        onOpenHistory={device => navigateTo({ page: "commands", deviceId: view.deviceId, deviceCode: device?.device_code || view.summary?.device_code })}
        onOpenConfig={device => navigateTo({ page: "config", deviceId: view.deviceId, deviceCode: device?.device_code || view.summary?.device_code, deviceName: device?.name || view.summary?.name, deviceStatus: device?.status })}
        onOpenCommands={() => navigateTo({ page: "commands" })}
        onOpenAlerts={() => navigateTo({ page: "alerts" })}
        onLogout={handleLogout}
        onUnauthorized={handleLogout}
      />
    );
  }

  if (view.page === "commands") {
    return (
      <CommandHistoryPage
        user={session.user}
        realtime={realtime}
        deviceId={view.deviceId}
        deviceCode={view.deviceCode}
        onBack={() => navigateBack({ page: "device-detail", deviceId: view.deviceId })}
        onDashboard={() => navigateTo(DASHBOARD_VIEW)}
        onDevices={() => navigateTo({ page: "devices" })}
        onAlerts={() => navigateTo({ page: "alerts" })}
        onLogout={handleLogout}
        onUnauthorized={handleLogout}
      />
    );
  }

  if (view.page === "config") {
    return (
      <RemoteConfigPage
        key={view.deviceId}
        user={session.user}
        realtime={realtime}
        deviceId={view.deviceId}
        deviceCode={view.deviceCode}
        deviceName={view.deviceName}
        deviceStatus={view.deviceStatus}
        onBack={() => navigateBack({ page: "device-detail", deviceId: view.deviceId })}
        onDashboard={() => navigateTo(DASHBOARD_VIEW)}
        onDevices={() => navigateTo({ page: "devices" })}
        onCommands={() => navigateTo({ page: "commands" })}
        onAlerts={() => navigateTo({ page: "alerts" })}
        onLogout={handleLogout}
        onUnauthorized={handleLogout}
      />
    );
  }

  if (view.page === "alerts") {
    return <AlertHistoryPage
      user={session.user}
      realtime={realtime}
      onDashboard={() => navigateTo(DASHBOARD_VIEW)}
      onDevices={() => navigateTo({ page: "devices" })}
      onCommands={alert => navigateTo(alert && Number.isSafeInteger(alert.device_id) ?
        { page: "commands", deviceId: alert.device_id, deviceCode: alert.device_code } :
        { page: "commands" })}
      onLogout={handleLogout}
      onUnauthorized={handleLogout}
    />;
  }

  return (
    <Dashboard
      user={session.user}
      realtime={realtime}
      onOpenDevices={() => navigateTo({ page: "devices" })}
      onOpenCommands={() => navigateTo({ page: "commands" })}
      onOpenAlerts={() => navigateTo({ page: "alerts" })}
      onLogout={handleLogout}
      onUnauthorized={handleLogout}
    />
  );
}

export default App;
