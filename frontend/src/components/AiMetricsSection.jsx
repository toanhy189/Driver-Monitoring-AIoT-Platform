import { useEffect, useRef, useState } from "react";
import { getTelemetryHistory } from "../services/telemetryApi.js";
import { Icon } from "./AppShell.jsx";
import "../styles/ai-metrics.css";

const FILTER_OPTIONS = [
  { key: "15m", label: "15 phút qua", minutes: 15 },
  { key: "1h", label: "1 giờ qua", minutes: 60 },
  { key: "24h", label: "24 giờ qua", minutes: 1440 },
  { key: "all", label: "Tất cả", minutes: null },
];

const STATE_COLORS = {
  ATTENTIVE: { bg: "#dcfce7", text: "#166534", border: "#86efac", label: "Tỉnh táo" },
  DISTRACTED: { bg: "#fef9c3", text: "#854d0e", border: "#fde047", label: "Mất tập trung" },
  DROWSY: { bg: "#fee2e2", text: "#991b1b", border: "#fca5a5", label: "Buồn ngủ" },
  UNKNOWN: { bg: "#f3f4f6", text: "#4b5563", border: "#d1d5db", label: "Không xác định" },
};

function formatTime(isoString) {
  if (!isoString) return "—";
  const d = new Date(isoString);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export default function AiMetricsSection({ deviceId, deviceCode, realtime, onUnauthorized }) {
  const [filterKey, setFilterKey] = useState("1h");
  const [history, setHistory] = useState({ items: [], total_samples: 0, model_version: null, last_updated: null });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const inFlightRef = useRef(false);
  const lastEventSeq = useRef(realtime?.events?.at(-1)?.sequence ?? 0);

  // Fetch telemetry history with filters and limit
  useEffect(() => {
    if (!deviceId) return;
    let active = true;
    const controller = new AbortController();
    inFlightRef.current = true;
    setLoading(true);
    setError("");

    const selectedFilter = FILTER_OPTIONS.find(f => f.key === filterKey);
    let fromTime = null;
    if (selectedFilter?.minutes) {
      fromTime = new Date(Date.now() - selectedFilter.minutes * 60 * 1000).toISOString();
    }

    getTelemetryHistory(deviceId, { fromTime, limit: 100, signal: controller.signal })
      .then(res => {
        if (!active) return;
        setHistory(res || { items: [], total_samples: 0, model_version: null, last_updated: null });
        setError("");
      })
      .catch(err => {
        if (!active || err.name === "AbortError") return;
        if (err.status === 401) onUnauthorized?.();
        else setError(err.message || "Không thể tải lịch sử số đo AI.");
      })
      .finally(() => {
        if (active) {
          inFlightRef.current = false;
          setLoading(false);
        }
      });

    return () => {
      active = false;
      controller.abort();
      inFlightRef.current = false;
    };
  }, [deviceId, filterKey, reloadKey, onUnauthorized]);

  // Reconnect recovery: when WebSocket reconnects, refresh history snapshot (TV4-15)
  useEffect(() => {
    if (realtime?.generation) {
      setReloadKey(k => k + 1);
    }
  }, [realtime?.generation]);

  // Realtime updates without duplicate points (TV4-14)
  useEffect(() => {
    if (!realtime?.events) return;
    for (const ev of realtime.events) {
      if (ev.sequence <= lastEventSeq.current) continue;
      lastEventSeq.current = ev.sequence;
      if (ev.type !== "telemetry.updated") continue;
      const data = ev.data;
      if (data.device_id !== deviceId && data.device_code !== deviceCode) continue;

      setHistory(current => {
        const items = current?.items || [];
        // Prevent duplicate timestamp / id
        const exists = items.some(it => it.recorded_at === data.recorded_at || (data.id && it.id === data.id));
        if (exists) return current;

        const newItem = {
          id: data.id || Date.now(),
          recorded_at: data.recorded_at || new Date().toISOString(),
          ear: data.ear,
          perclos: data.perclos,
          driver_state: data.driver_state,
          confidence: data.confidence,
          face_detected: data.face_detected,
          model_version: data.model_version || current.model_version,
        };

        const updatedItems = [...items.slice(-99), newItem];
        return {
          ...current,
          items: updatedItems,
          total_samples: updatedItems.length,
          model_version: newItem.model_version || current.model_version,
          last_updated: newItem.recorded_at,
        };
      });
    }
  }, [realtime?.events, deviceId, deviceCode]);

  const items = history.items || [];
  const isStale = !realtime?.connected;

  // Chart coordinate calculation for EAR & PERCLOS
  const chartWidth = 700;
  const chartHeight = 220;
  const padding = { top: 20, right: 30, bottom: 35, left: 45 };
  const innerW = chartWidth - padding.left - padding.right;
  const innerH = chartHeight - padding.top - padding.bottom;

  const validItems = items.filter(it => Number.isFinite(it.ear) || Number.isFinite(it.perclos));
  
  let earPath = "";
  let perclosPath = "";
  if (validItems.length > 1) {
    const xStep = innerW / (validItems.length - 1);
    earPath = validItems.map((it, idx) => {
      const x = padding.left + idx * xStep;
      // EAR normal range 0.0 - 0.5
      const y = padding.top + innerH - (Math.min(0.5, Math.max(0, it.ear ?? 0)) / 0.5) * innerH;
      return `${idx === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
    }).join(" ");

    perclosPath = validItems.map((it, idx) => {
      const x = padding.left + idx * xStep;
      // PERCLOS normal range 0.0 - 1.0
      const y = padding.top + innerH - (Math.min(1.0, Math.max(0, it.perclos ?? 0)) / 1.0) * innerH;
      return `${idx === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
    }).join(" ");
  }

  return (
    <section className="surface-card ai-metrics-section" aria-label="AI Metrics và Timeline">
      <div className="section-heading ai-metrics-header">
        <div>
          <h2>AI Metrics & Timeline số đo</h2>
          <p>Lịch sử chuỗi thời gian EAR / PERCLOS và timeline trạng thái tài xế</p>
        </div>
        <div className="ai-metrics-controls">
          <div className="filter-pill-group" role="group" aria-label="Bộ lọc khoảng thời gian">
            {FILTER_OPTIONS.map(opt => (
              <button
                key={opt.key}
                type="button"
                className={`filter-pill ${filterKey === opt.key ? "active" : ""}`}
                onClick={() => setFilterKey(opt.key)}
              >
                {opt.label}
              </button>
            ))}
          </div>
          <button
            className="icon-button"
            type="button"
            onClick={() => setReloadKey(k => k + 1)}
            disabled={loading}
            title="Tải lại số đo"
          >
            <Icon name="refresh" />
          </button>
        </div>
      </div>

      {/* Metadata Bar (TV4-12) */}
      <div className="ai-metadata-bar">
        <div className="metadata-item">
          <span className="metadata-label">Phiên bản mô hình:</span>
          <strong>{history.model_version || "v1.0.0 (Baseline)"}</strong>
        </div>
        <div className="metadata-item">
          <span className="metadata-label">Tổng số mẫu:</span>
          <strong>{history.total_samples || items.length} mẫu</strong>
        </div>
        <div className="metadata-item">
          <span className="metadata-label">Cập nhật cuối:</span>
          <strong>{formatTime(history.last_updated)}</strong>
        </div>
        <div className="metadata-item">
          <span className="metadata-label">Trạng thái:</span>
          <span className={`status-pill ${isStale ? "stale" : "live"}`}>
            {isStale ? "Dữ liệu cũ (Mất socket)" : "Realtime đồng bộ"}
          </span>
        </div>
      </div>

      {/* Loading / Error States (TV4-13) */}
      {loading && items.length === 0 && (
        <div className="ai-metrics-loading" role="status">
          <Icon name="clock" size={24} />
          <span>Đang tải lịch sử số đo AI…</span>
        </div>
      )}

      {error && (
        <div className="notice-error" role="alert">
          <span>{error}</span>
          <button className="outline-button" onClick={() => setReloadKey(k => k + 1)}>
            Thử lại
          </button>
        </div>
      )}

      {/* Empty State (TV4-13) */}
      {!loading && !error && items.length === 0 && (
        <div className="ai-metrics-empty">
          <Icon name="info" size={32} />
          <p>Chưa có dữ liệu lịch sử số đo trong khoảng thời gian đã chọn.</p>
          <small>Số đo sẽ tự động cập nhật khi Vision Node gửi telemetry.</small>
        </div>
      )}

      {/* Graph and Timeline */}
      {items.length > 0 && (
        <>
          <div className="chart-legend">
            <span className="legend-item"><span className="legend-dot ear-dot" /> EAR (Mở mắt, max 0.5)</span>
            <span className="legend-item"><span className="legend-dot perclos-dot" /> PERCLOS (Nhắm mắt, max 100%)</span>
          </div>

          <div className="ai-chart-container">
            <svg viewBox={`0 0 ${chartWidth} ${chartHeight}`} className="ai-timeseries-svg" preserveAspectRatio="none">
              {/* Grid lines */}
              <line x1={padding.left} y1={padding.top} x2={chartWidth - padding.right} y2={padding.top} stroke="#e2e8f0" strokeDasharray="4" />
              <line x1={padding.left} y1={padding.top + innerH / 2} x2={chartWidth - padding.right} y2={padding.top + innerH / 2} stroke="#e2e8f0" strokeDasharray="4" />
              <line x1={padding.left} y1={padding.top + innerH} x2={chartWidth - padding.right} y2={padding.top + innerH} stroke="#cbd5e1" />

              {/* Y Axis Labels */}
              <text x={padding.left - 8} y={padding.top + 4} textAnchor="end" fontSize="10" fill="#64748b">0.5 / 100%</text>
              <text x={padding.left - 8} y={padding.top + innerH / 2 + 4} textAnchor="end" fontSize="10" fill="#64748b">0.25 / 50%</text>
              <text x={padding.left - 8} y={padding.top + innerH + 4} textAnchor="end" fontSize="10" fill="#64748b">0</text>

              {/* Lines */}
              {earPath && <path d={earPath} fill="none" stroke="#0284c7" strokeWidth="2.5" strokeLinecap="round" />}
              {perclosPath && <path d={perclosPath} fill="none" stroke="#10b981" strokeWidth="2.5" strokeLinecap="round" />}

              {/* X Axis Time Labels */}
              {validItems.length > 0 && (
                <>
                  <text x={padding.left} y={chartHeight - 8} fontSize="10" fill="#64748b">{formatTime(validItems[0].recorded_at)}</text>
                  <text x={chartWidth - padding.right} y={chartHeight - 8} textAnchor="end" fontSize="10" fill="#64748b">{formatTime(validItems.at(-1)?.recorded_at)}</text>
                </>
              )}
            </svg>
          </div>

          {/* Timeline Trạng thái tài xế (TV4-11) */}
          <div className="ai-timeline-wrap">
            <h3 className="timeline-title">Timeline trạng thái tài xế</h3>
            <div className="timeline-bar" role="list" aria-label="Chuỗi trạng thái theo thời gian">
              {items.slice(-20).map((it, idx) => {
                const conf = STATE_COLORS[it.driver_state] || STATE_COLORS.UNKNOWN;
                return (
                  <div
                    key={it.id || idx}
                    className="timeline-segment"
                    style={{ backgroundColor: conf.bg, borderColor: conf.border, color: conf.text }}
                    title={`${formatTime(it.recorded_at)} - ${conf.label} (EAR: ${it.ear ?? "—"}, PERCLOS: ${it.perclos ? (it.perclos * 100).toFixed(0) + "%" : "—"})`}
                  >
                    <span>{conf.label}</span>
                    <small>{formatTime(it.recorded_at)}</small>
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}

      {/* Model Evaluation Notice (TV4-17) */}
      <div className="ai-model-evaluation-card">
        <div className="evaluation-heading">
          <Icon name="info" size={18} />
          <strong>Đánh giá mô hình thực nghiệm (TV4-17):</strong>
        </div>
        <p className="evaluation-text">
          Chưa có dữ liệu đánh giá trên tập test độc lập. Nhóm AI (TV3) đang thu thập dataset có nhãn và thực hiện baseline evaluation. Giao diện không tự tạo chỉ số Accuracy/F1 giả.
        </p>
      </div>
    </section>
  );
}
