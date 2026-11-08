import { useEffect, useRef, useState } from "react";
import { getVideoContent, getVideoForMessage } from "../services/videos.js";
import { authenticatedRequest } from "../services/api.js";

export default function VideoPlayer({ deviceId, messageId, state, onClose, onUnauthorized, canDelete = false }) {
  const [video, setVideo] = useState(null);
  const [source, setSource] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const closeButton = useRef(null);

  useEffect(() => {
    let active = true;
    let objectUrl;
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setVideo(null);
    setSource(null);

    getVideoForMessage(deviceId, messageId, { signal: controller.signal })
      .then(async videos => {
        if (!active) return;
        const match = videos[0];
        if (!match) {
          setError("Sự kiện này chưa có video được lưu.");
          return;
        }
        setVideo(match);
        const content = await getVideoContent(match.video_id, { signal: controller.signal });
        if (!active) return;
        objectUrl = URL.createObjectURL(content);
        setSource(objectUrl);
      })
      .catch(cause => {
        if (!active || cause.name === "AbortError") return;
        if (cause.status === 401) onUnauthorized?.();
        else setError(cause.message || "Không tải được video.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [deviceId, messageId, onUnauthorized]);

  useEffect(() => {
    closeButton.current?.focus();
    const handleKeyDown = event => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div
      className="video-modal-backdrop"
      onMouseDown={event => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        className="video-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="video-modal-title"
      >
        <header className="video-modal-header">
          <div>
            <h2 id="video-modal-title">Video trạng thái {state || video?.state || ""}</h2>
            <p>Mã sự kiện: {messageId}</p>
          </div>
          <button
            ref={closeButton}
            type="button"
            className="video-modal-close"
            aria-label="Đóng video"
            onClick={onClose}
          >
            ×
          </button>
        </header>
        <div className="video-modal-content">
          {loading && <p role="status">Đang tải video…</p>}
          {error && <p role="alert" className="notice-error">{error}</p>}
          {source && (
            <video
              controls
              preload="metadata"
              src={source}
              className="history-video"
              aria-label={`Video trạng thái ${video?.state || ""}`}
            />
          )}
          {video && <small>{video.state} · {(video.size_bytes / (1024 * 1024)).toFixed(1)} MB</small>}
          {video && canDelete && <button className="outline-button" onClick={async () => {
            if (!window.confirm("Xóa vĩnh viễn video này? Lịch sử sự kiện vẫn được giữ.")) return;
            try { await authenticatedRequest(`/videos/${video.video_id}`, { method: "DELETE" }); onClose(); }
            catch (cause) { if (cause.status === 401) onUnauthorized?.(); else setError(cause.message); }
          }}>Xóa video</button>}
        </div>
      </section>
    </div>
  );
}
