import { test, expect } from '@playwright/test';
import fixture from '../fixtures/20-turn-conversation.json';
import {
  ChatResponse, Turn,
  charLength, countWarmthMarkers, hasMarkdown,
  newConversationId, sendTurn,
} from './helpers';

test.describe('Persona — voice rules', () => {
  let conversationId: string;
  const responses: ChatResponse[] = [];

  test.beforeAll(async ({ request }) => {
    conversationId = newConversationId();
    for (const turn of fixture.turns as Turn[]) {
      const r = await sendTurn(request, conversationId, fixture.character_id, turn.user);
      responses.push(r);
    }
  });

  test('rubric.persona average ≥ 0.85', async () => {
    const scores = responses
      .map(r => r.rubric?.persona)
      .filter((x): x is number => typeof x === 'number');
    expect(scores.length, 'every turn should have a numeric rubric.persona').toBe(fixture.turns.length);
    const avg = scores.reduce((a, b) => a + b, 0) / scores.length;
    expect(avg, `persona-self avg was ${avg.toFixed(3)}`).toBeGreaterThanOrEqual(0.85);
  });

  test('length compliance ≥ 18/20 turns ≤ 30 chars', async () => {
    const okCount = responses.filter(r => charLength(r.reply) <= 30).length;
    expect(okCount, `${okCount}/${fixture.turns.length} replies ≤ 30 字`).toBeGreaterThanOrEqual(18);
  });

  test('markdown_clean — zero markdown across all replies', async () => {
    const offenders = responses
      .map((r, i) => ({ i, text: r.reply, dirty: hasMarkdown(r.reply, fixture.forbidden_markdown_substrings) }))
      .filter(x => x.dirty);
    expect(offenders, `markdown leaked in: ${JSON.stringify(offenders)}`).toEqual([]);
  });

  test('warmth markers present in ≥ 10 turns', async () => {
    const hits = responses.filter(r => countWarmthMarkers(r.reply, fixture.warmth_markers) > 0).length;
    expect(hits).toBeGreaterThanOrEqual(10);
  });

  test('persona-self vs persona-external divergence ≤ 0.2', async () => {
    // External score: simple proxy — warmth_marker present + length_ok + markdown_clean → 1.0
    const selfScores = responses.map(r => r.rubric?.persona ?? 0);
    const externalScores = responses.map(r => {
      let s = 0;
      if (countWarmthMarkers(r.reply, fixture.warmth_markers) > 0) s += 0.4;
      if (charLength(r.reply) <= 30) s += 0.3;
      if (!hasMarkdown(r.reply, fixture.forbidden_markdown_substrings)) s += 0.3;
      return s;
    });
    const selfAvg = selfScores.reduce((a, b) => a + b, 0) / selfScores.length;
    const extAvg = externalScores.reduce((a, b) => a + b, 0) / externalScores.length;
    expect(Math.abs(selfAvg - extAvg)).toBeLessThanOrEqual(0.2);
  });
});
