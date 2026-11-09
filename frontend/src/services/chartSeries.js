// Missing measurements break the curve; they are never drawn as measured zero.
export function metricPath(items, valueOf, { maxValue, width, height, padding, maxGapMs = 5000 }) {
  const rows = items.filter(item => Number.isFinite(Date.parse(item.recorded_at)));
  if (rows.length < 2) return "";
  const start = Date.parse(rows[0].recorded_at);
  const duration = Date.parse(rows.at(-1).recorded_at) - start;
  if (duration <= 0) return "";
  const innerW = width - padding.left - padding.right;
  const innerH = height - padding.top - padding.bottom;
  let previous = null;
  return rows.map(item => {
    const time = Date.parse(item.recorded_at);
    const value = valueOf(item);
    if (item.face_detected === false || !Number.isFinite(value) || value < 0) {
      previous = null;
      return "";
    }
    const command = previous === null || time - previous > maxGapMs ? "M" : "L";
    previous = time;
    const x = padding.left + (time - start) / duration * innerW;
    const y = padding.top + innerH * (1 - Math.min(value, maxValue) / maxValue);
    return `${command} ${x.toFixed(1)} ${y.toFixed(1)}`;
  }).filter(Boolean).join(" ");
}
