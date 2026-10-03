// !!! Lưu ý xử lý PERCLOS:
// Backend gửi perclos = 0.12 -> UI hiển thị 12%

import { useEffect, useState } from "react";

import DeviceStatusCard from "./DeviceStatusCard.jsx";
import DriverStatusCard from "./DriverStatusCard.jsx";
import MetricCard from "./MetricCard.jsx";

import { createTelemetrySocket } from "../services/websocket.js";

function Dashboard({ onLogout }) {
  // Dữ liệu mẫu ban đầu để test giao diện.
  // Sau này WebSocket nhận dữ liệu thật thì telemetry sẽ được cập nhật.
  const [telemetry, setTelemetry] = useState({
    device_id: "vision-01",
    ear: 0.28,
    perclos: 0.12,
    driver_state: "ATTENTIVE"
  });

  // Trạng thái kết nối WebSocket
  const [connected, setConnected] = useState(false);

  // Kết nối WebSocket
  useEffect(() => {
    const socket = createTelemetrySocket({
      onOpen: () => {
        setConnected(true);
      },

      onMessage: (data) => {
        setTelemetry(data);
      },

      onClose: () => {
        setConnected(false);
      },

      onError: () => {
        setConnected(false);
      }
    });

    return () => {
      socket.close();
    };
  }, []);

  // Backend gửi perclos = 0.12
  // UI hiển thị 12%
  const perclosPercent =
    Number(telemetry.perclos || 0) * 100;

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
              connected
                ? "connection-status connection-status--online"
                : "connection-status connection-status--offline"
            }
          >
            {connected
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

      <section className="dashboard-grid">
        <DeviceStatusCard
          deviceId={telemetry.device_id}
          connected={connected}
        />

        <DriverStatusCard
          state={telemetry.driver_state}
        />

        <MetricCard
          title="EAR"
          value={Number(telemetry.ear).toFixed(2)}
          description="Tỷ lệ khép mắt"
        />

        <MetricCard
          title="PERCLOS"
          value={perclosPercent.toFixed(0)}
          unit="%"
          description="Tỷ lệ nhắm mắt"
        />
      </section>
    </main>
  );
}

export default Dashboard;