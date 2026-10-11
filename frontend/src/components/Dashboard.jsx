import { useEffect, useRef, useState } from "react";
import DashboardView from "./DashboardView.jsx";
import { getDevices, applyDeviceUpdate, markDevicesStale } from "../services/devices.js";
import { normalizeTelemetry } from "../services/telemetry.js";
import { getLatestTelemetry } from "../services/telemetryApi.js";
import { matchesDevice } from "../services/realtime.js";

const DEVICE_REFRESH_MS = 10000;
const NO_REALTIME = { connected: false, generation: 0, events: [] };

function Dashboard({ user, realtime = NO_REALTIME, onLogout, onUnauthorized, onOpenDevices, onOpenCommands, onOpenAlerts }) {
  const [devices, setDevices] = useState([]);
  const [devicesLoading, setDevicesLoading] = useState(true);
  const [devicesError, setDevicesError] = useState("");
  const [selectedDeviceId, setSelectedDeviceId] = useState(null);
  const [telemetry, setTelemetry] = useState(null);
  const [telemetrySource, setTelemetrySource] = useState(null);
  const [telemetryError, setTelemetryError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const pendingDeviceUpdates = useRef([]);
  const deviceRequestInFlight = useRef(false);
  const lastEventSequence = useRef(realtime.events.at(-1)?.sequence ?? 0);
  const telemetryArrival = useRef(0);
  const connectedRef = useRef(realtime.connected);
  connectedRef.current = realtime.connected;

  useEffect(() => {
    let active = true;
    let timer;
    const controller = new AbortController();
    pendingDeviceUpdates.current = [];
    deviceRequestInFlight.current = true;
    getDevices({ signal: controller.signal })
      .then(snapshot => {
        if (!active) return;
        const initial = connectedRef.current ? snapshot : markDevicesStale(snapshot);
        setDevices(pendingDeviceUpdates.current.reduce(applyDeviceUpdate, initial));
        setDevicesError("");
      })
      .catch(error => {
        if (!active || error.name === "AbortError") return;
        if (error.status === 401) onUnauthorized();
        else setDevicesError(error.message || "Không tải được trạng thái thiết bị.");
        setDevices(markDevicesStale);
      })
      .finally(() => {
        if (!active) return;
        deviceRequestInFlight.current = false;
        setDevicesLoading(false);
        timer = setTimeout(() => setReloadKey(value => value + 1), DEVICE_REFRESH_MS);
      });
    return () => { active = false; clearTimeout(timer); controller.abort(); deviceRequestInFlight.current = false; };
  }, [reloadKey, realtime.generation, onUnauthorized]);

  useEffect(() => {
    if (!realtime.connected) {
      pendingDeviceUpdates.current = [];
      setDevices(markDevicesStale);
    }
  }, [realtime.connected]);

  useEffect(() => {
    if (devices.length === 1 && selectedDeviceId == null) setSelectedDeviceId(devices[0].id);
    if (selectedDeviceId != null && !devices.some(device => device.id === selectedDeviceId)) {
      setSelectedDeviceId(null);
    }
  }, [devices, selectedDeviceId]);

  const selectedDevice = devices.find(device => device.id === selectedDeviceId);
  useEffect(() => {
    setTelemetry(null);
    setTelemetrySource(null);
    setTelemetryError("");
  }, [selectedDeviceId]);

  useEffect(() => {
    for (const event of realtime.events) {
      if (event.sequence <= lastEventSequence.current) continue;
      lastEventSequence.current = event.sequence;
      if (event.type === "device.updated") {
        if (deviceRequestInFlight.current) pendingDeviceUpdates.current.push(event.data);
        setDevices(current => applyDeviceUpdate(current, event.data));
      } else if (event.type === "telemetry.updated" && selectedDevice &&
          matchesDevice(event.data, selectedDevice.id, selectedDevice.device_code)) {
        try {
          const normalized = normalizeTelemetry(event.data);
          telemetryArrival.current += 1;
          setTelemetry({ ...normalized, received_at: new Date().toISOString() });
          setTelemetrySource("realtime");
          setTelemetryError("");
        } catch {
          setTelemetry(null);
          setTelemetryError("Dữ liệu số đo không đúng định dạng.");
        }
      }
    }
  }, [realtime.events, selectedDevice]);

  useEffect(() => {
    if (selectedDeviceId == null) return;
    let active = true;
    const controller = new AbortController();
    const arrivalAtStart = telemetryArrival.current;
    getLatestTelemetry(selectedDeviceId, { signal: controller.signal })
      .then(result => {
        if (!active || arrivalAtStart !== telemetryArrival.current) return;
        setTelemetry(result);
        setTelemetrySource(result ? "snapshot" : null);
      })
      .catch(error => {
        if (!active || error.name === "AbortError" || arrivalAtStart !== telemetryArrival.current) return;
        if (error.status === 401) onUnauthorized();
        else if (error.status !== 404) setTelemetryError(error.message || "Không tải được số đo gần nhất.");
      });
    return () => { active = false; controller.abort(); };
  }, [selectedDeviceId, realtime.generation, onUnauthorized]);

  const hasEar = Number.isFinite(telemetry?.ear);
  const hasPerclos = Number.isFinite(telemetry?.perclos);
  const earText = hasEar ? telemetry.ear.toFixed(2) : "—";
  const perclosText = hasPerclos ? (telemetry.perclos * 100).toFixed(0) : "—";

  return <DashboardView
    user={user} onLogout={onLogout} onOpenDevices={onOpenDevices} onOpenCommands={onOpenCommands} onOpenAlerts={onOpenAlerts}
    wsConnected={realtime.connected} devices={devices} devicesLoading={devicesLoading}
    devicesError={devicesError} selectedDeviceId={selectedDeviceId} onSelectDevice={setSelectedDeviceId}
    telemetry={telemetry} telemetrySource={telemetrySource} telemetryStale={!realtime.connected}
    telemetryError={telemetryError} earText={earText} perclosText={perclosText}
    hasEar={hasEar} hasPerclos={hasPerclos}
  />;
}

export default Dashboard;
