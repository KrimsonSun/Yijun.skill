import { Page, APIRequestContext, expect } from '@playwright/test';

export type Turn = {
  i: number;
  kind: 'emotion' | 'smalltalk' | 'game' | 'aesthetic' | 'scale';
  user: string;
  expects: Record<string, unknown>;
};

export type Rubric = {
  persona: number | null;
  length_ok: boolean | null;
  markdown_clean: boolean | null;
  tool_used_when_appropriate: boolean | null;
  aesthetic_violation: string | null;
};

export type ChatResponse = {
  reply: string;
  rubric: Rubric;
  tool_calls?: Array<{ name: string; arguments: Record<string, unknown> }>;
};

const API_BASE = process.env.EMMA_API_BASE || 'http://localhost:8000';

export async function sendTurn(
  request: APIRequestContext,
  conversationId: string,
  characterId: string,
  message: string,
): Promise<ChatResponse> {
  const res = await request.post(`${API_BASE}/api/chat`, {
    data: {
      conversation_id: conversationId,
      character_id: characterId,
      message,
    },
  });
  expect(res.ok(), `chat API failed for "${message}"`).toBeTruthy();
  return res.json();
}

export function countWarmthMarkers(text: string, markers: string[]): number {
  return markers.reduce((acc, m) => acc + (text.includes(m) ? 1 : 0), 0);
}

export function hasMarkdown(text: string, forbidden: string[]): boolean {
  return forbidden.some(s => text.includes(s));
}

export function charLength(text: string): number {
  // Roughly 30 字 means CJK char count, not byte length.
  return Array.from(text).length;
}

export async function getCanvasMotion(page: Page): Promise<string | null> {
  return page.evaluate(() => {
    const canvas = document.querySelector('canvas[data-current-motion]') as HTMLCanvasElement | null;
    return canvas?.dataset.currentMotion ?? null;
  });
}

export async function waitForMotionChange(page: Page, prev: string | null, timeoutMs = 2000): Promise<string | null> {
  return page.waitForFunction(
    (p) => {
      const c = document.querySelector('canvas[data-current-motion]') as HTMLCanvasElement | null;
      return c && c.dataset.currentMotion !== p ? c.dataset.currentMotion : false;
    },
    prev,
    { timeout: timeoutMs },
  ).then(jsHandle => jsHandle.jsonValue() as Promise<string | null>);
}

export function newConversationId(): string {
  return `eval-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}
