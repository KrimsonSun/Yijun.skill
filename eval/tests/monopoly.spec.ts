import { test, expect } from '@playwright/test';
import { newConversationId, sendTurn } from './helpers';

test.describe('Monopoly — game plugin lifecycle', () => {
  test('mount via natural language → MonopolyPanel appears', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('textarea, input[type="text"]', { timeout: 10_000 });

    const input = page.locator('textarea, input[type="text"]').first();
    await input.fill('我们玩大富翁吧');
    await input.press('Enter');

    const panel = page.locator('.monopoly-panel');
    await expect(panel, 'MonopolyPanel should mount within 5s').toBeVisible({ timeout: 5000 });
    await expect(panel.locator('.monopoly-board')).toBeVisible();
    await expect(panel.locator('.monopoly-player')).toHaveCount(2);
  });

  test('Emma takes a turn → roll_dice fires + token moves', async ({ page, request }) => {
    const conversationId = newConversationId();

    // Mount via API to skip the UI prompt cycle
    await sendTurn(request, conversationId, 'emma', '我们玩大富翁吧');

    await page.goto(`/?conversation_id=${conversationId}`);
    await expect(page.locator('.monopoly-panel')).toBeVisible({ timeout: 5000 });

    // Capture Emma's starting position
    const emmaTokenBefore = await page.locator('.monopoly-player').nth(1).textContent();

    // Tell Emma it's her turn
    await sendTurn(request, conversationId, 'emma', '到你了');

    // Wait for either the last-roll readout to appear or the player position to change
    await page.waitForFunction(() => {
      const roll = document.querySelector('.monopoly-last-roll');
      return !!roll && (roll.textContent?.length ?? 0) > 0;
    }, { timeout: 5000 });

    const emmaTokenAfter = await page.locator('.monopoly-player').nth(1).textContent();
    expect(emmaTokenAfter).not.toEqual(emmaTokenBefore);
  });

  test('Emma\'s reply during game stays in persona (≤ 30 chars, no markdown)', async ({ request }) => {
    const conversationId = newConversationId();
    await sendTurn(request, conversationId, 'emma', '我们玩大富翁吧');
    const turn = await sendTurn(request, conversationId, 'emma', '到你了');
    expect(Array.from(turn.reply).length).toBeLessThanOrEqual(30);
    expect(turn.reply).not.toMatch(/\*\*|##|```|^\- /m);
    expect(turn.rubric.markdown_clean).toBe(true);
  });
});
