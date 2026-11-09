import assert from 'node:assert/strict';
import test from 'node:test';
import { metricPath } from '../src/services/chartSeries.js';

const options = { maxValue: 1, width: 100, height: 100, padding: { top: 0, bottom: 0, left: 0, right: 0 } };
const row = (seconds, value, face_detected = true) => ({ recorded_at: new Date(seconds * 1000).toISOString(), value, face_detected });
test('missing eyes or face break a curve while measured zero remains visible', () => {
  assert.equal(metricPath([row(0, .5), row(1, null), row(2, 0), row(3, .5, false), row(4, .2)], x => x.value, options),
    'M 0.0 50.0 M 50.0 100.0 M 100.0 80.0');
});
test('time spacing remains proportional and a telemetry outage is not interpolated', () => {
  assert.equal(metricPath([row(0, .5), row(1, .5), row(10, .5)], x => x.value, options),
    'M 0.0 50.0 L 10.0 50.0 M 100.0 50.0');
});
