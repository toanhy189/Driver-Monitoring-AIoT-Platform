// !!! Lưu ý xử lý PERCLOS:
// Backend gửi perclos = 0.12 -> UI hiển thị 12%

import { useEffect, useState } from "react";

import DeviceStatusCard from "./DeviceStatusCard.jsx";
import DriverStatusCard from "./DriverStatusCard.jsx";
import MetricCard from "./MetricCard.jsx";

import { createTelemetrySocket } from "../services/websocket.js";
import { getDevices, applyDeviceUpdate, markDevicesStale } from "../services/devices.js";
import { normalizeTelemetry } from "../services/telemetry.js";

const DEVICE_REFRESH_MS = 10000;

function Dashboard({ onLogout }) {
  // Chưa nhận số đo thì giữ null, không hiển thị dữ liệu mẫu như kết quả thật.
  const [telemetry, setTelemetry] = useState(null);
  const [telemetryError, setTelemetryError] = useState("");

  // Trạng thái kết nối WebSocket
  const [wsConnected, setWsConnected] = useState(false);
  const [devices, setDevices] = useState([]);
  const [devicesLoading, setDevicesLoading] = useState(true);
  const [devicesError, setDevicesError] = useState("");

  // Kết nối WebSocket
  useEffect(() => {
    let stopped = false;
    let refreshTimer;
    let requestController = null;
    let disconnectVersion = 0;
    let pendingDeviceUpdates = [];

    // API hiện có status/last_seen. Đọc lại định kỳ khi BE chưa phát device.updated.
    async function loadDevices() {
      if (stopped || requestController) return;
      clearTimeout(refreshTimer);
      const controller = new AbortController();
      requestController = controller;
      const versionAtStart = disconnectVersion;
      pendingDeviceUpdates = [];
      try {
        const snapshot = await getDevices({ signal: controller.signal });
        if (stopped) return;
        // Giữ sự kiện mới hơn snapshot và đánh dấu cũ nếu vừa mất kết nối.
        const initial = versionAtStart === disconnectVersion
          ? snapshot : markDevicesStale(snapshot);
        setDevices(pendingDeviceUpdates.reduce(applyDeviceUpdate, initial));
        setDevicesError("");
      } catch (error) {
        if (stopped || error.name === "AbortError") return;
        setDevicesError(error.message || "Không tải được trạng thái thiết bị.");
        const updatesDuringRequest = pendingDeviceUpdates;
        setDevices(current => updatesDuringRequest.reduce(
          applyDeviceUpdate, markDevicesStale(current)
        ));
      } finally {
        requestController = null;
        if (!stopped) {
          setDevicesLoading(false);
          refreshTimer = setTimeout(loadDevices, DEVICE_REFRESH_MS);
        }
      }
    }

    function handleDisconnect() {
      if (stopped) return;
      disconnectVersion += 1;
      pendingDeviceUpdates = [];
      setWsConnected(false);
      setDevices(markDevicesStale);
    }

    loadDevices();
    const socket = createTelemetrySocket({
      onOpen: () => {
        if (stopped) return;
        setWsConnected(true);
        loadDevices();
      },

      onMessage: (message) => {
        if (stopped || !message || typeof message !== "object" || Array.isArray(message)) return;
        // Envelope device.updated là giao thức đề xuất cho BE tuần 2.
        if (message.type === "device.updated") {
          if (requestController) pendingDeviceUpdates.push(message.data);
          setDevices(current => applyDeviceUpdate(current, message.data));
          return;
        }

        if (message.type === "telemetry.updated" || message.type == null) {
          const data = message.type === "telemetry.updated" ? message.data : message;
          try {
            // Mỗi tin là số đo mới, có ID số và mã hiển thị tách biệt.
            setTelemetry(normalizeTelemetry(data));
            setTelemetryError("");
          } catch (error) {
            setTelemetry(null);
            setTelemetryError("Dữ liệu số đo không đúng định dạng. Chưa thể hiển thị kết quả.");
            console.warn("[Telemetry]", error.message);
          }
        }
      },

      onClose: handleDisconnect,
      onError: handleDisconnect,
    });

    return () => {
      stopped = true;
      clearTimeout(refreshTimer);
      requestController?.abort();
      socket.close();
    };
  }, []);

  const hasEar = Number.isFinite(telemetry?.ear);
  const hasPerclos = Number.isFinite(telemetry?.perclos);
  const earText = hasEar ? telemetry.ear.toFixed(2) : "—";
  // Backend gửi perclos = 0.35 thì UI hiển thị 35%; null không phải 0%.
  const perclosText = hasPerclos ? (telemetry.perclos * 100).toFixed(0) : "—";

  return (
    <main className="dashboard">
      <header className="dashboard-header">
        <div>
          <p className="dashboard-label">
            GIÁM SÁT TÀI XẾ AIoT
          </p>

          <h1>
            Hệ thống giám sát tài xế
          </h1>
        </div>

        <div className="dashboard-header-actions">
          <div
            className={
              wsConnected
                ? "connection-status connection-status--online"
                : "connection-status connection-status--offline"
            }
          >
            {wsConnected
              ? "Đã kết nối máy chủ"
              : "Mất kết nối máy chủ"}
          </div>

          <button
            className="logout-button"
            onClick={onLogout}
          >
            Đăng xuất
          </button>
        </div>
      </header>

      <section className="dashboard-devices" aria-labelledby="devices-heading">
        <h2 id="devices-heading">Trạng thái thiết bị</h2>
        {devicesLoading && <p role="status">Đang tải trạng thái thiết bị…</p>}
        {devicesError && <p className="device-status-error" role="alert">{devicesError}</p>}
        {!devicesLoading && !devicesError && devices.length === 0 && (
          <p>Chưa có thiết bị được gán cho tài khoản này.</p>
        )}
        <div className="dashboard-grid">
          {devices.map(device => (
            <DeviceStatusCard
              key={device.id}
              deviceCode={device.device_code}
              name={device.name || device.model || "Thiết bị"}
              status={device.status}
              lastSeen={device.last_seen}
              isStale={device.isStale}
            />
          ))}
          {devices.length === 0 && (devicesLoading || devicesError) && (
            <DeviceStatusCard />
          )}
        </div>
      </section>

      <section aria-labelledby="telemetry-heading">
        <h2 id="telemetry-heading">Số đo và trạng thái tài xế</h2>
        <p>
          Nguồn số đo: {telemetry
            ? telemetry.device_code || "Chưa có mã thiết bị"
            : "Chưa có dữ liệu"}
        </p>
        {telemetryError && <p className="device-status-error" role="alert">{telemetryError}</p>}
        <div className="dashboard-grid">
          <DriverStatusCard
            state={telemetry?.driver_state}
          />

          <MetricCard
            title="EAR"
            value={earText}
            description={hasEar ? "Tỷ lệ khép mắt" : "Chưa có dữ liệu"}
          />

          <MetricCard
            title="PERCLOS"
            value={perclosText}
            unit={hasPerclos ? "%" : ""}
            description={hasPerclos ? "Tỷ lệ nhắm mắt" : "Chưa đủ dữ liệu"}
          />
        </div>
      </section>
    </main>
  );
}

export default Dashboard;
