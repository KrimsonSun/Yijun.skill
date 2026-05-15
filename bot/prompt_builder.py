"""Assemble the final OpenAI-style messages list for llama-server.

Inputs: mode (friend|intimate), recent channel history, the new user message,
a Retrieval instance, and (optional) a planning outline from the reasoner.

Output: list of {role, content} ready to POST to /v1/chat/completions.
"""
from __future__ import annotations

from pathlib import Path

from .mode_gate import Mode
from .retrieval import Pair, Retrieval

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
INTIMATE_PROMPT = PROMPTS_DIR / "yijun_voice_intimate.md"
FRIEND_PROMPT = PROMPTS_DIR / "yijun_voice_friend.md"


def _load(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def format_few_shot(pairs: list[Pair]) -> str:
    if not pairs:
        return ""
    lines = ["以下是你过去类似情境的真实回复风格参考（仅作风格参考，不要照抄内容）："]
    for i, p in enumerate(pairs, 1):
        a = p.assistant.replace("\n", " / ")
        u = p.user.replace("\n", " / ")
        lines.append(f"例{i}：对方说「{u}」，你的回复风格类似：「{a}」")
    return "\n".join(lines)


def format_outline(outline: str | None) -> str:
    if not outline:
        return ""
    return (
        "## 这次回复必须包含的核心内容（来自上下文推理）\n"
        f"{outline}\n"
        "上面这一句是逻辑指引：内容方向必须照做，"
        "但语气/换行/用词要保持你自己的风格，不要照抄它。"
    )


def build_messages(
    mode: Mode,
    user_message: str,
    history: list[dict],
    retrieval: Retrieval,
    rag_k: int = 3,
    outline: str | None = None,
) -> list[dict]:
    """Build a chat completion request.

    history is a list of recent {role, content} dicts (oldest first), excluding
    the new user_message. The caller is responsible for trimming history to a
    sensible size.

    outline is the reasoner's one-sentence content directive. If None, we
    skip the plan-then-style augmentation (degrades gracefully).
    """
    if mode == "intimate":
        system = _load(INTIMATE_PROMPT)
        pairs = retrieval.search(user_message, k=rag_k, exclude_intimate=False)
    else:
        system = _load(FRIEND_PROMPT)
        pairs = retrieval.search(user_message, k=rag_k, exclude_intimate=True)

    sections = [system]

    outline_block = format_outline(outline)
    if outline_block:
        sections.append(outline_block)

    few_shot_block = format_few_shot(pairs)
    if few_shot_block:
        sections.append(few_shot_block)

    messages: list[dict] = [{"role": "system", "content": "\n\n".join(sections)}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})
    return messages
