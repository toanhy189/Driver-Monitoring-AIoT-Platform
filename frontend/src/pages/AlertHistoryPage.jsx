import { useEffect, useRef, useState } from "react";
import AppShell, { Icon } from "../components/AppShell.jsx";
import { acknowledgeAlert, canAcknowledgeAlert, getAlerts, isAlertAcknowledged, mergeAlerts } from "../services/alerts.js";
import { commandTime, commandValue } from "../services/commandDisplay.js";
import { hasPermission } from "../services/permissions.js";
import "../styles/commands.css";

const REFRESH_MS = 10000;
const NO_REALTIME = { connected: false, generation: 0, events: [] };

function AlertHistoryPage({ user, realtime = NO_REALTIME, onDashboard, onDevices, onCommands, onLogout, onUnauthorized }) {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [actionError, setActionError] = useState("");
  const [busyId, setBusyId] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);
  const lastEventSequence = useRef(realtime.events.at(-1)?.sequence ?? 0);
  const actionController = useRef(null);

  useEffect(() => () => actionController.current?.abort(), []);

  useEffect(() => {
    let active = true;
    let timer;
    const controller = new AbortController();
    getAlerts({ signal: controller.signal })
      .then(result => {
        if (!active) return;
        setAlerts(result);
        setError("");
      })
      .catch(requestError => {
        if (!active || requestError.name === "AbortError") return;
        if (requestError.status === 401) onUnauthorized();
        else setError(requestError.status === 404 ?
          "BE chưa có API lịch sử cảnh báo (HTTP 404)." :
          requestError.message || "Không tải được lịch sử cảnh báo.");
      })
      .finally(() => {
        if (!active) return;
        setLoading(false);
        timer = setTimeout(() => setReloadKey(value => value + 1), REFRESH_MS);
      });
    return () => { active = false; clearTimeout(timer); controller.abort(); };
  }, [reloadKey, realtime.generation, onUnauthorized]);

  useEffect(() => {
    for (const event of realtime.events) {
      if (event.sequence <= lastEventSequence.current) continue;
      lastEventSequence.current = event.sequence;
      if (event.type === "alert.created") setReloadKey(value => value + 1);
    }
  }, [realtime.events]);

  const acknowledge = async alert => {
    if (!hasPermission(user?.role, "alert:acknowledge") || !canAcknowledgeAlert(alert) || busyId) return;
    const controller = new AbortController();
    actionController.current = controller;
    setBusyId(alert.alert_id);
    setActionError("");
    setNotice("");
    try {
      const result = await acknowledgeAlert(alert.alert_id, { signal: controller.signal });
      if (controller.signal.aborted) return;
      if (result && isAlertAcknowledged(result)) {
        setAlerts(current => mergeAlerts(current, [result]));
        setNotice(`Đã xác nhận cảnh báo ${alert.alert_id}.`);
      } else {
        setNotice("BE đã nhận yêu cầu. Đang tải lại trạng thái cảnh báo.");
        setReloadKey(value => value + 1);
      }
    } catch (requestError) {
      if (requestError.name === "AbortError") return;
      if (requestError.status === 401) onUnauthorized();
      else setActionError(requestError.message || "Không xác nhận được cảnh báo.");
    } finally {
      if (actionController.current === controller) actionController.current = null;
      setBusyId(null);
    }
  };

  return <AppShell user={user} activePage="alerts" serverConnected={realtime.connected}
    onDashboard={onDashboard} onDevices={onDevices} onCommands={() => onCommands()}
    onAlerts={() => {}} onLogout={onLogout}>
    <div className="page-title"><h1>Cảnh báo</h1><p>Lịch sử cảnh báo của các thiết bị bạn được phép xem</p></div>
    <section className="surface-card history-panel" aria-label="Lịch sử cảnh báo">
      <div className="section-heading"><div><h2>Các cảnh báo</h2><p>Xác nhận đã xem chỉ cập nhật cảnh báo, không thay đổi ACK của lệnh thiết bị.</p></div>
        <button className="outline-button" type="button" onClick={() => setReloadKey(value => value + 1)}><Icon name="refresh" size={17} /> Tải lại</button></div>
      {loading && <p role="status">Đang tải cảnh báo…</p>}
      {error && <p className="notice-error" role="alert">{error}</p>}
      {actionError && <p className="notice-error" role="alert">{actionError}</p>}
      {notice && <p className="notice-success" role="status">{notice}</p>}
      {!loading && !error && alerts.length === 0 && <p>Chưa có cảnh báo nào.</p>}
      {alerts.length > 0 && <div className="history-table-wrap"><table className="history-table"><thead><tr>
        <th>Mã cảnh báo</th><th>Thiết bị</th><th>Loại</th><th>Mức</th><th>Thời gian</th><th>Trạng thái</th><th>Lệnh liên quan</th><th>Thao tác</th>
      </tr></thead><tbody>{alerts.map(alert => <tr key={alert.alert_id}>
        <td><strong>{alert.alert_id}</strong></td>
        <td>{commandValue(alert.device_code ?? alert.device_id)}</td>
        <td>{commandValue(alert.alert_type ?? alert.type)}</td>
        <td>{Number.isInteger(alert.severity) ? `Mức ${alert.severity}` : "—"}</td>
        <td>{commandTime(alert.created_at ?? alert.timestamp)}</td>
        <td>{isAlertAcknowledged(alert) ? "Đã xem" : commandValue(alert.status)}</td>
        <td>{alert.request_id && hasPermission(user?.role, "command:view") ?
          <button className="text-link" type="button" onClick={() => onCommands(alert)}>{alert.request_id}</button> :
          commandValue(alert.request_id)}</td>
        <td>{hasPermission(user?.role, "alert:acknowledge") && canAcknowledgeAlert(alert) ?
          <button className="outline-button" type="button" disabled={busyId !== null} onClick={() => acknowledge(alert)}>
            {busyId === alert.alert_id ? "Đang gửi…" : "Đã xem"}
          </button> : "—"}</td>
      </tr>)}</tbody></table></div>}
    </section>
  </AppShell>;
}

export default AlertHistoryPage;
