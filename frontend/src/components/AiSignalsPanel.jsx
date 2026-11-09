import { eyeStateLabel, mouthStateLabel, normalizeAiSignals } from "../services/aiSignals.js";

export default function AiSignalsPanel({ signals, stale = false }) {
  const data = normalizeAiSignals(signals);
  if (!data) return null;
  const percentage = value => Number.isFinite(value) ? `${(value * 100).toFixed(0)}%` : "Chưa có";
  return <section className="surface-card detail-panel" aria-label="Tín hiệu mắt và miệng">
    <div className="panel-heading"><h2>Tín hiệu mắt và miệng {data.experimental ? "· Bản thử nghiệm" : ""}</h2></div>
    {stale && <p role="status" className="muted-note">Đây là số đo cũ, chưa xác nhận quan sát hiện tại.</p>}
    <dl className="device-details">
      <div><dt>MAR — độ mở miệng</dt><dd>{data.mar === null ? "Chưa có" : data.mar.toFixed(3)}</dd></div>
      <div><dt>Hoạt động miệng</dt><dd>{mouthStateLabel(data.mouth_state)}</dd></div>
      <div><dt>Điểm nhận diện ngáp</dt><dd>{percentage(data.yawn_probability)}</dd></div>
      <div><dt>Quan sát vùng miệng</dt><dd>{data.mouth_available ? "Có tín hiệu" : "Chưa dùng được"}</dd></div>
      <div><dt>Biểu hiện vùng mắt</dt><dd>{eyeStateLabel(data.eye_state)}</dd></div>
      <div><dt>Quan sát vùng mắt</dt><dd>{data.eyes_available ? "Có tín hiệu" : "Chưa dùng được"}</dd></div>
    </dl>
    <p className="muted-note">MAR là số đo mở miệng; ngáp là kết quả nhận diện hành động. Điểm mô hình chưa phải xác suất đã hiệu chuẩn. Nhãn mắt buồn ngủ không đồng nghĩa mắt nhắm. Quyết định cảnh báo còn xét tín hiệu theo thời gian và policy.</p>
  </section>;
}
