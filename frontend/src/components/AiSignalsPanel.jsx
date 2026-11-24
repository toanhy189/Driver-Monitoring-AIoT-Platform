import { eyeStateLabel, mouthStateLabel, normalizeAiSignals, qualityLabel, decisionReasonLabel, closureLabel, headMotionLabel, headDownLabel } from "../services/aiSignals.js";

export default function AiSignalsPanel({ signals, stale = false }) {
  const data = normalizeAiSignals(signals);
  if (!data) return null;
  const percentage = value => Number.isFinite(value) ? `${(value * 100).toFixed(0)}%` : "Chưa có";
  const showPosture = !stale && ["LOWERED", "DOWN_RISK", "RECOVERING"].includes(data.head_down_policy?.state);
  return <section className="surface-card detail-panel" aria-label="Tín hiệu mắt và miệng">
    <div className="panel-heading"><h2>Tín hiệu mắt và miệng {data.experimental ? "· Bản thử nghiệm" : ""}</h2></div>
    {stale && <p role="status" className="muted-note">Đây là số đo cũ, chưa xác nhận quan sát hiện tại.</p>}
    {!stale && data.schema_version === "eye-mouth-v2" && data.mouth_crop_reason === "OUTSIDE_FRAME" &&
      <p role="status" className="muted-note">Vùng miệng vượt khung camera. Hãy lùi lại hoặc chỉnh camera để thấy trọn miệng và cằm khi ngáp.</p>}
    <dl className="signals-grid">
      {data.schema_version === "eye-mouth-v2" &&
        <div><dt>Lý do trạng thái AI</dt><dd>{decisionReasonLabel(data.decision_reason)}</dd></div>
      }
      <div><dt>Biểu hiện vùng mắt</dt><dd>{eyeStateLabel(data.eye_state)}</dd></div>
      <div><dt>Hoạt động miệng</dt><dd>{mouthStateLabel(data.mouth_state)}</dd></div>
    </dl>
    {showPosture && <section className="signals-posture" aria-label="Cảnh báo cúi đầu kéo dài">
      <h3>Cảnh báo cúi đầu kéo dài</h3>
      <dl className="signals-grid">
        <div><dt>Theo dõi tư thế</dt><dd>{headDownLabel(data.head_down_policy.state)}</dd></div>
        <div><dt>Góc cúi so với mốc nhìn thẳng</dt><dd>{Number.isFinite(data.head_motion?.pitch_deg) ? `${data.head_motion.pitch_deg.toFixed(1)}°` : "Chưa có"}</dd></div>
        <div><dt>Thời gian cúi được quan sát</dt><dd>{data.head_down_policy.observed_down_seconds.toFixed(1)} / 3 giây</dd></div>
      </dl>
      <p className="muted-note">Cúi ≥12° trong 3 giây có thể kích hoạt cảnh báo, kể cả khi chủ động nhìn xuống.</p>
    </section>}
    <details className="signals-technical">
      <summary>Chi tiết AI</summary>
      <dl className="device-details">
        <div><dt>MAR — độ mở miệng</dt><dd>{data.mar === null ? "Chưa có" : data.mar.toFixed(3)}</dd></div>
        <div><dt>Điểm nhận diện ngáp</dt><dd>{percentage(data.yawn_probability)}</dd></div>
        {data.schema_version === "eye-mouth-v2" &&
          <div><dt>Độ chắc chắn phân loại mắt</dt><dd>{percentage(data.eye_confidence)}{data.eyes_available && data.eye_confidence < .6 ? " · Chưa chắc chắn giữa hai lớp" : ""}</dd></div>}
        <div><dt>Quan sát vùng miệng</dt><dd>{data.mouth_available ? "Có tín hiệu" : "Chưa dùng được"}</dd></div>
        <div><dt>Quan sát vùng mắt</dt><dd>{data.eyes_available ? "Có tín hiệu" : "Chưa dùng được"}</dd></div>
        {data.schema_version === "eye-mouth-v2" && <>
          <div><dt>Chất lượng ảnh mắt</dt><dd>{qualityLabel(data.eye_quality)}</dd></div>
          <div><dt>Chất lượng ảnh miệng</dt><dd>{qualityLabel(data.mouth_quality)}</dd></div>
          <div><dt>Đo hình học mắt EAR</dt><dd>{data.ear_available ? "Có số đo riêng" : "Chưa đo được"}</dd></div>
          <div><dt>Nhánh nhắm mắt kéo dài</dt><dd>{closureLabel(data.eye_closure_state)}</dd></div>
        </>}
        {data.head_down_policy && <>
          <div><dt>Theo dõi tư thế</dt><dd>{headDownLabel(data.head_down_policy.state)}</dd></div>
          <div><dt>Thời gian cúi được quan sát</dt><dd>{data.head_down_policy.observed_down_seconds.toFixed(1)} / 3 giây</dd></div>
        </>}
      </dl>
      <p className="muted-note">Nhánh nhắm mắt cần đúng profile. Phản sáng và che khuất có thể ảnh hưởng kết quả.</p>
    {data.head_motion && <section aria-label="Theo dõi gật đầu">
      <h3>Chuyển động đầu · Đang thử nghiệm</h3>
      <dl className="device-details">
        <div><dt>Quan sát chuyển động</dt><dd>{headMotionLabel(data.head_motion.state)}</dd></div>
        <div><dt>Chu kỳ gật trong 20 giây</dt><dd>{data.head_motion.available && data.head_motion.calibrated ? data.head_motion.nod_count : "Chưa có"}</dd></div>
        <div><dt>Góc cúi so với mốc nhìn thẳng</dt><dd>{data.head_motion.pitch_deg === null ? "Chưa có" : `${data.head_motion.pitch_deg.toFixed(1)}°`}</dd></div>
        <div><dt>Tín hiệu mắt đi kèm</dt><dd>{data.head_motion.eye_closure_supported ? "Gật lặp lại kèm nhắm mắt kéo dài" : "Chưa có bằng chứng kết hợp"}</dd></div>
      </dl>
      <p className="muted-note">Bộ đếm chu kỳ gật chỉ dùng để theo dõi.</p>
    </section>}
    {data.head_eye_fusion && <section aria-label="Kết hợp đầu và mắt">
      <h3>Kết hợp đầu và mắt · {data.head_eye_fusion.mode === "PRIVATE_PREVIEW" ? "Thử riêng trên máy" : "Đã bật theo profile"}</h3>
      <dl className="device-details">
        <div><dt>Quan sát mắt theo tư thế</dt><dd>{closureLabel(data.head_eye_fusion.state)}</dd></div>
        <div><dt>Ngưỡng EAR theo góc đầu</dt><dd>{data.head_eye_fusion.ear_threshold === null ? "Chưa có" : data.head_eye_fusion.ear_threshold.toFixed(3)}</dd></div>
        <div><dt>Bằng chứng kết hợp</dt><dd>{data.head_eye_fusion.risk_candidate ? "Có nguy cơ từ đầu và mắt" : "Chưa đủ bằng chứng nguy cơ"}</dd></div>
      </dl>
      <p className="muted-note">Dữ liệu kết hợp đầu và mắt cần đúng profile; quy tắc cúi kéo dài được xử lý riêng.</p>
    </section>}
      <p className="muted-note signals-note">MAR đo độ mở miệng. Điểm mô hình chưa phải xác suất đã hiệu chuẩn.</p>
    </details>
  </section>;
}
