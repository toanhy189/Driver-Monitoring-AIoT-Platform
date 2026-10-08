import { useEffect, useRef, useState } from "react";
import DeviceDetailView from "./DeviceDetailView.jsx";

import { applyDeviceUpdate, getDeviceDetail, markDevicesStale, runDeviceAction } from "../services/devices.js";
import { matchesDevice } from "../services/realtime.js";
import { hasPermission } from "../services/permissions.js";
import { deviceApiError } from "../services/deviceDisplay.js";
import "../styles/devices.css";

const NO_REALTIME = { connected: false, generation: 0, events: [] };

function DeviceDetailPage({ user, realtime = NO_REALTIME, deviceId, summary, onBack, onDashboard, onOpenHistory, onOpenConfig, onOpenCommands, onOpenAlerts, onLogout, onUnauthorized }) {
  const [device, setDevice] = useState(summary || null);
  const [detailSource, setDetailSource] = useState(summary ? "list" : "none");
  const [loading, setLoading] = useState(true);
  const [detailError, setDetailError] = useState("");
  const [actionError, setActionError] = useState("");
  const [actionNotice, setActionNotice] = useState("");
  const [busyAction, setBusyAction] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);
  const actionController = useRef(null);
  const pendingUpdates = useRef([]);
  const detailRequestInFlight = useRef(false);
  const lastEventSequence = useRef(realtime.events.at(-1)?.sequence ?? 0);
  const connectedRef = useRef(realtime.connected);
  connectedRef.current = realtime.connected;

  useEffect(() => () => actionController.current?.abort(), []);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    pendingUpdates.current = [];
    detailRequestInFlight.current = true;

    getDeviceDetail(deviceId, { signal: controller.signal })
      .then(result => {
        if (!active) return;
        const initial = connectedRef.current ? result : markDevicesStale([result])[0];
        setDevice(pendingUpdates.current.reduce(
          (current, update) => applyDeviceUpdate([current], update)[0], initial));
        setDetailSource("detail");
        setDetailError("");
      })
      .catch(error => {
        if (!active || error.name === "AbortError") return;
        if (error.status === 401) {
          onUnauthorized();
          return;
        }
        setDetailError(deviceApiError(error));
      })
      .finally(() => { if (active) { detailRequestInFlight.current = false; setLoading(false); } });

    return () => {
      active = false;
      controller.abort();
      detailRequestInFlight.current = false;
    };
  }, [deviceId, reloadKey, realtime.generation, onUnauthorized]);

  useEffect(() => {
    if (!realtime.connected) {
      pendingUpdates.current = [];
      setDevice(current => current ? markDevicesStale([current])[0] : current);
    }
  }, [realtime.connected]);

  useEffect(() => {
    for (const event of realtime.events) {
      if (event.sequence <= lastEventSequence.current) continue;
      lastEventSequence.current = event.sequence;
      if (event.type !== "device.updated" ||
          !matchesDevice(event.data, deviceId, device?.device_code ?? summary?.device_code)) continue;
      if (detailRequestInFlight.current) pendingUpdates.current.push(event.data);
      setDevice(current => current ? applyDeviceUpdate([current], event.data)[0] : current);
    }
  }, [realtime.events, deviceId, device?.device_code, summary?.device_code]);

  const retry = () => {
    setLoading(true);
    setDetailError("");
    setReloadKey(value => value + 1);
  };

  const performAction = async action => {
    const permission = action === "decommission" ? "device:decommission" : "device:manage";
    if (!hasPermission(user?.role, permission) || busyAction) return;
    if (action === "decommission" && !window.confirm(
      `Ngừng sử dụng thiết bị ${device?.device_code || deviceId}? Hãy kiểm tra đúng thiết bị trước khi tiếp tục.`
    )) return;

    setBusyAction(action);
    setActionError("");
    setActionNotice("");
    const controller = new AbortController();
    actionController.current = controller;
    try {
      await runDeviceAction(deviceId, action, { signal: controller.signal });
      if (controller.signal.aborted) return;
      setActionNotice("BE đã xác nhận yêu cầu. Đang lấy lại trạng thái thiết bị.");
      setLoading(true);
      setReloadKey(value => value + 1);
    } catch (error) {
      if (error.name === "AbortError") return;
      if (error.status === 401) onUnauthorized();
      else setActionError(deviceApiError(error));
    } finally {
      actionController.current = null;
      setBusyAction(null);
    }
  };

  return <DeviceDetailView
    user={user} realtime={realtime} deviceId={deviceId} device={device} detailSource={detailSource}
    loading={loading} detailError={detailError} actionError={actionError}
    actionNotice={actionNotice} busyAction={busyAction} retry={retry}
    performAction={performAction} onBack={onBack} onDashboard={onDashboard}
    onOpenHistory={onOpenHistory} onOpenConfig={onOpenConfig} onOpenCommands={onOpenCommands} onOpenAlerts={onOpenAlerts} onUnauthorized={onUnauthorized} onLogout={onLogout}
  />;
}

export default DeviceDetailPage;
