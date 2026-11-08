/* Optional real-browser smoke. Only use a temporary Customer named final-qa-*.
   Install Playwright outside this repo; pass PLAYWRIGHT_MODULE and QA_FIXTURE.
   The fixture contains a local password and must remain ignored. */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const fixture = JSON.parse(fs.readFileSync(process.env.QA_FIXTURE, 'utf8'));
  assert.match(fixture.username, /^final-qa-[a-f0-9]+$/);
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const steps = [];
  const newPassword = fixture.password + '-changed';
  try {
    await page.goto('http://127.0.0.1:5173');
    async function login(password) {
      await page.locator('#username').fill(fixture.username);
      await page.locator('#password').fill(password);
      const received = page.waitForResponse(response => response.url().endsWith('/api/login') && response.request().method() === 'POST');
      await page.locator('button[type=submit]').click();
      assert.equal((await received).status(), 200);
      await page.getByRole('button', { name: 'Mở tài khoản', exact: true }).waitFor();
    }
    await login(fixture.password); steps.push('Customer login against deployed API');
    await page.getByRole('button', { name: 'Mở tài khoản', exact: true }).click();
    const dialog = page.getByRole('dialog');
    await dialog.getByLabel('Họ tên', { exact: true }).fill('Temporary QA Updated');
    const profile = page.waitForResponse(response => response.url().endsWith('/api/me') && response.request().method() === 'PUT');
    await dialog.getByRole('button', { name: 'Lưu thông tin', exact: true }).click();
    assert.equal((await profile).status(), 200); steps.push('Profile form saved through React');
    await page.waitForFunction(() => document.querySelector('.topbar-user')?.textContent.includes('Temporary QA Updated'));
    await dialog.getByRole('button', { name: 'Đóng', exact: true }).click();
    await page.getByRole('button', { name: 'Mở tài khoản', exact: true }).click();
    assert.equal(await page.getByRole('dialog').getByLabel('Họ tên', { exact: true }).inputValue(), 'Temporary QA Updated');
    steps.push('Saved profile appears in header and when reopening form');
    await dialog.getByLabel('Mật khẩu hiện tại', { exact: true }).fill(fixture.password);
    await dialog.getByLabel('Mật khẩu mới (ít nhất 8 ký tự)', { exact: true }).fill(newPassword);
    const changed = page.waitForResponse(response => response.url().endsWith('/api/me/password'));
    await dialog.getByRole('button', { name: 'Đổi mật khẩu', exact: true }).click();
    assert.equal((await changed).status(), 204);
    await page.locator('#username').waitFor(); steps.push('Password change returns to login');
    await login(newPassword); steps.push('Changed password login');
    const logout = page.waitForResponse(response => response.url().endsWith('/api/logout'));
    await page.getByRole('button', { name: 'Đăng xuất', exact: true }).click();
    assert.equal((await logout).status(), 204);
    await page.locator('#username').waitFor(); steps.push('Server logout and local session cleared');
    assert.deepEqual(errors, []);
    const result = { timestamp: new Date().toISOString(), scope: 'Installed Edge headless + deployed React/FastAPI; temporary Customer; no camera or physical outputs', steps, page_errors: errors, pass: true };
    const output = process.env.QA_OUTPUT;
    if (output) { fs.mkdirSync(path.dirname(output), { recursive: true }); fs.writeFileSync(output, JSON.stringify(result, null, 2)); }
    console.log(JSON.stringify(result, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
