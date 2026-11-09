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
    await page.route('**/api/**', async route => {
      const request = route.request(), pathname = new URL(request.url()).pathname;
      const reply = body => route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
      if (pathname === '/api/me') return reply({ id: 9, username: 'qa-customer', role: 'Customer', status: 'ACTIVE' });
      if (pathname === '/api/ws-ticket') return reply({ ticket: 'disposable-mocked-ticket' });
      if (request.method() !== 'GET') { forbidden.push(pathname); return route.abort(); }
      if (pathname === '/api/devices') return reply([camera]);
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
    socket.send(JSON.stringify({ type: 'telemetry.updated', data: { ...telemetry, id: 3, face_detected: false, recorded_at: new Date(now + 2000).toISOString() } }));
    await panel.waitFor({ state: 'hidden' });
    assert.deepEqual(errors, []);
    assert.deepEqual(forbidden, []);
    console.log('PASS: Customer snapshot -> realtime MAR/yawn -> history curve -> face loss clears measurements; no commands.');
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
