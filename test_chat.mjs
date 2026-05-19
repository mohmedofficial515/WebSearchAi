import { chromium } from 'playwright';

const BASE = 'http://localhost:5173/chat/';

(async () => {
  const browser = await chromium.launch({ headless: false, slowMo: 200, channel: 'chrome' });
  const page    = await browser.newPage();
  page.setDefaultTimeout(180_000);

  console.log('Opening', BASE);
  await page.goto(BASE, { waitUntil: 'networkidle', timeout: 20_000 });
  console.log('Page loaded ✓');

  const input = page.locator('textarea').first();
  await input.waitFor({ state: 'visible' });
  await input.click();
  await input.fill('مرحبا');
  await input.press('Enter');
  console.log('Message "مرحبا" sent ✓');

  await page.waitForSelector('div.bg-indigo-600', { timeout: 10_000 });
  console.log('User bubble visible ✓');

  await page.waitForFunction(() => {
    const col = document.querySelector('.chat-column');
    return col && col.children.length >= 2;
  }, { timeout: 15_000 });
  console.log('Agent card appeared ✓');
  await page.screenshot({ path: 'ss_running.png' });

  // Wait for Running... to disappear
  console.log('Waiting for agent to finish (up to 3 min)…');
  try {
    await page.waitForFunction(() => {
      const col = document.querySelector('.chat-column');
      return col && !col.innerText.includes('Running...');
    }, { timeout: 180_000 });
    console.log('Agent finished ✓');
  } catch {
    console.warn('Still running after 3 min');
  }

  await page.screenshot({ path: 'ss_final.png' });

  const full = await page.evaluate(() => document.body.innerText);
  console.log('\n====== FULL PAGE TEXT ======');
  console.log(full.slice(0, 2000));
  console.log('============================');

  await page.waitForTimeout(8_000);
  await browser.close();
})();
