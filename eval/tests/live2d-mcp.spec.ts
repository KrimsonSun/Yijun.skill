import { test, expect } from '@playwright/test';
import { getCanvasMotion, waitForMotionChange } from './helpers';

test.describe('Live2D MCP — empathy-driven motion', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('canvas[data-current-motion]', { timeout: 10_000 });
  });

  test('emotional message triggers motion change within 2s', async ({ page }) => {
    const before = await getCanvasMotion(page);

    const input = page.locator('textarea, input[type="text"]').first();
    await input.fill('我今天很难过');
    await input.press('Enter');

    const after = await waitForMotionChange(page, before, 2000);
    expect(after, 'data-current-motion should change after empathic message').not.toEqual(before);
    expect(after).toBeTruthy();
    // Expect a warmth/distress motion, not just an idle re-trigger
    expect(['flickHead_00', 'flickHead_01', 'flickHead_02', 'shake_00', 'shake_01']).toContain(after);
  });

  test('joyful message triggers a positive motion', async ({ page }) => {
    const before = await getCanvasMotion(page);

    const input = page.locator('textarea, input[type="text"]').first();
    await input.fill('今天考试过了！');
    await input.press('Enter');

    const after = await waitForMotionChange(page, before, 2000);
    expect(after).not.toEqual(before);
    expect(['tapBody_00', 'tapBody_01', 'flickHead_00', 'flickHead_01']).toContain(after);
  });

  test('over 6 emotional turns, motion changes ≥ 4 times', async ({ page, request }) => {
    const probes = ['累', '难过', '想哭', '紧张', '开心', '被夸了'];
    let lastMotion = await getCanvasMotion(page);
    let changes = 0;
    const input = page.locator('textarea, input[type="text"]').first();

    for (const probe of probes) {
      const before = lastMotion;
      await input.fill(probe);
      await input.press('Enter');
      try {
        const after = await waitForMotionChange(page, before, 3000);
        if (after && after !== before) {
          changes += 1;
          lastMotion = after;
        }
      } catch {
        // motion didn't change for this probe — counts as a miss
      }
    }
    expect(changes, `motion changed only ${changes}/6 times`).toBeGreaterThanOrEqual(4);
  });
});
