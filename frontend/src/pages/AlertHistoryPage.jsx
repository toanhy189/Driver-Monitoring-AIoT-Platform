import { useEffect, useRef, useState } from "react";
import AppShell, { Icon } from "../components/AppShell.jsx";
import FeedbackDialog from "../components/FeedbackDialog.jsx";
import { acknowledgeAlert, getAlerts } from "../services/alerts.js";
import { canAcknowledgeAlert, isAlertAcknowledged, mergeAlerts } from "../services/alertModel.js";
import { alertStatusLabel, alertTypeLabel } from "../services/alertDisplay.js";
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
  const [feedback, setFeedback] = useState(null);
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
          "Không tìm thấy dữ liệu lịch sử cảnh báo (HTTP 404)." :
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
        setNotice("Đã đánh dấu cảnh báo là đã xem.");
        setFeedback({ tone: "success", title: "Đã đánh dấu là đã xem", message: "Trạng thái cảnh báo đã được cập nhật." });
      } else {
        setNotice("BE đã nhận yêu cầu. Đang tải lại trạng thái cảnh báo.");
        setFeedback({ tone: "success", title: "Đã nhận yêu cầu", message: "Đang tải lại trạng thái cảnh báo để kiểm tra kết quả." });
        setReloadKey(value => value + 1);
      }
    } catch (requestError) {
      if (requestError.name === "AbortError") return;
      if (requestError.status === 401) onUnauthorized();
      else {
        const message = requestError.message || "Không xác nhận được cảnh báo.";
        setActionError(message);
        setFeedback({ tone: "error", title: "Chưa đánh dấu được", message });
      }
    } finally {
      if (actionController.current === controller) actionController.current = null;
      setBusyId(null);
    }
  };

  const canManageAlerts = hasPermission(user?.role, "alert:acknowledge");

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
        <th>Thiết bị</th><th>Loại cảnh báo</th><th>Mức</th><th>Thời gian</th><th>Trạng thái</th><th>Lệnh liên quan</th>{canManageAlerts && <th>Thao tác</th>}
      </tr></thead><tbody>{alerts.map(alert => <tr key={alert.alert_id}>
        <td>{commandValue(alert.device_code ?? alert.device_id)}</td>
        <td>{alertTypeLabel(alert.alert_type ?? alert.type)}</td>
        <td>{Number.isInteger(alert.severity) ? `Mức ${alert.severity}` : "Chưa phân mức"}</td>
        <td>{commandTime(alert.created_at ?? alert.timestamp)}</td>
        <td><span className={`alert-state ${isAlertAcknowledged(alert) ? "alert-state--seen" : "alert-state--new"}`}>{alertStatusLabel(alert)}</span></td>
        <td>{alert.request_id && hasPermission(user?.role, "command:view") ?
          <button className="text-link" type="button" onClick={() => onCommands(alert)}>Xem lệnh</button> :
          "Không có"}</td>
        {canManageAlerts && <td>{canAcknowledgeAlert(alert) ?
          <button className="outline-button" type="button" disabled={busyId !== null} onClick={() => acknowledge(alert)}>
            {busyId === alert.alert_id ? "Đang gửi…" : "Đánh dấu đã xem"}
          </button> : <span className="alert-action-done">{isAlertAcknowledged(alert) ? "✓ Đã đánh dấu" : "Không thể đánh dấu"}</span>}</td>}
      </tr>)}</tbody></table></div>}
    </section>
    <FeedbackDialog feedback={feedback} onClose={() => setFeedback(null)} />
  </AppShell>;
}

export default AlertHistoryPage;
