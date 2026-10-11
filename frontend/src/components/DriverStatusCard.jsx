function DriverStatusCard({ state, faceDetected }) {
  const allowedStates = ["ATTENTIVE", "DISTRACTED", "DROWSY"];
  const safeState = faceDetected === false ? "UNKNOWN" :
    allowedStates.includes(state) ? state : "UNKNOWN";
  // Hiển thị tiếng Việt; giá trị thiếu hoặc không hợp lệ không phải ATTENTIVE.
  const stateText = {
    ATTENTIVE: "TỈNH TÁO",
    DISTRACTED: "MẤT TẬP TRUNG",
    DROWSY: "BUỒN NGỦ",
    UNKNOWN: "CHƯA XÁC ĐỊNH"
  };

  return (
    <article className="driver-status-card">
      <div className="card-header">
        <h2>Trạng thái tài xế</h2>

        <span
          className={`driver-state driver-state--${safeState.toLowerCase()}`}
        >
          {faceDetected === false ? "KHÔNG THẤY MẶT" : stateText[safeState]}
        </span>
      </div>

      <div className="driver-status-body">
        <span className={"driver-face driver-face--" + safeState.toLowerCase()} aria-hidden="true">
          <span className="driver-face-eyes"><span /><span /></span>
          <span className="driver-face-mouth" />
        </span>
        <p className="driver-status-message">
          {faceDetected === false ? "Không thấy mặt" :
            safeState === "UNKNOWN" ? "Chưa nhận được dữ liệu tài xế" : stateText[safeState]}
        </p>
        <p className="driver-status-description">
          {faceDetected === false ? "Camera chưa nhận diện được khuôn mặt tài xế." :
            safeState === "UNKNOWN"
            ? "Trạng thái sẽ cập nhật khi có dữ liệu hợp lệ."
            : "Trạng thái hiện tại của tài xế"}
        </p>
      </div>
    </article>
  );
}

export default DriverStatusCard;
