import { useState } from "react";
import { authenticatedRequest } from "../services/api.js";

export default function HardwareVersionForm({ deviceId, initialValue, onSaved, onUnauthorized }) {
  const [value, setValue] = useState(initialValue || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function save(event) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      await authenticatedRequest(`/devices/${deviceId}/hardware`, { method: "PATCH", body: { hardware_version: value.trim() } });
      onSaved?.();
    } catch (cause) { if (cause.status === 401) onUnauthorized?.(); else setError(cause.message); }
    finally { setBusy(false); }
  }
  return <form className="surface-card config-actions" onSubmit={save}>
    <label>Phiên bản phần cứng<input required maxLength={80} value={value} onChange={event => setValue(event.target.value)} /></label>
    <button className="outline-button" disabled={busy || !value.trim()}>Lưu phần cứng</button>
    {error && <p role="alert" className="notice-error">{error}</p>}
  </form>;
}
