/* Build first; set PLAYWRIGHT_MODULE if Playwright is installed outside this repo.
   All API/WebSocket traffic is intercepted: no real backend, MQTT or hardware. */
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const root = path.resolve(__dirname, '../dist');
  const server = http.createServer((req, res) => {
    const filename = path.resolve(root, '.' + new URL(req.url, 'http://localhost').pathname);
    if (filename !== root && !filename.startsWith(root + path.sep)) return res.writeHead(403).end();
    const file = filename === root ? path.join(root, 'index.html') : filename;
    if (!fs.existsSync(file)) return res.writeHead(404).end();
    res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html');
    fs.createReadStream(file).pipe(res);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  let browser;
  try {
    browser = await chromium.launch({ channel: 'msedge', headless: true });
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [], forbidden = [];
    page.on('pageerror', error => errors.push(error.message));
    let socket;
    await page.routeWebSocket('**/ws/telemetry*', route => { socket = route; });
    const now = Date.now();
    const camera = { id: 5, device_code: 'vision-01', name: 'Camera thử', type: 'VISION_NODE', model: 'camera', status: 'ONLINE', lifecycle_state: 'ACTIVE' };
    const signals = { schema_version: 'eye-mouth-v1', mar: .42, yawn_probability: .8, mouth_state: 'YAWN', eye_state: 'UNKNOWN', eyes_available: false, mouth_available: true, experimental: true };
    let telemetry = { id: 1, device_id: 5, device_code: 'vision-01', recorded_at: new Date(now).toISOString(), face_detected: true, driver_state: 'UNKNOWN', ear: null, perclos: null, model_version: 'eye-mouth-browser-test', ai_signals: signals };
    let emptyMetrics = false;
    await page.route('**/api/**', async route => {
      const request = route.request(), pathname = new URL(request.url()).pathname;
      const reply = body => route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
      if (pathname === '/api/me') return reply({ id: 9, username: 'qa-customer', role: 'Customer', status: 'ACTIVE' });
      if (pathname === '/api/ws-ticket') return reply({ ticket: 'disposable-mocked-ticket' });
      if (request.method() !== 'GET') { forbidden.push(pathname); return route.abort(); }
      if (pathname === '/api/devices') return reply([camera]);
      if (pathname === '/api/devices/5') return reply(camera);
      if (pathname === '/api/devices/5/timeline') return reply({items:[{kind:'event',event_id:'threshold-clip-test',
        occurred_at:new Date(now).toISOString(),data:{event_type:'DROWSY_THRESHOLD_REACHED',state:'DROWSY',
          clip_message_id:'linked-state-change'}}],has_more:false});
      if (['/api/devices/5/history','/api/devices/5/telemetry/history'].includes(pathname)) return reply({items:[],has_more:false});
      if (pathname === '/api/devices/5/metrics') {
        await new Promise(resolve=>setTimeout(resolve,150));
        if (emptyMetrics) return reply({});
        return reply({telemetry:{count:3,avg_ear:.3,avg_perclos:.1},alerts:{count:1},commands:{count:2},
          latency:{http_avg_ms:12,completed_avg_ms:100}});
      }
      if (pathname === '/api/5/telemetry') return reply(telemetry);
      if (pathname === '/api/5/telemetry/history') return reply({ items: [telemetry], total_samples: 1, model_version: telemetry.model_version, last_updated: telemetry.recorded_at });
      return reply([]);
    });
    await page.addInitScript(() => localStorage.setItem('access_token', 'disposable-test-token'));
    await page.goto(`http://127.0.0.1:${server.address().port}/#/dashboard`);
    const panel = page.getByRole('region', { name: 'Tín hiệu mắt và miệng', exact: true });
    await panel.getByText('0.420', { exact: true }).waitFor();
    assert.equal(await panel.getByText('Ngáp', { exact: true }).count(), 1);
    assert.equal(await panel.getByText('Chưa dùng được', { exact: true }).count(), 1);
    assert.ok(socket, 'WebSocket intercepted');
    telemetry = { ...telemetry, id: 2, driver_state: 'DROWSY', recorded_at: new Date(now + 1000).toISOString(), ai_signals: { ...signals, mar: .62 } };
    socket.send(JSON.stringify({ type: 'telemetry.updated', data: telemetry }));
    await panel.getByText('0.620', { exact: true }).waitFor();
    await page.getByText('MAR (Mở miệng, trục phải 0–2)', { exact: true }).waitFor();
    assert.equal(await page.getByRole('region', { name: 'AI Metrics và Timeline' }).locator('path[stroke="#9333ea"]').count(), 1);
    const v2 = { ...signals, schema_version: 'eye-mouth-v2', eyes_available: true, eye_sleepy_probability: .51,
      eye_confidence: .51, mouth_confidence: .8, ear_available: true, eye_quality: 'VALID', mouth_quality: 'VALID',
      quality_version: 'region-technical-quality-v1', decision_reason: 'RF_NEGATIVE', eye_closure_state: 'DISABLED', sample_age_ms: 30 };
    telemetry = { ...telemetry, id: 3, driver_state: 'ATTENTIVE', ear: .31, recorded_at: new Date(now + 2000).toISOString(), ai_signals: v2 };
    socket.send(JSON.stringify({ type: 'telemetry.updated', data: telemetry }));
    await panel.getByText('Model kết hợp chưa phát hiện nguy cơ', { exact: true }).waitFor();
    await panel.getByText('Có số đo riêng', { exact: true }).waitFor();
    await panel.getByText('51% · Chưa chắc chắn giữa hai lớp', { exact: true }).waitFor();
    assert.equal(await panel.getByText('Qua kiểm tra ảnh kỹ thuật', { exact: true }).count(), 2);
    await panel.getByText('Chưa bật profile hiệu chuẩn', { exact: true }).waitFor();
    socket.send(JSON.stringify({ type: 'telemetry.updated', data: { ...telemetry, id: 4,
      recorded_at: new Date(now + 2500).toISOString(), ai_signals: { ...v2, mouth_available: false,
        mouth_state: 'UNKNOWN', mouth_confidence: null, mar: null, yawn_probability: null,
        mouth_quality: 'NO_CROP', mouth_crop_reason: 'OUTSIDE_FRAME' } } }));
    await panel.getByText('Vùng miệng vượt khung camera. Hãy lùi lại hoặc chỉnh camera để thấy trọn miệng và cằm khi ngáp.', { exact: true }).waitFor();
    const motion = { version: 'head-motion-v1', mode: 'OBSERVE_ONLY', available: true, calibrated: true,
      state: 'REPEATED_NODS', pitch_deg: 2, yaw_deg: 0, roll_deg: 0, nod_count: 2,
      repeated_nods: true, eye_closure_supported: false };
    socket.send(JSON.stringify({ type: 'telemetry.updated', data: { ...telemetry, id: 5,
      recorded_at: new Date(now + 2800).toISOString(), ai_signals: { ...v2, head_motion: motion } } }));
    const headPanel = page.getByRole('region', { name: 'Theo dõi gật đầu', exact: true });
    await headPanel.getByText('Ghi nhận gật đầu lặp lại', { exact: true }).waitFor();
    await headPanel.getByText('2.0°', { exact: true }).waitFor();
    socket.send(JSON.stringify({ type: 'telemetry.updated', data: { ...telemetry, id: 6,
      recorded_at: new Date(now + 2850).toISOString(), ai_signals: { ...v2,
        head_motion: { ...motion, state: 'REACQUIRING', nod_count: 0, repeated_nods: false } } } }));
    await headPanel.getByText('Đang xác nhận nhìn thẳng sau gián đoạn', { exact: true }).waitFor();
    const fusion={version:'pose-calibrated-head-eye-v1',mode:'ENABLED',state:'CLOSED_RISK',
      ear_threshold:.28,risk_candidate:true,profile_sha256:'b'.repeat(64)};
    socket.send(JSON.stringify({type:'telemetry.updated',data:{...telemetry,id:7,
      recorded_at:new Date(now+2875).toISOString(),ai_signals:{...v2,calibration_id:'a'.repeat(64),
        head_motion:motion,head_eye_fusion:fusion,decision_reason:'HEAD_EYE_CLOSURE_RISK'}}}));
    const fusionPanel=page.getByRole('region',{name:'Kết hợp đầu và mắt',exact:true});
    await fusionPanel.getByText('Có nguy cơ từ đầu và mắt',{exact:true}).waitFor();
    await fusionPanel.getByText('0.280',{exact:true}).waitFor();
    socket.send(JSON.stringify({type:'telemetry.updated',data:{...telemetry,id:8,
      recorded_at:new Date(now+2880).toISOString(),driver_state:'DROWSY',ai_signals:{...v2,head_motion:{...motion,state:'LOWERED'},
        decision_reason:'HEAD_DOWN_RISK',head_down_policy:{version:'sustained-head-down-v1',state:'DOWN_RISK',
          risk_candidate:true,observed_down_seconds:3.5,enter_pitch_deg:12,min_seconds:3}}}}));
    await page.getByRole('region',{name:'Cảnh báo cúi đầu kéo dài',exact:true}).getByText('3.5 / 3 giây',{exact:true}).waitFor();
    await panel.getByText('Cúi đầu kéo dài theo quy tắc cảnh báo',{exact:true}).waitFor();
    socket.send(JSON.stringify({ type: 'telemetry.updated', data: { ...telemetry, id: 6,
      recorded_at: new Date(now + 2900).toISOString(), ai_signals: { ...v2,
        head_motion: { ...motion, state: 'UNAVAILABLE', available: false, pitch_deg: null, yaw_deg: null,
          roll_deg: null, nod_count: 0, repeated_nods: false } } } }));
    await headPanel.getByText('Chưa đo được chuyển động đầu', { exact: true }).waitFor();
    assert.equal(await headPanel.getByText('2.0°', { exact: true }).count(), 0);
    socket.send(JSON.stringify({ type: 'telemetry.updated', data: { ...telemetry, id: 7, face_detected: false, recorded_at: new Date(now + 3000).toISOString() } }));
    await panel.waitFor({ state: 'hidden' });
    await page.goto(`http://127.0.0.1:${server.address().port}/#/devices/5`);
    const history=page.getByRole('region',{name:'Lịch sử và thống kê',exact:true});
    await history.getByRole('button',{name:'Lịch sử và thống kê thiết bị',exact:true}).click();
    await history.getByRole('button',{name:'Lệnh',exact:true}).click();
    await history.getByText('Chưa có dữ liệu trong khoảng đã chọn.',{exact:true}).waitFor();
    await history.getByRole('button',{name:'Thống kê',exact:true}).click();
    await history.getByText('Số bản ghi đo',{exact:true}).waitFor();
    await history.getByRole('button',{name:'Diễn biến',exact:true}).click();
    await history.getByRole('button',{name:'Xem clip liên kết với sự kiện Buồn ngủ',exact:true}).waitFor();
    emptyMetrics = true;
    await history.getByRole('button',{name:'Thống kê',exact:true}).click();
    await history.getByText('Chưa có dữ liệu thống kê trong khoảng thời gian đã chọn.',{exact:true}).waitFor();
    await history.getByRole('button',{name:'Số đo',exact:true}).click();
    await history.getByText('Chưa có dữ liệu trong khoảng đã chọn.',{exact:true}).waitFor();
    await history.getByRole('button',{name:'Thống kê',exact:true}).click();
    await history.getByText('Số bản ghi đo',{exact:true}).waitFor();
    assert.deepEqual(errors, []);
    assert.deepEqual(forbidden, []);
    console.log('PASS: v1 snapshot -> realtime MAR/yawn -> v2 independent geometry/uncertainty/reasons -> face loss clears measurements; no commands.');
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
