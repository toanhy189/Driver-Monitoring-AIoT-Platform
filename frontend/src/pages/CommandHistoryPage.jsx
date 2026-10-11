import { useEffect, useRef, useState } from "react";
import AppShell, { Icon } from "../components/AppShell.jsx";
import { collapseCommands, commandBelongsToDevice, getCommands, keepNewerCommand, normalizeCommand } from "../services/commands.js";
import { commandStatus, commandTime, commandValue } from "../services/commandDisplay.js";
import "../styles/commands.css";

const REFRESH_MS = 10000;

const NO_REALTIME = { connected: false, generation: 0, events: [] };

function CommandHistoryPage({ user, realtime = NO_REALTIME, deviceId, deviceCode, onBack, onDashboard, onDevices, onAlerts, onLogout, onUnauthorized }) {
  const [commands, setCommands] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const lastEventSequence = useRef(realtime.events.at(-1)?.sequence ?? 0);
  const pendingUpdates = useRef([]);
  const requestInFlight = useRef(false);

  useEffect(() => {
    let active = true;
    let timer;
    const controller = new AbortController();
    pendingUpdates.current = [];
    requestInFlight.current = true;
    getCommands({ deviceId, signal: controller.signal })
      .then(result => {
        if (!active) return;
        const matching = deviceId == null ? result : result.filter(command =>
          commandBelongsToDevice(command, deviceId, deviceCode, { requireIdentity: true }));
        setCommands(collapseCommands(matching.map(command =>
          pendingUpdates.current.reduce((current, update) =>
            keepNewerCommand(current, update), command))));
        setError("");
      })
      .catch(requestError => {
        if (!active || requestError.name === "AbortError") return;
        if (requestError.status === 401) onUnauthorized();
        else setError(requestError.status === 404 ?
          "BE chưa có API lịch sử lệnh. Chưa thể lấy kết quả lệnh đã lưu." :
          requestError.message || "Không tải được lịch sử lệnh.");
      })
      .finally(() => {
        if (active) {
          requestInFlight.current = false;
          setLoading(false);
          timer = setTimeout(() => setReloadKey(value => value + 1), REFRESH_MS);
        }
      });
    return () => { active = false; clearTimeout(timer); controller.abort(); requestInFlight.current = false; };
  }, [deviceId, deviceCode, reloadKey, realtime.generation, onUnauthorized]);

  useEffect(() => {
    for (const event of realtime.events) {
      if (event.sequence <= lastEventSequence.current) continue;
      lastEventSequence.current = event.sequence;
      if (event.type !== "command.updated") continue;
      let update;
      try { update = normalizeCommand(event.data); } catch { continue; }
      if (deviceId != null && !commandBelongsToDevice(update, deviceId, deviceCode, { requireIdentity: true })) continue;
      if (requestInFlight.current) pendingUpdates.current.push(update);
      setCommands(current => current.map(command =>
        command.request_id === update.request_id ? keepNewerCommand(command, update) : command));
      if (!commands.some(command => command.request_id === update.request_id)) {
        setReloadKey(value => value + 1);
      }
    }
  }, [realtime.events, deviceId, deviceCode, commands]);

  const retry = () => { setError(""); setLoading(true); setReloadKey(value => value + 1); };

  return <AppShell user={user} activePage="commands" serverConnected={realtime.connected} onDashboard={onDashboard} onDevices={onDevices} onCommands={() => {}} onAlerts={onAlerts} onLogout={onLogout}>
    <div className="page-title"><h1>Lịch sử lệnh</h1><p>{deviceId == null ? "Các lệnh trên thiết bị bạn được phép xem" : `Thiết bị ${deviceCode || `#${deviceId}`}`}</p></div>
    {deviceId != null && <button className="text-link back-link" onClick={onBack}><Icon name="back" size={18} /> Quay lại thiết bị</button>}
    <section className="surface-card history-panel" aria-label="Danh sách lệnh">
      <div className="section-heading"><div><h2>Các lệnh đã gửi</h2><p>Kết quả hoàn tất chỉ dựa trên ACK do BE ghi nhận.</p></div><button className="outline-button" onClick={retry}><Icon name="refresh" size={17} /> Tải lại</button></div>
      {loading && <p role="status">Đang tải lịch sử lệnh…</p>}
      {error && <p className="notice-error" role="alert">{error}</p>}
      {!loading && !error && commands.length === 0 && <p>Chưa có lệnh nào.</p>}
      {commands.length > 0 && <div className="history-table-wrap"><table className="history-table"><thead><tr><th>Mã lệnh</th><th>Thiết bị</th><th>Action</th><th>Người gửi</th><th>Thời gian</th><th>Kết quả</th><th>ACK</th><th>Lỗi</th><th>Độ trễ</th></tr></thead><tbody>{commands.map(command => {
        const state = commandStatus(command);
        const latency = Number.isFinite(command.latency_ms) && command.latency_ms >= 0 ? `${command.latency_ms} ms` : "—";
        return <tr key={command.request_id}><td><strong>{command.request_id}</strong></td><td>{commandValue(command.device_code ?? command.device_id)}</td><td>{commandValue(command.action)}</td><td>{commandValue(command.created_by_name ?? command.created_by)}</td><td>{commandTime(command.created_at)}</td><td><span className={`command-state command-state--${state.tone}`}>{state.label}</span></td><td>{commandValue(command.ack_status)}</td><td>{commandValue(command.error_message ?? command.error_code)}</td><td>{latency}</td></tr>;
      })}</tbody></table></div>}
    </section>
  </AppShell>;
}

export default CommandHistoryPage;
