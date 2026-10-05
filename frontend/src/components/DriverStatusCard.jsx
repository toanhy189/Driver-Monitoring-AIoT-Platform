function DriverStatusCard({ state }) {
  const allowedStates = ["ATTENTIVE", "DISTRACTED", "DROWSY"];
  const safeState = allowedStates.includes(state) ? state : "UNKNOWN";
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
          {stateText[safeState]}
        </span>
      </div>

      <p className="driver-status-description">
        {safeState === "UNKNOWN"
          ? "Chưa có trạng thái tài xế hợp lệ"
          : "Trạng thái hiện tại của tài xế"}
      </p>
    </article>
  );
}

export default DriverStatusCard;
