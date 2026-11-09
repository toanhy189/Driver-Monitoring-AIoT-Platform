import { useEffect, useRef, useState } from "react";
import { getRule, saveRule, RULE_POLICY_VERSION, ruleBlockerLabel } from "../services/rules.js";
import { Icon } from "./AppShell.jsx";
import "../styles/rules.css";

export default function RuleBindingPanel({ deviceId, device, onUnauthorized, onOpenTarget, onOpenAlerts }) {
  const [saved, setSaved] = useState(null);
  const [draft, setDraft] = useState({ target: "", enabled: false });
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [readError, setReadError] = useState("");
  const [conflict, setConflict] = useState(false);
  const [notice, setNotice] = useState("");
  const baseline = useRef(null);
  const dirtyRef = useRef(false);
  const busyRef = useRef(false);
  const readController = useRef(null);
  const saveController = useRef(null);

  function apply(result, reset) {
    setSaved(result);
    if (reset || !dirtyRef.current) {
      baseline.current = result;
      setDraft({ target: result.target_device_id ? String(result.target_device_id) : "", enabled: result.enabled });
      dirtyRef.current = false;
      setDirty(false);
    }
  }

  async function refresh(reset = false) {
    if (busyRef.current || readController.current) return;
    if (reset && dirtyRef.current && !window.confirm("Tải lại và bỏ thay đổi chưa lưu?")) return;
    const controller = new AbortController();
    readController.current = controller;
    try {
      const result = await getRule(deviceId, { signal: controller.signal });
      if (controller.signal.aborted) return;
      apply(result, reset);
      setReadError("");
      if (reset) { setConflict(false); setError(""); setNotice(""); }
    } catch (cause) {
      if (cause.name === "AbortError") return;
      if (cause.status === 401) onUnauthorized?.();
      else setReadError(cause.message);
    } finally {
      if (readController.current === controller) readController.current = null;
    }
  }

  useEffect(() => {
    refresh();
    const timer = setInterval(() => refresh(), 5000);
    return () => {
      clearInterval(timer);
      readController.current?.abort();
      readController.current = null;
      saveController.current?.abort();
    };
  }, [deviceId]);

  function edit(values) {
    dirtyRef.current = true;
    setDirty(true);
    setNotice("");
    setError("");
    setDraft(current => ({ ...current, ...values }));
  }

  async function submit(event) {
    event.preventDefault();
    if (busyRef.current || conflict || !baseline.current || readError) return;
    busyRef.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    readController.current?.abort();
    readController.current = null;
    const controller = new AbortController();
    saveController.current = controller;
    try {
      const result = await saveRule(deviceId, baseline.current, draft, { signal: controller.signal });
      if (controller.signal.aborted) return;
      apply(result, true);
      setNotice(result.enabled ? "Đã lưu và bật cảnh báo tự động. Xem trạng thái hoạt động bên dưới." :
        "Đã lưu liên kết ở trạng thái tắt. Có thể mở ESP32 để kiểm tra trước khi bật tự động.");
    } catch (cause) {
      if (cause.name === "AbortError") return;
      if (cause.status === 401) onUnauthorized?.();
      else { setError(cause.message); if (cause.status === 409) setConflict(true); }
    } finally {
      busyRef.current = false;
      if (saveController.current === controller) saveController.current = null;
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  const target = saved?.targets.find(item => item.id === Number(draft.target));
  const targetChanged = Number(draft.target) !== baseline.current?.target_device_id;
  const enableReason = !baseline.current?.target_device_id || targetChanged ? "Lưu thiết bị nhận ở trạng thái tắt trước khi bật tự động." :
    device?.lifecycle_state !== "ACTIVE" || target?.lifecycle_state !== "ACTIVE" ? "Camera và ESP32 phải được kích hoạt trước khi bật." :
    target?.active_source_id ? "ESP32 này đang nhận cảnh báo từ camera khác." :
    saved?.readiness.inflight && !baseline.current.enabled ? "Lệnh trước còn đang gửi hoặc chờ phản hồi; hãy kiểm tra lịch sử." : "";
  const loadedTarget = saved?.readiness.target;
  const blockers = saved?.readiness.blockers || [];

  return <section className="surface-card rule-panel" aria-labelledby="rule-binding-heading">
    <div className="panel-heading"><Icon name="settings" /><h2 id="rule-binding-heading">Cảnh báo tự động</h2></div>
    <p>Chọn ESP32 nhận cảnh báo từ camera {device?.device_code}. Lưu liên kết không gửi lệnh kiểm tra tải.</p>
    {!saved && !readError && <p role="status">Đang tải liên kết…</p>}
    {readError && <p role="alert" className="notice-error">{readError} Trạng thái bên dưới có thể đã cũ.</p>}
    {saved && <>
      <form onSubmit={submit} className="rule-form">
        <label htmlFor="rule-target">Thiết bị nhận cảnh báo</label>
        <select id="rule-target" value={draft.target} disabled={busy} onChange={event => edit({ target: event.target.value, enabled: false })}>
          <option value="">Chọn Alert Node…</option>
          {saved.targets.map(item => <option key={item.id} value={item.id}>
            {item.name ? `${item.name} · ` : ""}{item.device_code} — {item.status === "ONLINE" ? "Online" : "Offline"}
            {item.lifecycle_state !== "ACTIVE" ? ` · ${item.lifecycle_state}` : ""}{item.active_source_id ? " · Đã liên kết camera khác" : ""}
          </option>)}
          {loadedTarget && !saved.targets.some(item => item.id === loadedTarget.id) &&
            <option value={loadedTarget.id}>{loadedTarget.device_code} — Không còn khả dụng</option>}
        </select>
        {!saved.targets.length && <p>Chưa có Alert Node khả dụng. Đăng ký và kích hoạt ESP32 trong danh sách thiết bị.</p>}
        <label className="rule-toggle"><input type="checkbox" checked={draft.enabled}
          disabled={busy || Boolean(enableReason && !draft.enabled)} onChange={event => edit({ enabled: event.target.checked })} />
          Bật cảnh báo tự động</label>
        {enableReason && <p className="rule-help">{enableReason}</p>}
        <p className="rule-help">Khi bật, sự kiện AI mới hợp lệ có thể điều khiển LED, còi và motor. Tắt sẽ chặn lệnh mới và hủy phần chưa gửi; tải đã chạy có thể tiếp tục hết thời lượng.</p>
        <div className="rule-actions">
          <button className="primary-button" type="submit" disabled={busy || !draft.target || conflict || Boolean(readError)}>{busy ? "Đang lưu…" : "Lưu thiết lập"}</button>
          <button className="outline-button" type="button" disabled={busy} onClick={() => refresh(true)}>Tải lại thiết lập</button>
        </div>
        {dirty && <p className="rule-help">Có thay đổi chưa lưu. Trạng thái hoạt động bên dưới phản ánh thiết lập đã lưu.</p>}
        {error && <p role="alert" className="notice-error">{error}{conflict && " Bấm Tải lại thiết lập để kiểm tra trước khi lưu tiếp."}</p>}
        {notice && <p role="status" className="notice-success">{notice}</p>}
      </form>
      <div className="rule-status" aria-live="polite">
        <strong>{saved.enabled ? "Thiết lập đã lưu: Bật tự động" : "Thiết lập đã lưu: Tắt tự động"}</strong>
        {readError ? <p>Chưa xác nhận được trạng thái mới.</p> : blockers.length ? <ul>{blockers.map(code => <li key={code}>{ruleBlockerLabel(code)}</li>)}</ul> :
          <p>Đang nhận quan sát AI mới và thiết bị nhận còn kết nối. Backend tiếp tục kiểm tra từng sự kiện trước khi phát lệnh.</p>}
        {saved.readiness.inflight && <p>Lệnh trước còn đang gửi hoặc chờ phản hồi. Xem lịch sử tại ESP32 nhận cảnh báo.</p>}
        {loadedTarget && <button type="button" className="outline-button" onClick={() => onOpenTarget?.(loadedTarget)}>
          Mở {loadedTarget.device_code} để kiểm tra / xem lệnh
        </button>}
        <button type="button" className="text-link" onClick={onOpenAlerts}>Xem lịch sử cảnh báo</button>
      </div>
    </>}
    {!saved && readError && <button type="button" className="outline-button" onClick={() => refresh(true)}>Thử tải lại</button>}
    <details className="rule-policy"><summary>Policy áp dụng: {RULE_POLICY_VERSION}</summary>
      <div className="rule-table-wrap"><table><thead><tr><th>Mức</th><th>Nguy cơ kéo dài</th><th>Thời lượng</th><th>Tải</th></tr></thead>
        <tbody><tr><td>1</td><td>3 giây</td><td>1 giây</td><td>LED + còi</td></tr>
          <tr><td>2</td><td>6 giây</td><td>2 giây</td><td>LED + còi + motor</td></tr>
          <tr><td>3</td><td>10 giây</td><td>3 giây</td><td>LED + còi + motor</td></tr></tbody></table></div>
      <p>DROWSY và DISTRACTED dùng policy này. Mức 3 chỉ nhắc tiếp khi đủ khoảng tối thiểu 5 giây, có quan sát mới và không bị chặn bởi lệnh đang chờ. ATTENTIVE ổn định 2 giây kết thúc đợt nguy cơ. UNKNOWN ngắt tính liên tục, báo lỗi giám sát riêng sau 2 giây và giới hạn nhắc lỗi 30 giây. SESSION_ENDED đóng phiên, hủy phần chưa gửi. Dữ liệu gửi bù không kích tải.</p>
      <p>Nhịp bật/tắt từng tải chỉnh tại Cấu hình cảnh báo của ESP32. Các ngưỡng trên là policy thử nghiệm đồ án.</p>
    </details>
  </section>;
}
