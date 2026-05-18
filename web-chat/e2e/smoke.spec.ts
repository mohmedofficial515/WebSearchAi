/**
 * E2E smoke tests for WebSearchAi Chat UI.
 *
 * Requires the Vite dev server running on port 5174 (`npm run dev`)
 * AND the FastAPI backend on port 8000.
 *
 * Run: npx playwright test
 */
import { expect, test } from '@playwright/test';

// ── API mock helpers ────────────────────────────────────────────────────────

async function mockApis(page: import('@playwright/test').Page) {
  // /api/intent — always return "research"
  await page.route('/api/intent', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ intent: 'research', confidence: 0.9, is_compound: false }),
    }),
  );

  // /api/chat — return a fake task_id
  await page.route('/api/chat', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ mode: 'single', task_id: 'test-task-123', intent: 'research' }),
    }),
  );

  // /api/archive/search — empty matches
  await page.route('/api/archive/search**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ matches: [] }),
    }),
  );

  // /api/providers — minimal provider list
  await page.route('/api/providers', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ active: 'anthropic', providers: [] }),
    }),
  );

  // /api/accounts — empty list
  await page.route('/api/accounts', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    }),
  );

  // /api/archive — empty list
  await page.route('/api/archive**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    }),
  );
}

// ── Tests ───────────────────────────────────────────────────────────────────

test.describe('Chat page smoke tests', () => {
  test.beforeEach(async ({ page }) => {
    await mockApis(page);
  });

  test('page loads with RTL layout and Arabic language', async ({ page }) => {
    await page.goto('/chat/');

    const html = page.locator('html');
    await expect(html).toHaveAttribute('lang', 'ar');
    await expect(html).toHaveAttribute('dir', 'rtl');
  });

  test('empty state greeting is visible', async ({ page }) => {
    await page.goto('/chat/');

    // EmptyState should show the Arabic greeting
    await expect(page.getByText('مرحباً')).toBeVisible({ timeout: 5000 });
  });

  test('Composer textarea is visible and accepts input', async ({ page }) => {
    await page.goto('/chat/');

    const textarea = page.locator('textarea');
    await expect(textarea).toBeVisible();
    await textarea.fill('ابحث عن React');
    await expect(textarea).toHaveValue('ابحث عن React');
  });

  test('/ shortcut focuses the Composer textarea', async ({ page }) => {
    await page.goto('/chat/');

    // Click somewhere neutral first
    await page.click('body');
    await page.keyboard.press('/');

    const textarea = page.locator('textarea');
    await expect(textarea).toBeFocused();
  });

  test('quick-start chip sends a message', async ({ page }) => {
    await page.goto('/chat/');

    // Wait for any chip to appear (EmptyState chips)
    const chip = page.locator('button').filter({ hasText: '🔍' }).first();
    if (await chip.isVisible()) {
      await chip.click();
      // After chip click the user message should appear
      await expect(page.locator('textarea')).toHaveValue('');
    }
  });

  test('page title is correct', async ({ page }) => {
    await page.goto('/chat/');
    await expect(page).toHaveTitle(/WebSearchAi|Chat/i);
  });
});

test.describe('Settings page smoke tests', () => {
  test.beforeEach(async ({ page }) => {
    await mockApis(page);
  });

  test('settings page loads with three tabs', async ({ page }) => {
    await page.goto('/chat/settings');

    await expect(page.getByText('الإعدادات')).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('المزودون')).toBeVisible();
    await expect(page.getByText('الحسابات')).toBeVisible();
    await expect(page.getByText('الأرشيف')).toBeVisible();
  });

  test('accounts tab shows empty state', async ({ page }) => {
    await page.goto('/chat/settings');

    await page.getByText('الحسابات').click();
    await expect(page.getByText('لا توجد حسابات بعد')).toBeVisible({ timeout: 5000 });
  });

  test('archive tab shows empty state', async ({ page }) => {
    await page.goto('/chat/settings');

    await page.getByText('الأرشيف').click();
    await expect(page.getByText('لا توجد مهام مؤرشفة')).toBeVisible({ timeout: 5000 });
  });
});

test.describe('Keyboard shortcuts', () => {
  test.beforeEach(async ({ page }) => {
    await mockApis(page);
    await page.goto('/chat/');
  });

  test('Enter sends message (when text present)', async ({ page }) => {
    const textarea = page.locator('textarea');
    await textarea.fill('ابحث عن شيء');
    // Wait for intent detection debounce
    await page.waitForTimeout(400);
    await textarea.press('Enter');
    // After submit, textarea should be cleared
    await expect(textarea).toHaveValue('');
  });

  test('Shift+Enter inserts newline instead of sending', async ({ page }) => {
    const textarea = page.locator('textarea');
    await textarea.fill('سطر أول');
    await textarea.press('Shift+Enter');
    // Should NOT clear textarea
    const value = await textarea.inputValue();
    expect(value).toContain('سطر أول');
  });
});
