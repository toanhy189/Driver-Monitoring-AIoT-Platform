function DriverStatusCard({ state }) {
    // hiển thị tiếng việt
  const stateText = {
    ATTENTIVE: "TỈNH TÁO",
    DISTRACTED: "MẤT TẬP TRUNG",
    DROWSY: "BUỒN NGỦ",
    UNKNOWN: "KHÔNG XÁC ĐỊNH"
  };

  return (
    <article className="driver-status-card">
      <div className="card-header">
        <h2>Trạng thái tài xế</h2>

        <span
          className={`driver-state driver-state--${state.toLowerCase()}`}
        >
          {stateText[state] || "KHÔNG XÁC ĐỊNH"}
        </span>
      </div>

      <p className="driver-status-description">
        Trạng thái hiện tại của tài xế
      </p>
    </article>
  );
}

export default DriverStatusCard;