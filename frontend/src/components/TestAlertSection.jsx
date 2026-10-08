import { useEffect, useRef, useState } from "react";
import { Icon } from "./AppShell.jsx";
import { commandStatus, commandValue } from "../services/commandDisplay.js";
import { TEST_ALERT_BODY, commandBelongsToDevice, commandFinished, getCommand, keepNewerCommand, normalizeCommand, sendTestAlert, testAlertBlockReason, validateTestAlertParameters } from "../services/commands.js";
import "../styles/commands.css";

const RESULT_REFRESH_MS = 5000;

const NO_REALTIME = { events: [] };

function TestAlertSection({ user, realtime = NO_REALTIME, device, deviceId, onUnauthorized, onOpenHistory }) {
  const [isOpen, setIsOpen] = useState(false);
  const [form, setForm] = useState(() => ({
    buzzer_ms: String(TEST_ALERT_BODY.buzzer_ms),
    vibration_ms: String(TEST_ALERT_BODY.vibration_ms),
    led_mode: TEST_ALERT_BODY.led_mode,
  }));
  const [command, setCommand] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [resultError, setResultError] = useState("");
  const submitController = useRef(null);
  const resultController = useRef(null);
  const lastEventSequence = useRef(realtime.events.at(-1)?.sequence ?? 0);
  const pendingResults = useRef(new Map());

  useEffect(() => () => {
    submitController.current?.abort();
    resultController.current?.abort();
  }, []);

  useEffect(() => {
    for (const event of realtime.events) {
      if (event.sequence <= lastEventSequence.current) continue;
      lastEventSequence.current = event.sequence;
      if (event.type !== "command.updated") continue;
      let update;
      try { update = normalizeCommand(event.data); } catch { continue; }
      if (!commandBelongsToDevice(update, deviceId, device?.device_code, { requireIdentity: true })) continue;
      pendingResults.current.set(update.request_id,
        keepNewerCommand(pendingResults.current.get(update.request_id), update));
      setCommand(current => current?.request_id === update.request_id ?
        keepNewerCommand(current, update) : current);
    }
  }, [realtime.events, deviceId, device?.device_code]);

  const reason = testAlertBlockReason({ user, device, isSubmitting });
  const state = commandStatus(command);

  const refreshResult = async () => {
    if (!command?.request_id) return false;
    if (resultController.current) return true;
    const controller = new AbortController();
    resultController.current = controller;
    try {
      const result = await getCommand(command.request_id, { signal: controller.signal });
      if (!commandBelongsToDevice(result, deviceId, device?.device_code)) {
        throw new Error("BE trả kết quả của thiết bị khác.");
      }
      setCommand(current => keepNewerCommand(current, result));
      setResultError("");
      return !commandFinished(result);
    } catch (error) {
      if (error.name === "AbortError") return false;
      if (error.status === 401) onUnauthorized();
      else setResultError(error.status === 404 ?
        "BE chưa có API xem kết quả lệnh. Chưa thể xác nhận ESP32 đã hoàn tất." :
        `${error.message || "Không lấy được kết quả lệnh."} Chưa thể xác nhận ESP32 đã hoàn tất.`);
      return false;
    } finally {
      if (resultController.current === controller) resultController.current = null;
    }
  };

  useEffect(() => {
    if (!command?.request_id || commandFinished(command) || resultError) return;
    let active = true;
    let timer;
    const poll = async () => {
      const shouldContinue = await refreshResult();
      if (active && shouldContinue) timer = setTimeout(poll, RESULT_REFRESH_MS);
    };
    timer = setTimeout(poll, RESULT_REFRESH_MS);
    return () => { active = false; clearTimeout(timer); };
  }, [command?.request_id, command?.status, command?.ack_status, resultError]);

  const submit = async event => {
    event.preventDefault();
    if (reason || submitController.current) return;
    let parameters;
    try {
      parameters = validateTestAlertParameters(form);
    } catch (error) {
      setSubmitError(error.message);
      return;
    }
    setIsSubmitting(true);
    setSubmitError("");
    setResultError("");
    const controller = new AbortController();
    submitController.current = controller;
    try {
      const response = await sendTestAlert(deviceId, { parameters, signal: controller.signal });
      if (!commandBelongsToDevice(response, deviceId, device?.device_code)) {
        throw new Error("BE trả lệnh của thiết bị khác.");
      }
      setCommand(keepNewerCommand(response, pendingResults.current.get(response.request_id)));
    } catch (error) {
      if (error.name === "AbortError") return;
      if (error.status === 401) onUnauthorized();
      else setSubmitError(`${error.message || "Không gửi được yêu cầu."} Nếu kết nối bị gián đoạn, hãy kiểm tra lịch sử trước khi gửi lại.`);
    } finally {
      if (submitController.current === controller) submitController.current = null;
      setIsSubmitting(false);
    }
  };

  const updateForm = (field, value) => {
    setSubmitError("");
    setForm(current => ({ ...current, [field]: value }));
  };

  return <>
    <button className="outline-button detail-test-trigger" type="button" aria-expanded={isOpen} aria-controls="test-alert-form" onClick={() => setIsOpen(open => !open)}><Icon name="alert" size={18} /> {isOpen ? "Ẩn kiểm tra cảnh báo" : "Kiểm tra cảnh báo"}</button>
    {isOpen && <section id="test-alert-form" className="surface-card test-alert-panel" aria-labelledby="test-alert-heading">
      <div className="panel-heading"><Icon name="alert" /><h2 id="test-alert-heading">Kiểm tra cảnh báo</h2></div>
      <p>Thử LED, còi và motor trong một lệnh. Lệnh này không chọn mức cảnh báo và không đổi cấu hình mặc định. Chỉ xác nhận hoàn tất khi BE nhận ACK từ ESP32.</p>
      <form onSubmit={submit} noValidate>
        <div className="test-alert-fields">
          <label>Thời lượng còi (ms)<input type="number" min="0" max="10000" step="1" inputMode="numeric" value={form.buzzer_ms} onChange={event => updateForm("buzzer_ms", event.target.value)} disabled={isSubmitting} /></label>
          <label>Thời lượng rung (ms)<input type="number" min="0" max="10000" step="1" inputMode="numeric" value={form.vibration_ms} onChange={event => updateForm("vibration_ms", event.target.value)} disabled={isSubmitting} /></label>
          <label>Chế độ LED<select value={form.led_mode} onChange={event => updateForm("led_mode", event.target.value)} disabled={isSubmitting}><option value="ON">Sáng liên tục</option><option value="FLASH">Nhấp nháy</option></select></label>
        </div>
        <p className="test-alert-help">1000 ms = 1 giây. Thời lượng cho phép: 0–10000 ms.</p>
        {reason && <p className="action-reason" role="status">{reason}</p>}
        {submitError && <p className="notice-error" role="alert">{submitError}</p>}
        <div className="test-alert-actions">
          <button className="primary-button" type="submit" disabled={Boolean(reason)}>{isSubmitting ? "Đang gửi…" : "Gửi lệnh kiểm tra"}</button>
          <button className="outline-button" type="button" onClick={onOpenHistory}>Xem lịch sử lệnh <Icon name="arrow" size={16} /></button>
        </div>
      </form>
      {command && <div className="current-command" aria-live="polite"><div><strong>Lệnh {command.request_id}</strong><span className={`command-state command-state--${state.tone}`}>{state.label}</span></div><p>Trạng thái BE: {commandValue(command.status)} · ACK: {commandValue(command.ack_status)}</p>{(command.error_code || command.error_message) && <p>Lỗi: {commandValue(command.error_message || command.error_code)}</p>}{!commandFinished(command) && <button className="text-link" type="button" onClick={refreshResult}>Kiểm tra kết quả</button>}</div>}
      {resultError && <p className="notice-error" role="alert">{resultError}</p>}
    </section>}
  </>;
}

export default TestAlertSection;
