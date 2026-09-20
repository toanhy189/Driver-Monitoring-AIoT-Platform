/* ../component/ = một mảnh giao diện có thể tái sử dụng.
Sau này có thể dùng:
    <MetricCard title="EAR" value={ear} />
    <MetricCard title="PERCLOS" value={perclos} unit="%" />
    <MetricCard title="FPS" value={fps} />
*/

function MetricCard({
    title,
    value,
    unit = "",
    description = ""
}) {
    return(
        <div className="metric-card">
        <div className="metric-card__title">
            {title}
        </div>

        <div className="metric-card__value">
            {value}
            {unit && (
            <span className="metric-card__unit">
                {unit}
            </span>
            )}
        </div>

        {description && (
            <div className="metric-card__description">
            {description}
            </div>
        )}
        </div>
    );
}

export default MetricCard;