import { useEffect, useRef, useState } from "react";
import AppShell, { ConnectionBadge, Icon } from "../components/AppShell.jsx";
import { CONFIG_LEVELS, CONFIG_OUTPUTS, MAX_TIMING_MS, configStatus, draftFromTimings, emptyDraft, getDeviceConfig, timingsFromDraft, updateDeviceConfig } from "../services/config.js";
import { deviceApiError } from "../services/deviceDisplay.js";
import { hasPermission } from "../services/permissions.js";
import { matchesDevice } from "../services/realtime.js";
import "../styles/config.css";

const REFRESH_MS = 10000;

function ConfigSummary({ timings, level }) {
  if (!timings) return <p className="config-summary-empty" aria-label="Chưa có dữ liệu">—</p>;
  return <div className="config-summary-grid">{CONFIG_OUTPUTS.map(output => <div key={output.key}>
    <span>{output.label}</span>
    <strong>Bật {timings[output.key][level].on_ms} ms</strong>
    <small>Tắt {timings[output.key][level].off_ms} ms</small>
  </div>)}</div>;
}

const NO_REALTIME = { connected: false, generation: 0, events: [] };

function RemoteConfigPage({ user, realtime = NO_REALTIME, deviceId, deviceCode, deviceName, deviceStatus, onBack, onDashboard, onDevices, onCommands, onAlerts, onLogout, onUnauthorized }) {
  const canEdit = hasPermission(user?.role, "config:edit");
  const [selectedLevel, setSelectedLevel] = useState(1);
  const [snapshot, setSnapshot] = useState(null);
  const [draft, setDraft] = useState(emptyDraft);
  const [draftBaseId, setDraftBaseId] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [saveError, setSaveError] = useState("");
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const dirtyRef = useRef(false);
  const submittedIdRef = useRef(null);
  const saveController = useRef(null);
  const lastEventSequence = useRef(realtime.events.at(-1)?.sequence ?? 0);

  useEffect(() => () => saveController.current?.abort(), []);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    getDeviceConfig(deviceId, { signal: controller.signal })
      .then(result => {
        if (!active) return;
        if (submittedIdRef.current && result.desiredId !== submittedIdRef.current) {
          setLoadError("BE chưa trả cấu hình vừa gửi. Đang chờ đồng bộ; không gửi lại để tránh ghi trùng.");
          return;
        }
        setSnapshot(result);
        setLoadError("");
        if (!dirtyRef.current) {
          setDraft(draftFromTimings(result.desired));
          setDraftBaseId(result.desiredId);
        }
        if (submittedIdRef.current && result.appliedId === submittedIdRef.current) {
          submittedIdRef.current = null;
        }
      })
      .catch(error => {
        if (!active || error.name === "AbortError") return;
        if (error.status === 401) onUnauthorized();
        else setLoadError(error.status === 404 ?
          "BE chưa có API cấu hình cho thiết bị này, hoặc thiết bị không tồn tại (HTTP 404)." :
          deviceApiError(error));
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; controller.abort(); };
  }, [deviceId, reloadKey, realtime.generation, onUnauthorized]);

  useEffect(() => {
    for (const event of realtime.events) {
      if (event.sequence <= lastEventSequence.current) continue;
      lastEventSequence.current = event.sequence;
      if (event.type === "config.updated" &&
          matchesDevice(event.data, deviceId, deviceCode)) {
        setReloadKey(value => value + 1);
      }
    }
  }, [realtime.events, deviceId, deviceCode]);

  const status = configStatus(snapshot);
  const awaitingApplication = status.kind === "pending";
  useEffect(() => {
    if (!awaitingApplication) return;
    const timer = setInterval(() => setReloadKey(value => value + 1), REFRESH_MS);
    return () => clearInterval(timer);
  }, [awaitingApplication]);

  const refresh = () => {
    setLoading(true);
    setLoadError("");
    setReloadKey(value => value + 1);
  };

  const edit = (output, level, field, value) => {
    dirtyRef.current = true;
    setDirty(true);
    setSaveError("");
    setDraft(current => ({
      ...current,
      [output]: {
        ...current[output],
        [level]: { ...current[output][level], [field]: value },
      },
    }));
  };

  const discard = () => {
    dirtyRef.current = false;
    setDirty(false);
    setDraft(draftFromTimings(snapshot?.desired));
    setDraftBaseId(snapshot?.desiredId ?? null);
    setSaveError("");
  };

  const changedOnServer = dirty && snapshot !== null && snapshot.desiredId !== draftBaseId;
  const save = async event => {
    event.preventDefault();
    if (!canEdit || !snapshot || loading || loadError || saving || changedOnServer) return;
    setSaveError("");
    setNotice("");
    let timings;
    try {
      timings = timingsFromDraft(draft);
    } catch (error) {
      setSaveError(error.message);
      return;
    }
    if (JSON.stringify(timings) === JSON.stringify(snapshot.desired)) {
      setSaveError("Bạn chưa thay đổi giá trị nào.");
      return;
    }

    const controller = new AbortController();
    saveController.current = controller;
    setSaving(true);
    try {
      const configId = await updateDeviceConfig(deviceId, timings, { signal: controller.signal });
      if (controller.signal.aborted) return;
      submittedIdRef.current = configId;
      setSnapshot(current => ({ ...current, desiredId: configId, desired: timings }));
      setDraftBaseId(configId);
      dirtyRef.current = false;
      setDirty(false);
      setNotice("BE đã nhận cấu hình. Đang chờ thiết bị xác nhận áp dụng.");
      setReloadKey(value => value + 1);
    } catch (error) {
      if (error.name === "AbortError") return;
      if (error.status === 401) onUnauthorized();
      else setSaveError(`${deviceApiError(error)} Hãy tải lại cấu hình trước khi thử gửi lần nữa.`);
    } finally {
      if (saveController.current === controller) saveController.current = null;
      setSaving(false);
    }
  };

  return <AppShell user={user} activePage="devices" serverConnected={realtime.connected} onDashboard={onDashboard} onDevices={onDevices} onCommands={onCommands} onAlerts={onAlerts} onLogout={onLogout}>
    <div className="breadcrumbs">Thiết bị <span>/</span> {deviceCode || "Thiết bị đã chọn"} <span>/</span> Cấu hình</div>
    <button className="text-link back-link" type="button" onClick={onBack}><Icon name="back" size={18} /> Chi tiết thiết bị</button>
    <div className="config-page-heading"><h1>Cấu hình cảnh báo</h1><div><span>{deviceName || "ESP32 cảnh báo"}{deviceCode ? ` · ${deviceCode}` : ""}</span>{deviceStatus && <ConnectionBadge status={deviceStatus} isStale />}</div></div>

    <div className="config-layout">
      <form className="surface-card config-form" onSubmit={save} noValidate>
        <h2>Thiết lập cảnh báo</h2>
        <p>Chọn mức để chỉnh nhịp bật/tắt cho từng đầu ra. Khi lưu, FE gửi cả ba mức.</p>
        <div className="config-levels" role="group" aria-label="Mức cảnh báo đang chỉnh">{CONFIG_LEVELS.map(level => <button key={level} type="button" className={selectedLevel === level ? "selected" : ""} aria-pressed={selectedLevel === level} onClick={() => setSelectedLevel(level)}>Mức {level}</button>)}</div>
        <div className="config-level-note"><Icon name="info" size={17} /> Đang xem mức {selectedLevel}. Thay đổi ở các mức khác vẫn được giữ khi chuyển tab.</div>
        {!canEdit && <p className="config-readonly">Tài khoản của bạn chỉ được xem cấu hình.</p>}
        {canEdit && !snapshot && <p className="config-draft-note">Bạn có thể nhập thử. Bản nháp chưa gửi đi; nút Lưu chỉ hoạt động khi BE trả cấu hình hợp lệ.</p>}
        <div className="config-output-grid">
          {CONFIG_OUTPUTS.map(output => <section className="config-output" key={output.key} aria-label={output.label}>
            <h3>{output.label}</h3>
            <div className="config-fields">{["on_ms", "off_ms"].map(field => <label key={field}>Thời gian {field === "on_ms" ? "bật" : "tắt"} (ms)<input
              type="number" inputMode="numeric" min="0" max={MAX_TIMING_MS} step="1"
              aria-label={`${output.label} mức ${selectedLevel}, thời gian ${field === "on_ms" ? "bật" : "tắt"} (ms)`}
              value={draft[output.key][selectedLevel][field]}
              onChange={event => edit(output.key, selectedLevel, field, event.target.value)}
              readOnly={!canEdit || saving}
            /></label>)}</div>
          </section>)}
        </div>
        <p className="config-unit-note">1000 ms = 1 giây. Mỗi giá trị từ 0 đến {MAX_TIMING_MS} ms.</p>
        {changedOnServer && <p className="notice-error" role="alert">Cấu hình trên BE đã đổi trong lúc bạn đang sửa. Hãy bỏ thay đổi hoặc tải lại trước khi lưu.</p>}
        {saveError && <p className="notice-error" role="alert">{saveError}</p>}
        {notice && <p className="notice-success" role="status">{notice}</p>}
        {canEdit && <div className="config-actions"><button className="outline-button" type="button" onClick={discard} disabled={!dirty || saving}>Bỏ thay đổi</button><button className="primary-button" type="submit" disabled={!snapshot || loading || Boolean(loadError) || !dirty || saving || changedOnServer}>{saving ? "Đang gửi…" : "Lưu cấu hình"}</button></div>}
      </form>

      <aside className="surface-card config-status-panel" aria-label="Trạng thái áp dụng">
        <h2>Trạng thái áp dụng</h2>
        {loadError ? <p className="notice-error config-load-error" role="alert">{loadError}</p> :
          <div className={`config-status-banner config-status-banner--${status.kind}`} role="status"><Icon name={status.kind === "pending" ? "clock" : "info"} size={20} /><strong>{loading && !snapshot ? "Đang tải cấu hình…" : status.label}</strong></div>}
        <section className="config-snapshot" aria-label="Cấu hình đã lưu">
          <div className="config-snapshot-heading"><strong>Cấu hình đã lưu</strong>{snapshot?.desiredId && <span>{snapshot.desiredId}</span>}</div>
          {snapshot?.desired && <p>Mức {selectedLevel}</p>}
          <ConfigSummary timings={snapshot?.desired} level={selectedLevel} />
        </section>
        <section className="config-snapshot" aria-label="Cấu hình thiết bị">
          <div className="config-snapshot-heading"><strong>Cấu hình thiết bị</strong>{snapshot?.appliedId && <span>{snapshot.appliedId}</span>}</div>
          {snapshot?.applied && <p>Mức {selectedLevel}</p>}
          <ConfigSummary timings={snapshot?.applied} level={selectedLevel} />
        </section>
        <button className="outline-button config-refresh" type="button" onClick={refresh} disabled={loading}><Icon name="refresh" size={17} /> Kiểm tra lại</button>
      </aside>
    </div>
  </AppShell>;
}

export default RemoteConfigPage;
