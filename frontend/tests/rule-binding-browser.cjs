/* Optional: build frontend, set PLAYWRIGHT_MODULE to an external installation,
   then node frontend/tests/rule-binding-browser.cjs. All APIs are intercepted;
   this test cannot reach the production Backend, MQTT or hardware. */
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const root = path.resolve(__dirname, '../dist');
  const server = http.createServer((req, res) => {
    const filename = path.resolve(root, '.' + new URL(req.url, 'http://localhost').pathname);
    if (filename !== root && !filename.startsWith(root + path.sep)) { res.writeHead(403).end(); return; }
    const file = filename === root ? path.join(root, 'index.html') : filename;
    if (!fs.existsSync(file)) { res.writeHead(404).end(); return; }
    res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html');
    fs.createReadStream(file).pipe(res);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  let browser;
  try {
    browser = await chromium.launch({ channel: 'msedge', headless: true });
    const page = await browser.newPage();
    const errors = [];
    const writes = [];
    page.on('pageerror', error => errors.push(error.message));
    const camera = { id: 5, device_code: 'vision-01', name: 'Camera thử', model: 'camera', type: 'VISION_NODE', lifecycle_state: 'ACTIVE', status: 'ONLINE' };
    const targets = [1, 2].map(id => ({ id, device_code: `alert-0${id}`, name: `ESP32 ${id}`, model: 'esp32',
      device_type: 'ALERT_NODE', lifecycle_state: 'ACTIVE', status: 'ONLINE', active_source_id: null }));
    let state = { source_device_id: 5, target_device_id: null, enabled: false, effective_enabled: false,
      engine_enabled: true, updated_at: null, targets, readiness: { ready: false, blockers: ['UNBOUND', 'WAITING_FOR_AI'], target: null, inflight: false } };
    let revision = 0;
    let ruleReads = 0;
    let hardwareWrites = 0;
    await page.route('**/api/**', async route => {
      const request = route.request();
      const pathname = new URL(request.url()).pathname;
      const reply = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
      if (pathname === '/api/me') return reply({ id: 1, username: 'qa-admin', role: 'Admin', status: 'ACTIVE' });
      if (pathname === '/api/devices/5/hardware' && request.method() === 'PATCH') {
        camera.hardware_version = request.postDataJSON().hardware_version;
        hardwareWrites++;
        return reply(camera);
      }
      if (pathname.endsWith('/rule')) {
        if (request.method() === 'GET') { ruleReads++; return reply(state); }
        const body = request.postDataJSON();
        writes.push(body);
        if (body.expected_updated_at !== state.updated_at) return reply({ detail: 'Liên kết đã được người khác thay đổi. Hãy tải lại trước khi lưu.' }, 409);
        state = { ...state, target_device_id: body.target_device_id, enabled: body.enabled,
          effective_enabled: body.enabled, updated_at: `revision-${++revision}`,
          readiness: { ready: false, blockers: body.enabled ? ['WAITING_FOR_AI'] : ['DISABLED', 'WAITING_FOR_AI'],
            target: targets.find(item => item.id === body.target_device_id), inflight: false } };
        return reply(state);
      }
      const match = /^\/api\/devices\/(\d+)$/.exec(pathname);
      if (match) return reply(Number(match[1]) === 5 ? camera : { ...targets.find(item => item.id === Number(match[1])), type: 'ALERT_NODE' });
      // Do not allow commands even against the mocked endpoints.
      if (request.method() !== 'GET') return reply({ detail: 'No command execution in this test' }, 503);
      return reply([]);
    });
    await page.addInitScript(() => localStorage.setItem('access_token', 'disposable-test-token'));
    const base = `http://127.0.0.1:${server.address().port}`;
    await page.goto(base + '/#/devices/5');
    const panel = page.getByRole('region', { name: 'Cảnh báo tự động', exact: true });
    await panel.getByLabel('Thiết bị nhận cảnh báo').waitFor();
    // Saving hardware reloads detail and toggles the loading notice. The rule
    // editor and hardware form must keep separate React identities throughout.
    await page.getByLabel('Phiên bản phần cứng', { exact: true }).fill('camera-qa');
    await page.getByRole('button', { name: 'Lưu phần cứng', exact: true }).click();
    await page.waitForResponse(response => response.url().endsWith('/api/devices/5') && response.request().method() === 'GET');
    await page.getByText('Đang tải chi tiết thiết bị…', { exact: true }).waitFor({ state: 'hidden' });
    assert.equal(hardwareWrites, 1);
    assert.equal(await panel.count(), 1, 'Only one automatic warning editor after detail reload');
    assert.equal(await page.locator('#rule-target').count(), 1);
    assert.equal(writes.length, 0);
    assert.equal(await panel.getByLabel('Bật cảnh báo tự động').isDisabled(), true);
    await panel.getByLabel('Thiết bị nhận cảnh báo').selectOption('1');
    await panel.getByRole('button', { name: 'Lưu thiết lập', exact: true }).click();
    await panel.getByText('Thiết lập đã lưu: Tắt tự động', { exact: true }).waitFor();
    await panel.getByLabel('Bật cảnh báo tự động').check();
    await panel.getByRole('button', { name: 'Lưu thiết lập', exact: true }).click();
    await panel.getByText('Thiết lập đã lưu: Bật tự động', { exact: true }).waitFor();
    assert.deepEqual(writes.map(item => item.enabled), [false, true]);

    // Polling must refresh status without replacing the user's draft or CAS token.
    await panel.getByLabel('Thiết bị nhận cảnh báo').selectOption('2');
    const oldRevision = state.updated_at;
    state = { ...state, updated_at: `revision-${++revision}` };
    const reads = ruleReads;
    await page.waitForResponse(response => response.url().endsWith('/rule') && response.request().method() === 'GET');
    assert.ok(ruleReads > reads);
    assert.equal(await panel.getByLabel('Thiết bị nhận cảnh báo').inputValue(), '2');
    await panel.getByRole('button', { name: 'Lưu thiết lập', exact: true }).click();
    await panel.getByRole('alert').filter({ hasText: 'Liên kết đã được người khác thay đổi' }).waitFor();
    assert.equal(writes.at(-1).expected_updated_at, oldRevision);
    assert.equal(await panel.getByRole('button', { name: 'Lưu thiết lập', exact: true }).isDisabled(), true);
    page.once('dialog', dialog => dialog.accept());
    await panel.getByRole('button', { name: 'Tải lại thiết lập', exact: true }).click();
    await panel.getByRole('button', { name: 'Lưu thiết lập', exact: true }).waitFor({ state: 'visible' });
    await page.waitForFunction(() => document.querySelector('#rule-target')?.value === '1');
    await panel.getByLabel('Thiết bị nhận cảnh báo').selectOption('2');
    await panel.getByRole('button', { name: 'Lưu thiết lập', exact: true }).click();
    await panel.getByText('Thiết lập đã lưu: Tắt tự động', { exact: true }).waitFor();
    assert.equal(writes.at(-1).enabled, false);
    await panel.getByRole('button', { name: 'Mở alert-02 để kiểm tra / xem lệnh', exact: true }).click();
    await page.waitForURL('**/#/devices/2');
    await page.getByRole('button', { name: 'Kiểm tra cảnh báo', exact: true }).waitFor();
    assert.equal(await page.getByRole('heading', { name: 'Cảnh báo tự động', exact: true }).count(), 0);
    assert.deepEqual(errors, []);
    console.log('PASS: browser create -> enable -> poll preserves draft -> stale save 409 -> reload -> retarget disarmed -> correct ESP32; no commands.');
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
