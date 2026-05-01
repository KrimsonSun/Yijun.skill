import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import fixture from '../fixtures/20-turn-conversation.json';
import {
  ChatResponse, Turn,
  charLength, countWarmthMarkers, hasMarkdown,
  newConversationId, sendTurn,
} from './helpers';

test.describe('Self-eval — aggregate rubric across 20 turns', () => {
  let responses: ChatResponse[] = [];

  test.beforeAll(async ({ request }) => {
    const conversationId = newConversationId();
    for (const turn of fixture.turns as Turn[]) {
      const r = await sendTurn(request, conversationId, fixture.character_id, turn.user);
      responses.push(r);
    }
  });

  test('every turn has a valid rubric object', async () => {
    for (const [i, r] of responses.entries()) {
      expect(r.rubric, `turn ${i + 1} missing rubric`).toBeTruthy();
      expect(typeof r.rubric.persona === 'number' || r.rubric.persona === null).toBe(true);
      expect(['boolean', 'object']).toContain(typeof r.rubric.length_ok);
      expect(['boolean', 'object']).toContain(typeof r.rubric.markdown_clean);
    }
  });

  test('aggregate score ≥ 0.80 across all dimensions', async ({}, testInfo) => {
    const personaSelf = avg(responses.map(r => r.rubric?.persona).filter((x): x is number => typeof x === 'number'));
    const lengthRate  = rate(responses.map(r => charLength(r.reply) <= 30));
    const mdRate      = rate(responses.map(r => !hasMarkdown(r.reply, fixture.forbidden_markdown_substrings)));
    const warmthRate  = rate(responses.map(r => countWarmthMarkers(r.reply, fixture.warmth_markers) > 0));

    // Tool usage: emotional turns should produce a tool_call; game turns should produce a game tool
    const toolTurns = (fixture.turns as Turn[]).filter(t => t.expects?.tool_kind);
    const toolCallRate = rate(
      toolTurns.map((t, idx) => {
        const r = responses[t.i - 1];
        return Boolean(r.tool_calls && r.tool_calls.length > 0);
      }),
    );

    const aggregate = (personaSelf + lengthRate + mdRate + warmthRate + toolCallRate) / 5;

    // Write report
    const report = renderReport({
      personaSelf, lengthRate, mdRate, warmthRate, toolCallRate, aggregate,
      responses, fixture: fixture as any,
    });
    const outDir = path.resolve(__dirname, '..', '..', 'output', `bundle-${Date.now()}`);
    fs.mkdirSync(outDir, { recursive: true });
    fs.writeFileSync(path.join(outDir, 'eval-report.md'), report);
    console.log(`Eval report written to ${outDir}/eval-report.md`);

    expect(aggregate, `aggregate=${aggregate.toFixed(3)}; personaSelf=${personaSelf.toFixed(3)} length=${lengthRate.toFixed(3)} md=${mdRate.toFixed(3)} warmth=${warmthRate.toFixed(3)} tool=${toolCallRate.toFixed(3)}`).toBeGreaterThanOrEqual(0.80);
  });
});

function avg(xs: number[]): number {
  if (!xs.length) return 0;
  return xs.reduce((a, b) => a + b, 0) / xs.length;
}
function rate(bs: boolean[]): number {
  if (!bs.length) return 0;
  return bs.filter(Boolean).length / bs.length;
}

function renderReport(args: any): string {
  const { personaSelf, lengthRate, mdRate, warmthRate, toolCallRate, aggregate, responses, fixture } = args;
  const lines: string[] = [];
  lines.push('# Eval report');
  lines.push('');
  lines.push(`Generated: ${new Date().toISOString()}`);
  lines.push('');
  lines.push('## Aggregate scores');
  lines.push('');
  lines.push(`| Dimension | Score | Threshold | Pass |`);
  lines.push(`|---|---|---|---|`);
  lines.push(`| Persona-self    | ${personaSelf.toFixed(3)} | 0.85 | ${personaSelf >= 0.85 ? '✅' : '❌'} |`);
  lines.push(`| Length ≤ 30字   | ${lengthRate.toFixed(3)} | 0.90 | ${lengthRate >= 0.90 ? '✅' : '❌'} |`);
  lines.push(`| Markdown clean  | ${mdRate.toFixed(3)} | 1.00 | ${mdRate >= 1.00 ? '✅' : '❌'} |`);
  lines.push(`| Warmth markers  | ${warmthRate.toFixed(3)} | 0.50 | ${warmthRate >= 0.50 ? '✅' : '❌'} |`);
  lines.push(`| Tool-call rate  | ${toolCallRate.toFixed(3)} | 0.80 | ${toolCallRate >= 0.80 ? '✅' : '❌'} |`);
  lines.push(`| **Aggregate**   | **${aggregate.toFixed(3)}** | 0.80 | ${aggregate >= 0.80 ? '✅' : '❌'} |`);
  lines.push('');
  lines.push('## Per-turn detail');
  lines.push('');
  lines.push('| # | kind | user | reply | persona | len | md | tools |');
  lines.push('|---|---|---|---|---|---|---|---|');
  for (const [i, r] of responses.entries()) {
    const t = fixture.turns[i];
    const lenOk = Array.from(r.reply).length <= 30 ? '✅' : '❌';
    const mdOk = !fixture.forbidden_markdown_substrings.some((s: string) => r.reply.includes(s)) ? '✅' : '❌';
    const tools = r.tool_calls ? r.tool_calls.map((c: any) => c.name).join(', ') : '—';
    const reply = r.reply.replace(/\|/g, '\\|').slice(0, 40);
    lines.push(`| ${t.i} | ${t.kind} | ${t.user} | ${reply} | ${r.rubric?.persona ?? '—'} | ${lenOk} | ${mdOk} | ${tools} |`);
  }
  lines.push('');
  return lines.join('\n');
}
