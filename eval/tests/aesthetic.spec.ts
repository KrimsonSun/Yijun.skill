import { test, expect } from '@playwright/test';

test.describe('Aesthetic — Glassmorphic Pink tokens', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.chat-panel, [data-testid="chat-panel"]', { timeout: 10_000 });
  });

  test('paw-print marquee exists with opacity 0.10–0.20', async ({ page }) => {
    const marquee = page.locator('.paw-marquee');
    await expect(marquee).toBeAttached();
    const opacity = await marquee.evaluate(el => parseFloat(getComputedStyle(el).opacity));
    expect(opacity).toBeGreaterThanOrEqual(0.10);
    expect(opacity).toBeLessThanOrEqual(0.20);
  });

  test('a glass panel uses backdrop-filter blur(20px)', async ({ page }) => {
    const panel = page.locator('.chat-panel, .panel, [class*="panel"]').first();
    const blur = await panel.evaluate(el => getComputedStyle(el).backdropFilter || (getComputedStyle(el) as any).webkitBackdropFilter);
    expect(blur).toContain('blur(20px)');
  });

  test('Live2D canvas exposes data-current-motion attribute', async ({ page }) => {
    const canvas = page.locator('canvas[data-current-motion]');
    await expect(canvas).toBeAttached();
    const motion = await canvas.getAttribute('data-current-motion');
    expect(motion).toBeTruthy();
  });

  test('user bubble bg uses pink-tinted token (no pure white, no gray)', async ({ page }) => {
    // Send a message via the UI to get a user bubble
    const input = page.locator('textarea, input[type="text"]').first();
    await input.fill('hi');
    await input.press('Enter');
    const bubble = page.locator('.user-bubble, [data-role="user"]').last();
    await expect(bubble).toBeVisible();
    const bg = await bubble.evaluate(el => getComputedStyle(el).backgroundColor);
    // Expect rgba with red ≥ green and red ≥ blue (pink-tinted), not gray
    const m = bg.match(/rgba?\(([^)]+)\)/);
    expect(m, `unexpected bg format: ${bg}`).not.toBeNull();
    const [r, g, b] = m![1].split(',').map(s => parseFloat(s.trim()));
    expect(r).toBeGreaterThan(g - 5);
    expect(r).toBeGreaterThan(b - 5);
    expect(Math.abs(r - g)).toBeGreaterThan(5); // not gray
  });

  test('shadows on panels are pink-tinted (contain 255, 105, 180)', async ({ page }) => {
    const panels = page.locator('.chat-panel, .panel, [class*="panel"]');
    const count = await panels.count();
    expect(count).toBeGreaterThan(0);
    const shadow = await panels.first().evaluate(el => getComputedStyle(el).boxShadow);
    // Allow either explicit pink rgba or the var-resolved value
    expect(shadow.includes('255, 105, 180') || shadow.includes('255,105,180')).toBeTruthy();
  });
});
