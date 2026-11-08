/* Run only through backend/tests/run_alert_video_browser.py.
   All accounts, video and DB are disposable; no MQTT or physical outputs. */
const fs = require('node:fs');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE);

(async () => {
  const fixture = JSON.parse(fs.readFileSync(process.env.QA_FIXTURE, 'utf8'));
  assert.match(fixture.base_url, /^http:\/\/127\.0\.0\.1:\d+$/);
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const steps = [];
  const errors = [];
  async function session(role, hash) {
    const context = await browser.newContext({ acceptDownloads: true });
    await context.addInitScript(token => localStorage.setItem('access_token', token), fixture.tokens[role]);
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(fixture.base_url + '/' + hash);
    await page.getByRole('button', { name: 'Mở tài khoản', exact: true }).waitFor();
    return { context, page };
  }
  try {
    const { context, page } = await session('Customer', '#/alerts');
    const row = page.locator('tbody tr').filter({ hasText: 'Mức 1' });
    await row.getByRole('button', { name: 'Xem video', exact: true }).click();
    const dialog = page.getByRole('dialog');
    const player = dialog.locator('video');
    await player.waitFor();
    await page.waitForFunction(() => document.querySelector('video')?.readyState >= 2);
    const metadata = await player.evaluate(video => ({ duration: video.duration, width: video.videoWidth, height: video.videoHeight }));
    assert.ok(metadata.duration > 0 && metadata.width > 0 && metadata.height > 0);
    await player.evaluate(video => video.play());
    await page.waitForFunction(() => document.querySelector('video')?.currentTime > .1);
    await player.evaluate(video => { video.pause(); video.currentTime = .6; });
    await page.waitForFunction(() => {
      const video = document.querySelector('video');
      return video && !video.seeking && video.currentTime >= .5;
    });
    steps.push('Customer opens alert clip, decodes H.264, plays and seeks in Edge');
    assert.equal(await dialog.getByRole('button', { name: 'Xóa video', exact: true }).count(), 0);
    assert.equal(await page.getByRole('button', { name: 'Đánh dấu đã xem', exact: true }).count(), 0);
    const downloadEvent = page.waitForEvent('download');
    await dialog.getByRole('button', { name: 'Tải video gốc', exact: true }).click();
    const download = await downloadEvent;
    const hash = crypto.createHash('sha256').update(fs.readFileSync(await download.path())).digest('hex');
    assert.equal(hash, fixture.original_sha256);
    steps.push('Original download is byte-identical; Customer has no delete/ack controls');
    await dialog.getByRole('button', { name: 'Đóng video', exact: true }).click();
    const forbidden = await page.evaluate(async ({ id, token }) => {
      const result = await fetch(`/api/videos/${id}/playback`, { method: 'POST', headers: { Authorization: `Bearer ${token}` } });
      return result.status;
    }, { id: fixture.unassigned_video_id, token: fixture.tokens.Customer });
    assert.equal(forbidden, 404);
    await page.locator('tbody tr').filter({ hasText: 'Mức 3' }).getByText('Chưa nhận clip', { exact: true }).waitFor();
    await page.locator('tbody tr').filter({ hasText: 'Mức 2' }).getByRole('button', { name: 'Xem video', exact: true }).click();
    await dialog.getByRole('alert').filter({ hasText: 'Bạn vẫn có thể tải video gốc' }).waitFor();
    assert.equal(await dialog.getByRole('button', { name: 'Tải video gốc', exact: true }).isEnabled(), true);
    steps.push('Unassigned camera is denied; pending clip and conversion failure are displayed');
    await context.close();

    const admin = await session('Admin', '#/dashboard');
    await admin.page.getByRole('button', { name: 'Giám sát AI', exact: true }).click();
    await admin.page.getByRole('heading', { name: 'Giám sát AI', exact: true }).waitFor();
    assert.match(admin.page.url(), /#\/monitoring$/);
    await admin.page.goBack();
    assert.match(admin.page.url(), /#\/dashboard$/);
    await admin.page.getByRole('button', { name: 'Giám sát AI', exact: true }).waitFor();
    await admin.page.goForward();
    await admin.page.getByRole('heading', { name: 'Giám sát AI', exact: true }).waitFor();
    await admin.page.getByRole('button', { name: 'Quản trị', exact: true }).click();
    assert.match(admin.page.url(), /#\/dashboard$/);
    await admin.page.getByRole('button', { name: 'Cảnh báo', exact: true }).click();
    await admin.page.locator('tbody tr').filter({ hasText: 'Mức 1' }).getByRole('button', { name: 'Xem video', exact: true }).click();
    await admin.page.getByRole('dialog').getByRole('button', { name: 'Xóa video', exact: true }).waitFor();
    steps.push('Admin switches management/AI, Back/Forward, alerts and retains delete permission');
    await admin.context.close();
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ pass: true, scope: 'React build + real FastAPI routes + isolated SQLite + synthetic MPEG4 converted to H264 + installed Edge', steps, page_errors: errors }, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
