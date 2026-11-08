import { useEffect, useRef, useState } from "react";
import { getEventVideo, getVideoContent, getPlayback, getPlaybackContent } from "../services/videos.js";
import { authenticatedRequest } from "../services/api.js";

const statusText = {
  DELETED: "Video đã được xóa.", MISSING: "File video không còn trong kho lưu trữ.",
  UNLINKED: "Sự kiện chưa có liên kết video.",
  PENDING_OR_UNAVAILABLE: "Chưa nhận được clip của sự kiện này. Hãy thử lại sau khi clip được đóng và gửi lên.",
};

const wait = (signal, ms) => new Promise((resolve, reject) => {
  const aborted = () => { clearTimeout(timer); reject(new DOMException("Aborted", "AbortError")); };
  const timer = setTimeout(() => { signal.removeEventListener("abort", aborted); resolve(); }, ms);
  signal.addEventListener("abort", aborted, { once: true });
  if (signal.aborted) aborted();
});

export default function VideoPlayer({ video: initialVideo, deviceId, messageId, state, title, onClose, onUnauthorized, canDelete = false }) {
  const [video, setVideo] = useState(null);
  const [source, setSource] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const closeButton = useRef(null);
  const request = useRef(null);

  useEffect(() => {
    let active = true;
    let objectUrl;
    const controller = new AbortController();
    request.current = controller;
    setLoading(true); setError(""); setVideo(null); setSource(null);
    async function load() {
      const result = initialVideo ? { status: initialVideo.deleted_at ? "DELETED" : "AVAILABLE", video: initialVideo }
        : await getEventVideo(deviceId, messageId, { signal: controller.signal });
      if (!active) return;
      if (result.status !== "AVAILABLE" || !result.video) throw new Error(statusText[result.status] || "Chưa có video.");
      const match = result.video;
      if (match.device_id !== deviceId) throw new Error("Video không thuộc thiết bị đang xem.");
      setVideo(match);
      let playback = await getPlayback(match.video_id, { signal: controller.signal, start: true });
      const deadline = Date.now() + 150000;
      while (playback.status === "PROCESSING" && Date.now() < deadline) {
        await wait(controller.signal, 1000);
        playback = await getPlayback(match.video_id, { signal: controller.signal });
      }
      if (playback.status !== "READY") {
        const message = playback.reason === "STORAGE_FULL" ? "Kho video không còn đủ chỗ tạo bản xem trên web."
          : playback.status === "BUSY" ? "Máy chủ đang xử lý các clip khác. Hãy thử lại."
          : "Chưa chuẩn bị được bản xem trên trình duyệt.";
        throw new Error(message + " Bạn vẫn có thể tải video gốc.");
      }
      const content = await getPlaybackContent(match.video_id, { signal: controller.signal });
      if (!active) return;
      objectUrl = URL.createObjectURL(content);
      setSource(objectUrl);
    }
    load().catch(cause => {
      if (!active || cause.name === "AbortError") return;
      if (cause.status === 401) onUnauthorized?.();
      else setError(cause.message || "Không tải được video.");
    }).finally(() => { if (active) setLoading(false); });
    return () => {
      active = false; controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [initialVideo?.video_id, initialVideo?.deleted_at, deviceId, messageId, onUnauthorized, attempt]);

  useEffect(() => {
    closeButton.current?.focus();
    const handleKeyDown = event => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  async function downloadOriginal() {
    if (!video || downloading) return;
    setDownloading(true);
    try {
      const content = await getVideoContent(video.video_id, { signal: request.current.signal });
      const url = URL.createObjectURL(content);
      const link = document.createElement("a");
      link.href = url; link.download = `video-${video.video_id}.mp4`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (cause) {
      if (cause.name !== "AbortError") {
        if (cause.status === 401) onUnauthorized?.(); else setError(cause.message);
      }
    } finally { setDownloading(false); }
  }

  return <div className="video-modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="video-modal" role="dialog" aria-modal="true" aria-labelledby="video-modal-title">
      <header className="video-modal-header">
        <div><h2 id="video-modal-title">{title || `Video trạng thái ${state || video?.state || ""}`}</h2><p>Mã clip: {video?.message_id || messageId}</p></div>
        <button ref={closeButton} type="button" className="video-modal-close" aria-label="Đóng video" onClick={onClose}>×</button>
      </header>
      <div className="video-modal-content">
        {loading && <p role="status">Đang chuẩn bị video cho trình duyệt…</p>}
        {error && <p role="alert" className="notice-error">{error}</p>}
        {source && <video controls preload="metadata" src={source} className="history-video"
          aria-label={`Video trạng thái ${video?.state || ""}`}
          onError={() => setError("Trình duyệt không phát được video này. Bạn có thể tải video gốc để xem.")} />}
        {video && <p><small>{video.state} · {(video.size_bytes / 1048576).toFixed(1)} MB (bản gốc)</small></p>}
        <div className="config-actions">
          {video && <button className="outline-button" disabled={downloading} onClick={downloadOriginal}>{downloading ? "Đang tải…" : "Tải video gốc"}</button>}
          {error && !loading && <button className="outline-button" onClick={() => setAttempt(value => value + 1)}>Thử lại</button>}
          {video && canDelete && <button className="outline-button" onClick={async () => {
            if (!window.confirm("Xóa vĩnh viễn video này? Lịch sử sự kiện vẫn được giữ.")) return;
            try { await authenticatedRequest(`/videos/${video.video_id}`, { method: "DELETE" }); onClose(); }
            catch (cause) { if (cause.status === 401) onUnauthorized?.(); else setError(cause.message); }
          }}>Xóa video</button>}
        </div>
      </div>
    </section>
  </div>;
}
