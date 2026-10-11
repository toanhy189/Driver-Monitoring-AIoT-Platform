import { useEffect, useRef, useState } from "react";
import DeviceListView from "./DeviceListView.jsx";

import { getDevices, applyDeviceUpdate, markDevicesStale, registerDevice } from "../services/devices.js";
import { hasPermission } from "../services/permissions.js";
import { deviceApiError } from "../services/deviceDisplay.js";
import "../styles/devices.css";

const REFRESH_MS = 10000;

const NO_REALTIME = { connected: false, generation: 0, events: [] };

function DeviceListPage({ user, realtime = NO_REALTIME, onBack, onOpenDevice, onOpenCommands, onOpenAlerts, onLogout, onUnauthorized }) {
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [fields, setFields] = useState({ device_code: "", name: "", model: "" });
  const [registerBusy, setRegisterBusy] = useState(false);
  const [registerError, setRegisterError] = useState("");
  const [registerNotice, setRegisterNotice] = useState("");
  const pendingUpdates = useRef([]);
  const requestInFlight = useRef(false);
  const registerController = useRef(null);
  const lastEventSequence = useRef(realtime.events.at(-1)?.sequence ?? 0);
  const connectedRef = useRef(realtime.connected);
  connectedRef.current = realtime.connected;

  useEffect(() => () => registerController.current?.abort(), []);

  useEffect(() => {
    let active = true;
    let timer;
    const controller = new AbortController();
    pendingUpdates.current = [];
    requestInFlight.current = true;

    getDevices({ signal: controller.signal })
      .then(snapshot => {
        if (!active) return;
        setDevices(pendingUpdates.current.reduce(applyDeviceUpdate,
          connectedRef.current ? snapshot : markDevicesStale(snapshot)));
        setError("");
      })
      .catch(requestError => {
        if (!active || requestError.name === "AbortError") return;
        if (requestError.status === 401) {
          onUnauthorized();
          return;
        }
        setError(deviceApiError(requestError));
        setDevices(markDevicesStale);
      })
      .finally(() => {
        if (!active) return;
        requestInFlight.current = false;
        setLoading(false);
        timer = setTimeout(() => setReloadKey(value => value + 1), REFRESH_MS);
      });

    return () => {
      active = false;
      requestInFlight.current = false;
      clearTimeout(timer);
      controller.abort();
    };
  }, [reloadKey, realtime.generation, onUnauthorized]);

  useEffect(() => {
    if (!realtime.connected) {
      pendingUpdates.current = [];
      setDevices(markDevicesStale);
    }
  }, [realtime.connected]);

  useEffect(() => {
    for (const event of realtime.events) {
      if (event.sequence <= lastEventSequence.current) continue;
      lastEventSequence.current = event.sequence;
      if (event.type !== "device.updated") continue;
      if (requestInFlight.current) pendingUpdates.current.push(event.data);
      setDevices(current => applyDeviceUpdate(current, event.data));
    }
  }, [realtime.events]);

  const retry = () => {
    setError("");
    setLoading(true);
    setReloadKey(value => value + 1);
  };

  const resetRegistration = () => {
    setFields({ device_code: "", name: "", model: "" });
    setRegisterError("");
    setRegisterNotice("");
  };

  const submitRegistration = async event => {
    event.preventDefault();
    if (!hasPermission(user?.role, "device:manage") || registerBusy) return;
    setRegisterBusy(true);
    setRegisterError("");
    setRegisterNotice("");
    const controller = new AbortController();
    registerController.current = controller;
    try {
      await registerDevice(fields, { signal: controller.signal });
      if (controller.signal.aborted) return;
      setRegisterNotice("BE đã chấp nhận yêu cầu đăng ký. Danh sách đang được tải lại.");
      setFields({ device_code: "", name: "", model: "" });
      setReloadKey(value => value + 1);
    } catch (requestError) {
      if (requestError.name === "AbortError") return;
      if (requestError.status === 401) onUnauthorized();
      else setRegisterError(deviceApiError(requestError));
    } finally {
      registerController.current = null;
      setRegisterBusy(false);
    }
  };

  return <DeviceListView
    user={user} onBack={onBack} onOpenDevice={onOpenDevice} onOpenCommands={onOpenCommands} onOpenAlerts={onOpenAlerts} onLogout={onLogout}
    serverConnected={realtime.connected} devices={devices} loading={loading} error={error}
    retry={retry} fields={fields} setFields={setFields} registerBusy={registerBusy}
    registerError={registerError} registerNotice={registerNotice}
    submitRegistration={submitRegistration} resetRegistration={resetRegistration}
  />;
}

export default DeviceListPage;
