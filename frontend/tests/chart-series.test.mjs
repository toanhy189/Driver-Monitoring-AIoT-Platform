import assert from 'node:assert/strict';
import test from 'node:test';
import { metricPath, metricBandPath, appendTimeline } from '../src/services/chartSeries.js';

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

test('a bucket containing missing observations is not joined to neighbouring buckets', () => {
  const rows = [row(0,.5), {...row(1,.5), gap:true}, row(2,.5)];
  assert.equal(metricPath(rows, x=>x.value, {...options,gapOf:x=>x.gap}),
    'M 0.0 50.0 M 50.0 50.0 M 100.0 50.0');
});

test('time buckets retain min/max envelope and missing measurements split it', () => {
  const rows = [0, 1, 2, 3, 4].map(seconds => ({ ...row(seconds, .5), ear_min: seconds === 2 ? null : .1, ear_max: seconds === 2 ? null : .8 }));
  const path = metricBandPath(rows, 'ear', options);
  assert.equal((path.match(/ Z/g) || []).length, 2);
  assert.match(path, /80\.0|20\.0/);
});

test('timeline merges equal states, retains changes and breaks at an observation gap', () => {
  const items = [
    { ...row(0,.3), driver_state:'ATTENTIVE' }, { ...row(1,.3), driver_state:'ATTENTIVE' },
    { ...row(2,.1), driver_state:'DROWSY' }, { ...row(20,.1), driver_state:'DROWSY' },
    { ...row(21,null,false), driver_state:'ATTENTIVE' },
  ];
  const segments = items.reduce(appendTimeline, []);
  assert.equal(segments.length, 4);
  assert.equal(segments[0].samples, 2);
  assert.equal(segments.at(-1).driver_state, 'UNKNOWN');
  assert.deepEqual(appendTimeline(segments, items[0]), segments);
});
