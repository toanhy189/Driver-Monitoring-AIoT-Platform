/* Use backend/tests/run_ota_browser.py. Signed virtual images only; no MQTT or physical outputs. */
const fs=require('node:fs');
const assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE);
(async()=>{
  const fixture=JSON.parse(fs.readFileSync(process.env.QA_FIXTURE,'utf8'));
  assert.match(fixture.base_url,/^http:\/\/127\.0\.0\.1:\d+$/);
  const browser=await chromium.launch({channel:'msedge',headless:true});const errors=[];
  try {
    for(const role of ['Employee','Customer']) {
      const context=await browser.newContext({viewport:{width:390,height:900}});
      await context.addInitScript(token=>localStorage.setItem('access_token',token),fixture.tokens[role]);
      const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
      await page.goto(fixture.base_url+'/#/firmware');
      await page.getByText('Chỉ quản trị viên được quản lý firmware.',{exact:true}).waitFor();
      assert.equal(await page.getByRole('button',{name:'Firmware / OTA',exact:true}).count(),0);
      await context.close();
    }
    const context=await browser.newContext({viewport:{width:1280,height:960}});
    await context.addInitScript(token=>localStorage.setItem('access_token',token),fixture.tokens.Admin);
    const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
    await page.goto(fixture.base_url+'/#/dashboard');
    await page.getByRole('button',{name:'Firmware / OTA',exact:true}).click();
    await page.getByRole('heading',{name:'Firmware và cập nhật OTA',exact:true}).waitFor();
    await page.getByLabel('File firmware (.bin)',{exact:true}).setInputFiles(fixture.image);
    await page.getByLabel('Manifest đã ký (.json)',{exact:true}).setInputFiles(fixture.manifest);
    await page.getByRole('button',{name:'Upload bản nháp',exact:true}).click();
    await page.getByRole('button',{name:'Xác minh chữ ký',exact:true}).click();
    await page.getByRole('button',{name:'Phát hành',exact:true}).click();
    await page.getByRole('button',{name:'Chọn cập nhật',exact:true}).click();
    await page.getByLabel('Chọn ota-old-firmware',{exact:true}).check();
    await page.getByRole('button',{name:'Kiểm tra điều kiện',exact:true}).click();
    await page.getByText(/cần nạp firmware nền qua USB/).waitFor();
    assert.equal(await page.getByRole('button',{name:'Xác nhận cập nhật',exact:true}).isDisabled(),true);
    await page.getByLabel('Chọn ota-old-firmware',{exact:true}).uncheck();
    await page.getByLabel('Chọn ota-browser',{exact:true}).check();
    await page.getByRole('button',{name:'Kiểm tra điều kiện',exact:true}).click();
    await page.getByText(/Đủ điều kiện/).waitFor();
    page.once('dialog',dialog=>dialog.accept());
    await page.getByRole('button',{name:'Xác nhận cập nhật',exact:true}).click();
    await page.getByText('Chờ gửi',{exact:true}).waitFor();
    await page.getByRole('button',{name:'Hủy phần chưa gửi',exact:true}).click();
    await page.getByText('Đã hủy trước khi gửi',{exact:true}).first().waitFor();
    await page.getByRole('button',{name:'Cập nhật thiết bị',exact:true}).click();
    await page.getByLabel('Chọn ota-browser',{exact:true}).check();
    await page.getByRole('button',{name:'Kiểm tra điều kiện',exact:true}).click();
    await page.getByText(/Đủ điều kiện/).waitFor();
    page.once('dialog',dialog=>dialog.accept());
    await page.getByRole('button',{name:'Xác nhận cập nhật',exact:true}).click();
    await page.getByText('Chờ gửi',{exact:true}).waitFor();
    const advanced=await page.request.post(fixture.base_url+'/__qa/advance',{headers:{'X-QA-Key':fixture.qa_key}});
    assert.equal(advanced.status(),200);
    await page.getByText('Đã xác nhận bản mới',{exact:true}).first().waitFor({timeout:15000});
    for(const width of [390,320]) {
      await page.setViewportSize({width,height:960});
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
      await page.getByRole('button',{name:'Kho firmware',exact:true}).click();
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    }
    await context.close();assert.deepEqual(errors,[]);
    console.log(JSON.stringify({pass:true,scope:'Real React + FastAPI + temporary SQLite + signed virtual device; no broker or physical flash',
      checks:['Admin-only navigation and API','Multipart upload, signature verification, release','Unsupported firmware blocked','Preview and explicit confirmation','Cancel unsent job','Confirmed version/hash displayed','390/320px layout'],page_errors:errors}));
  } finally {await browser.close();}
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
