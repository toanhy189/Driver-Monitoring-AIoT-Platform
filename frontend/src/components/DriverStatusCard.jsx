function DriverStatusCard({
  state
}) {
  const normalizedState =
    state || "UNKNOWN";

  return (
    <section className="driver-status-card">
      <div className="card-header">
        <h2>Driver State</h2>

        <span
          className={`driver-state driver-state--${normalizedState.toLowerCase()}`}
        >
          {normalizedState}
        </span>
      </div>

      <p className="driver-status-description">
        Current driver monitoring state
      </p>
    </section>
  );
}

export default DriverStatusCard;