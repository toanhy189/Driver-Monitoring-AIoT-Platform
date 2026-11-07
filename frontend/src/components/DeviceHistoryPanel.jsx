import { useEffect, useState } from "react";
import { getDeviceHistory } from "../services/history.js";
import { commandStatus } from "../services/commandDisplay.js";
import VideoPlayer from "./VideoPlayer.jsx";
import { Icon } from "@iconify/react";

const TABS = { telemetry: "Số đo", timeline: "Diễn biến", commands: "Lệnh", metrics: "Thống kê" };
const time = value => value ? new Date(value).toLocaleString("vi-VN") : "Chưa có";
const number = value => typeof value === "number" ? value.toFixed(2) : "Chưa có";
const percentage = value => typeof value === "number" ? `${(value * 100).toFixed(0)}%` : "Chưa có";
const states = { ATTENTIVE: "Tỉnh táo", DISTRACTED: "Mất tập trung", DROWSY: "Buồn ngủ" };

export default function DeviceHistoryPanel({ deviceId, deviceType, onUnauthorized }) {
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState("telemetry");
  const [filters, setFilters] = useState({ from: "", to: "", modelVersion: "" });
  const [query, setQuery] = useState(filters);
  const [offset, setOffset] = useState(0);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [selectedVideoEvent, setSelectedVideoEvent] = useState(null);
  const isVisionNode = deviceType === "VISION_NODE";
  const tabs = isVisionNode ? TABS : { timeline: TABS.timeline, commands: TABS.commands };
  const activeKind = tabs[kind] ? kind : "timeline";

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    setLoading(true); setError(""); setResult(null);

    getDeviceHistory(deviceId, activeKind, { ...query, offset, limit: 50, signal: controller.signal })
      .then(value => { if (!controller.signal.aborted) setResult(value); })
      .catch(cause => {
        if (cause.name === "AbortError") return;
        if (cause.status === 401) onUnauthorized?.(); else setError(cause.message);
      }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();

  }, [open, deviceId, activeKind, query, offset, onUnauthorized]);

  return <section className="surface-card detail-panel" aria-label="Lịch sử và thống kê">
    <button type="button" className="outline-button" aria-expanded={open} onClick={() => setOpen(!open)}>Lịch sử và thống kê thiết bị</button>
    {open && <>
      <div className="config-actions">{Object.entries(tabs).map(([key, label]) => <button key={key} type="button"
        className={key === activeKind ? "primary-button" : "outline-button"} onClick={() => { setKind(key); setOffset(0); }}>{label}</button>)}</div>
      <form className="test-alert-fields" onSubmit={event => { event.preventDefault(); setOffset(0); setQuery({ ...filters }); }}>
        <label>Từ thời điểm<input type="datetime-local" value={filters.from} onChange={event => setFilters({ ...filters, from: event.target.value })} /></label>
        <label>Đến thời điểm<input type="datetime-local" value={filters.to} onChange={event => setFilters({ ...filters, to: event.target.value })} /></label>
        <label>Phiên bản AI<input value={filters.modelVersion} maxLength={80} onChange={event => setFilters({ ...filters, modelVersion: event.target.value })} /></label>
        <button className="outline-button" type="submit">Lọc dữ liệu</button>
      </form>
      <p>Mặc định xem 24 giờ gần nhất. Khoảng thời gian tối đa 31 ngày.</p>
      {loading && <p role="status">Đang tải dữ liệu…</p>}
      {error && <p role="alert" className="notice-error">{error}</p>}
      {selectedVideoEvent && (
        <VideoPlayer
          deviceId={deviceId}
          messageId={selectedVideoEvent.event_id}
          state={selectedVideoEvent.state}
          onClose={() => setSelectedVideoEvent(null)}
          onUnauthorized={onUnauthorized}
        />
      )}
      {activeKind === "metrics" && result && <dl className="device-details">
        <div><dt>Số bản ghi đo</dt><dd>{result.telemetry.count}</dd></div>
        <div><dt>EAR trung bình</dt><dd>{number(result.telemetry.avg_ear)}</dd></div>
        <div><dt>PERCLOS trung bình</dt><dd>{number(result.telemetry.avg_perclos)}</dd></div>
        <div><dt>Cảnh báo / lệnh</dt><dd>{result.alerts.count} / {result.commands.count}</dd></div>
        <div><dt>Thời gian HTTP trung bình</dt><dd>{number(result.latency.http_avg_ms)} ms</dd></div>
        <div><dt>Thời gian hoàn tất trung bình</dt><dd>{number(result.latency.completed_avg_ms)} ms</dd></div>
      </dl>}
      {activeKind !== "metrics" && result?.items && <>
        {result.items.length === 0 ? <p>Chưa có dữ liệu trong khoảng đã chọn.</p> : <div className="table-scroll">
          <table className="device-table">
            <thead>
              <tr>
                <th>Thời gian</th>
                {activeKind === "telemetry" ? (
                  <>
                    <th>Mắt (PERCLOS / EAR)</th>
                    <th>Trạng thái đầu (Yaw / Pitch / Roll)</th>
                    <th>Phiên bản AI</th>
                  </>
                ) : (
                  <>
                    <th>Nội dung</th>
                    <th>Thông tin</th>
                    {activeKind === "timeline" && isVisionNode && <th className="video-column-heading">Video</th>}
                  </>
                )}
              </tr>
            </thead>

            <tbody>
              {result.items.map((item, index) => (
                <tr key={`${item.kind || activeKind}-${item.id || item.request_id || index}`}>
                  <td>{time(item.timestamp || item.recorded_at || item.created_at)}</td>

                  {activeKind === "telemetry" ? (
                    <>
                      <td title={`PERCLOS: ${percentage(item.perclos)}\nEAR: ${number(item.ear)}`}>
                        {percentage(item.perclos)} / {number(item.ear)}
                      </td>

                      <td title={`Yaw: ${number(item.head_pose?.yaw)}\nPitch: ${number(item.head_pose?.pitch)}\nRoll: ${number(item.head_pose?.roll)}`}>
                        {number(item.head_pose?.yaw)} /{" "}
                        {number(item.head_pose?.pitch)} /{" "}
                        {number(item.head_pose?.roll)}
                      </td>

                      <td>{item.model_version || "Chưa có"}</td>
                    </>
                  ) : (
                    <>
                      <td>
                        {activeKind === "commands"
                          ? commandStatus(item).label
                          : {
                              event: "Sự kiện AI",
                              alert: "Cảnh báo",
                              command: "Lệnh thiết bị",
                            }[item.kind] || "Chưa xác định"}
                      </td>

                      <td>
                        {activeKind === "commands"
                          ? `${number(item.latency_ms)} ms`
                          : item.kind === "command"
                            ? commandStatus(item.data).label
                            : item.kind === "alert"
                              ? `Mức ${item.data.severity || "chưa có"}`
                              : states[item.data?.state] || "Đã ghi nhận"}
                      </td>
                      {activeKind === "timeline" && isVisionNode && (
                        <td className="video-column-cell">
                          {item.kind === "event" && item.data?.event_type === "STATE_CHANGED" && item.event_id && (
                            <button
                              type="button"
                              className="video-open-button"
                              aria-label={`Xem video sự kiện ${states[item.data.state] || item.data.state || ""}`}
                              title="Xem video"
                              onClick={() => setSelectedVideoEvent({
                                event_id: item.event_id,
                                state: item.data.state,
                              })}
                            >
                              <Icon icon="material-symbols:play-circle-outline" width={23} height={23} aria-hidden="true" />
                            </button>
                          )}
                        </td>
                      )}
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>

          </div>}
        <div className="config-actions">
          <button className="outline-button" disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - 50))}>Trang trước</button>
          <button className="outline-button" disabled={!result.has_more || loading} onClick={() => setOffset(offset + 50)}>Trang sau</button>
        </div>
      </>}
    </>}
  </section>;
}
