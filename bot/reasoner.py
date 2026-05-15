"""Local reasoner: a small base model (not the Yijun finetune) that reads
recent conversation history and outputs a one-sentence outline of what the
Yijun model should say next.

This is the "plan" step of plan-then-style. The reasoner has no opinion on
voice/persona — it only enforces logical coherence (don't contradict prior
turns, give specific answers when the user asks). The Yijun-7B stylist
then receives the outline as additional system-prompt context and produces
the actual reply in Yijun's voice.

Degrades gracefully: if the reasoner is unreachable or slow, the bot just
generates without an outline (same as the no-reasoner path)."""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

REASONER_SYSTEM = """你是一个对话引导助手。读 bot 的对话历史和用户最新一条消息，写一句话告诉 bot 这次回复应该包含的核心内容。

要求：
- 一句话，30 字以内，只写"该说什么方向"
- 如果 bot 上一轮承诺了什么具体的事（比如"我准备了X"），这次必须给出具体的 X
- 如果用户在追问 bot 刚说的内容，不能回避，必须接着回答
- 如果用户在纠正 bot 的身份认知，要承认或改正
- 如果用户的话很短（"嗯""啊""哦"），引导一个自然的延续话题
- 不要写最终回复的具体文字，只写方向
- 不要解释你的推理过程，直接输出指引

例：
对话历史：
assistant: 猪猪给你准备了 [破涕为笑]
user: 准备了什么呀
指引：必须给出一个具体的食物名字，不能说不知道

对话历史：
assistant: 我就是孙小珺呀
user: 不对，我是孙小珺
指引：承认自己搞错了，认下用户是孙小珺，问对方今天好吗
"""


class Reasoner:
    def __init__(
        self,
        base_url: str = "http://localhost:8081",
        timeout_s: float = 15.0,
        enabled: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.enabled = enabled

    async def plan(self, history: list[dict], user_message: str) -> str | None:
        """Return a one-sentence outline, or None if reasoner is disabled/unreachable."""
        if not self.enabled:
            return None

        convo_lines = []
        for m in history[-6:]:
            role = "assistant" if m["role"] == "assistant" else "user"
            convo_lines.append(f"{role}: {m['content']}")
        convo = "\n".join(convo_lines) if convo_lines else "(无历史)"

        user_prompt = (
            f"对话历史：\n{convo}\n\n用户最新一条：{user_message}\n\n请给一句话指引："
        )

        payload = {
            "model": "reasoner",
            "messages": [
                {"role": "system", "content": REASONER_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": 80,
            "temperature": 0.3,
            "top_p": 0.9,
            "stop": ["\n\n", "<|im_end|>"],
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                r = await client.post(
                    f"{self.base_url}/v1/chat/completions", json=payload
                )
                r.raise_for_status()
            outline = r.json()["choices"][0]["message"]["content"].strip()
        except Exception:  # noqa: BLE001
            logger.exception("reasoner unreachable; falling back to no-plan")
            return None

        # Sanity: outline should be a single short sentence
        outline = outline.replace("\n", " ").strip()
        if len(outline) > 120:
            outline = outline[:120]
        return outline or None
