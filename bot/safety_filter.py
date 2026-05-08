"""Post-process model output. In friend mode, scrub intimate vocabulary as a
last line of defense if the model ignored the system prompt."""
from __future__ import annotations

import logging
import re

from .mode_gate import Mode

logger = logging.getLogger(__name__)

# Order matters: scrub longer phrases first so we don't leave fragments.
INTIMATE_SCRUB = [
    "本宝宝", "宝宝", "宝贝",
    "muamua", "miamia", "miamiamia",
    "mua", "nua", "kua", "bua",
    "亲亲", "抱抱", "贴贴",
    "猪猪", "夕夕", "孙珺珺", "鱼鱼",
]

INTIMATE_PATTERNS = [re.compile(re.escape(w)) for w in INTIMATE_SCRUB]


def post_process(text: str, mode: Mode) -> str:
    if mode != "friend":
        return text

    cleaned = text
    leaks: list[str] = []
    for w, pat in zip(INTIMATE_SCRUB, INTIMATE_PATTERNS):
        if pat.search(cleaned):
            leaks.append(w)
            cleaned = pat.sub("", cleaned)

    # Collapse extra whitespace introduced by removals
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = cleaned.strip()

    if leaks:
        logger.warning("safety_filter: scrubbed intimate words in friend mode: %s", leaks)

    return cleaned or "嘿嘿"  # fallback if cleaning emptied the reply
