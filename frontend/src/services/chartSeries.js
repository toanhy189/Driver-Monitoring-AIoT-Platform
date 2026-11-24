// Missing measurements break the curve; they are never drawn as measured zero.
export function metricPath(items, valueOf, { maxValue, width, height, padding, maxGapMs = 5000, gapOf = () => false }) {
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
    const command = previous === null || time - previous > maxGapMs || gapOf(item) ? "M" : "L";
    previous = gapOf(item) ? null : time;
    const x = padding.left + (time - start) / duration * innerW;
    const y = padding.top + innerH * (1 - Math.min(value, maxValue) / maxValue);
    return `${command} ${x.toFixed(1)} ${y.toFixed(1)}`;
  }).filter(Boolean).join(" ");
}

// Shaded min/max envelope for server time buckets; missing buckets break the band.
export function metricBandPath(items, key, options) {
  const bandOptions = { ...options, gapOf: row => row[key + "_has_gap"] === true };
  const upper = metricPath(items, row => row[key + "_max"], bandOptions);
  const lower = metricPath(items, row => row[key + "_min"], bandOptions);
  const upperSegments = upper.split("M ").filter(Boolean);
  const lowerSegments = lower.split("M ").filter(Boolean);
  return upperSegments.map((segment, index) => {
    const bottom = lowerSegments[index];
    if (!bottom) return "";
    return `M ${segment} L ${bottom.split(" L ").reverse().join(" L ")} Z`;
  }).join(" ");
}

export function appendTimeline(segments, item) {
  const timestamp = item.recorded_at;
  const state = item.face_detected === false ? "UNKNOWN" : item.driver_state || "UNKNOWN";
  const last = segments.at(-1);
  if (last && Date.parse(timestamp) <= Date.parse(last.end)) return segments;
  if (last && last.driver_state === state && Date.parse(timestamp) - Date.parse(last.end) <= 5000) {
    return [...segments.slice(0, -1), { ...last, end: timestamp, samples: last.samples + 1 }];
  }
  return [...segments, { driver_state: state, start: timestamp, end: timestamp, samples: 1 }].slice(-60);
}
