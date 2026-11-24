/* Build first; PLAYWRIGHT_MODULE may point to an external Playwright install.
   All API/WebSocket traffic is mocked. No production writes or physical outputs. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const root = path.resolve(__dirname, '../dist');
  const evidence = path.resolve(process.env.UI_EVIDENCE_DIR || '.local-backups/frontend-polish-20261110/browser');
  fs.mkdirSync(evidence, { recursive: true });
  const server = http.createServer((req, res) => {
    const candidate = path.resolve(root, '.' + new URL(req.url, 'http://localhost').pathname);
    if (candidate !== root && !candidate.startsWith(root + path.sep)) return res.writeHead(403).end();
    const file = candidate === root ? path.join(root, 'index.html') : candidate;
    if (!fs.existsSync(file)) return res.writeHead(404).end();
    res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html');
    fs.createReadStream(file).pipe(res);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  let browser;
  const results = [];
  try {
    browser = await chromium.launch({ channel: 'msedge', headless: true });
    for (const role of ['Admin', 'Employee', 'Customer']) for (const width of [1440, 390, 320]) {
      const context = await browser.newContext({ viewport: { width, height: 1000 } });
      const page = await context.newPage();
      page.setDefaultTimeout(8000);
      const errors = [], writes = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.routeWebSocket('**/ws/telemetry*', () => {});
      const now = new Date().toISOString();
      let user = { id: 9, username: 'qa-user', fullname: `Tài khoản ${role}`, role, status: 'ACTIVE', email: 'qa@example.test', phone: '0900000000' };
      const users = [user, { id: 10, username: 'qa-assigned', fullname: 'Người dùng được gán', role: 'Customer', status: 'ACTIVE', email: 'assigned@example.test', phone: '0900000001' }];
      const devices = [
        { id: 5, device_code: 'vision-01', name: 'Camera giám sát tài xế', model: 'AI Vision Node', type: 'VISION_NODE', status: 'ONLINE', lifecycle_state: 'ACTIVE', last_seen: now, hardware_version: 'webcam-v1' },
        { id: 1, device_code: 'alert-01', name: 'Thiết bị cảnh báo ESP32', model: 'ESP32 Alert Node', type: 'ALERT_NODE', status: 'ONLINE', lifecycle_state: 'ACTIVE', last_seen: now, firmware_version: '0.3.0', hardware_version: 'esp32doit-devkit-v1' },
      ];
      const signals = { schema_version: 'eye-mouth-v2', experimental: true, mar: .42, yawn_probability: .1,
        mouth_state: 'NORMAL', eye_state: 'SLEEPY', eyes_available: true, mouth_available: true,
        eye_sleepy_probability: .75, eye_confidence: .75, mouth_confidence: .9, ear_available: true,
        eye_quality: 'VALID', mouth_quality: 'VALID', quality_version: 'region-technical-quality-v1',
        decision_reason: 'HEAD_DOWN_RISK', eye_closure_state: 'OPEN', sample_age_ms: 10,
        head_motion: { version: 'head-motion-v1', mode: 'OBSERVE_ONLY', available: true, calibrated: true,
          state: 'LOWERED', pitch_deg: 15, yaw_deg: 0, roll_deg: 0, nod_count: 0, repeated_nods: false, eye_closure_supported: false },
        head_down_policy: { version: 'sustained-head-down-v1', state: 'DOWN_RISK', risk_candidate: true,
          observed_down_seconds: 3.5, enter_pitch_deg: 12, min_seconds: 3 } };
      const telemetry = { id: 1, device_id: 5, device_code: 'vision-01', recorded_at: now, received_at: now,
        ear: .22, perclos: .12, confidence: .75, face_detected: true, driver_state: 'DROWSY',
        head_pose: { yaw: .01, pitch: .15, roll: 1.3 }, model_version: 'eye-mouth-v2-posture-long-version-for-overflow-test', ai_signals: signals };
      const timings = Object.fromEntries(['led', 'buzzer', 'motor'].map(output => [output,
        Object.fromEntries([1, 2, 3].map(level => [level, { on_ms: 600, off_ms: 300 }]))]));
      await page.route('**/api/**', async route => {
        const request = route.request(), method = request.method(), pathname = new URL(request.url()).pathname;
        const reply = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
        if (pathname === '/api/me' && method === 'GET') return reply(user);
        if (pathname === '/api/ws-ticket') return reply({ ticket: 'mocked-layout-ticket' });
        if (method !== 'GET') {
          writes.push({ method, pathname, body: request.postDataJSON() });
          if (pathname === '/api/me' && method === 'PUT') { user = { ...user, ...request.postDataJSON() }; return reply(user); }
          if (pathname === '/api/users' && method === 'POST' && role === 'Admin') { const created = { id: 11, ...request.postDataJSON() }; users.push(created); return reply(created, 201); }
          return reply({ detail: 'Unexpected mutation in layout test' }, 403);
        }
        if (pathname === '/api/users') return reply(users);
        if (/^\/api\/users\/\d+\/devices$/.test(pathname)) return reply([devices[0]]);
        if (pathname === '/api/videos/storage') return reply({ used_bytes: 30 * 1048576, max_bytes: 4096 * 1048576, warning: false });
        if (pathname === '/api/devices') return reply(devices);
        if (pathname === '/api/commands') return reply([
          {request_id:'cancelled-176',device_id:1,device_code:'alert-01',action:'AUTO_ALERT',source:'AI',created_at:now,
            status:'FAILED',ack_status:'FAILED',cancellation_status:'CANCELLED',error_message:'Risk episode no longer actionable'},
          {request_id:'partial-177',device_id:1,device_code:'alert-01',action:'AUTO_ALERT',source:'AI',created_at:now,
            status:'FAILED',ack_status:'FAILED',cancellation_status:'PARTIALLY_CANCELLED',error_message:'Risk episode no longer actionable'},
          {request_id:'failed-178',device_id:1,device_code:'alert-01',action:'AUTO_ALERT',source:'AI',created_at:now,
            status:'FAILED',ack_status:'FAILED',cancellation_status:null,error_message:'COMMAND_EXPIRED'},
        ]);
        const detail = /^\/api\/devices\/(\d+)$/.exec(pathname);
        if (detail) return reply(devices.find(d => d.id === Number(detail[1])));
        if (pathname === '/api/5/telemetry') return reply(telemetry);
        if (pathname === '/api/5/telemetry/history') return reply({ items: [telemetry], total_samples: 1, model_version: telemetry.model_version, last_updated: now });
        if (pathname === '/api/devices/5/rule') return reply({ source_device_id: 5, target_device_id: 1,
          enabled: true, effective_enabled: false, engine_enabled: true, updated_at: now,
          targets: [{ ...devices[1], device_type: 'ALERT_NODE', active_source_id: null }],
          readiness: { ready: false, blockers: ['WAITING_FOR_AI'], target: devices[1], inflight: false } });
        if (pathname === '/api/devices/1/config') return reply({ config_id: 'qa-config', applied_config_id: 'qa-config', status: 'APPLIED', desired: { timings }, applied: { timings } });
        if (pathname.endsWith('/metrics')) return reply({ telemetry: { count: 1, avg_ear: .22, avg_perclos: .12 }, alerts: { count: 1 }, commands: { count: 0 }, latency: {} });
        if (/\/(history|timeline)$/.test(pathname)) return reply({ items: [], has_more: false });
        return reply([]);
      });
      await page.addInitScript(() => localStorage.setItem('access_token', 'disposable-layout-token'));
      async function check(name) {
        const dimensions = await page.evaluate(() => ({ page: document.documentElement.scrollWidth, viewport: innerWidth }));
        await page.screenshot({ path: path.join(evidence, `${role}-${width}-${name}.png`), fullPage: true });
        if (dimensions.page > dimensions.viewport + 1) {
          const overflow = await page.evaluate(() => [...document.querySelectorAll('main, main *')].map(el => {
            const box=el.getBoundingClientRect(), style=getComputedStyle(el);
            return {tag:el.tagName,class:el.className,width:box.width,right:box.right,display:style.display,minWidth:style.minWidth,overflow:style.overflowX};
          }).filter(el=>el.right>innerWidth+1).slice(0,24));
          console.error(JSON.stringify(overflow));
        }
        assert.ok(dimensions.page <= dimensions.viewport + 1, `${role}/${width}/${name}: page overflows ${JSON.stringify(dimensions)}`);
        assert.deepEqual(errors, [], `${role}/${width}/${name}: JS errors`);
      }
      await page.goto(base + '/#/dashboard');
      await page.getByRole('button', { name: 'Mở tài khoản', exact: true }).click();
      const account = page.getByRole('dialog', { name: 'Tài khoản của tôi', exact: true });
      await account.getByLabel('Họ tên', { exact: true }).fill(`Cập nhật ${role}`);
      const profile = page.waitForResponse(response => response.url().endsWith('/api/me') && response.request().method() === 'PUT');
      await account.getByRole('button', { name: 'Lưu thông tin', exact: true }).click();
      assert.equal((await profile).status(), 200);
      await account.getByText('Đã lưu thông tin tài khoản.', { exact: true }).waitFor();
      await check('account');
      await account.screenshot({ path: path.join(evidence, `${role}-${width}-account-dialog.png`) });
      await account.getByRole('button', { name: 'Đóng', exact: true }).focus();
      await page.keyboard.press('Shift+Tab');
      assert.ok(await account.evaluate(el => el.contains(document.activeElement)), 'Keyboard focus stays in the modal');
      assert.equal(await page.evaluate(() => document.body.style.overflow), 'hidden');
      await page.keyboard.press('Escape');
      await account.waitFor({ state: 'hidden' });
      assert.equal(await page.getByRole('button', { name: 'Mở tài khoản', exact: true }).evaluate(el => el === document.activeElement), true);
      if (role === 'Admin') {
        await page.getByRole('tab', { name: 'Người dùng', exact: true }).click();
        await page.locator('.admin-create-user > summary').click();
        const create = page.locator('.admin-user-form');
        await create.getByRole('combobox').waitFor();
        assert.deepEqual(await create.getByRole('combobox').locator('option').evaluateAll(options => options.map(option => option.value)), ['Employee', 'Customer']);
        assert.equal(await page.getByLabel('Vai trò qa-user', { exact: true }).count(), 0);
        for (const [label, value] of [['Họ tên', 'Người dùng thử'], ['Tên đăng nhập', 'qa-created'], ['Email', 'new@example.test'], ['Điện thoại', '0900000002'], ['Mật khẩu', 'layout-demo-pass'], ['Nhập lại mật khẩu', 'layout-demo-pass']]) {
          await create.getByLabel(label, { exact: true }).fill(value);
        }
        await check('admin-create');
        const created = page.waitForResponse(response => response.url().endsWith('/api/users') && response.request().method() === 'POST');
        await create.getByRole('button', { name: 'Tạo tài khoản', exact: true }).click();
        assert.equal((await created).status(), 201);
        await page.getByRole('row').filter({ hasText: 'qa-assigned' }).getByRole('button', { name: 'Thiết bị được gán', exact: true }).click();
        await page.locator('.admin-user-devices .device-table tbody tr').waitFor();
        assert.equal(await page.locator('.admin-user-devices th').count(), 6);
        assert.equal(await page.locator('.admin-user-devices td').count(), 6);
        assert.equal(await page.locator('.admin-user-devices td').last().getByRole('button', { name: 'Thu hồi', exact: true }).count(), 1);
        await check('admin-users');
      }
      await page.goto(base + (role === 'Admin' ? '/#/monitoring' : '/#/dashboard'));
      await page.getByRole('region', { name: 'Tín hiệu mắt và miệng', exact: true }).waitFor();
      const posture = page.getByRole('region', { name: 'Cảnh báo cúi đầu kéo dài', exact: true });
      await posture.getByText('3.5 / 3 giây', { exact: true }).waitFor();
      assert.equal(await page.locator('.signals-technical[open]').count(), 0);
      assert.equal(await page.getByText('Chi tiết AI', { exact: true }).count(), 1);
      assert.equal(await page.getByText('MAR — độ mở miệng', { exact: true }).isVisible(), false);
      await page.getByText('Cúi đầu kéo dài theo quy tắc cảnh báo', { exact: true }).waitFor();
      assert.equal(await page.getByText('(TV4-17)', { exact: false }).count(), 0);
      await check('dashboard');
      await page.goto(base + '/#/devices/5');
      await page.getByRole('heading', { name: 'Thông tin thiết bị', exact: true }).waitFor();
      assert.equal(await page.getByRole('heading', { name: 'Quản lý thiết bị', exact: true }).count(), role === 'Admin' ? 1 : 0);
      assert.equal(await page.getByText('Thông tin kỹ thuật', { exact: true }).count(), role === 'Admin' ? 1 : 0);
      const rule = page.getByRole('region', { name: 'Cảnh báo tự động', exact: true });
      assert.equal(await rule.count(), role === 'Admin' ? 1 : 0);
      if (role === 'Admin') {
        await rule.getByText('Đang chờ quan sát AI mới hợp lệ từ camera.', { exact: true }).waitFor();
        const target = rule.getByLabel('Thiết bị nhận cảnh báo', { exact: true });
        assert.equal(await target.isDisabled(), false);
        assert.equal(await target.evaluate(el => getComputedStyle(el).backgroundColor), 'rgb(255, 255, 255)');
      }
      await page.getByRole('button', { name: 'Lịch sử và thống kê thiết bị', exact: true }).click();
      await page.getByRole('button', { name: 'Thống kê', exact: true }).click();
      await page.getByText('Số bản ghi đo', { exact: true }).waitFor();
      await check('vision-detail');
      await page.goto(base + '/#/devices/1');
      await page.getByRole('heading', { name: 'Thông tin thiết bị', exact: true }).waitFor();
      if (role !== 'Customer') await page.getByRole('button', { name: 'Kiểm tra cảnh báo', exact: true }).waitFor();
      assert.equal(await page.getByRole('button', { name: 'Kiểm tra cảnh báo', exact: true }).count(), role === 'Customer' ? 0 : 1);
      await page.getByRole('button', { name: 'Cấu hình cảnh báo', exact: true }).click();
      const firstTiming = page.getByLabel('Đèn LED mức 1, thời gian bật (ms)', { exact: true });
      await firstTiming.waitFor();
      await page.waitForFunction(() => document.querySelector('.config-fields input')?.value === '600');
      assert.equal(await firstTiming.evaluate(el => el.readOnly), role === 'Customer');
      assert.equal(await page.getByRole('button', { name: 'Lưu cấu hình', exact: true }).count(), role === 'Customer' ? 0 : 1);
      await check('remote-config');
      await page.goto(base + '/#/commands');
      const cancelledRow = page.getByRole('row').filter({hasText:'Đã hủy trước khi gửi'});
      await cancelledRow.getByText('Chưa gửi tới thiết bị', {exact:true}).waitFor();
      assert.equal(await cancelledRow.getByText('Thiết bị báo lỗi', {exact:true}).count(), 0);
      await page.getByText('Đã hủy phần chưa gửi', {exact:true}).waitFor();
      const failedRow = page.getByRole('row').filter({hasText:'COMMAND_EXPIRED'});
      await failedRow.getByText('Lệnh thất bại', {exact:true}).waitFor();
      await failedRow.getByText('Thiết bị báo lỗi', {exact:true}).waitFor();
      await check('command-cancellations');
      assert.ok(writes.every(w => w.pathname === '/api/me' || role === 'Admin' && w.pathname === '/api/users'), 'No command/config/hardware mutation');
      results.push({ role, width, pass: true, mocked_writes: writes.map(w => ({ method: w.method, path: w.pathname })) });
      await context.close();
    }
    fs.writeFileSync(path.join(evidence, 'results.json'), JSON.stringify({ pass: true, physical_outputs_used: false, results }, null, 2));
    console.log('PASS: Admin/Employee/Customer at 1440/390/320px; account save, Admin creation/assignment table, AI posture, rule blockers, history, readonly config; no page overflow or real API writes.');
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
