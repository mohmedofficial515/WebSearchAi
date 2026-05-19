/**
 * Quick Playwright smoke test — run with:
 *   node test_browser.mjs
 */
import { chromium } from 'playwright';
import { writeFileSync, mkdirSync } from 'fs';

const BASE = 'http://localhost:5174';
const SHOTS = './screenshots';
mkdirSync(SHOTS, { recursive: true });

// Use already-installed chromium if the default one isn't downloaded yet
const CHROMIUM_PATH = process.env.CHROMIUM_PATH ||
  'C:\\Users\\MOHAMED AHMED\\AppData\\Local\\ms-playwright\\chromium-1217\\chrome-win64\\chrome.exe';

async function shot(page, name) {
  await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: false });
  console.log(`  📸 ${name}.png`);
}

(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: CHROMIUM_PATH,
  });
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await ctx.newPage();

  const results = [];

  // ── 1. Chat page loads ───────────────────────────────────────────────────
  console.log('\n1. Chat page load...');
  try {
    await page.goto(`${BASE}/chat/`, { waitUntil: 'networkidle', timeout: 15_000 });
    const title = await page.title();
    await shot(page, '01-chat-empty');
    results.push({ test: 'Chat page loads', ok: true, detail: `title="${title}"` });
  } catch (e) {
    results.push({ test: 'Chat page loads', ok: false, detail: e.message });
  }

  // ── 2. New Chat button visible ───────────────────────────────────────────
  console.log('2. Sidebar - New Chat button...');
  try {
    const btn = page.locator('button').filter({ hasText: /محادثة جديدة|New Chat/ }).first();
    await btn.waitFor({ timeout: 5000 });
    results.push({ test: 'New Chat button visible', ok: true });
  } catch (e) {
    results.push({ test: 'New Chat button visible', ok: false, detail: e.message });
  }

  // ── 3. Composer textarea focusable ───────────────────────────────────────
  console.log('3. Composer textarea...');
  try {
    const ta = page.locator('textarea').first();
    await ta.waitFor({ timeout: 5000 });
    await ta.click();
    await ta.fill('ابحث عن الذكاء الاصطناعي');
    await page.waitForTimeout(500);
    await shot(page, '02-composer-typed');
    results.push({ test: 'Composer textarea focusable', ok: true });
  } catch (e) {
    results.push({ test: 'Composer textarea focusable', ok: false, detail: e.message });
  }

  // ── 4. Token counter appears when typing ────────────────────────────────
  console.log('4. Live token counter...');
  try {
    const tok = page.locator('text=/tok/').first();
    await tok.waitFor({ timeout: 4000 });
    const tokText = await tok.textContent();
    results.push({ test: 'Token counter visible', ok: true, detail: tokText?.trim() });
  } catch (e) {
    results.push({ test: 'Token counter visible', ok: false, detail: e.message });
  }

  // ── 5. Send message → conversation appears ───────────────────────────────
  console.log('5. Send message → conversation appears in sidebar...');
  try {
    await page.keyboard.press('Enter');
    await page.waitForTimeout(2500);
    await shot(page, '03-after-send');
    // Check sidebar for conversation title
    const sidebarItems = await page.locator('aside button p').count();
    results.push({ test: 'Conversation appears in sidebar', ok: sidebarItems > 0, detail: `${sidebarItems} items in sidebar` });
  } catch (e) {
    results.push({ test: 'Conversation appears in sidebar', ok: false, detail: e.message });
  }

  // ── 6. Token count in sidebar ────────────────────────────────────────────
  console.log('6. Token count in sidebar...');
  try {
    await shot(page, '04-sidebar-tokens');
    const tokenText = await page.locator('aside').locator('text=/tok/').first().textContent();
    results.push({ test: 'Token count in sidebar', ok: true, detail: tokenText?.trim() });
  } catch (e) {
    results.push({ test: 'Token count in sidebar', ok: false, detail: e.message });
  }

  // ── 7. Artifacts page loads ──────────────────────────────────────────────
  console.log('7. Artifacts page...');
  try {
    await page.goto(`${BASE}/chat/artifacts`, { waitUntil: 'networkidle', timeout: 10_000 });
    await shot(page, '05-artifacts');
    const heading = await page.locator('h1').first().textContent();
    results.push({ test: 'Artifacts page loads', ok: true, detail: `heading="${heading?.trim()}"` });
  } catch (e) {
    results.push({ test: 'Artifacts page loads', ok: false, detail: e.message });
  }

  // ── 8. Settings page loads ───────────────────────────────────────────────
  console.log('8. Settings page...');
  try {
    await page.goto(`${BASE}/chat/settings`, { waitUntil: 'networkidle', timeout: 10_000 });
    await shot(page, '06-settings');
    const heading = await page.locator('h2, h1').first().textContent();
    results.push({ test: 'Settings page loads', ok: true, detail: `heading="${heading?.trim()}"` });
  } catch (e) {
    results.push({ test: 'Settings page loads', ok: false, detail: e.message });
  }

  // ── 9. Dark mode toggle ──────────────────────────────────────────────────
  console.log('9. Dark mode toggle...');
  try {
    await page.goto(`${BASE}/chat/`, { waitUntil: 'networkidle', timeout: 10_000 });
    const toggle = page.locator('[aria-label*="mode"], [aria-label*="ode"]').first();
    await toggle.waitFor({ timeout: 4000 });
    await toggle.click();
    await page.waitForTimeout(400);
    await shot(page, '07-dark-mode');
    results.push({ test: 'Dark mode toggle', ok: true });
  } catch (e) {
    results.push({ test: 'Dark mode toggle', ok: false, detail: e.message });
  }

  // ── 10. API health ───────────────────────────────────────────────────────
  console.log('10. API health checks...');
  const apiTests = [
    { url: 'http://localhost:8000/api/artifacts', name: 'GET /api/artifacts' },
    { url: 'http://localhost:8000/api/tasks', name: 'GET /api/tasks' },
  ];
  for (const { url, name } of apiTests) {
    try {
      const res = await page.request.get(url);
      results.push({ test: name, ok: res.ok(), detail: `status=${res.status()}` });
    } catch (e) {
      results.push({ test: name, ok: false, detail: e.message });
    }
  }

  await browser.close();

  // ── Summary ──────────────────────────────────────────────────────────────
  console.log('\n' + '═'.repeat(60));
  console.log('BROWSER TEST RESULTS');
  console.log('═'.repeat(60));
  let passed = 0;
  for (const r of results) {
    const icon = r.ok ? '✅' : '❌';
    console.log(`${icon} ${r.test}${r.detail ? ` — ${r.detail}` : ''}`);
    if (r.ok) passed++;
  }
  console.log('═'.repeat(60));
  console.log(`\nPassed: ${passed}/${results.length}  Screenshots in: ${SHOTS}/`);

  writeFileSync('./test_results.json', JSON.stringify({ passed, total: results.length, results }, null, 2));
  process.exit(passed >= results.length * 0.8 ? 0 : 1);
})();
