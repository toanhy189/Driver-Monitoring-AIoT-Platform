import { useEffect, useRef, useState } from "react";
import { getTelemetryHistory } from "../services/telemetryApi.js";
import { mergeTelemetryItems } from "../services/telemetry.js";
import { Icon } from "./AppShell.jsx";
import { normalizeAiSignals } from "../services/aiSignals.js";
import { metricPath, metricBandPath, appendTimeline } from "../services/chartSeries.js";
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

function latestTimestamp(current, candidate) {
  const currentTime = Date.parse(current);
  const candidateTime = Date.parse(candidate);
  return Number.isFinite(currentTime) && (!Number.isFinite(candidateTime) || currentTime > candidateTime)
    ? current : candidate || current;
}

export default function AiMetricsSection({ deviceId, deviceCode, realtime, onUnauthorized }) {
  const [filterKey, setFilterKey] = useState("1h");
  const [history, setHistory] = useState({ items: [], total_samples: 0, model_version: null, last_updated: null });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const inFlightRef = useRef(false);
  const realtimeItemsRef = useRef([]);
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

    getTelemetryHistory(deviceId, { fromTime, limit: 100, chart: true, signal: controller.signal })
      .then(res => {
        if (!active) return;
        const snapshot = res || { items: [], total_samples: 0, model_version: null, last_updated: null };
        const fromTimestamp = fromTime ? Date.parse(fromTime) : null;
        const recentRealtimeItems = realtimeItemsRef.current.filter(item =>
          fromTimestamp === null || Date.parse(item.recorded_at) >= fromTimestamp);
        const items = mergeTelemetryItems(snapshot.items || [], recentRealtimeItems);
        const livePoints = recentRealtimeItems.filter(item => Date.parse(item.recorded_at) >= Date.parse(snapshot.snapshot_at));
        setHistory({
          ...snapshot,
          items,
          live_points: livePoints,
          total_samples: snapshot.chart_points ? snapshot.total_samples + livePoints.length : items.length,
          timeline_segments: snapshot.timeline_segments ? livePoints.reduce(appendTimeline, snapshot.timeline_segments) : null,
          model_version: items.at(-1)?.model_version || snapshot.model_version,
          last_updated: latestTimestamp(snapshot.last_updated, items.at(-1)?.recorded_at),
        });
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

  useEffect(() => {
    if (!realtime?.connected || !history.chart_mode) return;
    const timer = setInterval(() => setReloadKey(value => value + 1), 15000);
    return () => clearInterval(timer);
  }, [realtime?.connected, history.chart_mode, deviceId]);

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
      const selectedFilter = FILTER_OPTIONS.find(option => option.key === filterKey);
      if (selectedFilter?.minutes && Date.parse(data.recorded_at) < Date.now() - selectedFilter.minutes * 60000) continue;

      const newItem = {
        id: data.id || Date.now(),
        recorded_at: data.recorded_at || new Date().toISOString(),
        ear: data.ear,
        perclos: data.perclos,
        driver_state: data.driver_state,
        confidence: data.confidence,
        face_detected: data.face_detected,
        model_version: data.model_version,
        ai_signals: data.face_detected === false ? null : normalizeAiSignals(data.ai_signals),
      };
      realtimeItemsRef.current = mergeTelemetryItems(realtimeItemsRef.current, [newItem]);
      setHistory(current => {
        const items = current?.items || [];
        const updatedItems = mergeTelemetryItems(items, [{
          ...newItem,
          model_version: newItem.model_version || current.model_version,
        }]);
        const livePoints = [...(current.live_points || [])];
        const isNew = current.chart_points && Date.parse(newItem.recorded_at) >= Date.parse(current.snapshot_at)
          && !livePoints.some(item => item.id === newItem.id || item.recorded_at === newItem.recorded_at);
        if (isNew) livePoints.push(newItem);
        return {
          ...current,
          items: updatedItems,
          live_points: livePoints,
          timeline_segments: isNew && current.timeline_segments ? appendTimeline(current.timeline_segments, newItem) : current.timeline_segments,
          total_samples: current.chart_points ? current.total_samples + (isNew ? 1 : 0) : updatedItems.length,
          model_version: updatedItems.at(-1)?.model_version || current.model_version,
          last_updated: latestTimestamp(current.last_updated, updatedItems.at(-1)?.recorded_at),
        };
      });
    }
  }, [realtime?.events, deviceId, deviceCode, filterKey]);

  const items = history.items || [];
  const isStale = !realtime?.connected;

  // Chart coordinate calculation for EAR & PERCLOS
  const chartWidth = 700;
  const chartHeight = 220;
  const padding = { top: 20, right: 45, bottom: 35, left: 60 };
  const innerW = chartWidth - padding.left - padding.right;
  const innerH = chartHeight - padding.top - padding.bottom;

  const chartItems = history.chart_points ? [...history.chart_points, ...(history.live_points || [])] : items;
  const validItems = chartItems.filter(it => Number.isFinite(Date.parse(it.recorded_at)))
    .sort((a, b) => Date.parse(a.recorded_at) - Date.parse(b.recorded_at));
  const timeline = history.timeline_segments || items.reduce(appendTimeline, []);
  const chartOptions = { width: chartWidth, height: chartHeight, padding,
    maxGapMs: Math.max(5000, (history.bucket_seconds || 0) * 1500) };
  const earPath = metricPath(validItems, it => it.ear, { ...chartOptions, maxValue: .5, gapOf: it => it.ear_has_gap });
  const perclosPath = metricPath(validItems, it => it.perclos, { ...chartOptions, maxValue: 1, gapOf: it => it.perclos_has_gap });
  const marOf = it => Object.hasOwn(it, "mar") ? it.mar : normalizeAiSignals(it.ai_signals)?.mar;
  const hasMar = validItems.some(it => Number.isFinite(marOf(it)));
  const marPath = metricPath(validItems, marOf, { ...chartOptions, maxValue: 2, gapOf: it => it.mar_has_gap });

  return (
    <section className="surface-card ai-metrics-section" aria-label="AI Metrics và Timeline">
      <div className="section-heading ai-metrics-header">
        <div>
          <h2>Số đo AI & trạng thái tài xế</h2>
          <p>Lịch sử EAR / PERCLOS{hasMar ? " / MAR" : ""} và timeline trạng thái tài xế</p>
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
          <strong className="metadata-version" title={history.model_version || "Chưa cung cấp"}>{history.model_version || "Chưa cung cấp"}</strong>
        </div>
        <div className="metadata-item">
          <span className="metadata-label">{history.chart_points ? "Bản ghi trong khoảng:" : "Mẫu gần nhất:"}</span>
          <strong>{history.total_samples || items.length} mẫu</strong>
        </div>
        <div className="metadata-item"><span className="metadata-label">Điểm hiển thị:</span><strong>{validItems.length}</strong></div>
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
            {hasMar && <span className="legend-item"><span className="legend-dot" style={{ backgroundColor: "#9333ea" }} /> MAR (Mở miệng, trục phải 0–2)</span>}
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

              {/* Mean curves and min/max envelopes from time buckets. */}
              {history.chart_mode === "BUCKETED" && [["ear", .5, "#0284c7"], ["perclos", 1, "#10b981"], ["mar", 2, "#9333ea"]].map(([key, maxValue, color]) =>
                <path key={key} d={metricBandPath(validItems, key, { ...chartOptions, maxValue })} fill={color} fillOpacity="0.12" />)}
              {earPath && <path d={earPath} fill="none" stroke="#0284c7" strokeWidth="2.5" strokeLinecap="round" />}
              {perclosPath && <path d={perclosPath} fill="none" stroke="#10b981" strokeWidth="2.5" strokeLinecap="round" />}
              {marPath && <path d={marPath} fill="none" stroke="#9333ea" strokeWidth="2.5" strokeLinecap="round" />}
              {hasMar && [2, 1, 0].map((value, index) => <text key={value} x={chartWidth - padding.right + 8} y={padding.top + innerH * index / 2 + 4} fontSize="10" fill="#9333ea">{value}</text>)}

              {/* X Axis Time Labels */}
              {validItems.length > 0 && (
                <>
                  <text x={padding.left} y={chartHeight - 8} fontSize="10" fill="#64748b">{formatTime(validItems[0].recorded_at)}</text>
                  <text x={chartWidth - padding.right} y={chartHeight - 8} textAnchor="end" fontSize="10" fill="#64748b">{formatTime(validItems.at(-1)?.recorded_at)}</text>
                </>
              )}
            </svg>
          </div>
          {history.chart_mode === "BUCKETED" && <p className="muted-note">Đường biểu diễn trung bình theo khoảng {history.bucket_seconds} giây; vùng màu nhạt thể hiện nhỏ nhất–lớn nhất. Khoảng trống là thiếu số đo.</p>}

          {/* Timeline Trạng thái tài xế (TV4-11) */}
          <div className="ai-timeline-wrap">
            <h3 className="timeline-title">Diễn biến trạng thái · tối đa 60 đoạn gần nhất</h3>
            <div className="timeline-bar" role="list" aria-label="Chuỗi trạng thái theo thời gian">
              {timeline.map((it, idx) => {
                const conf = STATE_COLORS[it.driver_state] || STATE_COLORS.UNKNOWN;
                return (
                  <div
                    key={`${it.start}-${idx}`}
                    role="listitem"
                    className="timeline-segment"
                    style={{ backgroundColor: conf.bg, borderColor: conf.border, color: conf.text }}
                    title={`${conf.label} · ${formatTime(it.start)}–${formatTime(it.end)} · ${it.samples} mẫu`}
                  >
                    <span>{conf.label}</span>
                    <small>{formatTime(it.start)}{it.end !== it.start ? `–${formatTime(it.end)}` : ""}</small>
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}

      <p className="muted-note ai-metrics-note">Số đo vận hành từ Vision Node; không phải kết quả đánh giá độ chính xác mô hình.</p>
    </section>
  );
}
