// !!! lưu ý dòng 50+, về giá trị PERCLOS

import { useEffect, useState } from "react";

import DeviceStatusCard from "./DeviceStatusCard.jsx";
import DriverStatusCard from "./DriverStatusCard.jsx";
import MetricCard from "./MetricCard.jsx";

import { createTelemetrySocket } from "../services/websocket.js";

function Dashboard() {
    // Bước 1 – Tạo state, là dữ liệu mà giao diện đang sử dụng.
  const [telemetry, setTelemetry] = useState({
    device_id: "vision-01",
    ear: 0,
    perclos: 0,
    driver_state: "UNKNOWN"
  });

    // Bước 2 – Kết nối WebSocket
    // Bước 3 – Backend gửi dữ liệu
    // Bước 4 – React tự render lại
  const [connected, setConnected] =
    useState(false);
    // useEffect(..., []) nghĩa là effect này chạy khi Dashboard được tạo.
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

    // !xử lý Perclos dựa trên ví dụ ở file hướng dẫn perclos=0.12 -> UI=12%
    // nếu sau này thống nhất APT gửi json "perclos"=12 -> phải sửa frontend 
  const perclosPercent =
    Number(telemetry.perclos || 0) * 100;

  return (
    <main className="dashboard">
      <header className="dashboard-header">
        <div>
          <p className="dashboard-label">
            AIoT DRIVER MONITORING
          </p>

          <h1>
            Driver Monitoring Dashboard
          </h1>
        </div>

        <div
          className={
            connected
              ? "connection-status connection-status--online"
              : "connection-status connection-status--offline"
          }
        >
          {connected
            ? "Backend Connected"
            : "Backend Disconnected"}
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
          description="Eye Aspect Ratio"
        />

        <MetricCard
          title="PERCLOS"
          value={perclosPercent.toFixed(0)}
          unit="%"
          description="Percentage of Eye Closure"
        />
      </section>
    </main>
  );
}

export default Dashboard;